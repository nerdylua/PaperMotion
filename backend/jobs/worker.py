"""
Background job processing for ArXiviz.

Processes papers asynchronously with progress tracking.
"""

import asyncio
import logging
import os
import pathlib
from datetime import datetime
from db.connection import async_session_maker
from db import queries
from db.models import Section
from rendering import process_visualization, get_video_path
from agents.pipeline import generate_visualizations
from ingestion.pdf_sources import resolve_doi, safe_title_from_filename, validate_pdf_bytes
from ingestion.arxiv_fetcher import validate_arxiv_id
from models.paper import (
    ArxivPaperMeta,
    Equation,
    Figure,
    Section as PaperSection,
    StructuredPaper,
    Table,
)

logger = logging.getLogger(__name__)
RENDER_TIMEOUT_SECONDS = int(os.getenv("RENDER_TIMEOUT_SECONDS", "1200"))


class ProgressBar:
    """Simple progress bar for logging output."""

    def __init__(self, total: int, name: str = "Progress"):
        self.total = total
        self.current = 0
        self.name = name
        self.start_time = datetime.now()

    def update(self, increment: int = 1):
        self.current += increment
        self._display()

    def _display(self):
        """Display progress bar in logs."""
        if self.total == 0:
            return

        percent = self.current / self.total
        bar_length = 30
        filled = int(bar_length * percent)
        bar = "█" * filled + "░" * (bar_length - filled)

        elapsed = (datetime.now() - self.start_time).total_seconds()
        if self.current > 0 and percent > 0:
            avg_time = elapsed / self.current
            eta_seconds = avg_time * (self.total - self.current)
            eta_str = f" ETA: {int(eta_seconds)}s"
        else:
            eta_str = ""

        percent_str = f"{percent*100:5.1f}%"
        logger.info(f"  [{self.name}] {bar} {percent_str} ({self.current}/{self.total}){eta_str}")


