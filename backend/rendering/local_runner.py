"""
Local Manim rendering via subprocess.

Adapted from manim-mcp-server/src/manim_server.py
"""

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
MANIM_SUBPROCESS_TIMEOUT_SECONDS = int(os.getenv("MANIM_SUBPROCESS_TIMEOUT_SECONDS", "900"))


def get_manim_executable() -> str:
    """Get Manim executable path from environment or venv, with system fallback."""
    env_val = os.getenv("MANIM_EXECUTABLE")
    if env_val:
        return env_val
    # Prefer the manim binary from the same venv as the running Python
    import sys
    venv_manim = Path(sys.executable).parent / "manim"
    if venv_manim.exists():
        return str(venv_manim)
    return "manim"


def extract_scene_name(code: str) -> str:
    """
    Extract the Scene class name from Manim code.

    Looks for patterns like: class MyScene(Scene), class TestScene(ThreeDScene), etc.
    """
    # Match class definitions that inherit from Scene or any *Scene class
    pattern = r'class\s+(\w+)\s*\(\s*\w*Scene\s*\)'
    match = re.search(pattern, code)
    if match:
        return match.group(1)
    return "MainScene"  # Fallback


def _build_render_env() -> dict[str, str]:
    """
    Build subprocess env for Manim rendering.

    Ensures TeX tools (latex/dvisvgm) are discoverable for MathTex on Windows,
    even when a fresh shell hasn't picked up installer PATH changes yet.
    """
    env = dict(os.environ)
    path_key = "Path" if "Path" in env else "PATH"
    current_path = env.get(path_key, env.get("PATH", ""))
    path_parts = [p for p in current_path.split(os.pathsep) if p]
    normalized = {str(Path(p)).lower() for p in path_parts}

    candidates: list[str] = []
    custom_miktex = os.getenv("MIKTEX_BIN_DIR")
    if custom_miktex:
        candidates.append(custom_miktex)

    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        candidates.append(
            str(Path(local_appdata) / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64")
        )

    program_files = os.getenv("ProgramFiles")
    if program_files:
        candidates.append(
            str(Path(program_files) / "MiKTeX" / "miktex" / "bin" / "x64")
        )

    prepend: list[str] = []
    for candidate in candidates:
        candidate_path = Path(candidate)
        if candidate_path.exists():
            key = str(candidate_path).lower()
            if key not in normalized:
                prepend.append(str(candidate_path))
                normalized.add(key)

    if prepend:
        env[path_key] = os.pathsep.join(prepend + path_parts)
        # Avoid duplicate PATH/Path keys with conflicting values on Windows.
        if path_key == "Path" and "PATH" in env:
            del env["PATH"]
        elif path_key == "PATH" and "Path" in env:
            del env["Path"]
        logger.info("  [Renderer] Added TeX tool paths: %s", "; ".join(prepend))

    return env


def _run_manim_subprocess(
    code: str,
    scene_name: str,
    quality: str,
    label: str = "",
) -> bytes:
    """Run a single Manim render subprocess and return video bytes."""
    manim_executable = get_manim_executable()
    tag = f"  [Renderer{label}]"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        code_path = tmpdir_path / "scene.py"
        logger.info(f"{tag} Writing Manim code to {code_path.name}")
        code_path.write_text(code, encoding="utf-8")

        output_dir = tmpdir_path / "media"
        quality_flags = {
            "low_quality": "-ql",
            "medium_quality": "-qm",
            "high_quality": "-qh",
        }
        quality_flag = quality_flags.get(quality, "-ql")
        logger.info(f"{tag} Rendering quality: {quality} ({quality_flag})")

        cmd = [
            manim_executable,
            "render",
            str(code_path),
            scene_name,
            quality_flag,
            "--format=mp4",
            f"--media_dir={output_dir}",
        ]

        logger.info(f"{tag} Starting Manim render for scene: {scene_name}")
        logger.debug(f"{tag} Command: {' '.join(cmd)}")

        try:
            render_env = _build_render_env()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=MANIM_SUBPROCESS_TIMEOUT_SECONDS,
                cwd=tmpdir,
                env=render_env,
            )
            if result.stdout:
                logger.debug(f"{tag} Manim stdout:\n{result.stdout}")
            if result.stderr:
                logger.debug(f"{tag} Manim stderr:\n{result.stderr}")
        except subprocess.TimeoutExpired:
            logger.error(
                "%s Rendering timeout after %s seconds for %s",
                tag,
                MANIM_SUBPROCESS_TIMEOUT_SECONDS,
                scene_name,
            )
            raise RuntimeError(
                "Manim render timed out after "
                f"{MANIM_SUBPROCESS_TIMEOUT_SECONDS} seconds for scene {scene_name}"
            )

        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "Unknown error"
            logger.error(f"{tag} Manim render failed with return code {result.returncode}")
            logger.error(f"{tag} Error: {error_msg}")
            raise RuntimeError(f"Manim render failed: {error_msg}")

        logger.info(f"{tag} Manim render completed successfully")

        video_files = list(output_dir.rglob("*.mp4"))
        if not video_files:
            logger.error(f"{tag} No MP4 files found in {output_dir}")
            raise RuntimeError(
                f"No video file produced. Manim output:\n{result.stdout}\n{result.stderr}"
            )

        video_file = video_files[0]
        file_size = video_file.stat().st_size
        logger.info(f"{tag} Found video: {video_file.name} ({file_size:,} bytes)")
        video_bytes = video_file.read_bytes()
        logger.info(f"{tag} Successfully read video file ({len(video_bytes):,} bytes)")
        return video_bytes


