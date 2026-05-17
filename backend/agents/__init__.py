"""
PaperMotion Agent Pipeline - Team 2

This module provides the multi-agent AI pipeline for generating Manim visualizations
from structured academic papers.

Sponsor Integrations:
    - OpenAI Responses API for all model calls

Usage:
    from agents import generate_visualizations
    from models import StructuredPaper

    paper = StructuredPaper(...)
    visualizations = await generate_visualizations(paper)

"""

try:
    from .base import BaseAgent
    from .section_analyzer import SectionAnalyzer
    from .visualization_planner import VisualizationPlanner
    from .m2m2_layer import M2M2PlanningLayer
    from .manim_generator import ManimGenerator
    from .code_validator import CodeValidator
    from .voiceover_script_validator import VoiceoverScriptValidator
    from .pipeline import generate_visualizations, generate_single_visualization
except ImportError:
    from base import BaseAgent
    from section_analyzer import SectionAnalyzer
    from visualization_planner import VisualizationPlanner
    from m2m2_layer import M2M2PlanningLayer
    from manim_generator import ManimGenerator
    from code_validator import CodeValidator
    from voiceover_script_validator import VoiceoverScriptValidator
    from pipeline import generate_visualizations, generate_single_visualization

__all__ = [
    # Base agents
    "BaseAgent",
    # Pipeline agents
    "SectionAnalyzer",
    "VisualizationPlanner",
    "M2M2PlanningLayer",
    "ManimGenerator",
    "CodeValidator",
    "VoiceoverScriptValidator",
    # Utilities
    "generate_visualizations",
    "generate_single_visualization",
]