async def process_paper_job(job_id: str, source: dict):
    """
    Main job processing function. Called as a background task.

    Pipeline:
    1. Ingest paper from arXiv (real fetch + parse)
    2. Store paper and sections in database
    3. Pick visualizations for sections
    4. Render all visualizations
    5. Update job status to completed
    """
    logger.info("=" * 60)
    source_type = (source or {}).get("type", "arxiv")
    paper_id = (source or {}).get("paper_id") or (source or {}).get("arxiv_id")

    logger.info(f"STARTING JOB: {job_id}")
    logger.info(f"Source type: {source_type}")
    logger.info(f"Paper ID: {paper_id}")
    logger.info("=" * 60)

    async with async_session_maker() as db:
        try:
            if not paper_id:
                raise ValueError("Missing paper_id for processing")
            # Step 1: Ingest paper from source
            logger.info("STEP 1: Ingesting paper")
            logger.info("-" * 60)

            await queries.update_job_status(
                db, job_id,
                status="processing",
                current_step="Fetching paper source",
                progress=0.10
            )

            paper_exists = await queries.paper_exists(db, paper_id)
            if paper_exists:
                logger.info("Paper %s already exists in database, skipping ingestion", paper_id)
            else:
                logger.info("Paper %s not found, ingesting from %s", paper_id, source_type)

            if not paper_exists:
                structured_paper = await _ingest_from_source(job_id, source)
                await _store_structured_paper(db, job_id, paper_id, structured_paper)
            else:
                # Paper already exists, just link the job to it
                logger.info("Linking job to existing paper...")
                job = await queries.get_job(db, job_id)
                if job:
                    job.paper_id = paper_id
                    await db.commit()
                logger.info("Job linked successfully")

                # Update progress to match what would happen after ingestion
                await queries.update_job_status(
                    db, job_id,
                    current_step="Paper already processed",
                    progress=0.30
                )

            # Step 2: Generate visualizations from structured paper
            logger.info("=" * 60)
            logger.info("STEP 2: Generating visualizations from structured paper")
            logger.info("=" * 60)

            await queries.update_job_status(
                db, job_id,
                current_step="Analyzing concepts for visualization",
                progress=0.50
            )

            db_paper = await queries.get_paper(db, paper_id)
            logger.info(f"Found paper in database: {db_paper.title}")

            db_sections = sorted(db_paper.sections, key=lambda s: s.order_index)
            logger.info(f"Loaded {len(db_sections)} sections from database")

            structured_paper = _build_structured_paper_from_db(db_paper, db_sections)
            logger.info("Converted database sections to StructuredPaper format")

            logger.info("Invoking visualization generation pipeline...")
            generated_visualizations = await generate_visualizations(structured_paper)
            logger.info(f"Generated {len(generated_visualizations)} visualization(s)")

            # Create visualization records
            logger.info("Creating visualization records in database...")
            viz_records = []

            # Use paper-based prefix for consistent viz_ids across re-runs
            paper_suffix = paper_id.replace(".", "")[:8]

            for i, visualization in enumerate(generated_visualizations):
                # Create consistent viz_id based on paper and index, not job
                viz_id = f"viz_{paper_suffix}_{i+1}"
                logger.info(f"  [{i+1}/{len(generated_visualizations)}] Creating record for {viz_id}")
                logger.debug(f"    Concept: {visualization.concept}")
                logger.debug(f"    Section: {visualization.section_id}")

                await queries.upsert_visualization(
                    db,
                    viz_id=viz_id,
                    paper_id=paper_id,
                    section_id=visualization.section_id,
                    concept=visualization.concept,
                    storyboard={"raw": visualization.storyboard},
                    manim_code=visualization.manim_code,
                    status="pending",
                )
                viz_records.append({
                    "id": viz_id,
                    "manim_code": visualization.manim_code,
                })

            if not viz_records:
                logger.warning("No valid visualizations were generated from the paper")
                await queries.update_job_status(
                    db, job_id,
                    status="completed",
                    current_step="No valid visualizations generated",
                    progress=1.0
                )
                return

            # Step 3: Render visualizations
            logger.info("=" * 60)
            logger.info(f"STEP 3: Rendering {len(viz_records)} visualizations")
            logger.info("=" * 60)

            await queries.update_job_status(
                db, job_id,
                current_step="Generating animations",
                progress=0.70,
                sections_total=len(viz_records),
                sections_completed=0
            )

            # Update again when actually rendering starts
            await queries.update_job_status(
                db, job_id,
                current_step="Rendering videos",
                progress=0.75
            )

            render_concurrency = max(1, int(os.getenv("RENDER_CONCURRENCY", "2")))
            render_semaphore = asyncio.Semaphore(render_concurrency)
            progress_lock = asyncio.Lock()
            progress_bar = ProgressBar(len(viz_records), "Video Rendering")
            completed_count = 0

            async def _mark_viz_rendering(viz_id: str) -> None:
                """Mark visualization as actively rendering in an isolated DB session."""
                async with async_session_maker() as progress_db:
                    await queries.update_visualization_status(
                        progress_db,
                        viz_id,
                        status="rendering",
                        error=None,
                    )

            async def _record_render_outcome(
                viz_id: str,
                status: str,
                video_url: str | None = None,
                error: str | None = None,
            ) -> None:
                """
                Record render result + job progress.

                Uses its own AsyncSession because AsyncSession is not safe for
                concurrent use across render tasks.
                """
                nonlocal completed_count
                async with progress_lock:
                    completed_count += 1
                    render_progress = 0.75 + (0.20 * (completed_count / len(viz_records)))
                    async with async_session_maker() as progress_db:
                        await queries.update_visualization_status(
                            progress_db,
                            viz_id,
                            status=status,
                            video_url=video_url,
                            error=error,
                        )
                        await queries.update_job_status(
                            progress_db,
                            job_id,
                            progress=render_progress,
                            sections_completed=completed_count,
                        )
                progress_bar.update()

            async def _render_one(viz: dict, index: int):
                async with render_semaphore:
                    viz_id = viz["id"]
                    try:
                        logger.info(f"Starting render: {viz_id}")
                        await _mark_viz_rendering(viz_id)
                        video_url = await asyncio.wait_for(
                            process_visualization(
                                viz_id=viz_id,
                                manim_code=viz["manim_code"],
                                quality="low_quality",
                            ),
                            timeout=RENDER_TIMEOUT_SECONDS,
                        )
                        logger.info(f"✓ Successfully rendered {viz_id}")
                        await _record_render_outcome(
                            viz_id=viz_id,
                            status="complete",
                            video_url=video_url,
                        )
                        return True
                    except Exception as e:
                        logger.error(f"✗ Failed to render {viz_id}: {str(e)}")
                        await _record_render_outcome(
                            viz_id=viz_id,
                            status="failed",
                            error=str(e),
                        )
                        return False

            logger.info(
                "Rendering %d videos concurrently (max %d parallel)...",
                len(viz_records),
                render_concurrency,
            )
            render_results = await asyncio.gather(*[
                _render_one(viz, i) for i, viz in enumerate(viz_records)
            ])

            logger.info("All render tasks finished.")

            success_count = sum(1 for ok in render_results if ok)
            failure_count = len(render_results) - success_count
            logger.info(
                "Render summary: %d succeeded, %d failed (total=%d)",
                success_count,
                failure_count,
                len(render_results),
            )

            if success_count == 0:
                await queries.update_job_status(
                    db,
                    job_id,
                    status="failed",
                    current_step="Rendering failed",
                    progress=1.0,
                    error=f"All {failure_count} visualizations failed to render",
                )
                logger.error(
                    "All visualizations failed for job %s (paper %s)",
                    job_id,
                    paper_id,
                )
                return

            # Brief pause to ensure all DB commits have settled
            await asyncio.sleep(0.5)

            # Step 4: Complete
            logger.info("=" * 60)
            logger.info("STEP 4: Finalizing job")
            logger.info("=" * 60)

            await queries.update_job_status(
                db, job_id,
                status="completed",
                current_step="Complete",
                progress=1.0
            )

            logger.info("Job status updated to completed with progress 1.0")

            logger.info("=" * 60)
            logger.info(f"✓ JOB COMPLETED SUCCESSFULLY: {job_id}")
            logger.info(f"✓ Paper: {paper_id}")
            logger.info(f"✓ Visualizations rendered: {len(viz_records)}")
            logger.info("=" * 60)

        except Exception as e:
            logger.exception(f"✗ JOB FAILED: {job_id} for paper {paper_id}")
            logger.error(f"Error: {str(e)}")
            try:
                await db.rollback()
                await queries.update_job_status(
                    db, job_id,
                    status="failed",
                    error=str(e)
                )
            except Exception:
                logger.exception("Failed to update job status after error")
            raise


