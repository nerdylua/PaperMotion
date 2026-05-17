"""
Paper Ingestion Pipeline for PaperMotion.

Main entry point: ingest_paper(arxiv_id) -> StructuredPaper

Pipeline:
1. Fetch metadata from arXiv API
2. Check for ar5iv HTML availability
3. Parse HTML (preferred) or PDF (fallback)
4. Extract sections with hierarchy
5. Cache and return StructuredPaper

Team 1 owns this module. Output goes to Team 2's AI agents.
"""

import logging
import re
from typing import Optional

from models.paper import (
    ArxivPaperMeta,
    ParsedContent,
    Section,
    StructuredPaper,
)
from .arxiv_fetcher import (
    fetch_paper_meta,
    download_pdf,
    fetch_html_content,
    normalize_arxiv_id,
    validate_arxiv_id,
)
from .pdf_fetcher import (
    download_pdf_from_url,
    derive_pdf_paper_id,
    guess_title_from_url,
)
from .pdf_parser import parse_pdf
from .pdf_sources import download_pdf_bytes
from .html_parser import parse_html, fetch_and_parse_html
from .section_extractor import extract_sections
from .section_formatter import format_sections

# Configure logging
logger = logging.getLogger(__name__)

# Simple in-memory cache for development
# In production, use Redis or database
_paper_cache: dict[str, StructuredPaper] = {}


async def ingest_paper(
    arxiv_id: str,
    force_refresh: bool = False,
    prefer_pdf: bool = False
) -> StructuredPaper:
    """
    Main entry point for paper ingestion.

    Takes an arXiv ID and returns a fully structured paper ready for
    Team 2's AI visualization pipeline.

    Args:
        arxiv_id: arXiv paper ID (e.g., "1706.03762" or "1706.03762v1")
        force_refresh: If True, bypass cache and re-fetch
        prefer_pdf: If True, use PDF even if HTML is available

    Returns:
        StructuredPaper with metadata and extracted sections

    Raises:
        ValueError: If paper not found or parsing fails
    """
    # Normalize ID
    arxiv_id = normalize_arxiv_id(arxiv_id)
    logger.info(f"Starting ingestion for paper: {arxiv_id}")

    # Check cache
    if not force_refresh:
        cached = await get_cached_paper(arxiv_id)
        if cached:
            logger.info(f"Returning cached paper: {arxiv_id}")
            return cached

    # Step 1: Fetch metadata from arXiv
    logger.info(f"Fetching metadata for: {arxiv_id}")
    meta = await fetch_paper_meta(arxiv_id)
    logger.info(f"Got paper: {meta.title}")

    # Step 2: Parse content (HTML preferred, PDF fallback)
    content: ParsedContent

    if meta.html_url and not prefer_pdf:
        # Try HTML first (cleaner structure)
        logger.info(f"Parsing ar5iv HTML: {meta.html_url}")
        try:
            content = await fetch_and_parse_html(meta.html_url)
            logger.info("Successfully parsed HTML content")
        except Exception as e:
            logger.warning(f"HTML parsing failed, falling back to PDF: {e}")
            content = await _parse_pdf_content(meta.pdf_url)
    else:
        # Use PDF
        content = await _parse_pdf_content(meta.pdf_url)

    # Step 3: Extract sections
    logger.info("Extracting sections from parsed content")
    sections = extract_sections(content, meta)
    raw_count = len(sections)
    total_chars = sum(len(s.content) for s in sections)
    logger.info(f"Extracted {raw_count} raw sections ({total_chars:,} chars total)")

    # Step 4: Summarize + organize into <=5 sections (two-phase LLM pipeline)
    try:
        sections = await format_sections(sections, meta)
        logger.info(
            f"Section formatting succeeded: {raw_count} raw → {len(sections)} summarized sections"
        )
    except Exception as e:
        logger.error(
            f"Section formatting FAILED ({type(e).__name__}: {e}). "
            f"Falling back to {raw_count} raw sections. "
            f"This usually means the LLM call timed out or the API key is invalid."
        )

    # Step 5: Build final structure
    paper = StructuredPaper(
        meta=meta,
        sections=sections
    )

    # Step 6: Cache result
    await cache_paper(paper)

    logger.info(f"Ingestion complete for: {arxiv_id}")
    return paper


