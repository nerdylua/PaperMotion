# arXivisual Features

arXivisual turns research papers into structured, scrollable visual explanations. The product combines paper ingestion, LLM analysis, Manim animation generation, validation, rendering, and a Next.js scrollytelling reader.

## Product Surface

| Area | Feature | Technical notes |
| --- | --- | --- |
| Paper input | arXiv ID/URL, DOI, direct PDF URL, PDF upload | Frontend parses input modes; backend normalizes source metadata through `/api/process` or `/api/process/upload`. |
| Cached demos | Instant demos for `1706.03762`, `2005.14165`, `2303.08774` | Served from `frontend/lib/mock-data.ts` and `frontend/public/videos/demo`. No backend required. |
| Processing status | Pollable async jobs | `/api/status/{job_id}` returns progress, current step, section counts, and failures. |
| Scrollytelling reader | Paper hero, abstract, section cards, progress bar, embedded videos | `frontend/app/abs/[...id]/page.tsx` renders a card-stack reader with scroll-driven transitions. |
| Video playback | Inline MP4 player with progress, seek, fullscreen, load/error state | `frontend/components/VideoPlayer.tsx`. |
| Topic graph | Search arXiv by topic, embed papers, build similarity graph, render explainer | `/topic` UI calls `/api/topic/graph`; backend uses OpenAI embeddings and Manim. |
| Health and diagnostics | Backend dependency status | `/api/health` checks DB, Manim/local rendering, storage, and Modal config. |

## Backend Pipeline

1. **Ingest**
   - arXiv metadata via arXiv API.
   - ar5iv HTML preferred when available.
   - PDF fallback through PyMuPDF/PyMuPDF4LLM.
   - DOI resolution and arbitrary PDF ingestion supported.
   - Uploads are validated as PDFs and processed from temp files.

2. **Structure**
   - Extracts sections, hierarchy, equations, figures, and tables.
   - Runs section formatting/summarization when LLM access is available.
   - Persists papers, sections, jobs, visualizations, and topic graph jobs in SQLAlchemy models.

3. **Analyze**
   - `SectionAnalyzer` identifies concepts worth visualizing.
   - Skips low-value sections such as references, bibliography, acknowledgements, appendix, supplementary, and related work.
   - Prioritizes up to `MAX_VISUALIZATIONS = 5`.

4. **Plan**
   - `VisualizationPlanner` produces scene-by-scene storyboards.
   - Optional `M2M2PlanningLayer` enriches plans with beat-level specs.

5. **Generate**
   - `ManimGenerator` creates runnable Manim Python code.
   - Few-shot examples are selected by visualization type.
   - Unified voice mode can emit `VoiceoverScene` code with timed narration blocks.

6. **Validate**
   - `CodeValidator`: AST parse, imports, scene/construct checks, common auto-fixes.
   - `SpatialValidator`: bounds, overlap, spacing, and positioning checks.
   - `VoiceoverScriptValidator`: narration structure and quality gates.
   - `RenderTester`: import/runtime smoke test when rendering locally.
   - Failed validation feeds back into regeneration.

7. **Render and store**
   - Local Manim subprocess rendering by default.
   - Optional Modal rendering through `RENDER_MODE=modal`.
   - Local video storage under `./media/videos` by default.
   - Optional Cloudflare R2 storage through `STORAGE_MODE=r2`.

## API Contract

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/process` | Start paper processing for `arxiv`, `doi`, or `pdf_url`. |
| `POST` | `/api/process/upload` | Start processing an uploaded PDF. |
| `GET` | `/api/status/{job_id}` | Poll paper processing progress. |
| `GET` | `/api/paper/{paper_id}` | Fetch processed paper, sections, and visualization metadata. |
| `GET` | `/api/papers` | List processed papers. |
| `GET` | `/api/video/{video_id}` | Serve local MP4 or redirect to cloud video URL. |
| `POST` | `/api/render` | Development endpoint to render raw Manim code. |
| `POST` | `/api/topic/graph` | Start topic graph generation. |
| `GET` | `/api/topic/graph/{job_id}` | Poll topic graph job and fetch nodes, edges, and video URL. |
| `GET` | `/api/health` | Check API, DB, rendering, storage, and Modal status. |

## Frontend Architecture

- Next.js App Router with React 19 and TypeScript.
- Tailwind CSS v4 for styling.
- Framer Motion for scroll, entrance, and card transitions.
- KaTeX via `react-markdown`, `remark-math`, and `rehype-katex`.
- API client in `frontend/lib/api.ts`.
- Demo data in `frontend/lib/mock-data.ts`.
- Reader route: `/abs/{paper_id}`.
- Topic graph route: `/topic`.

## Runtime Configuration

Backend environment is defined in `backend/.env.example`.

Required:

- `OPENAI_API_KEY`

Common optional settings:

- `OPENAI_MODEL`
- `OPENAI_REASONING_EFFORT`
- `RENDER_MODE=local|modal`
- `STORAGE_MODE=local|r2`
- `RENDER_CONCURRENCY`
- `RENDER_TIMEOUT_SECONDS`
- `MANIM_SUBPROCESS_TIMEOUT_SECONDS`
- `ARXIV_*` throttling and retry controls

Frontend environment:

- `NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000`.
- `NEXT_PUBLIC_USE_MOCK=true` enables mock API behavior.

## Deployment Shape

- Backend Dockerfile installs Manim system dependencies, FFmpeg, Cairo, Pango, TeX, Python deps, and runs Uvicorn.
- `docker-compose.yml` runs the backend on port `8000` with live source mounts.
- Frontend runs separately with `npm run dev` or a Next.js production deployment.