async def _ingest_from_source(job_id: str, source: dict) -> StructuredPaper:
    """Ingest a paper from the specified source type."""
    from ingestion import ingest_paper, ingest_pdf_bytes, ingest_pdf_url

    source_type = (source or {}).get("type", "arxiv")
    paper_id = (source or {}).get("paper_id") or (source or {}).get("arxiv_id")

    if source_type == "arxiv":
        arxiv_id = (source or {}).get("arxiv_id")
        if not arxiv_id:
            raise ValueError("Missing arXiv ID for processing")
        return await ingest_paper(arxiv_id)

    if source_type == "pdf_url":
        pdf_url = (source or {}).get("pdf_url")
        if not pdf_url:
            raise ValueError("Missing PDF URL for processing")
        title = (source or {}).get("title")
        return await ingest_pdf_url(paper_id, pdf_url, title=title)

    if source_type == "doi":
        doi_value = (source or {}).get("doi")
        if not doi_value:
            raise ValueError("Missing DOI for processing")
        await asyncio.sleep(0)  # allow context switch before network calls
        resolution = await resolve_doi(doi_value)
        pdf_url = resolution.get("pdf_url")
        if not pdf_url:
            raise ValueError("Could not locate a PDF for the provided DOI")
        title = (source or {}).get("title")
        return await ingest_pdf_url(paper_id, pdf_url, title=title)

    if source_type == "pdf_upload":
        upload_path = (source or {}).get("file_path")
        original_name = (source or {}).get("filename")
        if not upload_path:
            raise ValueError("Missing uploaded PDF path for processing")
        path = pathlib.Path(upload_path)
        pdf_bytes = path.read_bytes()
        validate_pdf_bytes(pdf_bytes)
        title = (source or {}).get("title") or safe_title_from_filename(original_name)
        try:
            return await ingest_pdf_bytes(paper_id, pdf_bytes, title=title)
        finally:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to remove temp upload: %s", upload_path)

    raise ValueError(f"Unsupported source type: {source_type}")


