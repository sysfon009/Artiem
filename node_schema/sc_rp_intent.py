from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field




class IntentType(str, Enum):
    acknowledgement = "roleplay_continuation"
    ask_question = "narrative_direction"
    discussion_topic = "story_information"
    evaluation_request = "out of roleplay_discussion"
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


class UserInformationState(BaseModel):

    speech_tone: Optional[str] = Field(
        default=None,
        description="The tone of the user's speech or text (e.g., sarcastic, gentle, loud)"
    )
    mood: Optional[str] = Field(
        default=None,
        description="The current mood of the user (e.g., gloomy, cheerful)"
    )
    emotion: Optional[str] = Field(
        default=None,
        description="Specific emotions expressed by the user (e.g., angry, sad, happy)"
    )
    pose_posture: Optional[str] = Field(
        default=None,
        description="The physical pose or posture of the user, if described (e.g., crossing arms, leaning)"
    )
    sensation: Optional[str] = Field(
        default=None,
        description="Any physical sensations felt by the user (e.g., cold, pain, dizzy)"
    )

class IntentDetection(BaseModel):
    user_intents_detection: List[IntentItem] = Field(
        description="List of detected intents from the user message"
    )
    user_information_state: UserInformationState
    requires_context: bool = Field(
        description="Whether previous conversation or narrative context is required"
    )
