"""Legacy compatibility wrappers for model-chain agents.

This file keeps the historical `DedalusBaseAgent` API surface intact, while the
implementation now uses OpenAI Responses API through `agents.base`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

try:
    from .base import call_llm, get_model_name
except ImportError:
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agents.base import call_llm, get_model_name

TaskType = Literal["research", "code", "creative", "analysis", "multi_step"]

# Lightweight model chains; users can override with `custom_models`.
MODEL_CHAINS: dict[TaskType, list[str]] = {
    "research": ["gpt-5.4-mini", "gpt-5.4"],
    "code": ["gpt-5.4-mini", "gpt-5.4"],
    "creative": ["gpt-5.4"],
    "analysis": ["gpt-5.4-mini", "gpt-5.4"],
    "multi_step": ["gpt-5.4-mini", "gpt-5.4"],
}


class DedalusBaseAgent:
    """
    Backward-compatible chain agent.

    The name is retained for compatibility with existing imports, but all calls
    are now routed through OpenAI.
    """

    def __init__(
        self,
        prompt_file: str,
        task_type: TaskType = "research",
        custom_models: list[str] | None = None,
        max_tokens: int = 4096,
        mcp_servers: list[str] | None = None,
    ):
        self.task_type = task_type
        self.max_tokens = max_tokens
        self.mcp_servers = mcp_servers or []  # Kept for compatibility
        self.models = custom_models or MODEL_CHAINS.get(task_type, MODEL_CHAINS["research"])

        self.system_prompt = self._load_system_prompt()
        self.prompt_template = self._load_prompt(prompt_file)

        print(f"🔄 Model chain ({task_type}): {' -> '.join(self.models)}")

    def _get_prompts_dir(self) -> Path:
        return Path(__file__).parent.parent / "prompts"

    def _load_system_prompt(self) -> str:
        path = self._get_prompts_dir() / "system" / "manim_reference.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _load_prompt(self, filename: str) -> str:
        path = self._get_prompts_dir() / filename
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8")

    def _format_prompt(self, **kwargs: Any) -> str:
        result = self.prompt_template
        for key, value in kwargs.items():
            result = result.replace("{" + key + "}", str(value))
        return result.replace("{{", "{").replace("}}", "}")

    def _parse_json_response(self, content: str) -> dict:
        for pattern in (r"```json\s*([\s\S]*?)\s*```", r"```\s*([\s\S]*?)\s*```"):
            match = re.search(pattern, content)
            if not match:
                continue
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        return json.loads(content.strip())

    def _extract_code_block(self, content: str, language: str = "python") -> str:
        pattern = rf"```{language}\s*([\s\S]*?)\s*```"
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()
        match = re.search(r"```\s*([\s\S]*?)\s*```", content)
        if match:
            return match.group(1).strip()
        return content.strip()

    async def _run_chain(self, prompt: str) -> str:
        """
        Run a simple sequential model chain.

        Each model receives the previous model's output as input (except step 1).
        """
        current = prompt
        for idx, model in enumerate(self.models):
            if idx == 0:
                model_prompt = current
            else:
                model_prompt = (
                    "Refine and improve the following draft while preserving correctness.\n\n"
                    f"{current}"
                )
            current = await call_llm(
                prompt=model_prompt,
                model=get_model_name(model),
                system_prompt=self.system_prompt,
                max_tokens=self.max_tokens,
            )
        return current

    async def run(self, **kwargs: Any) -> dict:
        prompt = self._format_prompt(**kwargs)
        text = await self._run_chain(prompt)
        return self._parse_json_response(text)

    async def run_raw(self, **kwargs: Any) -> str:
        prompt = self._format_prompt(**kwargs)
        return await self._run_chain(prompt)

    async def run_code(self, **kwargs: Any) -> str:
        return self._extract_code_block(await self.run_raw(**kwargs))

    def run_sync(self, **kwargs: Any) -> dict:
        import asyncio

        return asyncio.run(self.run(**kwargs))


class ResearchAgent(DedalusBaseAgent):
    def __init__(self, prompt_file: str, **kwargs: Any):
        super().__init__(prompt_file, task_type="research", **kwargs)


class CodeAgent(DedalusBaseAgent):
    def __init__(self, prompt_file: str, **kwargs: Any):
        super().__init__(prompt_file, task_type="code", **kwargs)


class CreativeAgent(DedalusBaseAgent):
    def __init__(self, prompt_file: str, **kwargs: Any):
        super().__init__(prompt_file, task_type="creative", **kwargs)


class AnalysisAgent(DedalusBaseAgent):
    def __init__(self, prompt_file: str, **kwargs: Any):
        super().__init__(prompt_file, task_type="analysis", **kwargs)
