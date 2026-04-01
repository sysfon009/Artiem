from pydantic import BaseModel, Field

class ExecutionResult(BaseModel):
    image_prompt: str = Field(
        description="The exact final text prompt that was sent to the image generation tool"
    )
    image_title: str = Field(
        description="title of the image based on response model image generation"
    )
    image_description: str = Field(
        description="A brief description summarizing the visual content of the generated image"
    )