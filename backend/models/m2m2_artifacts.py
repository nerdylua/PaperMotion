"""Typed artifacts for the thin Math-To-Manim planning layer."""

from pydantic import BaseModel, Field


class PaperConceptIntent(BaseModel):
    """Paper-grounded teaching intent for one visualization."""

    concept: str = Field(..., description="Primary concept being taught")
    paper_context: str = Field(..., description="How the concept appears in the paper")
    section_context: str = Field(..., description="Relevant section-local context")
    learner_objective: str = Field(..., description="What the viewer should understand")
    prerequisites: list[str] = Field(default_factory=list, description="Conceptual prerequisites")
    misconceptions: list[str] = Field(default_factory=list, description="Likely misconceptions to avoid")


class PaperMathPacket(BaseModel):
    """Equation and assumption packet extracted from the paper context."""

    definitions: list[str] = Field(default_factory=list, description="Definitions needed for the animation")
    equations: list[str] = Field(default_factory=list, description="Raw paper equations")
    render_safe_equations: list[str] = Field(
        default_factory=list,
        description="Simplified MathTex-safe equation forms when useful",
    )
    variables: list[str] = Field(default_factory=list, description="Variable names and meanings")
    assumptions: list[str] = Field(default_factory=list, description="Paper assumptions used by the demo")
    paper_grounding_notes: list[str] = Field(
        default_factory=list,
        description="Notes tying the math back to the cited paper section",
    )


class SceneBeat(BaseModel):
    """One ordered Manim-oriented teaching beat."""

    order: int = Field(..., ge=1, description="Beat order")
    intent: str = Field(..., description="What this beat should teach")
    visual_action: str = Field(..., description="What should happen on screen")
    narration_goal: str = Field(..., description="What the voiceover should convey")
    math_focus: list[str] = Field(default_factory=list, description="Equations or symbols emphasized")


class PaperSceneSpec(BaseModel):
    """Implementation-neutral scene contract for richer Manim generation."""

    intent: PaperConceptIntent = Field(..., description="Paper-grounded concept intent")
    math_packet: PaperMathPacket = Field(..., description="Paper-grounded math packet")
    visual_metaphor: str = Field(..., description="Core visual metaphor for the animation")
    beats: list[SceneBeat] = Field(default_factory=list, description="Ordered teaching beats")
    required_mobjects: list[str] = Field(default_factory=list, description="Expected Manim object families")
    layout_constraints: list[str] = Field(default_factory=list, description="Layout and spatial constraints")
    voiceover_intent: list[str] = Field(default_factory=list, description="Narration goals by beat")
    code_requirements: list[str] = Field(default_factory=list, description="Implementation requirements")
