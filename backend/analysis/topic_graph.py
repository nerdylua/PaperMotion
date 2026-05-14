"""Topic graph utilities for arXiv topic exploration."""

from __future__ import annotations

import logging
import math
import os
from typing import Iterable

from openai import AsyncOpenAI

from ingestion.arxiv_fetcher import search_arxiv_papers
from models.generation import Scene, VisualizationPlan, VisualizationType
from models.paper import ArxivPaperMeta

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")


def _client_kwargs() -> dict:
    kwargs: dict = {
        "api_key": os.environ.get("OPENAI_API_KEY"),
        "timeout": 120.0,
    }
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return kwargs


async def embed_texts(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Embed texts using OpenAI embeddings."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for embeddings")

    client = AsyncOpenAI(**_client_kwargs())
    model_name = model or DEFAULT_EMBEDDING_MODEL

    result = await client.embeddings.create(model=model_name, input=texts)
    return [item.embedding for item in result.data]


async def fetch_topic_papers(topic: str, max_results: int) -> list[ArxivPaperMeta]:
    """Fetch arXiv papers for a topic."""
    return await search_arxiv_papers(topic=topic, max_results=max_results)


def build_graph_nodes(papers: Iterable[ArxivPaperMeta]) -> list[dict]:
    """Build graph node payloads from paper metadata."""
    nodes: list[dict] = []
    for paper in papers:
        nodes.append(
            {
                "id": paper.arxiv_id,
                "title": paper.title,
                "authors": paper.authors,
                "abstract": paper.abstract,
                "pdf_url": paper.pdf_url,
                "categories": paper.categories,
                "published": paper.published.isoformat() if paper.published else None,
            }
        )
    return nodes


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b, strict=False):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / math.sqrt(norm_a * norm_b)


def build_similarity_edges(ids: list[str], embeddings: list[list[float]]) -> list[dict]:
    """Compute pairwise cosine similarities for a complete graph."""
    edges: list[dict] = []
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sim = _cosine_similarity(embeddings[i], embeddings[j])
            edges.append(
                {
                    "source": ids[i],
                    "target": ids[j],
                    "weight": round(sim, 4),
                    "label": f"sim {sim:.2f}",
                }
            )
    return edges


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def build_topic_graph_plan(
    topic: str,
    nodes: list[dict],
    edges: list[dict],
    mode: str,
) -> VisualizationPlan:
    """Create a deterministic plan for the topic graph visualization."""
    title = topic.strip() or "Topic"
    node_lines = [
        f"- {n['id']}: {_truncate(n['title'], 72)}" for n in nodes
    ]
    edge_lines = [
        f"- {e['source']} <-> {e['target']} ({e['label']})" for e in edges
    ]

    scenes = [
        Scene(
            order=1,
            description=(
                "Title card and legend. Show the topic title and explain that nodes are papers "
                "and edges are embedding similarity."
            ),
            duration_seconds=6,
            transitions="Write title, fade in legend",
            elements=["Text", "VGroup"],
        ),
        Scene(
            order=2,
            description=(
                "Lay out the paper nodes in a radial graph with connecting edges. "
                "Use short labels per node.\n" + "\n".join(node_lines)
            ),
            duration_seconds=12,
            transitions="GrowFromCenter nodes, Create edges",
            elements=["VGroup", "Circle", "Line", "Text"],
        ),
        Scene(
            order=3,
            description=(
                "Explain each paper briefly (3-4) and describe how it relates to the rest.\n"
                "Cover all nodes in order, then summarize the strongest connections.\n"
                + "\n".join(node_lines)
                + "\nKey edges:\n"
                + "\n".join(edge_lines[:5])
            ),
            duration_seconds=12,
            transitions="Indicate edges, highlight nodes",
            elements=["Line", "SurroundingRectangle", "Text"],
        ),
    ]

    if mode == "comparison":
        scenes.append(
            Scene(
                order=4,
                description=(
                    "Comparison recap: point out 2-3 contrastive nodes and summarize differences."
                ),
                duration_seconds=8,
                transitions="Fade focus between nodes",
                elements=["Text", "Arrow"],
            )
        )

    narration_points = [
        f"We searched arXiv for papers on {title}.",
        "Each node is a paper; each edge shows embedding similarity.",
        "We will briefly cover each paper, then connect them by the strongest similarities.",
    ]
    if mode == "comparison":
        narration_points.append(
            "We will compare the most similar cluster against a contrasting outlier."
        )
    else:
        narration_points.append(
            "We will explain how the strongest connections map the core theme."
        )

    return VisualizationPlan(
        concept_name=f"{title} paper map",
        visualization_type=VisualizationType.ARCHITECTURE,
        duration_seconds=30,
        scenes=scenes,
        narration_points=narration_points,
    )
