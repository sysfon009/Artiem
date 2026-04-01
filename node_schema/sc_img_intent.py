from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class IntentType(str, Enum):
    create_image = "create_image"
    image_to_image = "image_to_image"
    discussion = "discussion"
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

class UserIntentDetection(BaseModel):
    user_intents_detection: IntentItem

    