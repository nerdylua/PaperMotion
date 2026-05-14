import json

import pytest

from agents import pipeline
from models.generation import (
    GeneratedCode,
    Scene,
    ValidatorOutput,
    VisualizationCandidate,
    VisualizationPlan,
    VisualizationType,
)
from models.m2m2_artifacts import (
    PaperConceptIntent,
    PaperMathPacket,
    PaperSceneSpec,
    SceneBeat,
)
from models.paper import ArxivPaperMeta, Equation, Section, StructuredPaper


def _candidate() -> VisualizationCandidate:
    return VisualizationCandidate(
        section_id="section-1",
        concept_name="Scaled Dot-Product Attention",
        concept_description="Query-key scores are normalized before mixing values.",
        visualization_type=VisualizationType.DATA_FLOW,
        priority=5,
        context=r"Attention(Q,K,V)=softmax(QK^T/\sqrt{d_k})V",
    )


def _plan() -> VisualizationPlan:
    return VisualizationPlan(
        concept_name="Scaled Dot-Product Attention",
        visualization_type=VisualizationType.DATA_FLOW,
        duration_seconds=36,
        scenes=[
            Scene(
                order=1,
                description="Introduce query, key, and value blocks",
                duration_seconds=10,
                transitions="Write labels and create arrows",
                elements=["Text", "Arrow"],
            )
        ],
        narration_points=["Scores decide which values matter most."],
    )


def _scene_spec() -> PaperSceneSpec:
    return PaperSceneSpec(
        intent=PaperConceptIntent(
            concept="Scaled Dot-Product Attention",
            paper_context="Transformer attention uses scaled scores to connect tokens.",
            section_context="The section defines attention over Q, K, and V matrices.",
            learner_objective="Understand why scores become weights over values.",
            prerequisites=["matrix multiplication", "softmax"],
            misconceptions=["Attention is not a fixed lookup table."],
        ),
        math_packet=PaperMathPacket(
            definitions=["Q, K, and V are learned projections."],
            equations=[r"Attention(Q,K,V)=softmax(QK^T/\sqrt{d_k})V"],
            render_safe_equations=[r"\mathrm{softmax}(QK^T / \sqrt{d_k})V"],
            variables=["Q: queries", "K: keys", "V: values"],
            assumptions=["Dot products represent token relevance."],
            paper_grounding_notes=["Equation appears in the attention section."],
        ),
        visual_metaphor="Queries cast score beams toward keys, then pull weighted values back.",
        beats=[
            SceneBeat(
                order=1,
                intent="Connect score computation to token relevance.",
                visual_action="Draw arrows from one query to multiple keys.",
                narration_goal="Explain that each score estimates relevance.",
                math_focus=["QK^T"],
            )
        ],
        required_mobjects=["Text", "VGroup", "Arrow", "MathTex"],
        layout_constraints=["Keep Q, K, V columns within the safe frame."],
        voiceover_intent=["Explain the idea behind scores before showing softmax."],
        code_requirements=["Use consistent colors for Q, K, and V."],
    )


def _paper() -> StructuredPaper:
    return StructuredPaper(
        meta=ArxivPaperMeta(
            arxiv_id="1706.03762",
            title="Attention Is All You Need",
            authors=["Vaswani et al."],
            abstract="The Transformer relies on attention mechanisms.",
            pdf_url="https://example.com/paper.pdf",
        ),
        sections=[
            Section(
                id="section-1",
                title="Attention",
                content="Scaled dot-product attention computes scores, normalizes them, and mixes values.",
                equations=[
                    Equation(
                        latex=r"Attention(Q,K,V)=softmax(QK^T/\sqrt{d_k})V",
                        context="Definition of scaled dot-product attention.",
                    )
                ],
            )
        ],
    )


class FakePlanner:
    async def run(self, **kwargs):
        return _plan()


class FakeM2M2Layer:
    async def run(self, **kwargs):
        assert kwargs["paper_title"] == "Attention Is All You Need"
        assert kwargs["section_equations"][0].latex.startswith("Attention")
        return _scene_spec()


class FailingM2M2Layer:
    async def run(self, **kwargs):
        raise RuntimeError("m2m2 unavailable")


class FakeGenerator:
    def __init__(self):
        self.scene_spec_json = "unset"

    async def run(self, **kwargs):
        self.scene_spec_json = kwargs.get("scene_spec_json")
        return GeneratedCode(
            code="from manim import *\nclass Generated(Scene):\n    def construct(self):\n        pass\n",
            scene_class_name="Generated",
            dependencies=["manim"],
        )


class FakeValidator:
    def validate(self, code: str) -> ValidatorOutput:
        return ValidatorOutput(is_valid=True, code=code)


def test_m2m2_artifact_schema_round_trips_json():
    spec = _scene_spec()
    raw = spec.model_dump_json()

    parsed = PaperSceneSpec.model_validate_json(raw)

    assert parsed.intent.concept == "Scaled Dot-Product Attention"
    assert parsed.math_packet.equations == [r"Attention(Q,K,V)=softmax(QK^T/\sqrt{d_k})V"]
    assert parsed.beats[0].math_focus == ["QK^T"]
    assert parsed.required_mobjects == ["Text", "VGroup", "Arrow", "MathTex"]


@pytest.mark.asyncio
async def test_pipeline_storyboard_contains_plan_and_m2m2(monkeypatch):
    monkeypatch.setattr(pipeline, "ENABLE_VOICEOVER", False)
    monkeypatch.setattr(pipeline, "MAX_RETRIES", 1)
    generator = FakeGenerator()

    viz = await pipeline.generate_single_visualization(
        candidate=_candidate(),
        paper=_paper(),
        planner=FakePlanner(),
        m2m2_layer=FakeM2M2Layer(),
        generator=generator,
        validator=FakeValidator(),
    )

    assert viz is not None
    storyboard = json.loads(viz.storyboard)
    assert storyboard["plan"]["concept_name"] == "Scaled Dot-Product Attention"
    assert storyboard["m2m2"]["visual_metaphor"].startswith("Queries cast score beams")
    assert generator.scene_spec_json is not None
    assert "paper_grounding_notes" in generator.scene_spec_json


@pytest.mark.asyncio
async def test_pipeline_falls_back_when_m2m2_layer_fails(monkeypatch):
    monkeypatch.setattr(pipeline, "ENABLE_VOICEOVER", False)
    monkeypatch.setattr(pipeline, "MAX_RETRIES", 1)
    generator = FakeGenerator()

    viz = await pipeline.generate_single_visualization(
        candidate=_candidate(),
        paper=_paper(),
        planner=FakePlanner(),
        m2m2_layer=FailingM2M2Layer(),
        generator=generator,
        validator=FakeValidator(),
    )

    assert viz is not None
    storyboard = json.loads(viz.storyboard)
    assert storyboard["concept_name"] == "Scaled Dot-Product Attention"
    assert "m2m2" not in storyboard
    assert generator.scene_spec_json is None
