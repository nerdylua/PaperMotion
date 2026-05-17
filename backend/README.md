# PaperMotion Backend

FastAPI backend for ingesting papers, generating validated Manim visualizations, rendering videos, and serving processing status to the frontend.

## Quick Start

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Required env:

```env
OPENAI_API_KEY=sk-your-openai-key
```

Common optional env:

```env
OPENAI_MODEL=gpt-5.4-mini
ENABLE_M2M2_LAYER=false
RENDER_CONCURRENCY=1
MEDIA_DIR=./media/videos
```

## Pipeline

1. **Ingest**: arXiv metadata, ar5iv HTML when available, PDF fallback, DOI resolution, direct PDF URLs, and PDF uploads.
2. **Structure**: extract sections/equations/figures/tables, then summarize and organize into up to five reader-friendly sections.
3. **Analyze and plan**: `SectionAnalyzer` and `VisualizationPlanner`; optional `M2M2PlanningLayer` is off by default.
4. **Generate**: `ManimGenerator` creates Manim code, using few-shot examples and live/static Manim docs.
5. **Validate**: code syntax, spatial layout, voiceover quality, and import/runtime smoke checks.
6. **Render and store**: local Manim rendering and local filesystem storage.

## API

- `POST /api/process`: start arXiv, DOI, or PDF URL processing.
- `POST /api/process/upload`: upload and process a PDF.
- `GET /api/status/{job_id}`: poll paper job progress.
- `GET /api/paper/{paper_id}`: fetch processed paper data.
- `GET /api/video/{video_id}`: serve local MP4 video.
- `POST /api/render`: development endpoint for raw Manim code.
- `POST /api/topic/graph`: start topic graph generation.
- `GET /api/topic/graph/{job_id}`: poll topic graph status/results.
- `GET /api/health`: dependency status.

## Notes

- Local DB defaults to `sqlite+aiosqlite:///./papermotion.db`; set `DATABASE_URL` for Postgres-compatible deployments.
- Local videos default to `./media/videos`; these are generated artifacts.
- `ENABLE_M2M2_LAYER=false` by default keeps generation faster. Set it to `true` only when testing the extra paper-grounded Math-To-Manim scene-spec pass for math-heavy visualizations.
- Local Manim rendering needs FFmpeg, Cairo, Pango, and often LaTeX/MiKTeX for `MathTex`.
- The current voiceover path uses `manim-voiceover[gtts]`; older ElevenLabs docs are stale.
- Runtime files differ slightly: `pyproject.toml` allows Python `>=3.11,<3.14`, `.python-version` is `3.13`, and `runtime.txt` is `python-3.11.14`.
