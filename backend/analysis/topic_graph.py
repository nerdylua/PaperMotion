"""Topic graph utilities for arXiv topic exploration."""

from __future__ import annotations

import logging
import math
import os
import re
import textwrap
from typing import Iterable

from openai import AsyncOpenAI

from ingestion.arxiv_fetcher import search_arxiv_papers
from models.generation import Scene, VisualizationPlan, VisualizationType
from models.paper import ArxivPaperMeta

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
MAX_ABSTRACT_SUMMARY_CHARS = 420
MAX_ABSTRACT_POINT_CHARS = 110


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
        summary, key_points = build_abstract_deep_dive(paper.abstract)
        nodes.append(
            {
                "id": paper.arxiv_id,
                "title": paper.title,
                "authors": paper.authors,
                "abstract": paper.abstract,
                "abstract_summary": summary,
                "abstract_key_points": key_points,
                "abstract_animation_url": None,
                "abstract_animation_error": None,
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


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", (text or "").strip())
    if not normalized:
        return []
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]


def build_abstract_deep_dive(abstract: str) -> tuple[str, list[str]]:
    """Create a compact text deep dive from an abstract."""
    sentences = _split_sentences(abstract)
    if not sentences:
        return "No abstract text was available for this paper.", []

    summary_parts: list[str] = []
    for sentence in sentences:
        candidate = " ".join(summary_parts + [sentence])
        if len(candidate) > MAX_ABSTRACT_SUMMARY_CHARS:
            break
        summary_parts.append(sentence)
        if len(summary_parts) >= 2:
            break
    summary = " ".join(summary_parts) or sentences[0]
    summary = _truncate(summary, MAX_ABSTRACT_SUMMARY_CHARS)

    key_points = [
        _truncate(sentence, MAX_ABSTRACT_POINT_CHARS)
        for sentence in sentences[:3]
    ]
    return summary, key_points


def _python_string(value: str) -> str:
    return repr(value)


def _wrap_for_screen(text: str, width: int, max_lines: int) -> list[str]:
    wrapped = textwrap.wrap(re.sub(r"\s+", " ", text).strip(), width=width)
    if len(wrapped) <= max_lines:
        return wrapped
    visible = wrapped[:max_lines]
    visible[-1] = _truncate(visible[-1], max(20, len(visible[-1]) - 3))
    return visible


def build_abstract_animation_code(node: dict) -> str:
    """Build a brief deterministic Manim animation for one paper abstract."""
    title = _truncate(node.get("title") or node.get("id") or "Paper", 82)
    authors = node.get("authors") or []
    author_line = ", ".join(authors[:3])
    if len(authors) > 3:
        author_line += " et al."
    if not author_line:
        author_line = "arXiv paper"

    summary = node.get("abstract_summary") or _truncate(node.get("abstract", ""), 360)
    summary_lines = _wrap_for_screen(summary, width=68, max_lines=5)
    key_points = node.get("abstract_key_points") or []
    point_lines = [
        _truncate(point, 92)
        for point in key_points[:3]
        if point
    ]

    summary_items = "\n".join(
        f"            {_python_string(line)},"
        for line in summary_lines
    )
    point_items = "\n".join(
        f"            {_python_string(f'{index}. {point}')},"
        for index, point in enumerate(point_lines, start=1)
    )

    if not summary_items:
        summary_items = "            'No abstract summary available.',"
    if not point_items:
        point_items = "            '1. Abstract details were unavailable.',"

    return f'''from manim import *


class PaperAbstractSnapshot(Scene):
    def construct(self):
        self.camera.background_color = "#080A0F"

        title = Text({_python_string(title)}, font_size=26, weight="BOLD", color=WHITE)
        title.to_edge(UP, buff=0.45)

        meta = Text({_python_string(author_line)}, font_size=15, color=GRAY_B)
        meta.next_to(title, DOWN, buff=0.18)

        label = Text("Abstract snapshot", font_size=18, color=GREEN_C)
        label.to_edge(LEFT, buff=0.75).shift(UP * 1.85)

        card = RoundedRectangle(
            width=12.0,
            height=3.25,
            corner_radius=0.18,
            stroke_color=GREEN_C,
            stroke_opacity=0.45,
            fill_color="#101820",
            fill_opacity=0.82,
        )
        card.shift(UP * 0.25)

        summary_lines = [
{summary_items}
        ]
        summary = VGroup(*[
            Text(line, font_size=18, color=WHITE)
            for line in summary_lines
        ]).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
        summary.move_to(card.get_center()).align_to(card, LEFT).shift(RIGHT * 0.45)

        points_title = Text("Key takeaways", font_size=18, color=BLUE_B)
        points_title.to_edge(LEFT, buff=0.75).shift(DOWN * 1.65)

        point_lines = [
{point_items}
        ]
        points = VGroup(*[
            Text(line, font_size=16, color=GRAY_A)
            for line in point_lines
        ]).arrange(DOWN, aligned_edge=LEFT, buff=0.16)
        points.next_to(points_title, DOWN, aligned_edge=LEFT, buff=0.25)

        pulse = Circle(radius=0.22, color=GREEN_C, fill_opacity=0.55)
        pulse.next_to(label, LEFT, buff=0.18)

        self.play(FadeIn(title, shift=DOWN * 0.2), FadeIn(meta), run_time=0.8)
        self.play(Create(card), FadeIn(label), GrowFromCenter(pulse), run_time=0.9)
        self.play(Write(summary), run_time=2.2)
        self.play(FadeIn(points_title, shift=RIGHT * 0.2), run_time=0.5)
        for point in points:
            self.play(FadeIn(point, shift=RIGHT * 0.18), run_time=0.45)
        self.play(Indicate(pulse, color=GREEN_C), run_time=0.7)
        self.wait(0.8)
'''


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
