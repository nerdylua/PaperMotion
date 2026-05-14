"""
Generic PDF fetcher for non-arXiv URLs.
"""

import hashlib
import logging
import os
from pathlib import PurePosixPath
from typing import Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

PDF_MAX_BYTES = int(os.getenv("PDF_MAX_BYTES", str(50 * 1024 * 1024)))
PDF_TIMEOUT_SECONDS = float(os.getenv("PDF_TIMEOUT_SECONDS", "60.0"))
PDF_USER_AGENT = os.getenv(
    "PDF_USER_AGENT",
    "arXivisual/0.1 (+https://github.com/nihaa/arXivisual)",
)


def derive_pdf_paper_id(pdf_url: str) -> str:
    """Derive a stable paper id for arbitrary PDF URLs."""
    normalized = pdf_url.strip().encode("utf-8")
    digest = hashlib.sha1(normalized).hexdigest()[:12]
    return f"pdf_{digest}"


def guess_title_from_url(pdf_url: str) -> str:
    """Derive a human-friendly title from the PDF URL."""
    path = urlparse(pdf_url).path
    name = PurePosixPath(path).name or "PDF Document"
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    title = name.replace("_", " ").replace("-", " ").strip()
    return title or "PDF Document"


def _is_direct_pdf_url(pdf_url: str) -> bool:
    """Check if URL is a direct PDF link based on path extension."""
    path = urlparse(pdf_url).path.lower()
    return path.endswith(".pdf")


async def download_pdf_from_url(pdf_url: str) -> Tuple[bytes, str]:
    """
    Download a PDF from a direct URL.

    Returns:
        (pdf_bytes, resolved_url)
    """
    if not pdf_url or not pdf_url.strip():
        raise ValueError("pdf_url is required")

    if not _is_direct_pdf_url(pdf_url):
        raise ValueError("pdf_url must be a direct link to a .pdf file")

    headers = {"User-Agent": PDF_USER_AGENT}
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=PDF_TIMEOUT_SECONDS,
        headers=headers,
    ) as client:
        response = await client.get(pdf_url)
        response.raise_for_status()

        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > PDF_MAX_BYTES:
            raise ValueError("PDF is larger than the configured max size")

        content_type = response.headers.get("Content-Type", "").lower()
        if "pdf" not in content_type and not _is_direct_pdf_url(str(response.url)):
            raise ValueError("URL did not return a PDF content type")

        pdf_bytes = response.content
        if len(pdf_bytes) > PDF_MAX_BYTES:
            raise ValueError("PDF is larger than the configured max size")

        resolved_url = str(response.url)

    logger.info("Downloaded PDF: %s bytes from %s", len(pdf_bytes), resolved_url)
    return pdf_bytes, resolved_url
