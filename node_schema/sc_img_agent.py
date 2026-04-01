from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ==========================================
# PHASE 1: IMAGE INTENT ANALYSIS
# ==========================================

class ImageRequestType(str, Enum):
    # --- Image tasks (triggers full pipeline) ---
    generate = "generate"
    edit = "edit"
    transfer = "transfer"
    style_change = "style_change"
    upscale = "upscale"
    variation = "variation"
    composite = "composite"
    remove_add = "remove_add"
    recolor = "recolor"
    # --- Non-image tasks (triggers conversational fallback) ---
    general_chat = "general_chat"
    discussion = "discussion"
    unspecified = "unspecified"


class ImageComplexity(str, Enum):
    simple = "simple"
    moderate = "moderate"
    complex = "complex"
    multi_step = "multi_step"


class ImplicitConstraint(BaseModel):
    constraint_type: str = Field(
        description=(
            "Category of unspoken requirement. Examples: "
            "'preserve_pose', 'maintain_proportions', 'keep_background', "
            "'consistent_lighting', 'preserve_identity', 'maintain_style', "
            "'keep_composition', 'preserve_expression', 'same_angle', 'color_coherence'"
        )
    )
    description: str = Field(
        description="Human-readable explanation of what must be preserved or maintained"
    )
    source_image: Optional[str] = Field(
        default=None,
        description="Which reference image this constraint originates from (e.g. 'attachment_image_1', 'generated_2'). Null if general."
    )
    priority: str = Field(
        default="high",
        description="Importance level: 'critical' (must never violate), 'high' (strongly prefer), 'medium' (nice to have)"
    )


class ImageIntentAnalysis(BaseModel):
    request_type: ImageRequestType = Field(
        description="Primary category of the image request"
    )

    complexity: ImageComplexity = Field(
        description="How complex is this image task"
    )

    subject_description: str = Field(
        description="Detailed description of what the user wants to see in the image. Expand abbreviations, fill in obvious gaps."
    )

    reference_images: List[str] = Field(
        default=[],
        description=(
            "List of reference image filenames detected from user message or conversation history. "
            "Include both attachment_image_N and generated_N filenames."
        )
    )

    target_image: Optional[str] = Field(
        default=None,
        description=(
            "For edit/transfer operations: which image should be modified. "
            "Should be the MOST RECENT generated image if the user doesn't specify explicitly."
        )
    )

    implicit_constraints: List[ImplicitConstraint] = Field(
        default=[],
        description=(
            "Logical requirements the user did NOT state but MUST be followed. "
            "Think: what would the user complain about if we ignored it? "
            "Examples: if transferring outfits, preserve the original pose & proportions. "
            "If recoloring, keep all other attributes identical."
        )
    )

    user_explicit_instructions: str = Field(
        description="The user's request restated clearly and precisely, without ambiguity"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="How confident you are in this analysis"
    )

    reasoning: str = Field(
        description="Brief chain-of-thought explaining your intent classification. 2-3 sentences max."
    )


# ==========================================
# PHASE 2: PROMPT ENGINEERING PLAN
# ==========================================

class PromptVariation(BaseModel):
    variation_id: int = Field(
        description="Sequential ID starting from 1"
    )
    mutation_type: str = Field(
        description=(
            "What aspect this variation mutates: "
            "'composition', 'lighting', 'detail_emphasis', 'style_shift', "
            "'angle_change', 'atmosphere', 'color_palette', 'texture_focus'"
        )
    )
    prompt_text: str = Field(
        description=(
            "The full engineered prompt for this variation. Must be significantly different "
            "from other variations while respecting all anchor constraints. "
            "Use rich, specific vocabulary — avoid generic descriptors."
        )
    )
    rationale: str = Field(
        description="Why this variation might work better than the base prompt"
    )


