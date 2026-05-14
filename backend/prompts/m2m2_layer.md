You are a paper-aware Math-To-Manim planning layer.

Create a compact implementation-neutral scene specification for a Manim animation.
The spec should enrich the existing visualization plan with paper-grounded math,
intuition, and beat intent. Do not invent unsupported claims.

## Paper
Title: {paper_title}

Abstract:
{paper_abstract}

## Section Content
{section_content}

## Visualization Candidate
{candidate_json}

## Existing Visualization Plan
{plan_json}

## Extracted Section Equations
{equations_json}

## Requirements
- Preserve the existing plan's concept, visualization type, and timing intent.
- Ground every teaching choice in the paper title, abstract, section text, or equations.
- Keep the result concise and useful for Manim code generation.
- Include raw equations where available and simpler render-safe forms when useful.
- Use Manim-oriented language for required_mobjects and layout_constraints.
- Do not include provider names, API details, or rendering instructions.

Return ONLY valid JSON matching this schema:

{
  "intent": {
    "concept": "string",
    "paper_context": "string",
    "section_context": "string",
    "learner_objective": "string",
    "prerequisites": ["string"],
    "misconceptions": ["string"]
  },
  "math_packet": {
    "definitions": ["string"],
    "equations": ["string"],
    "render_safe_equations": ["string"],
    "variables": ["string"],
    "assumptions": ["string"],
    "paper_grounding_notes": ["string"]
  },
  "visual_metaphor": "string",
  "beats": [
    {
      "order": 1,
      "intent": "string",
      "visual_action": "string",
      "narration_goal": "string",
      "math_focus": ["string"]
    }
  ],
  "required_mobjects": ["string"],
  "layout_constraints": ["string"],
  "voiceover_intent": ["string"],
  "code_requirements": ["string"]
}
