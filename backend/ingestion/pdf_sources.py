"""
Helpers for PDF/DOI ingestion.

Includes safe PDF download, DOI resolution, and stable paper IDs for non-arXiv inputs.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

PDF_MAGIC = b"%PDF-"
MAX_PDF_BYTES = int(os.getenv("MAX_PDF_BYTES", "26214400"))  # 25 MB default

_DOI_PATTERN = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)


def make_paper_id(prefix: str, value: str) -> str:
    """Create a short, stable paper ID for non-arXiv sources."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def normalize_doi(value: str) -> Optional[str]:
    """Extract and normalize DOI from text or DOI URL."""
    if not value:
        return None
    cleaned = value.strip()
    cleaned = cleaned.replace("doi:", "").replace("DOI:", "")
    cleaned = cleaned.replace("https://doi.org/", "").replace("http://doi.org/", "")
    cleaned = cleaned.replace("https://dx.doi.org/", "").replace("http://dx.doi.org/", "")
    match = _DOI_PATTERN.search(cleaned)
    if not match:
        return None
    return match.group(1).lower().strip()


def is_probably_pdf_url(url: str) -> bool:
    if not url:
        return False
    lower = url.lower()
    if lower.endswith(".pdf"):
        return True
    return ".pdf?" in lower or ".pdf#" in lower


def safe_title_from_filename(filename: str | None) -> str:
    if not filename:
        return "Untitled PDF"
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if name.lower().endswith(".pdf"):
        name = name[:-4]
    return name.strip() or "Untitled PDF"


def validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds size limit ({MAX_PDF_BYTES // (1024 * 1024)} MB)")
    if len(pdf_bytes) < 1024:
        raise ValueError("PDF appears to be too small to be valid")
    if not pdf_bytes.startswith(PDF_MAGIC):
        raise ValueError("File does not look like a valid PDF")


async def download_pdf_bytes(pdf_url: str) -> tuple[bytes, str]:
    """Download PDF bytes with basic validation. Returns bytes and final URL."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
        response = await client.get(pdf_url)
        response.raise_for_status()
        pdf_bytes = response.content
        validate_pdf_bytes(pdf_bytes)
        return pdf_bytes, str(response.url)


async def resolve_doi(doi: str) -> dict:
    """Resolve DOI to a landing page and best-effort PDF URL."""
    doi_url = f"https://doi.org/{doi}"
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(doi_url, headers={"Accept": "text/html,application/pdf"})
        response.raise_for_status()
        final_url = str(response.url)
        content_type = (response.headers.get("content-type") or "").lower()
        if "application/pdf" in content_type or response.content.startswith(PDF_MAGIC):
            return {"landing_url": final_url, "pdf_url": final_url}

        if "text/html" not in content_type:
            return {"landing_url": final_url, "pdf_url": None}

        soup = BeautifulSoup(response.text, "lxml")
        meta_pdf = soup.find("meta", attrs={"name": "citation_pdf_url"})
        if meta_pdf and meta_pdf.get("content"):
            return {"landing_url": final_url, "pdf_url": urljoin(final_url, meta_pdf["content"]) }

        for link in soup.find_all("a", href=True):
            href = link["href"]
            if ".pdf" in href.lower():
                return {"landing_url": final_url, "pdf_url": urljoin(final_url, href)}

        return {"landing_url": final_url, "pdf_url": None}
