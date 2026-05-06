"""
ArXiv paper fetcher for the ingestion pipeline.

Fetches paper metadata from the arXiv API and downloads PDFs.
Also checks for ar5iv HTML availability.
"""

import asyncio
import logging
import os
import random
import re
import httpx
from xml.etree import ElementTree as ET
from time import monotonic
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from models.paper import ArxivPaperMeta


# Regex to normalize arXiv IDs
ARXIV_ID_PATTERN = re.compile(r'^(\d{4}\.\d{4,5})(v\d+)?$|^([a-z-]+/\d{7})(v\d+)?$')

# Be conservative with arXiv API pacing to avoid 429s under concurrent jobs.
ARXIV_MIN_INTERVAL_SECONDS = float(os.getenv("ARXIV_MIN_INTERVAL_SECONDS", "3.0"))
ARXIV_META_MAX_RETRIES = int(os.getenv("ARXIV_META_MAX_RETRIES", "6"))
ARXIV_BACKOFF_BASE_SECONDS = float(os.getenv("ARXIV_BACKOFF_BASE_SECONDS", "3.0"))
ARXIV_USER_AGENT = os.getenv(
    "ARXIV_USER_AGENT",
    "arXiviz/0.1 (+https://github.com/nihaa/arXivisual)",
)
_arxiv_request_lock = asyncio.Lock()
_last_arxiv_request_ts = 0.0


def normalize_arxiv_id(arxiv_id: str) -> str:
    """
    Normalize arXiv ID by stripping version suffix if present.
    
    Examples:
        - "1706.03762v1" -> "1706.03762"
        - "1706.03762" -> "1706.03762"
        - "cs/0123456v2" -> "cs/0123456"
    """
    # Remove 'arXiv:' prefix if present
    arxiv_id = arxiv_id.replace('arXiv:', '').strip()
    
    # Strip version suffix
    match = ARXIV_ID_PATTERN.match(arxiv_id)
    if match:
        # Return the base ID without version
        return match.group(1) or match.group(3)
    
    # If no match, return as-is (might be invalid)
    return arxiv_id


def extract_version(arxiv_id: str) -> Optional[int]:
    """Extract version number from arXiv ID if present."""
    match = re.search(r'v(\d+)$', arxiv_id)
    if match:
        return int(match.group(1))
    return None


def validate_arxiv_id(arxiv_id: str) -> bool:
    """
    Validate that an arXiv ID is in a valid format.
    
    Valid formats:
    - 1706.03762 (new format)
    - 1706.03762v1 (with version)
    - cs/0123456 (old format)
    """
    cleaned = arxiv_id.replace('arXiv:', '').strip()
    return bool(ARXIV_ID_PATTERN.match(cleaned))


async def fetch_paper_meta(arxiv_id: str) -> ArxivPaperMeta:
    """
    Fetch paper metadata from arXiv API.
    
    Args:
        arxiv_id: arXiv paper ID (e.g., "1706.03762" or "1706.03762v1")
        
    Returns:
        ArxivPaperMeta with all paper metadata
        
    Raises:
        ValueError: If paper not found or invalid ID
    """
    # Normalize the ID (keep version for search if specified)
    search_id = arxiv_id.replace('arXiv:', '').strip()
    base_id = normalize_arxiv_id(arxiv_id)
    
    # Validate ID format first
    if not validate_arxiv_id(arxiv_id):
        raise ValueError(
            f"Invalid arXiv ID format: '{arxiv_id}'. "
            f"Expected formats: '1706.03762', '1706.03762v1', or 'cs/0123456'"
        )
    
    max_retries = max(1, ARXIV_META_MAX_RETRIES)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            await _respect_arxiv_rate_limit()
            paper_meta = await _fetch_meta_via_export_api(search_id)
            break
        except Exception as e:
            last_error = e
            error_msg = str(e)

            status_code = None
            retry_after = None
            if isinstance(e, httpx.HTTPStatusError):
                status_code = e.response.status_code
                retry_after = _parse_retry_after_seconds(e.response.headers.get("Retry-After"))

            # Retry on rate limit (429), transient server errors, and transport issues.
            if (
                status_code == 429
                or (status_code is not None and 500 <= status_code < 600)
                or isinstance(e, httpx.RequestError)
            ):
                if attempt == max_retries:
                    break
                wait = retry_after or _backoff_seconds(attempt)
                logger.warning(
                    "arXiv request failed (%s). Retrying in %.1fs (attempt %d/%d)",
                    status_code or type(e).__name__,
                    wait,
                    attempt,
                    max_retries,
                )
                await asyncio.sleep(wait)
                continue

            # Non-retryable errors — raise immediately.
            if status_code == 400 or "Bad Request" in error_msg:
                raise ValueError(f"Invalid arXiv ID: '{arxiv_id}' - arXiv API rejected the request")
            elif status_code == 404 or "Not Found" in error_msg:
                raise ValueError(f"Paper not found on arXiv: '{arxiv_id}'")
            elif "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                raise ConnectionError(f"Could not connect to arXiv API: {e}")
            else:
                raise ValueError(f"Error fetching paper '{arxiv_id}': {e}")
    else:
        # Defensive fallback for loop completion path.
        pass

    if last_error and 'paper_meta' not in locals():
        raise ValueError(f"Error fetching paper '{arxiv_id}' after {max_retries} retries: {last_error}")

    if 'paper_meta' not in locals():
        raise ValueError(f"Paper not found on arXiv: '{arxiv_id}'")
    
    # Build PDF URL
    pdf_url = f"https://arxiv.org/pdf/{base_id}.pdf"
    
    # Check for ar5iv HTML availability
    html_url = await check_ar5iv_available(base_id)
    
    return ArxivPaperMeta(
        arxiv_id=base_id,
        title=paper_meta["title"],
        authors=paper_meta["authors"],
        abstract=paper_meta["summary"],
        published=paper_meta["published"],
        updated=paper_meta["updated"],
        categories=paper_meta["categories"],
        pdf_url=pdf_url,
        html_url=html_url
    )


