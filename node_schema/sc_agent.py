from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ==========================================
# PHASE 1: INTENT ANALYSIS SCHEMA
# ==========================================

class IntentType(str, Enum):
    question = "question"
    task = "task"
    discussion = "discussion"
    analysis = "analysis"
    creation = "creation"
    clarification = "clarification"
    evaluation = "evaluation"
    troubleshooting = "troubleshooting"
    brainstorming = "brainstorming"
    unspecified = "unspecified"


class ComplexityLevel(str, Enum):
    simple = "simple"
    moderate = "moderate"
    complex = "complex"


class IntentAnalysis(BaseModel):
    intent_type: IntentType = Field(
        description="The primary category of the user's request"
    )

    complexity: ComplexityLevel = Field(
        description="Estimated complexity level of the request"
    )

    requires_tool: bool = Field(
        description="Whether external tools (code execution, search, image gen) are needed to fulfill the request"
    )

    key_entities: List[str] = Field(
        description="Important subjects, topics, or objects mentioned in the user message. Extract 1-5 key entities."
    )

    success_criteria: str = Field(
        description="What would make a successful response to this request. Be specific about what the user expects."
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="How confident you are in this analysis (0.0 = uncertain, 1.0 = very confident)"
    )

    reasoning: str = Field(
        description="Brief chain-of-thought explaining why you classified the intent this way. Max 2-3 sentences."
    )


# ==========================================
# PHASE 2: STRATEGIC PLANNING SCHEMA
# ==========================================

class PlanStep(BaseModel):
    step_number: int = Field(
        description="Order of this step (1-based)"
    )

    action: str = Field(
        description="What to do in this step. Be concrete and actionable."
    )

    expected_result: str = Field(
        description="What should be produced or achieved by this step"
    )

    requires_tool: bool = Field(
        default=False,
        description="Whether this step needs an external tool"
    )

    tool_name: Optional[str] = Field(
        default=None,
        description="Name of the tool to use if requires_tool is true"
    )


class ActionPlan(BaseModel):
    steps: List[PlanStep] = Field(
        description="Ordered list of concrete steps to fulfill the user's request. Must have at least 1 step."
    )

    expected_output: str = Field(
        description="Description of what the final output should look like when all steps are completed"
    )

    output_format: str = Field(
        description="The format the response should take: 'text', 'structured_data', 'code', 'analysis', 'list', 'conversation'"
    )

    risk_notes: str = Field(
        default="",
        description="Potential issues, ambiguities, or risks to watch for during execution. Empty if none."
    )

    estimated_quality_bar: float = Field(
        ge=0.0,
        le=1.0,
        default=0.7,
        description="Minimum quality score this response should achieve in evaluation. Default 0.7."
    )


# ==========================================
# PHASE 4: OUTPUT EVALUATION SCHEMA
# ==========================================

class EvaluationVerdict(str, Enum):
    passed = "pass"
    failed = "fail"
    partial = "partial"


class OutputEvaluation(BaseModel):
    plan_adherence: float = Field(
        ge=0.0,
        le=1.0,
        description="How well did the output follow the planned steps? (0.0 = completely deviated, 1.0 = perfectly followed)"
    )

    completeness: float = Field(
        ge=0.0,
        le=1.0,
        description="Did the output address ALL parts of the user's request? (0.0 = missed everything, 1.0 = fully complete)"
    )

    factual_consistency: float = Field(
        ge=0.0,
        le=1.0,
        description="Are there internal contradictions or inconsistencies? (0.0 = many contradictions, 1.0 = fully consistent)"
    )

    hallucination_risk: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence that the output contains no fabricated information (0.0 = likely hallucinated, 1.0 = grounded in facts)"
    )

    clarity: float = Field(
        ge=0.0,
        le=1.0,
        description="How clear and well-structured is the response? (0.0 = confusing, 1.0 = crystal clear)"
    )

    overall_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Weighted overall quality score. Formula: (plan_adherence*0.2 + completeness*0.25 + factual_consistency*0.25 + hallucination_risk*0.2 + clarity*0.1)"
    )

    issues: List[str] = Field(
        default=[],
        description="Specific problems found in the output. Empty list if no issues."
    )

    verdict: EvaluationVerdict = Field(
        description="Final verdict: 'pass' if score >= 0.7 and no critical issues, 'fail' if score < 0.5 or critical issues found, 'partial' otherwise"
    )

    correction_guidance: str = Field(
        default="",
        description="Specific instructions for fixing issues if verdict is 'fail' or 'partial'. What exactly should be changed, added, or removed."
    )
