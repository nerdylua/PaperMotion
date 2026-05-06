"""
Context7 documentation fetcher via OpenAI Responses API + MCP.

Primary strategy:
1) OpenAI Responses API with a remote MCP tool connection to Context7.
2) Direct Context7 REST API fallback.
3) Static manim_reference.md fallback (handled by caller).
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

import httpx
from openai import AsyncOpenAI

try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_CONTEXT7_MODEL = os.environ.get("OPENAI_CONTEXT7_MODEL", "gpt-5.4-mini")
CONTEXT7_MCP_SERVER_URL = os.environ.get(
    "CONTEXT7_MCP_SERVER_URL",
    "https://mcp.context7.com/mcp",
)

# Context7 REST API (direct fallback)
CONTEXT7_API_BASE = "https://context7.com/api/v2"

# Manim library identifier on Context7
MANIM_LIBRARY_NAME = "manim community"

# Cache for fetched docs to avoid redundant API calls within a pipeline run
_docs_cache: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Local utility tools (kept for local validation convenience)
# ---------------------------------------------------------------------------
def validate_manim_imports(code: str) -> str:
    """Validate that Manim code has correct imports and no disallowed modules."""
    issues: list[str] = []

    if "from manim import" not in code and "import manim" not in code:
        issues.append("Missing manim import: add 'from manim import *'")

    dangerous = ["os.system", "subprocess", "shutil.rmtree", "eval(", "exec("]
    for pattern in dangerous:
        if pattern in code:
            issues.append(f"Disallowed pattern found: {pattern}")

    try:
        ast.parse(code)
    except SyntaxError as exc:
        issues.append(f"Syntax error at line {exc.lineno}: {exc.msg}")

    return json.dumps({"valid": len(issues) == 0, "issues": issues})


def check_spatial_bounds(code: str) -> str:
    """Check whether obvious hardcoded positions are outside default Manim bounds."""
    warnings: list[str] = []
    max_x, max_y = 7.1, 4.0

    xy_patterns = [
        (r"\.move_to\(\s*\[?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)", "move_to"),
        (r"Dot\(\s*\[?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)", "Dot position"),
    ]

    for pattern, label in xy_patterns:
        for match in re.finditer(pattern, code):
            try:
                x, y = float(match.group(1)), float(match.group(2))
            except ValueError:
                continue
            if abs(x) > max_x:
                warnings.append(f"{label}: x={x} exceeds frame width ({max_x})")
            if abs(y) > max_y:
                warnings.append(f"{label}: y={y} exceeds frame height ({max_y})")

    shift_pattern = r"\.shift\(\s*(RIGHT|LEFT|UP|DOWN)\s*\*\s*(-?[\d.]+)"
    for match in re.finditer(shift_pattern, code):
        direction, value_str = match.groups()
        try:
            value = float(value_str)
        except ValueError:
            continue
        if direction in ("RIGHT", "LEFT") and abs(value) > max_x:
            warnings.append(f"shift: {direction}*{value} exceeds frame width ({max_x})")
        if direction in ("UP", "DOWN") and abs(value) > max_y:
            warnings.append(f"shift: {direction}*{value} exceeds frame height ({max_y})")

    return json.dumps({"in_bounds": len(warnings) == 0, "warnings": warnings})


def extract_scene_metadata(code: str) -> str:
    """Extract lightweight scene metadata from Manim code."""
    class_match = re.search(
        r"class\s+(\w+)\s*\(\s*(Scene|ThreeDScene|VoiceoverScene)\s*\)",
        code,
    )
    class_name = class_match.group(1) if class_match else "Unknown"
    base_class = class_match.group(2) if class_match else "Unknown"

    animation_count = len(re.findall(r"self\.play\(|self\.wait\(|self\.add\(", code))
    voiceover_blocks = len(re.findall(r"with\s+self\.voiceover\s*\(", code))
    has_construct = "def construct(self)" in code

    return json.dumps(
        {
            "class_name": class_name,
            "base_class": base_class,
            "animation_count": animation_count,
            "voiceover_blocks": voiceover_blocks,
            "has_construct": has_construct,
        }
    )


def _extract_output_text(response: object) -> str:
    """Extract response text robustly from a Responses API object."""
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text

    output_items = getattr(response, "output", []) or []
    chunks: list[str] = []
    for item in output_items:
        if getattr(item, "type", None) != "message":
            continue
        for block in getattr(item, "content", []) or []:
            if getattr(block, "type", None) == "output_text":
                value = getattr(block, "text", "")
                if value:
                    chunks.append(value)
    return "\n".join(chunks).strip()


# ---------------------------------------------------------------------------
# OpenAI + remote MCP integration
# ---------------------------------------------------------------------------
async def fetch_manim_docs_via_openai_mcp(
    query: str = "animations mobjects Scene ThreeDScene",
    max_tokens: int = 5000,
) -> str:
    """Fetch live Manim docs through OpenAI Responses + remote MCP Context7."""
    cache_key = f"openai_mcp:manim:{query}:{max_tokens}"
    if cache_key in _docs_cache:
        logger.info("Context7 docs cache hit for query: %s", query)
        return _docs_cache[cache_key]

    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not configured; skipping MCP docs fetch")
        return ""

    logger.info("=" * 50)
    logger.info("OPENAI RESPONSES + CONTEXT7 MCP: Fetching live Manim docs")
    logger.info("  Query: %s", query)
    logger.info("  Max tokens: %s", max_tokens)

    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=120.0)
        response = await client.responses.create(
            model=OPENAI_CONTEXT7_MODEL,
            tools=[
                {
                    "type": "mcp",
                    "server_label": "context7",
                    "server_url": CONTEXT7_MCP_SERVER_URL,
                    "require_approval": "never",
                }
            ],
            instructions=(
                "You are a documentation retrieval assistant. "
                "Use the MCP tools from the connected Context7 server to fetch "
                "current Manim Community Edition documentation. "
                "Return only useful documentation content and API references."
            ),
            input=(
                "Fetch the latest Manim Community Edition documentation about: "
                f"{query}. Prioritize authoritative API usage details and examples."
            ),
            max_output_tokens=max_tokens,
        )
        docs = _extract_output_text(response)
        if docs and len(docs) > 100:
            logger.info(
                "  Fetched %d chars of live Manim docs via OpenAI MCP",
                len(docs),
            )
            _docs_cache[cache_key] = docs
            return docs

        logger.warning("  OpenAI MCP docs response was short/empty, falling back")
        return ""
    except Exception as exc:
        logger.error("  OpenAI MCP + Context7 failed: %s", exc)
        logger.info("  Falling back to direct Context7 API")
        return ""


async def fetch_manim_docs_via_openai_mcp_with_tools(
    query: str = "animations mobjects Scene ThreeDScene",
    max_tokens: int = 5000,
    manim_code: str = "",
) -> str:
    """
    Fetch docs via OpenAI MCP and optionally append local validation summaries.

    This preserves the old function shape while avoiding SDK-specific tool wiring.
    """
    docs = await fetch_manim_docs_via_openai_mcp(query=query, max_tokens=max_tokens)
    if not docs:
        return ""

    if not manim_code:
        return docs

    validations = {
        "validate_manim_imports": json.loads(validate_manim_imports(manim_code)),
        "check_spatial_bounds": json.loads(check_spatial_bounds(manim_code)),
        "extract_scene_metadata": json.loads(extract_scene_metadata(manim_code)),
    }
    return docs + "\n\n# Local Validation Summary\n" + json.dumps(validations, indent=2)


# ---------------------------------------------------------------------------
# Direct Context7 REST API fallback
# ---------------------------------------------------------------------------
async def _resolve_library_id(library_name: str) -> Optional[str]:
    """Resolve a library name to a Context7 library ID."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{CONTEXT7_API_BASE}/search",
                params={"query": library_name},
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get("results", []) if isinstance(data, dict) else data
            if not isinstance(results, list) or not results:
                logger.warning("Context7: No library found for '%s'", library_name)
                return None

            for item in results:
                library_id = item.get("id", "")
                if "community" in library_id.lower() or "stable" in library_id.lower():
                    logger.info(
                        "Context7: Resolved '%s' -> %s (%s, %d tokens)",
                        library_name,
                        library_id,
                        item.get("title"),
                        item.get("totalTokens", 0),
                    )
                    return library_id
            library_id = results[0].get("id", "")
            logger.info("Context7: Resolved '%s' -> %s", library_name, library_id)
            return library_id
    except Exception as exc:
        logger.error("Context7 resolve-library-id failed: %s", exc)
        return None