def _parse_retry_after_seconds(value: str | None) -> float | None:
    """Parse Retry-After seconds header if present."""
    if not value:
        return None
    try:
        seconds = float(value.strip())
        return max(0.0, seconds)
    except ValueError:
        return None


def _backoff_seconds(attempt: int) -> float:
    """Exponential backoff with light jitter to avoid synchronized retries."""
    base = ARXIV_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
    jitter = random.uniform(0.0, 1.0)
    return min(90.0, base + jitter)


async def _respect_arxiv_rate_limit() -> None:
    """Serialize arXiv API requests and keep a minimum spacing between them."""
    global _last_arxiv_request_ts
    async with _arxiv_request_lock:
        now = monotonic()
        wait = ARXIV_MIN_INTERVAL_SECONDS - (now - _last_arxiv_request_ts)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_arxiv_request_ts = monotonic()


def _parse_atom_datetime(value: str | None) -> datetime | None:
    """Parse arXiv Atom datetime values into Python datetimes."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def _fetch_meta_via_export_api(arxiv_id: str) -> dict:
    """
    Fetch a single paper's metadata from export.arxiv.org Atom API.

    Raises:
        httpx.HTTPError on network/status failures
        ValueError when no entry is returned
    """
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": "",
        "id_list": arxiv_id,
        "sortBy": "relevance",
        "sortOrder": "descending",
        "start": 0,
        "max_results": 1,
    }
    headers = {"User-Agent": ARXIV_USER_AGENT}
    async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=headers) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        xml_text = response.text

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML received from arXiv API: {exc}") from exc

    atom = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", atom)
    if entry is None:
        raise ValueError(f"Paper not found on arXiv: '{arxiv_id}'")

    title = (entry.findtext("atom:title", default="", namespaces=atom) or "").strip()
    summary = (entry.findtext("atom:summary", default="", namespaces=atom) or "").strip()
    authors = [
        (author.findtext("atom:name", default="", namespaces=atom) or "").strip()
        for author in entry.findall("atom:author", atom)
    ]
    authors = [name for name in authors if name]
    categories = [
        (cat.attrib.get("term", "") or "").strip()
        for cat in entry.findall("atom:category", atom)
    ]
    categories = [cat for cat in categories if cat]

    if not title:
        raise ValueError(f"Paper metadata response missing title for '{arxiv_id}'")

    return {
        "title": title,
        "summary": summary,
        "authors": authors,
        "categories": categories,
        "published": _parse_atom_datetime(entry.findtext("atom:published", default=None, namespaces=atom)),
        "updated": _parse_atom_datetime(entry.findtext("atom:updated", default=None, namespaces=atom)),
    }


async def check_ar5iv_available(arxiv_id: str) -> Optional[str]:
    """
    Check if ar5iv HTML version is available for this paper.
    
    Args:
        arxiv_id: Normalized arXiv ID (without version)
        
    Returns:
        ar5iv URL if available, None otherwise
    """
    url = f"https://ar5iv.org/abs/{arxiv_id}"
    
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.head(url)
            
            if response.status_code == 200:
                return url
            
    except httpx.RequestError:
        # Network error, ar5iv might be down
        pass
    
    return None


async def download_pdf(pdf_url: str) -> bytes:
    """
    Download PDF from arXiv.
    
    Args:
        pdf_url: Direct PDF download URL
        
    Returns:
        Raw PDF bytes
        
    Raises:
        httpx.HTTPError: If download fails
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        response = await client.get(pdf_url)
        response.raise_for_status()
        return response.content


async def fetch_html_content(html_url: str) -> str:
    """
    Fetch HTML content from ar5iv.
    
    Args:
        html_url: ar5iv HTML URL
        
    Returns:
        HTML content as string
        
    Raises:
        httpx.HTTPError: If fetch fails
    """
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(html_url)
        response.raise_for_status()
        return response.text
