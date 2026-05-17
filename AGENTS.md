# PaperMotion Agent Context

PaperMotion turns papers into interactive visual explanations: ingest a paper, summarize/structure it, identify visualizable concepts, generate 3Blue1Brown-style Manim scenes with optional voiceover, validate/render videos, and display them in a Next.js scrollytelling reader.

## Repo Shape

- `frontend/`: Next.js 16 + React 19 App Router UI. Main routes are `/`, `/abs/[...id]`, and `/topic`.
- `backend/`: FastAPI + async SQLAlchemy backend. Handles ingestion, OpenAI-backed LLM agents, validation, local Manim rendering/storage, and job status.
- Root `docker-compose.yml` runs the backend only; run/deploy the frontend separately unless a frontend Dockerfile/service is added.
- Generated/local artifacts: do not commit `.env`, `.env.local`, `.venv/`, `.next/`, `node_modules/`, `backend/papermotion.db`, `*.sqlite3`, `backend/media/`, `backend/generated_output/`, `server/outputs/*`, or rendered MP4s.

## Product Surface

- Home supports arXiv ID/URL, DOI, direct PDF URL, and PDF upload.
- Frontend has instant demo papers for `1706.03762`, `2005.14165`, `2303.08774` from `frontend/lib/mock-data.ts`; these bypass the backend.
- Processed papers render as a card-stack scrollytelling reader with markdown, KaTeX equations, and inline MP4 visualizations.
- `/topic` starts a topic graph job: arXiv search, OpenAI embeddings, similarity graph, Manim explainer video, and per-paper abstract snapshot videos.

## Backend Architecture

- Entrypoint: `backend/main.py`; routes live in `backend/api/routes.py`; API schemas in `backend/api/schemas.py`.
- DB defaults to SQLite at `backend/papermotion.db`; `DATABASE_URL` switches to async Postgres URL forms in `backend/db/connection.py`.
- Tables: `Paper`, `Section`, `Visualization`, `ProcessingJob`, `TopicGraphJob` in `backend/db/models.py`.
- Jobs are FastAPI `BackgroundTasks`, not a real queue. `backend/jobs/worker.py` processes papers; `backend/jobs/topic_graph_worker.py` processes topic graphs.
- API contract:
  - `POST /api/process`: arXiv, DOI, PDF URL.
  - `POST /api/process/upload`: uploaded PDF.
  - `GET /api/status/{job_id}`: progress.
  - `GET /api/paper/{paper_id}`: paper, sections, visualization metadata.
  - `GET /api/video/{video_id}`: local MP4 file.
  - `POST /api/render`: development raw Manim render.
  - `POST /api/topic/graph`, `GET /api/topic/graph/{job_id}`.
  - `GET /api/health`: DB, Manim, storage, Modal status.

## Backend Flow

1. Ingestion (`backend/ingestion/`):
   - arXiv metadata via export API with conservative rate limiting and 429 cooldowns.
   - ar5iv HTML preferred when available; PDF fallback uses PyMuPDF/PyMuPDF4LLM.
   - DOI resolution looks for landing-page PDF links.
   - PDF bytes are magic-byte and size checked.
   - `section_extractor.py` finds hierarchy and filters references/appendices/etc.
   - `section_formatter.py` uses a two-phase LLM flow: holistic paper summary then organization into `<=5` beginner-friendly sections. If it fails, raw extracted sections may be used.
2. Generation pipeline (`backend/agents/pipeline.py`):
   - `SectionAnalyzer` finds candidates and skips low-value sections.
   - `VisualizationPlanner` creates 30-45s storyboards.
   - Optional `M2M2PlanningLayer` adds paper-grounded scene specs; it is disabled by default (`ENABLE_M2M2_LAYER=false`) because it adds one extra LLM call per visualization. Enable only for math-heavy experiments where the extra scene-spec pass is worth the latency. Failure falls back to the base plan.
   - `ManimGenerator` selects few-shot examples by `VisualizationType`, uses the bundled Manim reference prompt, and emits Manim code. Unified voice mode emits `VoiceoverScene` with gTTS blocks.
   - Validators: `CodeValidator`, `SpatialValidator`, `VoiceoverScriptValidator`, `RenderTester`. Validation failures feed back into regeneration.
