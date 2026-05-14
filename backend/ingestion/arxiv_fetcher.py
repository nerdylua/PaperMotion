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
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

from models.paper import ArxivPaperMeta
from .pdf_sources import download_pdf_bytes


# Regex to normalize arXiv IDs
ARXIV_ID_PATTERN = re.compile(r'^(\d{4}\.\d{4,5})(v\d+)?$|^([a-z-]+/\d{7})(v\d+)?$')

# Be conservative with arXiv API pacing to avoid 429s under concurrent jobs.
ARXIV_MIN_INTERVAL_SECONDS = float(os.getenv("ARXIV_MIN_INTERVAL_SECONDS", "3.0"))
ARXIV_SEARCH_MIN_INTERVAL_SECONDS = float(
    os.getenv("ARXIV_SEARCH_MIN_INTERVAL_SECONDS", "8.0")
)
ARXIV_META_MAX_RETRIES = int(os.getenv("ARXIV_META_MAX_RETRIES", "6"))
ARXIV_BACKOFF_BASE_SECONDS = float(os.getenv("ARXIV_BACKOFF_BASE_SECONDS", "3.0"))
ARXIV_429_COOLDOWN_SECONDS = float(os.getenv("ARXIV_429_COOLDOWN_SECONDS", "60"))
ARXIV_SEARCH_CACHE_TTL_SECONDS = float(os.getenv("ARXIV_SEARCH_CACHE_TTL_SECONDS", "600"))
ARXIV_TOPIC_RECENT_YEARS = int(os.getenv("ARXIV_TOPIC_RECENT_YEARS", "3"))
ARXIV_TOPIC_RECENT_CANDIDATE_MULTIPLIER = int(
    os.getenv("ARXIV_TOPIC_RECENT_CANDIDATE_MULTIPLIER", "4")
)
ARXIV_USER_AGENT = os.getenv(
    "ARXIV_USER_AGENT",
    "arXiviz/0.1 (+https://github.com/nihaa/arXivisual)",
)
_arxiv_request_lock = asyncio.Lock()
_last_arxiv_request_ts = 0.0
_arxiv_cooldown_until = 0.0

# Simple in-memory cache for topic search results to reduce 429s.
_search_cache: dict[str, tuple[float, list[ArxivPaperMeta]]] = {}


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


async def search_arxiv_papers(topic: str, max_results: int = 5) -> list[ArxivPaperMeta]:
    """
    Search arXiv by topic and return paper metadata.

    Args:
        topic: Search query (plain text)
        max_results: Max number of papers to return (1-5)

    Returns:
        List of ArxivPaperMeta entries
    """
    query = (topic or "").strip()
    if not query:
        raise ValueError("Topic query cannot be empty")

    max_results = max(1, min(5, int(max_results)))

    recent_years = max(1, ARXIV_TOPIC_RECENT_YEARS)
    cache_key = f"{query.lower()}|{max_results}|recent_years={recent_years}"
    cached = _get_search_cache(cache_key)
    if cached is not None:
        logger.info("arXiv search cache hit for '%s'", query)
        return cached

    candidate_limit = max(
        max_results,
        min(25, max_results * max(1, ARXIV_TOPIC_RECENT_CANDIDATE_MULTIPLIER)),
    )
    start_date, end_date = _recent_submission_window(recent_years)
    entries = await _fetch_search_via_export_api(
        query=query,
        max_results=candidate_limit,
        submitted_after=start_date,
        submitted_before=end_date,
        sort_by="relevance",
    )
    entries = _rank_recent_entries(entries)

    if len(entries) < max_results:
        logger.info(
            "Only found %d recent arXiv papers for '%s'; broadening search",
            len(entries),
            query,
        )
        fallback_entries = await _fetch_search_via_export_api(
            query=query,
            max_results=max_results,
            sort_by="relevance",
        )
        entries = _dedupe_entries(entries + fallback_entries)

    entries = entries[:max_results]

    results: list[ArxivPaperMeta] = []
    for entry in entries:
        arxiv_id = normalize_arxiv_id(entry["arxiv_id"])
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        results.append(
            ArxivPaperMeta(
                arxiv_id=arxiv_id,
                title=entry["title"],
                authors=entry["authors"],
                abstract=entry["summary"],
                published=entry["published"],
                updated=entry["updated"],
                categories=entry["categories"],
                pdf_url=pdf_url,
                html_url=None,
            )
        )

    _set_search_cache(cache_key, results)
    return results


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
            await _respect_arxiv_rate_limit(ARXIV_MIN_INTERVAL_SECONDS)
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
                if status_code == 429:
                    global _arxiv_cooldown_until
                    _arxiv_cooldown_until = max(
                        _arxiv_cooldown_until,
                        monotonic() + ARXIV_429_COOLDOWN_SECONDS,
                    )
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


async def _respect_arxiv_rate_limit(min_interval_seconds: float) -> None:
    """Serialize arXiv API requests and keep a minimum spacing between them."""
    global _last_arxiv_request_ts
    global _arxiv_cooldown_until
    async with _arxiv_request_lock:
        now = monotonic()
        if now < _arxiv_cooldown_until:
            await asyncio.sleep(_arxiv_cooldown_until - now)
            now = monotonic()
        wait = min_interval_seconds - (now - _last_arxiv_request_ts)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_arxiv_request_ts = monotonic()


def _get_search_cache(cache_key: str) -> list[ArxivPaperMeta] | None:
    if ARXIV_SEARCH_CACHE_TTL_SECONDS <= 0:
        return None
    cached = _search_cache.get(cache_key)
    if not cached:
        return None
    cached_at, results = cached
    if (monotonic() - cached_at) > ARXIV_SEARCH_CACHE_TTL_SECONDS:
        _search_cache.pop(cache_key, None)
        return None
    return results


