<h1 align="center">
  <a href="https://www.arxivisual.org/" target="_blank">arXivisual</a>
</h1>
<p align="center">
   Transform research papers into visual stories
</p>

## How It Works

1. **Ingest**: Paste an arXiv ID/URL, DOI, direct PDF URL, or upload a PDF
2. **Analyze**: AI agents analyze each section to identify key concepts and visual opportunities
3. **Generate**: Multi-agent pipeline creates 3Blue1Brown-style Manim animations with optional voiceover
4. **Validate**: Quality gates check syntax, spatial layout, narration, and runtime import stability
5. **Experience**: Read through an interactive scrollytelling interface with embedded videos

arXivisual also includes cached demos for `1706.03762`, `2005.14165`, and `2303.08774`, plus a topic graph mode that maps related arXiv papers with embeddings and Manim explainers.

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

**arXivisual** transforms fragments of academic text into animated visual explanations, making complex research accessible to everyone.