3. Rendering/storage:
   - `rendering/local_runner.py` shells out to Manim in a temp dir. It has Windows MiKTeX PATH handling.
   - Local storage writes videos under `./media/videos` by default.

## Frontend Architecture

- `frontend/lib/api.ts` mirrors backend schemas and resolves relative `/api/video/...` URLs against `NEXT_PUBLIC_API_URL`.
- `frontend/app/page.tsx` parses input modes and starts jobs; demo IDs route directly to `/abs/...`.
- `frontend/app/abs/[...id]/page.tsx` owns paper loading, demo simulation, status polling, and final reader state.
- Reader UI: `CardStack` + `StackCard` are the active card-stack implementation; `ScrollyReader`, `ScrollySection`, and `SectionViewer` are older/alternate readers.
- Markdown/equations: `MarkdownContent` uses `react-markdown`, `remark-math`, `rehype-katex`, and normalizes common PDF/LLM small-caps/LaTeX artifacts.
- Styling is Tailwind v4 plus dark glassmorphism variables in `app/globals.css`; many components use explicit `bg-white/[...]` classes.
- `VideoPlayer` is a custom HTML video wrapper with play overlay, progress seek, fullscreen, load/error state.
- Config: strict TypeScript, `@/*` path alias, Next ESLint core web vitals/typescript, Tailwind v4 via `@tailwindcss/postcss`. The frontend currently uses native `fetch`; `axios` and `@tanstack/react-query` were removed as unused.

## Runtime Config

- Backend required: `OPENAI_API_KEY`.
- Backend common optional: `OPENAI_MODEL`, `OPENAI_REASONING_EFFORT`, `OPENAI_BASE_URL`, `OPENAI_EMBEDDING_MODEL`, `ENABLE_M2M2_LAYER`, `MEDIA_DIR`, `RENDER_CONCURRENCY`, `RENDER_TIMEOUT_SECONDS`, `MANIM_SUBPROCESS_TIMEOUT_SECONDS`, `MIKTEX_BIN_DIR`, arXiv throttle env vars.
- Frontend: `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000`; `NEXT_PUBLIC_USE_MOCK=true` enables mock API behavior.
- Current code defaults to OpenAI `gpt-5.4-mini` and gTTS voiceover. Older docs mention ElevenLabs/Redis/Postgres/default `gpt-5.4` as plans; verify code before following those notes.
- Python runtime is slightly inconsistent across files: `backend/pyproject.toml` allows `>=3.11,<3.14`, `backend/.python-version` is `3.13`, and `backend/runtime.txt` says `python-3.11.14`.

## Commands

- Frontend setup/run: `cd frontend && npm install && npm run dev`.
- Frontend checks: `cd frontend && npm run lint && npm run build`.
- Backend setup/run: `cd backend && cp .env.example .env && uv sync && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000`.
- Docker backend only: `docker compose up` from repo root; this does not start the Next app.

## Change Guidance

- Keep API schema changes synchronized across `backend/api/schemas.py`, `backend/api/routes.py`, `frontend/lib/api.ts`, and `frontend/lib/types.ts`.
- For new visualization types, update `VisualizationType`, add a few-shot example in `backend/examples/`, and map it in `ManimGenerator.EXAMPLE_FILES` and `VOICEOVER_EXAMPLE_FILES`.
- Be conservative with Manim code generation prompts: MathTex splitting, missing `buff`, out-of-frame positions, and untimed voiceover `self.play` calls are recurring failure modes.
- Do not remove validation stages casually; they are compensating for common LLM/Manim/runtime failures.
- Background jobs use concurrent rendering with separate DB sessions. Do not share one `AsyncSession` across render tasks.
- When working on generated videos or local DB state, remember they are development artifacts and generally should not be committed.
- Prefer low-quality Manim renders while testing. Local Manim requires FFmpeg, Cairo, Pango, and often LaTeX/MiKTeX for `MathTex`.
- Only change lockfiles (`frontend/package-lock.json`, `backend/uv.lock`) when intentionally updating dependencies or workspace metadata.
- `tmp_job_diag.py` is a diagnostic script, not a core product path.
