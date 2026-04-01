from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class LightingType(str, Enum):
    natural = "natural"
    studio = "studio"
    cinematic = "cinematic"
    neon = "neon"
    moody = "moody"
    flat = "flat"
    unspecified = "unspecified"


class CameraAngle(str, Enum):
    extreme_close_up = "extreme_close_up"
    close_up = "close_up"
    medium_shot = "medium_shot"
    wide_shot = "wide_shot"
    extreme_wide_shot = "extreme_wide_shot"
    bird_eye_view = "bird_eye_view"
    worm_eye_view = "worm_eye_view"
    unspecified = "unspecified"


class SubjectInfo(BaseModel):
    subject_type: str = Field(
        description="Type of subject (e.g., human, animal, vehicle, abstract object)"
    )
    description: str = Field(
        description="Detailed visual description of the subject including physical appearance"
    )
    attributes: List[str] = Field(
        description="Key visual traits (e.g., 'wearing a red jacket', 'smiling', 'rusty texture')"
    )
    position: str = Field(
        description="Placement within the image frame (e.g., center, foreground, bottom-left)"
    )


class EnvironmentInfo(BaseModel):
    setting: str = Field(
        description="Description of the background or physical location (e.g., bustling city street, quiet forest, studio backdrop)"
    )
    time_of_day: Optional[str] = Field(
        description="Inferred time of day (e.g., morning, golden hour, night)"
    )
    weather_or_atmosphere: Optional[str] = Field(
        description="Inferred weather or atmospheric effects (e.g., foggy, raining, clear, dusty)"
    )


class StyleInfo(BaseModel):
    art_style: str = Field(
        description="The dominant art style (e.g., photorealistic, anime, oil painting, 3D render, sketch)"
    )
    color_palette: List[str] = Field(
        description="Primary colors or overall color scheme (e.g., warm, cool, pastel, monochromatic, high contrast)"
    )
    mood: str = Field(
        description="The emotional vibe or atmosphere conveyed by the image (e.g., melancholic, joyful, tense, serene)"
    )


class TechnicalInfo(BaseModel):
    lighting: LightingType = Field(
        description="The primary lighting setup detected in the image"
    )
    camera_angle: CameraAngle = Field(
        description="The perceived camera framing or perspective"
    )
    composition_notes: str = Field(
        description="Notes on layout techniques (e.g., rule of thirds, symmetry, leading lines, depth of field)"
    )


class QualityInfo(BaseModel):
    overall_quality: str = Field(
        description="General assessment of visual quality (e.g., high resolution, blurry, noisy)"
    )
    flaws_and_artifacts: List[str] = Field(
        description="List of detected AI artifacts, anatomical errors, or visual glitches (e.g., 'extra fingers on left hand', 'melting background lines')"
    )


class ImageAnalysisResult(BaseModel):
    overall_description: str = Field(
        description="A comprehensive, detailed summary caption of the entire image"
    )
    subjects: List[SubjectInfo] = Field(
        description="Detailed breakdown of all prominent subjects or characters in the image"
    )
    environment: EnvironmentInfo = Field(
        description="Breakdown of the background, setting, and atmosphere"
    )
    style: StyleInfo = Field(
        description="Artistic and stylistic breakdown of the image"
    )
    technical: TechnicalInfo = Field(
        description="Analysis of lighting, camera angles, and composition"
    )
    quality: QualityInfo = Field(
        description="Assessment of image quality and any potential structural flaws"
    )
    extracted_text: Optional[str] = Field(
        description="Any readable OCR text, signs, or watermarks visibly written inside the image"
    )

class ImageAnalysis(BaseModel):
    image_analysis: ImageAnalysisResult = Field(
        description="Comprehensive analysis of the attached image covering subjects, environment, style, technical aspects, and quality"
    )
    image_description: str = Field(
        description="description of the image content in a concise manner, useful for indexing and retrieval"
    )