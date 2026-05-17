# arXivisual Backend

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
RENDER_MODE=local       # local | modal
STORAGE_MODE=local      # local | r2
RENDER_CONCURRENCY=1
```

## Pipeline

1. **Ingest**: arXiv metadata, ar5iv HTML when available, PDF fallback, DOI resolution, direct PDF URLs, and PDF uploads.
2. **Structure**: extract sections/equations/figures/tables, then summarize and organize into up to five reader-friendly sections.
3. **Analyze and plan**: `SectionAnalyzer`, `VisualizationPlanner`, and optional `M2M2PlanningLayer`.
4. **Generate**: `ManimGenerator` creates Manim code, using few-shot examples and live/static Manim docs.
5. **Validate**: code syntax, spatial layout, voiceover quality, and import/runtime smoke checks.
6. **Render and store**: local Manim or Modal rendering; local filesystem or Cloudflare R2 storage.

## API

- `POST /api/process`: start arXiv, DOI, or PDF URL processing.
- `POST /api/process/upload`: upload and process a PDF.
- `GET /api/status/{job_id}`: poll paper job progress.
- `GET /api/paper/{paper_id}`: fetch processed paper data.
- `GET /api/video/{video_id}`: serve local MP4 or redirect to cloud video.
- `POST /api/render`: development endpoint for raw Manim code.
- `POST /api/topic/graph`: start topic graph generation.
- `GET /api/topic/graph/{job_id}`: poll topic graph status/results.
- `GET /api/health`: dependency status.

## Testing

```bash
cd backend
uv run pytest
uv run python tools/test_pipeline.py
uv run python tools/test_pipeline.py --online
uv run python tools/run_demo.py --max 3 --verbose
uv run python tools/run_demo.py --render --quality low
```

For render-only debugging, see `tools/pipeline-tests/`.

## Notes

- Local DB defaults to `sqlite+aiosqlite:///./arxiviz.db`; set `DATABASE_URL` for Postgres-compatible deployments.
- Local videos default to `./media/videos`; these are generated artifacts.
- Local Manim rendering needs FFmpeg, Cairo, Pango, and often LaTeX/MiKTeX for `MathTex`.
- The current voiceover path uses `manim-voiceover[gtts]`; older ElevenLabs docs are stale.
- Runtime files differ slightly: `pyproject.toml` allows Python `>=3.11,<3.14`, `.python-version` is `3.13`, and `runtime.txt` is `python-3.11.14`.
