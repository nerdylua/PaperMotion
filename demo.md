# arXivisual Demo

This demo shows the fastest reliable path first, then the full backend pipeline.

## Prerequisites

- Node.js 18+
- Python 3.11+
- `uv`
- FFmpeg, Cairo, Pango, and TeX/LaTeX for local Manim rendering
- `OPENAI_API_KEY`

For Docker backend runs, system dependencies are installed by `backend/Dockerfile`.

## Start Locally

### Backend

```bash
cd backend
cp .env.example .env
# edit .env and set OPENAI_API_KEY
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Expected: JSON with `database`, `manim`, `storage`, `modal`, and overall `status`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## Demo 1: Cached Paper Reader

Use this for a fast no-backend demo.

1. Open `http://localhost:3000`.
2. Click or enter `1706.03762`.
3. Wait for the short simulated processing state.
4. Scroll through the reader.

What to show:

- Search/input mode for arXiv papers.
- Animated processing state.
- Paper title, authors, abstract.
- Scroll-driven card-stack reading.
- Embedded Manim videos for key sections.
- PDF and arXiv source links.

Other cached demos:

- `2005.14165` - GPT-3 few-shot learning.
- `2303.08774` - GPT-4 technical report.

Direct URLs:

```text
http://localhost:3000/abs/1706.03762
http://localhost:3000/abs/2005.14165
http://localhost:3000/abs/2303.08774
```

## Demo 2: Full Paper Processing

Use this when the backend, OpenAI key, and Manim dependencies are ready.

Start a job:

```bash
curl -X POST http://localhost:8000/api/process ^
  -H "Content-Type: application/json" ^
  -d "{\"source_type\":\"arxiv\",\"arxiv_id\":\"1706.03762\"}"
```

Response shape:

```json
{
  "job_id": "...",
  "paper_id": "1706.03762",
  "source_type": "arxiv",
  "status": "queued",
  "message": "Processing started. Poll /api/status/{job_id} for updates."
}
```

Poll:

```bash
curl http://localhost:8000/api/status/JOB_ID
```

Expected progress steps:

- `Fetching paper source`
- `Parsing sections and content`
- `Analyzing concepts for visualization`
- `Generating animations`
- `Rendering videos`
- `Complete`

Fetch result:

```bash
curl http://localhost:8000/api/paper/1706.03762
```

Open in UI:

```text
http://localhost:3000/abs/1706.03762?jobId=JOB_ID
```

## Demo 3: DOI, PDF URL, and Upload

DOI:

```bash
curl -X POST http://localhost:8000/api/process ^
  -H "Content-Type: application/json" ^
  -d "{\"source_type\":\"doi\",\"doi\":\"10.1145/3366423.3380224\"}"
```

Direct PDF URL:

```bash
curl -X POST http://localhost:8000/api/process ^
  -H "Content-Type: application/json" ^
  -d "{\"source_type\":\"pdf_url\",\"pdf_url\":\"https://example.org/paper.pdf\"}"
```

PDF upload:

```bash
curl -X POST http://localhost:8000/api/process/upload ^
  -F "file=@paper.pdf" ^
  -F "title=Uploaded Paper"
```

The frontend exposes the same modes from the home page: `arXiv`, `DOI`, `PDF URL`, and `Upload PDF`.

## Demo 4: Topic Graph

UI path:

```text
http://localhost:3000/topic
```

Flow:

1. Enter a topic, for example `retrieval augmented generation`.
2. Choose `Max papers` from 1 to 5.
3. Choose `Explanation` or `Comparison`.
4. Click `Generate`.
5. Wait for arXiv search, embeddings, graph construction, Manim generation, and rendering.

API equivalent:

```bash
curl -X POST http://localhost:8000/api/topic/graph ^
  -H "Content-Type: application/json" ^
  -d "{\"topic\":\"retrieval augmented generation\",\"max_results\":5,\"mode\":\"explanation\"}"
```

Poll:

```bash
curl http://localhost:8000/api/topic/graph/JOB_ID
```

Expected result fields:

- `nodes`: arXiv papers with title, authors, abstract summary, key points, categories, and optional abstract animation URL.
- `edges`: pairwise embedding similarity scores.
- `video_url`: rendered Manim topic explainer.

## Demo 5: Raw Manim Render Endpoint

Use `/api/render` to verify rendering independently of the LLM pipeline.

```bash
curl -X POST http://localhost:8000/api/render ^
  -H "Content-Type: application/json" ^
  -d "{\"quality\":\"low_quality\",\"code\":\"from manim import *\\n\\nclass TestScene(Scene):\\n    def construct(self):\\n        circle = Circle(color=BLUE)\\n        self.play(Create(circle))\\n        self.wait()\"}"
```

Expected:

```json
{
  "video_id": "test_...",
  "video_url": "/api/video/test_...",
  "scene_name": "TestScene",
  "message": "Successfully rendered TestScene"
}
```

Open the video:

```text
http://localhost:8000/api/video/test_...
```

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Frontend cannot reach backend | Set `NEXT_PUBLIC_API_URL=http://localhost:8000`. |
| `/api/health` is degraded | Inspect `database`, `manim`, `storage`, and `modal` fields. |
| Manim render fails | Verify FFmpeg, Cairo, Pango, and TeX are installed or use Docker/Modal. |
| arXiv search is rate-limited | Tune `ARXIV_*` throttling variables. |
| No videos appear after processing | Check visualization statuses from `/api/paper/{paper_id}` and backend logs. |
| Topic graph fails at embeddings | Ensure `OPENAI_API_KEY` is set and valid. |

## Demo Narrative

One-sentence pitch:

> arXivisual converts dense papers into structured explanations with generated Manim animations embedded directly into a scrollytelling reader.

Technical walkthrough:

1. Input a paper source.
2. Backend ingests and structures the paper.
3. Agents identify visual concepts and plan scenes.
4. Manim code is generated, validated, rendered, and stored.
5. Frontend reads the processed paper contract and presents section-level videos inline.
6. Topic Graph generalizes the same rendering stack from one paper to a connected paper landscape.