def _render_manim_sync(
    code: str,
    scene_name: str,
    quality: str = "low_quality"
) -> bytes:
    """
    Synchronous Manim rendering.

    Args:
        code: Complete Manim Python code
        scene_name: Name of the Scene class to render
        quality: "low_quality", "medium_quality", or "high_quality"

    Returns:
        MP4 video file as bytes

    Raises:
        RuntimeError: If rendering fails
    """
    return _run_manim_subprocess(code, scene_name, quality)


async def render_manim_local(
    code: str,
    scene_name: Optional[str] = None,
    quality: str = "low_quality"
) -> bytes:
    """
    Async wrapper for local Manim rendering.

    Runs the synchronous subprocess in a thread pool to avoid blocking.

    Args:
        code: Complete Manim Python code
        scene_name: Name of the Scene class to render (auto-detected if None)
        quality: "low_quality", "medium_quality", or "high_quality"

    Returns:
        MP4 video file as bytes
    """
    if scene_name is None:
        logger.info("  [Renderer] Extracting scene name from code")
        scene_name = extract_scene_name(code)
        logger.info(f"  [Renderer] Detected scene name: {scene_name}")

    logger.info(f"[Rendering] Starting async render for {scene_name}")

    # Run in thread pool to not block async event loop
    return await asyncio.to_thread(
        _render_manim_sync,
        code,
        scene_name,
        quality
    )


# Test code for manual verification
TEST_MANIM_CODE = '''
from manim import *

class TestScene(Scene):
    def construct(self):
        circle = Circle(color=BLUE)
        square = Square(color=RED).shift(RIGHT * 2)
        self.play(Create(circle))
        self.play(Transform(circle, square))
        self.wait()
'''

if __name__ == "__main__":
    # Quick test
    import sys

    print(f"Using Manim executable: {get_manim_executable()}")
    print(f"Extracted scene name: {extract_scene_name(TEST_MANIM_CODE)}")

    try:
        print("Rendering test scene...")
        video_bytes = _render_manim_sync(TEST_MANIM_CODE, "TestScene", "low_quality")

        # Save to file
        output_path = Path("test_output.mp4")
        output_path.write_bytes(video_bytes)
        print(f"Success! Video saved to {output_path} ({len(video_bytes)} bytes)")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
