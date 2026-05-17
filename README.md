<h1 align="center">PaperMotion</h1>
<p align="center">
   Transform research papers into visual stories using Manim animations
</p>

## How It Works

1. **Ingest**: Paste an arXiv ID/URL, DOI, direct PDF URL, or upload a PDF
2. **Analyze**: AI agents analyze each section to identify key concepts and visual opportunities
3. **Generate**: Multi-agent pipeline creates 3Blue1Brown-style Manim animations with optional voiceover
4. **Validate**: Quality gates check syntax, spatial layout, narration, and runtime import stability
5. **Experience**: Read through an interactive scrollytelling interface with embedded videos

PaperMotion also includes cached demos for `1706.03762`, `2005.14165`, and `2303.08774`, plus a topic graph mode that maps related arXiv papers with embeddings and Manim explainers.

The optional M2M2 (Math-To-Manim) planning layer is disabled by default to keep generation faster. Set `ENABLE_M2M2_LAYER=true` when you want an extra paper-grounded scene-spec pass for math-heavy visualizations.

## Quick Start

### Prerequisites

- Node.js 18+
- Python 3.11+
- FFmpeg, Cairo, Pango (for Manim)
- API key for OpenAI (`OPENAI_API_KEY`)

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Backend Setup

```bash
cd backend
cp .env.example .env          # Add your API keys
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Docker Compose runs the backend only:

```bash
docker compose up
```

## Inspiration

Research papers arrive as monoliths — dense, opaque, intimidating. Within them lies a mosaic of brilliant ideas waiting to be seen.

**PaperMotion** transforms fragments of academic text into animated visual explanations, making complex research accessible to everyone.