async def _store_structured_paper(db, job_id: str, paper_id: str, structured_paper: StructuredPaper):
    """Store a StructuredPaper into the database and link it to the job."""
    meta = structured_paper.meta

    await queries.update_job_status(
        db, job_id,
        current_step="Parsing sections and content",
        progress=0.30
    )

    await queries.create_paper(
        db,
        paper_id=paper_id,
        title=meta.title,
        authors=meta.authors,
        abstract=meta.abstract,
        pdf_url=meta.pdf_url,
        html_url=meta.html_url,
    )

    job = await queries.get_job(db, job_id)
    if job:
        job.paper_id = paper_id
        await db.commit()

    stored_count = 0
    seen_ids = set()
    for i, section in enumerate(structured_paper.sections):
        sid = section.id
        if sid in seen_ids:
            sid = f"{sid}-{i}"
        seen_ids.add(sid)

        try:
            async with db.begin_nested():
                equations_json = [eq.latex for eq in section.equations]
                figures_json = [fig.model_dump() for fig in section.figures]
                tables_json = [tbl.model_dump() for tbl in section.tables]

                section_obj = Section(
                    id=sid,
                    paper_id=paper_id,
                    title=section.title,
                    content=section.content,
                    summary=section.summary or None,
                    level=section.level,
                    order_index=i,
                    equations=equations_json,
                    figures=figures_json,
                    tables=tables_json,
                )
                db.add(section_obj)
            stored_count += 1
        except Exception as e:
            logger.warning("Failed to store section '%s': %s", section.title, e)

    await db.commit()
    logger.info("Stored paper '%s' with %d/%d sections", meta.title, stored_count, len(structured_paper.sections))


def _build_structured_paper_from_db(db_paper, db_sections: list[Section]) -> StructuredPaper:
    """Reconstruct StructuredPaper from database rows for generator pipeline input."""
    pdf_url = db_paper.pdf_url
    if not pdf_url and validate_arxiv_id(db_paper.id):
        pdf_url = f"https://arxiv.org/pdf/{db_paper.id}"

    meta = ArxivPaperMeta(
        arxiv_id=db_paper.id,
        title=db_paper.title,
        authors=db_paper.authors or [],
        abstract=db_paper.abstract or "",
        pdf_url=pdf_url or "",
        html_url=db_paper.html_url,
    )

    sections: list[PaperSection] = []
    for db_section in db_sections:
        equations = [
            Equation(latex=eq if isinstance(eq, str) else str(eq), context="")
            for eq in (db_section.equations or [])
        ]
        figures = [
            Figure(
                id=fig.get("id", f"{db_section.id}-figure-{idx+1}"),
                caption=fig.get("caption", ""),
                page=fig.get("page"),
            )
            for idx, fig in enumerate(db_section.figures or [])
            if isinstance(fig, dict)
        ]
        tables = [
            Table(
                id=tbl.get("id", f"{db_section.id}-table-{idx+1}"),
                caption=tbl.get("caption", ""),
                headers=tbl.get("headers", []),
                rows=tbl.get("rows", []),
            )
            for idx, tbl in enumerate(db_section.tables or [])
            if isinstance(tbl, dict)
        ]

        sections.append(
            PaperSection(
                id=db_section.id,
                title=db_section.title,
                level=db_section.level,
                content=db_section.content or "",
                equations=equations,
                figures=figures,
                tables=tables,
            )
        )

    return StructuredPaper(meta=meta, sections=sections)
