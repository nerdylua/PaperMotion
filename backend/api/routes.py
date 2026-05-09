"""
FastAPI routes for the ArXiviz API.

Now using SQLite database and local Manim rendering.
"""

import os
import uuid
import hashlib
import tempfile
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .schemas import (
    ProcessRequest,
    ProcessResponse,
    StatusResponse,
    StepInfo,
    PaperResponse,
    PaperListResponse,
    PaperSummary,
    SectionResponse,
    VisualizationResponse,
    VideoResponse,
    HealthResponse,
    JobStatus,
    VisualizationStatus,
    RenderRequest,
    RenderResponse,
    SourceType,
)
from db.connection import get_db
from db import queries
from rendering import process_visualization, get_video_path, get_video_url, extract_scene_name
from jobs import process_paper_job
<<<<<<< Updated upstream
from ingestion.pdf_fetcher import derive_pdf_paper_id
=======
from ingestion.arxiv_fetcher import normalize_arxiv_id, validate_arxiv_id
from ingestion.pdf_sources import normalize_doi, make_paper_id, is_probably_pdf_url, validate_pdf_bytes, safe_title_from_filename
>>>>>>> Stashed changes

router = APIRouter(prefix="/api")


# === Endpoints ===

@router.post("/process", response_model=ProcessResponse)
async def start_processing(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    """
<<<<<<< Updated upstream
    Start processing an arXiv paper or a public PDF URL.

    Returns immediately with a job_id. Poll /api/status/{job_id} for progress.
    """
    if bool(request.arxiv_id) == bool(request.pdf_url):
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of arxiv_id or pdf_url",
        )

    # Create job in database
    job_id = await queries.create_job(db, request.arxiv_id or "pdf")

    # Resolve paper id for response (use derived id for PDFs)
    paper_id = request.arxiv_id or derive_pdf_paper_id(request.pdf_url or "")

    # Start background processing
    background_tasks.add_task(process_paper_job, job_id, request.arxiv_id, request.pdf_url)

    return ProcessResponse(
        job_id=job_id,
        arxiv_id=paper_id,
        status=JobStatus.queued,
        message="Processing started. Poll /api/status/{job_id} for updates.",
        pdf_url=request.pdf_url,
=======
    Start processing a paper (arXiv, DOI, or PDF URL).

    Returns immediately with a job_id. Poll /api/status/{job_id} for progress.
    """
    source_type = request.source_type

    if source_type == SourceType.arxiv:
        if not request.arxiv_id:
            raise HTTPException(status_code=400, detail="Missing arXiv ID")
        if not validate_arxiv_id(request.arxiv_id):
            raise HTTPException(status_code=400, detail="Invalid arXiv ID format")
        paper_id = normalize_arxiv_id(request.arxiv_id)
        source = {"type": "arxiv", "arxiv_id": paper_id, "paper_id": paper_id}

    elif source_type == SourceType.pdf_url:
        if not request.pdf_url:
            raise HTTPException(status_code=400, detail="Missing PDF URL")
        if not is_probably_pdf_url(request.pdf_url):
            raise HTTPException(status_code=400, detail="PDF URL must point to a .pdf file")
        paper_id = make_paper_id("pdf", request.pdf_url)
        source = {"type": "pdf_url", "pdf_url": request.pdf_url, "paper_id": paper_id}

    elif source_type == SourceType.doi:
        if not request.doi:
            raise HTTPException(status_code=400, detail="Missing DOI")
        doi_value = normalize_doi(request.doi)
        if not doi_value:
            raise HTTPException(status_code=400, detail="Invalid DOI format")
        paper_id = make_paper_id("doi", doi_value)
        source = {"type": "doi", "doi": doi_value, "paper_id": paper_id}

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source type: {source_type}")

    job_id = await queries.create_job(db, paper_id)
    background_tasks.add_task(process_paper_job, job_id, source)

    return ProcessResponse(
        job_id=job_id,
        paper_id=paper_id,
        source_type=source_type,
        status=JobStatus.queued,
        message="Processing started. Poll /api/status/{job_id} for updates.",
    )


@router.post("/process/upload", response_model=ProcessResponse)
async def start_processing_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Start processing an uploaded PDF file."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing PDF filename")

    pdf_bytes = await file.read()
    try:
        validate_pdf_bytes(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    digest = hashlib.sha256(pdf_bytes).hexdigest()[:12]
    paper_id = f"pdf_{digest}"

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    temp_file.write(pdf_bytes)
    temp_file.close()

    source = {
        "type": "pdf_upload",
        "paper_id": paper_id,
        "file_path": temp_file.name,
        "filename": file.filename,
        "title": title or safe_title_from_filename(file.filename),
    }

    job_id = await queries.create_job(db, paper_id)
    background_tasks.add_task(process_paper_job, job_id, source)

    return ProcessResponse(
        job_id=job_id,
        paper_id=paper_id,
        source_type=SourceType.pdf_upload,
        status=JobStatus.queued,
        message="Processing started. Poll /api/status/{job_id} for updates.",
>>>>>>> Stashed changes
    )


@router.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the processing status of a job.

    Team 4 polls this endpoint to track progress.
    """
    job = await queries.get_job(db, job_id)

    if job:
        # Build steps_completed from job progress
        progress = job.progress or 0.0
        steps = [
            StepInfo(
                name="fetch_paper",
                status="complete" if progress > 0.1 else ("in_progress" if progress > 0.0 else "pending"),
            ),
            StepInfo(
                name="parse_sections",
                status="complete" if progress > 0.25 else ("in_progress" if progress > 0.1 else "pending"),
            ),
            StepInfo(
                name="generate_visualizations",
                status="complete" if progress > 0.4 else ("in_progress" if progress > 0.25 else "pending"),
            ),
            StepInfo(
                name="render_videos",
                status="complete" if progress >= 1.0 else ("in_progress" if progress > 0.4 else "pending"),
            ),
        ]

        return StatusResponse(
            job_id=job.id,
            paper_id=job.paper_id or "unknown",
            status=JobStatus(job.status),
            progress=progress,
            current_step=job.current_step,
            sections_completed=job.sections_completed or 0,
            sections_total=job.sections_total or 0,
            steps_completed=steps,
            error=job.error,
            created_at=job.created_at,
            estimated_completion=job.created_at + timedelta(minutes=5) if job.status != "completed" else None
        )

    # Job not found - return 404
    raise HTTPException(
        status_code=404,
        detail=f"Job '{job_id}' not found"
    )


@router.get("/paper/{arxiv_id}", response_model=PaperResponse)
async def get_paper(arxiv_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get a processed paper with all sections and visualizations.

    Returns 404 if the paper hasn't been processed yet.
    """
<<<<<<< Updated upstream
    # Handle version suffix for arXiv IDs (e.g., "1706.03762v1" -> "1706.03762")
    if arxiv_id.startswith("pdf_"):
        base_id = arxiv_id
    else:
        base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
=======
    # Handle arXiv version suffix only when ID is arXiv-like
    if validate_arxiv_id(arxiv_id):
        base_id = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id
    else:
        base_id = arxiv_id
>>>>>>> Stashed changes

    paper = await queries.get_paper(db, base_id)

    if paper:
        # Convert database models to response schemas
        sections = sorted(paper.sections, key=lambda s: s.order_index)

        # Build section_id -> video_url lookup from visualizations
        # Prioritize complete videos and take the first complete one for each section
        section_video_map = {}
        section_status_map = {}  # Track status of mapped videos
        for v in paper.visualizations:
            if v.video_url and v.section_id:
                existing_status = section_status_map.get(v.section_id)

                video_url = v.video_url
                if video_url.startswith("/api/video/"):
                    video_id = video_url.rsplit("/", 1)[-1]
                    if not get_video_path(video_id):
                        video_url = None

                if not video_url:
                    continue

                # Only update if:
                # 1. We don't have a video for this section yet, OR
                # 2. This video is complete and the existing one is not complete
                if v.section_id not in section_video_map:
                    section_video_map[v.section_id] = video_url
                    section_status_map[v.section_id] = v.status
                elif v.status == "complete" and existing_status != "complete":
                    # Prefer complete videos over failed/pending/rendering
                    section_video_map[v.section_id] = video_url
                    section_status_map[v.section_id] = v.status

        return PaperResponse(
            paper_id=paper.id,
            title=paper.title,
            authors=paper.authors or [],
            abstract=paper.abstract or "",
            pdf_url=paper.pdf_url or f"https://arxiv.org/pdf/{paper.id}",
            html_url=paper.html_url,
            sections=[
                SectionResponse(
                    id=s.id,
                    title=s.title,
                    content=s.content or "",
                    summary=s.summary or None,
                    level=s.level,
                    order_index=s.order_index,
                    equations=s.equations or [],
                    video_url=section_video_map.get(s.id),
                )
                for s in sections
            ],
            visualizations=[
                VisualizationResponse(
                    id=v.id,
                    section_id=v.section_id,
                    concept=v.concept,
                    video_url=v.video_url,
                    status=VisualizationStatus(v.status),
                )
                for v in paper.visualizations
            ],
            processed_at=paper.updated_at or paper.created_at or datetime.utcnow(),
        )

    raise HTTPException(
        status_code=404,
        detail=f"Paper '{arxiv_id}' not found. Try processing it first with POST /api/process"
    )


@router.get("/papers", response_model=PaperListResponse)
async def list_papers(db: AsyncSession = Depends(get_db)):
    """
    List all processed papers.

    Returns a summary of each paper with visualization counts.
    """
    papers = await queries.list_papers(db)

    return PaperListResponse(
        papers=[
            PaperSummary(
                paper_id=p.id,
                title=p.title,
                authors=p.authors or [],
                visualization_count=len(p.visualizations) if p.visualizations else 0,
                processed_at=p.updated_at or p.created_at or datetime.utcnow(),
            )
            for p in papers
        ],
        total=len(papers),
    )


@router.get("/video/{video_id}")
async def get_video(video_id: str):
    """
    Get a rendered visualization video.

    Returns the actual video file if it exists locally,
    or redirects to the cloud URL (R2) if available.
    """
    # Try local file first
    video_path = get_video_path(video_id)
    if video_path and video_path.exists():
        return FileResponse(
            path=str(video_path),
            media_type="video/mp4",
            filename=f"{video_id}.mp4"
        )

    # Try cloud URL (R2 mode)
    cloud_url = get_video_url(video_id)
    if cloud_url and cloud_url.startswith("http"):
        return RedirectResponse(url=cloud_url, status_code=302)

    raise HTTPException(
        status_code=404,
        detail=f"Video '{video_id}' not found"
    )


@router.post("/render", response_model=RenderResponse)
async def render_manim(request: RenderRequest):
    """
    Test endpoint to render Manim code directly.

    This is for testing/development purposes.
    In production, rendering happens as part of the paper processing pipeline.
    """
    try:
        # Generate a unique video ID
        video_id = f"test_{uuid.uuid4().hex[:8]}"

        # Extract scene name for response
        scene_name = extract_scene_name(request.code)

        # Render the visualization
        video_url = await process_visualization(
            viz_id=video_id,
            manim_code=request.code,
            quality=request.quality
        )

        return RenderResponse(
            video_id=video_id,
            video_url=video_url,
            scene_name=scene_name,
            message=f"Successfully rendered {scene_name}"
        )

    except RuntimeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Rendering failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint.

    Returns status of the API and dependent services.
    """
    import subprocess
    import os

    # Test database connection
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Test Manim availability
    manim_status = "not found"
    try:
        manim_exe = os.getenv("MANIM_EXECUTABLE", "manim")
        result = subprocess.run(
            [manim_exe, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            version = result.stdout.strip().split("\n")[0]
            manim_status = f"available ({version})"
        else:
            manim_status = "error: command failed"
    except FileNotFoundError:
        manim_status = "not installed"
    except Exception as e:
        manim_status = f"error: {str(e)}"

    # Test storage connectivity
    from rendering.storage import STORAGE_MODE, get_backend
    storage_status = "local"
    if STORAGE_MODE == "r2":
        backend = get_backend()
        if hasattr(backend, "check_connectivity"):
            try:
                storage_status = "r2: connected" if backend.check_connectivity() else "r2: unreachable"
            except Exception as e:
                storage_status = f"r2: error ({e})"
        else:
            storage_status = "r2: configured"

    # Check Modal configuration
    from rendering import RENDER_MODE
    modal_status = "not configured"
    if RENDER_MODE == "modal":
        modal_token = os.getenv("MODAL_TOKEN_ID")
        modal_status = "configured" if modal_token else "missing MODAL_TOKEN_ID"

    # When using Modal, manim doesn't need to be local
    if RENDER_MODE == "modal":
        all_healthy = db_status == "connected"
    else:
        all_healthy = db_status == "connected" and "available" in manim_status

    return HealthResponse(
        status="healthy" if all_healthy else "degraded",
        version="0.1.0",
        services={
            "database": db_status,
            "manim": manim_status if RENDER_MODE != "modal" else f"offloaded to modal ({manim_status})",
            "storage": storage_status,
            "redis": "not configured",
            "modal": modal_status
        }
    )
