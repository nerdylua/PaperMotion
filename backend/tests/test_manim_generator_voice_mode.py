from agents.manim_generator import ManimGenerator
from models.generation import Scene, VisualizationPlan, VisualizationType


def test_extract_scene_class_name_supports_voiceover_scene():
    generator = ManimGenerator.__new__(ManimGenerator)
    code = """
from manim import *
from manim_voiceover import VoiceoverScene

class VoiceAligned(VoiceoverScene):
    def construct(self):
        pass
"""
    assert generator._extract_scene_class_name(code) == "VoiceAligned"


def test_extract_narration_lines_and_beats():
    generator = ManimGenerator.__new__(ManimGenerator)
    code = """
# Beat 1: intro
# Beat 2: scoring
with self.voiceover(text=\"Queries compare keys to score relevance across tokens in context-rich attention maps.\") as tracker:
    self.play(Create(arrow), run_time=tracker.duration)
# Beat 3: weighting
with self.voiceover(text=\"Softmax normalizes similarities so weighted values form each contextual representation cleanly.\") as tracker:
    self.play(Write(eq), run_time=tracker.duration)
"""
    lines = generator._extract_narration_lines(code)
    beats = generator._extract_beat_labels(code)

    assert len(lines) == 2
    assert lines[0].startswith("Queries compare keys")
    assert beats == ["# Beat 1: intro", "# Beat 2: scoring", "# Beat 3: weighting"]


def test_selects_voiceover_examples_when_enabled():
    generator = ManimGenerator.__new__(ManimGenerator)
    generator.examples = {VisualizationType.DATA_FLOW: "plain_example"}
    generator.voiceover_examples = {VisualizationType.DATA_FLOW: "voiceover_example"}

    selected_voice = generator._get_example_for_type(VisualizationType.DATA_FLOW, voiceover_enabled=True)
    selected_plain = generator._get_example_for_type(VisualizationType.DATA_FLOW, voiceover_enabled=False)

    assert selected_voice == "voiceover_example"
    assert selected_plain == "plain_example"


def _prompt_plan() -> VisualizationPlan:
    return VisualizationPlan(
        concept_name="Scaled Dot-Product Attention",
        visualization_type=VisualizationType.DATA_FLOW,
        duration_seconds=36,
        scenes=[
            Scene(order=1, description="Attention scores", duration_seconds=10, transitions="Write", elements=["MathTex"])
        ],
        narration_points=[],
    )


def test_build_prompt_includes_scene_spec_when_provided():
    generator = ManimGenerator.__new__(ManimGenerator)
    generator.prompt_template = "{plan_json}\n{scene_spec_section}\n{example_code}\n{scene_class_name}"
    generator.examples = {VisualizationType.DATA_FLOW: "plain_example"}
    generator.voiceover_examples = {VisualizationType.DATA_FLOW: "voiceover_example"}

    prompt = generator._build_prompt(
        plan=_prompt_plan(),
        voiceover_enabled=True,
        tts_service="gtts",
        voice_name="",
        narration_style="friendly_tutor",
        target_duration_seconds=(30, 45),
        scene_spec_json='{"visual_metaphor":"score beams"}',
    )

    assert "M2M2 Paper-Aware Scene Spec" in prompt
    assert "Treat the scene spec as the implementation contract" in prompt
    assert "score beams" in prompt
    assert "voiceover_example" in prompt


def test_build_prompt_remains_compatible_without_scene_spec():
    generator = ManimGenerator.__new__(ManimGenerator)
    generator.prompt_template = "{plan_json}\n{scene_spec_section}\n{example_code}\n{scene_class_name}"
    generator.examples = {VisualizationType.DATA_FLOW: "plain_example"}
    generator.voiceover_examples = {VisualizationType.DATA_FLOW: "voiceover_example"}

    prompt = generator._build_prompt(
        plan=_prompt_plan(),
        voiceover_enabled=False,
        tts_service="gtts",
        voice_name="",
        narration_style="friendly_tutor",
        target_duration_seconds=(30, 45),
    )

    assert "M2M2 Paper-Aware Scene Spec" not in prompt
    assert "Treat the scene spec as the implementation contract" not in prompt
    assert "plain_example" in prompt
