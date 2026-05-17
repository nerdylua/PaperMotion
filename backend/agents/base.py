"""Base agent class with OpenAI Responses API support."""

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, use system env vars



DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

# Provider is intentionally fixed to OpenAI for production consistency.
_provider: str = "openai"

# Shared clients (reuse across agents to avoid re-init)
_openai_client: OpenAI | None = None
_openai_async_client: AsyncOpenAI | None = None


def _detect_provider() -> str:
    """Detect provider and enforce OpenAI-only configuration."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is required. This project is configured to use "
            "OpenAI-only LLM routing."
        )
    return "openai"


def get_provider() -> str:
    """Get the current provider name."""
    # Always validate env when requested so misconfigurations fail fast.
    _detect_provider()
    return _provider


def _client_kwargs() -> dict[str, Any]:
    """Build OpenAI client kwargs from env."""
    kwargs: dict[str, Any] = {
        "api_key": os.environ.get("OPENAI_API_KEY"),
        "timeout": 300.0,  # 5 min — large paper summarization needs headroom
    }
    base_url = os.environ.get("OPENAI_BASE_URL")
    if base_url:
        kwargs["base_url"] = base_url
    return kwargs


def _get_openai_client() -> OpenAI:
    """Get or create the shared synchronous OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(**_client_kwargs())
    return _openai_client


def _get_openai_async_client() -> AsyncOpenAI:
    """Get or create the shared asynchronous OpenAI client."""
    global _openai_async_client
    if _openai_async_client is None:
        _openai_async_client = AsyncOpenAI(**_client_kwargs())
    return _openai_async_client


def _build_reasoning(model: str) -> dict[str, str] | None:
    """Build optional reasoning settings from env for reasoning-capable models."""
    effort = os.environ.get("OPENAI_REASONING_EFFORT")
    if not effort:
        return None
    normalized = effort.strip().lower()
    if normalized not in {"none", "minimal", "low", "medium", "high", "xhigh"}:
        logger.warning("Ignoring invalid OPENAI_REASONING_EFFORT=%s", effort)
        return None

    model_name = model.lower()
    if model_name.startswith("gpt-5") or model_name.startswith("o"):
        return {"effort": normalized}
    return None


def _extract_output_text(response: Any) -> str:
    """Extract best-effort text output from a Responses API response."""
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text

    outputs = getattr(response, "output", []) or []
    chunks: list[str] = []
    for item in outputs:
        item_type = getattr(item, "type", None)
        if item_type != "message":
            continue
        content = getattr(item, "content", []) or []
        for block in content:
            if getattr(block, "type", None) == "output_text":
                value = getattr(block, "text", "")
                if value:
                    chunks.append(value)
    return "\n".join(chunks).strip()


def _get_client() -> OpenAI:
    """Compatibility shim for existing call sites that expect a sync client."""
    return _get_openai_client()


def get_model_name(model: str | None = None) -> str:
    """Get the model name (bare name, no provider prefix)."""
    return model or DEFAULT_MODEL


# ---------------------------------------------------------------------------
# Standalone LLM call helpers (usable outside BaseAgent, e.g. validators)
# ---------------------------------------------------------------------------

async def call_llm(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
    max_tokens: int = 4096,
) -> str:
    """Async LLM call routed through OpenAI Responses API."""
    get_provider()
    client = _get_openai_async_client()
    model_name = get_model_name(model)
    reasoning = _build_reasoning(model_name)
    input_words = len(prompt.split())
    logger.info(
        "[LLM] Calling %s (%s input words, max_tokens=%s)",
        model_name,
        input_words,
        max_tokens,
    )
    t0 = time.monotonic()
    try:
        params: dict[str, Any] = {
            "model": model_name,
            "input": prompt,
            "instructions": system_prompt,
            "max_output_tokens": max_tokens,
        }
        if reasoning:
            params["reasoning"] = reasoning
        result = await client.responses.create(**params)
        elapsed = time.monotonic() - t0
        output = _extract_output_text(result)
        output_words = len(output.split())
        logger.info(
            "[LLM] %s responded in %.1fs (%s output words)",
            model_name,
            elapsed,
            output_words,
        )
        return output
    except Exception as e:
        elapsed = time.monotonic() - t0
        logger.error(
            "[LLM] %s FAILED after %.1fs: %s: %s",
            model_name,
            elapsed,
            type(e).__name__,
            e,
        )
        raise


