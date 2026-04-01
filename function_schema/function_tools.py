import inspect
from pydantic import BaseModel, Field
from typing import Literal, Dict, Any, List
from google.genai import types

# ==========================================
# 1. SCHEMA DEFINITIONS (PYDANTIC)
# ==========================================

# --- C. Python Code Schema ---
class CallPythonExecution(BaseModel):
    """
    Parameter schema for executing Python code.
    """
    code: str = Field(
        ...,
        description="Python code to be executed. Do not use the interactive input() function. Variables will be saved (stateful)."
    )

# --- D. Image Generation Schema (NEW) ---
class CallImageGeneration(BaseModel):
    """
    Parameter schema for generating images.
    """
    prompt: str = Field(
        ...,
        description="""write your prompt and your INSTRUCTIONS to image model in clear and detailed ."""
    )
    reference_images: List[str] = Field(
        default=[],
        description="List of image filenames (from generated images or provided by the user, example: ['image_1_cat_1234.png']). MUST be populated with relevant images matching the user's request."
    )
    aspect_ratio: Literal[
        "1:1", "16:9", "9:16", "3:4", "4:3", 
        "21:9", "3:2", "2:3", "5:4", "4:5"
    ] = Field(
        default="1:1",
        description="Choose the most suitable aspect ratio for the image."
    )
    
    resolution: Literal["1k", "2k", "3k", "4k"] = Field(
        default="1k",
        description="Adjust the resolution according to the image requirements."
    )


# --- F. Input Enhancement Schema (NEW) ---
class CallInputEnhancement(BaseModel):
    """
    Parameter schema for enhancing user input.
    """
    instructions: str = Field(
        ...,
        description="Specific instruction that you want to apply to enhance the user input. For example: 'make it more detailed', 'add more context about the setting', 'specify the subject's appearance more clearly', 'improve the clarity and coherence of the input', etc."
    )


# --- G. Get Image Detail Schema (NEW) ---
class CallGetImageDetail(BaseModel):
    """
    Parameter schema for getting image detail.
    """
    display_name: str = Field(
        ...,
        description="call this tools if you need more details and look the exact and actual image"
    )



# ==========================================
# 2. CONVERSION LOGIC (CLEANER)
# ==========================================
def pydantic_to_genai_tool(pydantic_model, func_name: str, func_desc: str):
    """
    Applies logic to clean up the Pydantic schema before 
    sending it to the Google GenAI SDK to prevent errors (Malformed Schema).
    """
    # 1. Get JSON Schema from Pydantic
    schema_dict = pydantic_model.model_json_schema()
    
    if "title" in schema_dict:
        del schema_dict["title"]
        
    if "$defs" in schema_dict:
        del schema_dict["$defs"]

    func_decl = types.FunctionDeclaration(
        name=func_name,
        description=func_desc,
        parameters=schema_dict
    )

    tool_obj = types.Tool(
        function_declarations=[func_decl]
    )
    
    return tool_obj

# ==========================================
# 3. PUBLIC GETTERS (CALLED BY RP_LOGIC)
# ==========================================


def get_python_tool():
    return pydantic_to_genai_tool(
        pydantic_model=CallPythonExecution,
        func_name="execute_python", 
        func_desc="CALL THIS TOOL to perform complex mathematical calculations, data analysis, or logic that requires Python code."
    )

# --- IMAGE GENERATOR GETTER (NEW) ---
def get_image_generator():
    return pydantic_to_genai_tool(
        pydantic_model=CallImageGeneration,
        func_name="generate_image", 
        func_desc="(Model: gemini-3-image-pro) CALL THIS TOOL specifically when the user requests to create, edit, or revise an image/photo/illustration. Use reference_images if you need references from the previous chat."
    )


def get_input_enhancement():
    return pydantic_to_genai_tool(
        pydantic_model=CallInputEnhancement,
        func_name="get_input_enhancement", 
        func_desc="CALL THIS TOOL TO IMPROVE/COMPLETE THE USER INPUT BEFORE GENERATING A PLAN."
    )

def get_image_detail():
    return pydantic_to_genai_tool(
        pydantic_model=CallGetImageDetail,
        func_name="get_image_detail", 
        func_desc="call this tools for more details and look the exact and actual image to use as analysis. This tool will give you the image that you request. "
    )

