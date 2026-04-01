from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ImplicitConstraint(BaseModel):
    preserve_subject_identity: bool = Field(
        default=False,
        description="Set to true if the core subject or character must remain exactly the same without alterations"
    )
    maintain_background: bool = Field(
        default=False,
        description="Set to true if the background of a reference image should be kept unchanged"
    )
    strict_style_adherence: bool = Field(
        default=False,
        description="Set to true if a specific art style is explicitly requested and must not deviate"
    )
    avoid_nsfw: bool = Field(
        default=True,
        description="Set to true to ensure the generated output remains safe for work"
    )
    preserve_color_palette: bool = Field(
        default=False,
        description="Set to true if the exact colors from the reference or prompt must be strictly maintained"
    )


class ImageRole(str, Enum):
    analyze_for_context = "analyze_for_context"
    style_reference = "style_reference"
    character_reference = "character_reference"
    composition_reference = "composition_reference"
    use_as_mask_inpaint = "use_as_mask_inpaint"
    ignore = "ignore"


class ImageAssetStrategy(BaseModel):
    image_identifier: str = Field(
        description="The filename, title, or path of the image from the user attachment or previous chat history"
    )
    assigned_role: ImageRole = Field(
        description="Specific role assigned to this image to guide the generation process"
    )
    influence_strength: float = Field(
        ge=0.0,
        le=1.0,
        description="How strongly this image should influence the final result (0.1 is subtle, 1.0 is strict adherence)"
    )
    reasoning: str = Field(
        description="Logical explanation for why this role and strength were assigned"
    )


class PlanningStep(BaseModel):
    step_number: int = Field(
        description="The sequential chronological order of this planning step"
    )
    action_title: str = Field( 
        description="Title of the planning action"
    )
    action_description: str = Field( 
        description="Detailed description of what the Planner is reasoning or analyzing"
    )
    expected_challenge: Optional[str] = Field(
        default=None,
        description="Potential issue or ambiguity that might occur during execution of this step"
    )
    mitigation_strategy: Optional[str] = Field(
        default=None,
        description="Instruction on how the Execution Node should overcome the expected challenge"
    )


class ExecutionDirective(BaseModel):
    prompt_building_guidelines: str = Field(
        description="Core instructions for the Execution Node to construct the final text prompt"
    )
    visual_elements_to_emphasize: List[str] = Field(
        description="Specific objects, details, or emotions that must prominently feature in the prompt"
    )
    visual_elements_to_avoid: List[str] = Field(
        description="Specific details, artifacts, or styles that the Execution Node must explicitly put in the negative prompt"
    )
    style_and_lighting: str = Field(
        description="Guidelines regarding the exact art style, camera angle, and lighting setup to use"
    )
    recommended_aspect_ratio: str = Field(
        description="Suggested aspect ratio for the final image (e.g., 16:9, 1:1, 9:16)"
    )
    base_image_directive: Optional[str] = Field(
        default=None,
        description="Specific instructions on how to handle the reference images, including blending or masking instructions"
    )


class ImageGeneratePlan(BaseModel):
    strategic_reasoning: str = Field(
        description="A high-level explanation of the strategy chosen to achieve the user's goal"
    )
    implicit_constraints: ImplicitConstraint = Field(
        description="Rules and boundaries that the Execution Node must strictly obey"
    )
    image_asset_routing: List[ImageAssetStrategy] = Field(
        description="Strategic decision mapping for all available images in the context"
    )
    planning_process: List[PlanningStep] = Field( 
        description="Step-by-step logical reasoning, identifying challenges and mitigations"
    )
    execution_directives: ExecutionDirective = Field(
        description="The final blueprint of rules and guidelines handed over to the Execution Node"
    )