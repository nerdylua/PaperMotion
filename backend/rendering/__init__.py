"""
Rendering package for PaperMotion.

Uses local Manim subprocess rendering only.
"""

import logging
from .local_runner import render_manim_local, extract_scene_name
from .storage import save_video, get_video_path, get_video_url, list_videos, get_backend

logger = logging.getLogger(__name__)

__all__ = [
    "render_manim_local",
    "extract_scene_name",
    "save_video",
    "get_video_path",
    "get_video_url",
    "list_videos",
    "process_visualization",
    "render_manim",
    "get_backend",
]


async def render_manim(code: str, scene_name: str, quality: str = "low_quality") -> bytes:
    """
    Render Manim code using local Manim.

    Args:
        code: Complete Manim Python code
        scene_name: Name of the Scene class to render
        quality: Rendering quality ("low_quality", "medium_quality", "high_quality")

    Returns:
        MP4 video file as bytes
    """
    return await render_manim_local(code, scene_name, quality)


async def process_visualization(viz_id: str, manim_code: str, quality: str = "low_quality") -> str:
    """
    Process a visualization: render Manim code and save the video.

    Args:
        viz_id: Unique identifier for this visualization
        manim_code: Complete Manim Python code
        quality: Rendering quality ("low_quality", "medium_quality", "high_quality")

    Returns:
        URL path to the rendered video (e.g., "/api/video/viz_001")

    Raises:
        RuntimeError: If rendering fails
    """
    logger.info(f"[Processing Visualization] {viz_id}")
    logger.info(f"[Processing Visualization] Quality setting: {quality}")

    # Extract scene name from code
    scene_name = extract_scene_name(manim_code)
    logger.info(f"[Processing Visualization] Scene name: {scene_name}")

    # Render the video using configured backend
    logger.info(f"[Processing Visualization] Starting rendering phase...")
    video_bytes = await render_manim(manim_code, scene_name, quality)
    logger.info(f"[Processing Visualization] Rendering complete ({len(video_bytes):,} bytes)")

    # Save to storage
    logger.info(f"[Processing Visualization] Saving to storage...")
    video_url = await save_video(video_bytes, f"{viz_id}.mp4")
    logger.info(f"[Processing Visualization] Video saved successfully")
    logger.info(f"[Processing Visualization] Video URL: {video_url}")

    return video_url