def call_llm_sync(
    prompt: str,
    model: str = DEFAULT_MODEL,
    system_prompt: str = "",
    max_tokens: int = 4096,
) -> str:
    """Synchronous LLM call routed through OpenAI Responses API."""
    get_provider()
    client = _get_openai_client()
    model_name = get_model_name(model)
    params: dict[str, Any] = {
        "model": model_name,
        "input": prompt,
        "instructions": system_prompt,
        "max_output_tokens": max_tokens,
    }
    reasoning = _build_reasoning(model_name)
    if reasoning:
        params["reasoning"] = reasoning
    result = client.responses.create(**params)
    return _extract_output_text(result)


class BaseAgent:
    """
    Base class for all AI agents in the pipeline.

    Uses OpenAI Responses API only (OPENAI_API_KEY).
    """

    def __init__(
        self,
        prompt_file: str,
        model: str | None = None,
        max_tokens: int = 4096,
    ):
        self._provider = get_provider()
        self.model = get_model_name(model)
        self.max_tokens = max_tokens
        self.system_prompt = self._load_system_prompt()
        self.prompt_template = self._load_prompt(prompt_file)

        # Keep self.client for any code that still references it directly
        self.client = _get_client()

        # Log active provider. Keep this ASCII-only for Windows consoles.
        print(f"OpenAI Responses API -> {self.model}")

    def _get_prompts_dir(self) -> Path:
        """Get the prompts directory path."""
        return Path(__file__).parent.parent / "prompts"

    def _load_system_prompt(self) -> str:
        """Load the curated Manim reference as system prompt."""
        path = self._get_prompts_dir() / "system" / "manim_reference.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def _load_prompt(self, filename: str) -> str:
        """Load a prompt template file."""
        path = self._get_prompts_dir() / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8")

    def _format_prompt(self, **kwargs: Any) -> str:
        """
        Format the prompt template with provided variables.

        Uses str.replace() instead of str.format() to avoid issues with
        content containing curly braces (like LaTeX's \\begin{pmatrix}).
        Also handles {{ and }} escape sequences like str.format() does.
        """
        result = self.prompt_template

        # Replace all placeholders first
        for key, value in kwargs.items():
            placeholder = "{" + key + "}"
            result = result.replace(placeholder, str(value))

        # Convert escaped braces ({{ -> {, }} -> }) like str.format() does
        result = result.replace("{{", "{").replace("}}", "}")

        return result

    def _parse_json_response(self, content: str) -> dict:
        """
        Extract and parse JSON from the response.

        Handles both raw JSON and JSON wrapped in markdown code blocks.
        """
        # Try to extract JSON from markdown code blocks
        json_patterns = [
            r"```json\s*([\s\S]*?)\s*```",  # ```json ... ```
            r"```\s*([\s\S]*?)\s*```",       # ``` ... ```
        ]

        for pattern in json_patterns:
            match = re.search(pattern, content)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    continue

        # Try parsing the whole content as JSON
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from response: {e}\nContent: {content[:500]}")

    def _extract_code_block(self, content: str, language: str = "python") -> str:
        """
        Extract code from a markdown code block.

        Args:
            content: Response content
            language: Language tag to look for

        Returns:
            Extracted code or empty string
        """
        # Try language-specific block first
        pattern = rf"```{language}\s*([\s\S]*?)\s*```"
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()

        # Try generic code block
        pattern = r"```\s*([\s\S]*?)\s*```"
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()

        # Return content as-is if no code blocks found
        return content.strip()

    # ------------------------------------------------------------------
    # LLM call helpers — route to the active provider
    # ------------------------------------------------------------------

    async def _call_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Call the LLM via the configured provider (async)."""
        return await call_llm(
            prompt=prompt,
            model=self.model,
            system_prompt=system_prompt or self.system_prompt,
            max_tokens=max_tokens or self.max_tokens,
        )

    def _call_llm_sync(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Call the LLM via the configured provider (sync)."""
        return call_llm_sync(
            prompt=prompt,
            model=self.model,
            system_prompt=system_prompt or self.system_prompt,
            max_tokens=max_tokens or self.max_tokens,
        )

    # ------------------------------------------------------------------
    # Default run methods
    # ------------------------------------------------------------------

    async def run(self, **kwargs: Any) -> dict:
        """
        Run the agent with the given parameters.

        This method should be overridden by subclasses for specific behavior.
        Default implementation formats the prompt and returns parsed JSON.
        """
        prompt = self._format_prompt(**kwargs)
        text = await self._call_llm(prompt)
        return self._parse_json_response(text)

    def run_sync(self, **kwargs: Any) -> dict:
        """Synchronous version of run() for testing."""
        prompt = self._format_prompt(**kwargs)
        text = self._call_llm_sync(prompt)
        return self._parse_json_response(text)
