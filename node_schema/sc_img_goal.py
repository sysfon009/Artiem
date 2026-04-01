from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ImageRequestType(str, Enum):
    generate = "generate"
    edit = "edit"
    transfer = "transfer"
    style_change = "style_change"
    upscale = "upscale"
    variation = "variation"
    composite = "composite"
    remove_add = "remove_add"
    recolor = "recolor"
    inpaint = "inpaint"
    outpaint = "outpaint"
    unspecified = "unspecified"


class ImageComplexity(str, Enum):
    simple = "simple"
    moderate = "moderate"
    complex = "complex"
    multi_step = "multi_step"

class InputInformation(BaseModel):
    request_type: ImageRequestType = Field(
        description="Detected type of the image request from the user input segment"
    )
    input_snippet: str = Field(
        description="Relevant text snippet from the user message supporting this request type"
    )


class GoalItem(BaseModel):
    input_information: List[InputInformation] = Field(
        description="List of detected input segments and their corresponding image request types"
    )
    complexity: ImageComplexity = Field(
        description="Estimated complexity of achieving the requested image goal"
    )
    
    goal: str = Field(
        description="Normalized, deep-analyzed goal inferred from the user message"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the inferred goal and category detection"
    )


class GoalDetection(BaseModel):
    user_goals: List[GoalItem] = Field(
        description="List of detailed and comprehensive goals synthesized from the user request"
    )
    image_enhancement: bool = Field(
        description="True if an attached image likely needs enhancement, fixing, or modification prior to main execution"
    )
    user_input_enhancement: bool = Field(
        description="True if the user message is too brief or ambiguous and requires prompt expansion/enhancement"
    )
    implicit_constraints: bool = Field(
        description="Implicit rules or constraints detected from the request that must be followed"
    )
    expected_output: str = Field(
        description="Description of the expected final visual output based on the intent detection"
    )