async def _get_library_docs(
    library_id: str,
    query: str = "animations mobjects scenes",
    max_tokens: int = 5000,
) -> Optional[str]:
    """Fetch documentation for a library from Context7."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{CONTEXT7_API_BASE}/context",
                params={
                    "libraryId": library_id,
                    "query": query,
                    "tokens": str(max_tokens),
                },
            )
            resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text/plain" in content_type:
                return resp.text

            try:
                data = resp.json()
            except Exception:
                return resp.text

            if isinstance(data, dict):
                return data.get("context") or data.get("content") or json.dumps(data, indent=2)
            return str(data)
    except Exception as exc:
        logger.error("Context7 get-library-docs failed: %s", exc)
        return None


async def fetch_manim_docs_direct(
    query: str = "animations mobjects Scene ThreeDScene",
    max_tokens: int = 5000,
) -> str:
    """Direct Context7 API fallback (no MCP / no OpenAI dependency)."""
    cache_key = f"direct:manim:{query}:{max_tokens}"
    if cache_key in _docs_cache:
        return _docs_cache[cache_key]

    logger.info("Context7 direct: Fetching docs for query '%s'", query)
    library_id = await _resolve_library_id(MANIM_LIBRARY_NAME)
    if not library_id:
        return ""

    docs = await _get_library_docs(library_id, query, max_tokens)
    if docs:
        logger.info("Context7 direct: Fetched %d chars", len(docs))
        _docs_cache[cache_key] = docs
        return docs
    return ""


# ---------------------------------------------------------------------------
# Main entry point with fallback chain
# ---------------------------------------------------------------------------
async def get_manim_docs(
    topic: str = "animations mobjects Scene ThreeDScene MathTex",
    max_tokens: int = 5000,
    use_openai: bool = True,
    use_dedalus: Optional[bool] = None,
) -> str:
    """
    Main entry point to fetch live Manim documentation.

    Fallback chain:
    1) OpenAI Responses + remote MCP Context7
    2) Direct Context7 REST API
    3) Static manim_reference.md

    `use_dedalus` is retained only as a backwards-compatibility alias.
    """
    if use_dedalus is not None:
        use_openai = use_dedalus

    docs = ""
    if use_openai and OPENAI_API_KEY:
        docs = await fetch_manim_docs_via_openai_mcp(topic, max_tokens)

    if not docs:
        docs = await fetch_manim_docs_direct(topic, max_tokens)

    if not docs:
        logger.info("All live doc sources failed, using static manim_reference.md")
        static_path = Path(__file__).parent.parent / "prompts" / "system" / "manim_reference.md"
        if static_path.exists():
            docs = static_path.read_text(encoding="utf-8")

    return docs


def clear_docs_cache() -> None:
    """Clear the in-memory documentation cache."""
    _docs_cache.clear()
