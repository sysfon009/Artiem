from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class InputCategory(str, Enum):
    question_speech = "question_speech"
    discussion_speech = "discussion_speech"
    clarification_speech = "clarification_speech"
    acknowledgment_speech = "acknowledgment_speech" 
    unspecified_speech = "unspecified_speech"
    internal_thinking = "internal_thinking"
    action = "action"
    story_direction = "story_direction"
    story_information = "story_information"
    improvement_request = "improvement_request"
    narrative_continuation = "narrative_continuation"
    clarification_request = "clarification_request"
    unspecified = "unspecified"

class InputInformation(BaseModel):
    category: InputCategory = Field(
        description="Detected input category"
    )
    input_snippet: str = Field(
        description="Relevant text snippet from the user message supporting this intent"
    )

class GoalItem(BaseModel): 
    input_order: int = Field(
        default=1,
        description="Order number based on chronological and narrative flow."
    )
  
    input_type: List[InputInformation] = Field(
        description="List of input information details"
    )
    goal: str = Field(
        description="Goal based on the intent"
    )
    related_context: Optional[str] = Field(
        default=None, 
        description="Snippet of the context that related to goal from the history or model output."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for this intent"
    )

class GoalDetection(BaseModel):
    user_goal_detection: List[GoalItem] = Field( 
        description="List of detected goal from the user message"
    )