def _extract_abstract(raw_text: str) -> str:
    """Best-effort abstract extraction from markdown text."""
    match = re.search(r"(?ims)^#{1,6}\s*abstract\s*$", raw_text)
    if not match:
        return ""
    start = match.end()
    next_header = re.search(r"(?im)^#{1,6}\s+", raw_text[start:])
    end = start + next_header.start() if next_header else len(raw_text)
    abstract = raw_text[start:end].strip()
    return abstract


async def ingest_pdf_bytes(
    paper_id: str,
    pdf_bytes: bytes,
    title: Optional[str] = None,
    pdf_url: Optional[str] = None,
) -> StructuredPaper:
    """Ingest a PDF from raw bytes and return a structured paper."""
    logger.info("Parsing PDF bytes for paper: %s", paper_id)
    content = parse_pdf(pdf_bytes)
    abstract = _extract_abstract(content.raw_text)

    meta = ArxivPaperMeta(
        arxiv_id=paper_id,
        title=title or "Uploaded PDF",
        authors=[],
        abstract=abstract,
        published=None,
        updated=None,
        categories=[],
        pdf_url=pdf_url or "",
        html_url=None,
    )

    sections = extract_sections(content, meta)
    raw_count = len(sections)
    total_chars = sum(len(s.content) for s in sections)
    logger.info("Extracted %d raw sections (%d chars total)", raw_count, total_chars)

    try:
        sections = await format_sections(sections, meta)
        logger.info("Section formatting succeeded: %d raw -> %d sections", raw_count, len(sections))
    except Exception as e:
        logger.error(
            "Section formatting FAILED (%s: %s). Falling back to raw sections.",
            type(e).__name__,
            e,
        )

    paper = StructuredPaper(meta=meta, sections=sections)
    await cache_paper(paper)
    return paper


async def ingest_pdf_url(
    paper_id: str,
    pdf_url: str,
    title: Optional[str] = None,
) -> StructuredPaper:
    """Download and ingest a PDF by URL, deriving a title from the URL when missing."""
    if not title:
        title = guess_title_from_url(pdf_url)
    logger.info("Downloading PDF from URL: %s", pdf_url)
    pdf_bytes, final_url = await download_pdf_bytes(pdf_url)
    return await ingest_pdf_bytes(paper_id, pdf_bytes, title=title, pdf_url=final_url)


async def _parse_pdf_content(pdf_url: str) -> ParsedContent:
    """Helper to download and parse PDF."""
    logger.info(f"Downloading PDF: {pdf_url}")
    pdf_bytes = await download_pdf(pdf_url)
    logger.info(f"Downloaded {len(pdf_bytes)} bytes, parsing...")

    content = parse_pdf(pdf_bytes)
    logger.info(
        f"Parsed PDF: {len(content.raw_text)} chars, "
        f"{len(content.equations)} equations, "
        f"{len(content.figures)} figures, "
        f"{len(content.tables)} tables"
    )
    return content


async def get_cached_paper(arxiv_id: str) -> Optional[StructuredPaper]:
    """
    Check cache for previously processed paper.

    In production, this would check Redis/database.
    """
    return _paper_cache.get(arxiv_id)


async def cache_paper(paper: StructuredPaper) -> None:
    """
    Cache processed paper for future requests.

    In production, this would store in Redis/database.
    """
    _paper_cache[paper.meta.arxiv_id] = paper
    logger.debug(f"Cached paper: {paper.meta.arxiv_id}")


def clear_cache() -> None:
    """Clear the paper cache (useful for testing)."""
    _paper_cache.clear()
    logger.info("Paper cache cleared")


# Export public API
__all__ = [
    # Main function
    "ingest_paper",
    "ingest_pdf_url",

    # Cache functions
    "get_cached_paper",
    "cache_paper",
    "clear_cache",

    # Lower-level functions for flexibility
    "fetch_paper_meta",
    "download_pdf",
    "download_pdf_from_url",
    "fetch_html_content",
    "parse_pdf",
    "ingest_pdf_bytes",
    "ingest_pdf_url",
    "parse_html",
    "fetch_and_parse_html",
    "extract_sections",
    "format_sections",
    "normalize_arxiv_id",
    "validate_arxiv_id",
    "derive_pdf_paper_id",
    "guess_title_from_url",

    # Models (re-exported for convenience)
    "ArxivPaperMeta",
    "ParsedContent",
    "Section",
    "StructuredPaper",
]