def _set_search_cache(cache_key: str, results: list[ArxivPaperMeta]) -> None:
    if ARXIV_SEARCH_CACHE_TTL_SECONDS <= 0:
        return
    _search_cache[cache_key] = (monotonic(), results)


def _recent_submission_window(years: int) -> tuple[datetime, datetime]:
    """Return the UTC submission date window for recent topic searches."""
    now = datetime.now(timezone.utc)
    return now - timedelta(days=365 * years), now


def _format_arxiv_datetime(value: datetime) -> str:
    """Format datetimes for arXiv's submittedDate range syntax."""
    return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M")


def _build_topic_search_query(
    query: str,
    submitted_after: datetime | None = None,
    submitted_before: datetime | None = None,
) -> str:
    search_query = f"all:{query}"
    if submitted_after and submitted_before:
        start = _format_arxiv_datetime(submitted_after)
        end = _format_arxiv_datetime(submitted_before)
        search_query = f"{search_query} AND submittedDate:[{start} TO {end}]"
    return search_query


def _dedupe_entries(entries: list[dict]) -> list[dict]:
    seen: set[str] = set()
    deduped: list[dict] = []
    for entry in entries:
        arxiv_id = normalize_arxiv_id(entry.get("arxiv_id", ""))
        if not arxiv_id or arxiv_id in seen:
            continue
        seen.add(arxiv_id)
        deduped.append(entry)
    return deduped


def _entry_sort_datetime(entry: dict) -> datetime:
    value = entry.get("published") or entry.get("updated")
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


def _rank_recent_entries(entries: list[dict]) -> list[dict]:
    """
    Prefer recency within the relevance-ranked candidate pool.

    arXiv does not expose citation/popularity signals in this API, so the API's
    relevance order acts as the keyword-quality filter before we locally promote
    newer submissions.
    """
    return sorted(entries, key=_entry_sort_datetime, reverse=True)


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


def _extract_arxiv_id_from_entry(entry: ET.Element) -> str:
    """Extract arXiv ID from an Atom entry."""
    atom = {"atom": "http://www.w3.org/2005/Atom"}
    entry_id = (entry.findtext("atom:id", default="", namespaces=atom) or "").strip()
    match = re.search(r"arxiv\.org/abs/([^\s?#]+)", entry_id)
    if match:
        return match.group(1)

    # Fallback: try alternate link
    for link in entry.findall("atom:link", atom):
        href = (link.attrib.get("href") or "").strip()
        match = re.search(r"arxiv\.org/abs/([^\s?#]+)", href)
        if match:
            return match.group(1)

    return entry_id or ""


async def _fetch_search_via_export_api(
    query: str,
    max_results: int,
    submitted_after: datetime | None = None,
    submitted_before: datetime | None = None,
    sort_by: str = "relevance",
) -> list[dict]:
    """
    Fetch multiple papers from export.arxiv.org Atom API by search query.

    Returns:
        List of dicts with title/summary/authors/categories/published/updated/arxiv_id
    """
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": _build_topic_search_query(
            query,
            submitted_after=submitted_after,
            submitted_before=submitted_before,
        ),
        "sortBy": sort_by,
        "sortOrder": "descending",
        "start": 0,
        "max_results": max_results,
    }
    headers = {"User-Agent": ARXIV_USER_AGENT}
    max_retries = max(1, ARXIV_META_MAX_RETRIES)
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            await _respect_arxiv_rate_limit(ARXIV_SEARCH_MIN_INTERVAL_SECONDS)
            async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=headers) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                xml_text = response.text
            break
        except Exception as exc:
            last_error = exc
            status_code = None
            retry_after = None
            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code
                retry_after = _parse_retry_after_seconds(exc.response.headers.get("Retry-After"))

            if (
                status_code == 429
                or (status_code is not None and 500 <= status_code < 600)
                or isinstance(exc, httpx.RequestError)
            ):
                if status_code == 429:
                    global _arxiv_cooldown_until
                    _arxiv_cooldown_until = max(
                        _arxiv_cooldown_until,
                        monotonic() + ARXIV_429_COOLDOWN_SECONDS,
                    )
                if attempt == max_retries:
                    break
                wait = retry_after or _backoff_seconds(attempt)
                logger.warning(
                    "arXiv search failed (%s). Retrying in %.1fs (attempt %d/%d)",
                    status_code or type(exc).__name__,
                    wait,
                    attempt,
                    max_retries,
                )
                await asyncio.sleep(wait)
                continue

            raise ValueError(f"Error searching arXiv: {exc}") from exc

    if last_error and "xml_text" not in locals():
        raise ValueError(f"Error searching arXiv after {max_retries} retries: {last_error}")

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML received from arXiv API: {exc}") from exc

    atom = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", atom)
    results: list[dict] = []
    for entry in entries:
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
        arxiv_id = _extract_arxiv_id_from_entry(entry)

        if not title or not arxiv_id:
            continue

        results.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "summary": summary,
                "authors": authors,
                "categories": categories,
                "published": _parse_atom_datetime(entry.findtext("atom:published", default=None, namespaces=atom)),
                "updated": _parse_atom_datetime(entry.findtext("atom:updated", default=None, namespaces=atom)),
            }
        )

    return results


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
        ValueError: If PDF validation fails
    """
    pdf_bytes, _ = await download_pdf_bytes(pdf_url)
    return pdf_bytes


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
