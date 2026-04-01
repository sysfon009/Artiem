from enum import Enum
from typing import List
from pydantic import BaseModel, Field

#------Image Evaluation------
class ImageEvaluation(BaseModel):
    evaluation_type: str = Field( 
        description="type of the evaluation (e.g art, image quality, composition, color, lighting, etc.)"
    )
    evaulation_description: str = Field( 
        description="describe the evaluation, detailed and specific based on the generated image. explain why the generated image has the evaluation based on the goal, analysis and input."
    )
class ImageGenerateEvaluation(BaseModel):
    image_evaluation: List[ImageEvaluation] = Field( 
        description="list of evaluation based on the generated image."
    )
    
    image_result_score: float = Field( 
        ge=0.0,
        le=1.0,
        description="score of the evaluation based on the generated image."
    )
    score_reasoning: str = Field( 
        description="reasoning of why the score is given based on the evaluation and the generated image."
    )

