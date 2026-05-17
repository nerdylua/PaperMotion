"""Background job for topic graph generation."""

from __future__ import annotations

import logging

from agents.code_validator import CodeValidator
from agents.manim_generator import ManimGenerator
from analysis.topic_graph import (
    build_abstract_animation_code,
    build_graph_nodes,
    build_similarity_edges,
    build_topic_graph_plan,
    embed_texts,
    fetch_topic_papers,
)
from db.connection import async_session_maker
from db import queries
from rendering import process_visualization

logger = logging.getLogger(__name__)


async def _render_abstract_animation(
    node: dict,
    job_id: str,
    validator: CodeValidator,
) -> None:
    """Render one brief abstract-based animation and attach the result to the node."""
    try:
        code = build_abstract_animation_code(node)
        validation = validator.validate(code)
        if not validation.is_valid:
            raise ValueError("Generated abstract animation code failed validation")

        safe_node_id = "".join(
            char if char.isalnum() else "_"
            for char in str(node.get("id", "paper"))
        )
        video_url = await process_visualization(
            viz_id=f"topicpaper_{job_id}_{safe_node_id}",
            manim_code=validation.code,
            quality="low_quality",
        )
        node["abstract_animation_url"] = video_url
        node["abstract_animation_error"] = None
    except Exception as exc:
        logger.warning(
            "Abstract animation failed for topic job %s paper %s: %s",
            job_id,
            node.get("id"),
            exc,
        )
        node["abstract_animation_url"] = None
        node["abstract_animation_error"] = str(exc)


async def process_topic_graph_job(job_id: str, topic: str, max_results: int, mode: str) -> None:
    async with async_session_maker() as db:
        try:
            await queries.update_topic_graph_job_status(
                db,
                job_id,
                status="processing",
                progress=0.05,
                current_step="Searching arXiv",
            )
            papers = await fetch_topic_papers(topic=topic, max_results=max_results)
            if not papers:
                raise ValueError("No papers found for this topic")

            await queries.update_topic_graph_job_status(
                db,
                job_id,
                progress=0.2,
                current_step="Embedding papers",
            )
            texts = [f"{p.title}\n{p.abstract}" for p in papers]
            embeddings = await embed_texts(texts)

            await queries.update_topic_graph_job_status(
                db,
                job_id,
                progress=0.4,
                current_step="Building similarity graph",
            )
            nodes = build_graph_nodes(papers)
            ids = [n["id"] for n in nodes]
            edges = build_similarity_edges(ids, embeddings)

            await queries.update_topic_graph_job_status(
                db,
                job_id,
                progress=0.55,
                current_step="Planning visualization",
            )
            plan = build_topic_graph_plan(topic=topic, nodes=nodes, edges=edges, mode=mode)

            await queries.update_topic_graph_job_status(
                db,
                job_id,
                progress=0.7,
                current_step="Generating Manim code",
            )
            generator = ManimGenerator()
            generated = await generator.run(plan=plan)

            validator = CodeValidator()
            validation = validator.validate(generated.code)
            if not validation.is_valid:
                raise ValueError("Generated code failed validation")

            await queries.update_topic_graph_job_status(
                db,
                job_id,
                progress=0.85,
                current_step="Rendering video",
            )
            viz_id = f"topicviz_{job_id}"
            video_url = await process_visualization(
                viz_id=viz_id,
                manim_code=validation.code,
                quality="low_quality",
            )

            await queries.update_topic_graph_job_status(
                db,
                job_id,
                progress=0.92,
                current_step="Rendering paper snapshots",
            )
            for index, node in enumerate(nodes, start=1):
                await queries.update_topic_graph_job_status(
                    db,
                    job_id,
                    progress=0.92 + (0.06 * ((index - 1) / max(1, len(nodes)))),
                    current_step=f"Rendering paper snapshot {index}/{len(nodes)}",
                )
                await _render_abstract_animation(node, job_id, validator)

            await queries.store_topic_graph_result(
                db,
                job_id,
                nodes=nodes,
                edges=edges,
                video_url=video_url,
            )

            await queries.update_topic_graph_job_status(
                db,
                job_id,
                status="completed",
                progress=1.0,
                current_step="Complete",
            )
        except Exception as exc:
            logger.exception("Topic graph job failed")
            await queries.update_topic_graph_job_status(
                db,
                job_id,
                status="failed",
                progress=1.0,
                current_step="Failed",
                error=str(exc),
            )
