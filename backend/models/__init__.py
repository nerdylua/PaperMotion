"""Data models for ingestion + generation pipeline."""

from .paper import (
    ArxivPaperMeta,
    Equation,
    Figure,
    Table,
    ParsedContent,
    Section,
    StructuredPaper,
)
from .generation import (
    VisualizationCandidate,
    AnalyzerOutput,
    Scene,
    VisualizationPlan,
    GeneratedCode,
    ValidatorOutput,
    Visualization,
)
from .voiceover import VoiceoverValidationOutput
from .m2m2_artifacts import (
    PaperConceptIntent,
    PaperMathPacket,
    PaperSceneSpec,
    SceneBeat,
)

__all__ = [
    "ArxivPaperMeta",
    "Equation",
    "Figure",
    "Table",
    "ParsedContent",
    "Section",
    "StructuredPaper",
    "VisualizationCandidate",
    "AnalyzerOutput",
    "Scene",
    "VisualizationPlan",
    "GeneratedCode",
    "ValidatorOutput",
    "Visualization",
    "VoiceoverValidationOutput",
    "PaperConceptIntent",
    "PaperMathPacket",
    "PaperSceneSpec",
    "SceneBeat",
]
