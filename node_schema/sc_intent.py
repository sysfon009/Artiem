from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    acknowledgement = "acknowledgement"
    ask_question = "ask_question"
    discussion_topic = "discussion_topic"
    evaluation_request = "evaluation_request"
    explanation_request = "explanation_request"
    imrpovement_request = "improvement_request"
    idea_request = "idea_request"
    clarification_request = "clarification_request"
    unspecified = "unspecified"


class IntentItem(BaseModel):
    intent: IntentType = Field(
        description="Detected intent category"
    )

    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for this intent"
    )

    snippet: str = Field(
        description="Relevant text snippet from the user message supporting this intent"
    )


class IntentDetection(BaseModel):
    intents_detection: List[IntentItem] = Field(
        description="List of detected intents from the user message"
    )

    requires_context: bool = Field(
        description="Whether previous conversation or narrative context is required"
    )