class ImagePromptPlan(BaseModel):
    base_prompt: str = Field(
        description=(
            "The primary, highly detailed image generation prompt. "
            "Must include: subject details, action/pose, environment, "
            "lighting, camera angle, art style, color palette, and mood. "
            "Each element should use vivid, specific language — never generic."
        )
    )

    anchor_constraints: List[str] = Field(
        description=(
            "Elements that MUST remain identical across ALL prompt variations. "
            "These are the immutable core of the request. "
            "Format each as a clear directive, e.g.: "
            "'Subject must be a young woman with dark hair in a red dress', "
            "'Camera angle must be eye-level portrait orientation'"
        )
    )

    negative_constraints: List[str] = Field(
        default=[],
        description=(
            "Things that must NOT appear in the image. "
            "E.g.: 'no text overlays', 'no watermarks', 'no extra limbs'"
        )
    )

    prompt_variations: List[PromptVariation] = Field(
        default=[],
        description=(
            "2-3 alternative prompt phrasings that keep anchor constraints intact "
            "but vary composition, lighting, detail emphasis, or style. "
            "Used as fallbacks if the base prompt produces saturated results."
        )
    )

    recommended_aspect_ratio: str = Field(
        default="1:1",
        description="Best aspect ratio for this prompt: '1:1', '16:9', '9:16', '3:4', '4:3'"
    )

    recommended_resolution: str = Field(
        default="1k",
        description="Recommended resolution: '1k', '2k', '3k', '4k'"
    )

    strategy_notes: str = Field(
        default="",
        description="Any additional notes about the prompting strategy, tips for the executor"
    )


# ==========================================
# PHASE 4: IMAGE OUTPUT EVALUATION
# ==========================================

class EvaluationVerdict(str, Enum):
    passed = "pass"
    retry_refine = "retry_refine"
    retry_rephrase = "retry_rephrase"
    failed = "fail"


class MutationStrategy(str, Enum):
    refine_details = "refine_details"
    rephrase_entirely = "rephrase_entirely"
    change_style = "change_style"
    adjust_composition = "adjust_composition"
    switch_reference = "switch_reference"
    simplify_prompt = "simplify_prompt"


class ImageEvaluation(BaseModel):
    prompt_alignment: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "How well does the generated image match the intended prompt? "
            "0.0 = completely wrong subject/scene, 1.0 = exactly as described"
        )
    )

    constraint_adherence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Were all implicit and explicit constraints respected? "
            "0.0 = constraints completely violated, 1.0 = all constraints perfectly met"
        )
    )

    visual_quality: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Overall artistic and technical quality of the image. "
            "Consider: coherence, detail, no artifacts, proper anatomy, natural lighting"
        )
    )

    reference_fidelity: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "If reference images were used, how well does the output honor them? "
            "1.0 if no references were needed. "
            "0.0 = reference completely ignored"
        )
    )

    overall_score: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Weighted score: "
            "(prompt_alignment*0.30 + constraint_adherence*0.30 + "
            "visual_quality*0.20 + reference_fidelity*0.20)"
        )
    )

    issues: List[str] = Field(
        default=[],
        description="Specific problems found. Be precise: 'wrong hair color', 'pose not preserved', 'background changed'"
    )

    verdict: EvaluationVerdict = Field(
        description=(
            "'pass' if score >= 0.75 and no critical constraint violations. "
            "'retry_refine' if score >= 0.5 — small adjustments needed. "
            "'retry_rephrase' if score < 0.5 — prompt needs fundamental rework. "
            "'fail' if image generation itself failed or returned garbage."
        )
    )

    correction_guidance: str = Field(
        default="",
        description=(
            "Specific, actionable instructions for fixing the issues. "
            "NOT vague ('make it better') but precise ('increase emphasis on red dress, "
            "add explicit pose description: standing with arms crossed')."
        )
    )

    mutation_strategy: MutationStrategy = Field(
        default=MutationStrategy.refine_details,
        description="Recommended approach for the next retry attempt if verdict is not 'pass'"
    )
