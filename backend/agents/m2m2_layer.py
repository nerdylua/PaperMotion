"""Thin Math-To-Manim planning layer for paper-grounded Manim specs."""

import json
import sys
from pathlib import Path

try:
    from .base import BaseAgent
    from ..models.generation import VisualizationCandidate, VisualizationPlan
    from ..models.m2m2_artifacts import PaperSceneSpec
    from ..models.paper import Equation
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from agents.base import BaseAgent
    from models.generation import VisualizationCandidate, VisualizationPlan
    from models.m2m2_artifacts import PaperSceneSpec
    from models.paper import Equation


class M2M2PlanningLayer(BaseAgent):
    """
    Produces a compact, paper-aware scene spec between planning and codegen.

    This enriches the existing VisualizationPlan; it does not replace timing,
    visualization type, validation, rendering, or voiceover policies.
    """

    def __init__(self, model: str | None = None):
        super().__init__("m2m2_layer.md", model=model, max_tokens=4096)

    async def run(
        self,
        candidate: VisualizationCandidate,
        plan: VisualizationPlan,
        section_content: str,
        paper_title: str,
        paper_abstract: str,
        section_equations: list[Equation],
    ) -> PaperSceneSpec:
        equations_json = json.dumps(
            [equation.model_dump(mode="json") for equation in section_equations],
            indent=2,
        )
        prompt = self._format_prompt(
            paper_title=paper_title,
            paper_abstract=paper_abstract,
            section_content=section_content,
            candidate_json=candidate.model_dump_json(indent=2),
            plan_json=plan.model_dump_json(indent=2),
            equations_json=equations_json,
        )

        text = await self._call_llm(prompt)
        result = self._parse_json_response(text)
        return PaperSceneSpec.model_validate(result)
