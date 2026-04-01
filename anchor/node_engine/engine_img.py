import sys
import os
import time
import base64
import mimetypes
import urllib.parse
import asyncio  
from typing import Dict, Any, List
from dotenv import load_dotenv
from google import genai
from google.genai import types
from inst_data import inst_work_img

# ==========================================
# PATH SETUP UNTUK MENGAKSES RP_CORE
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from anchor import rp_core
from anchor import secure_config

def _debug_print(section: str, message: str, data=None):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [LOGIC_TOOL][{section}] {message}")
    if data:
        str_data = str(data)
        if len(str_data) > 200: str_data = str_data[:200] + "... [TRUNCATED]"
        print(f"   >>> {str_data}")

async def generate_image_tool(
    char_id: str, 
    session_id: str, 
    prompt: str, 
    reference_images: List[str] = None, 
    config: Dict[str, Any] = None,
    char_data: Any = None,
    meta_context: Dict[str, Any] = None 
) -> Dict[str, Any]:

    if reference_images is None:
        reference_images = []
    if config is None:
        config = {}
        
    current_turn_id = 1
    if meta_context:
        current_turn_id = meta_context.get("current_turn_id", 1)
        if not char_id: char_id = meta_context.get("char_id")
        if not session_id: session_id = meta_context.get("current_session_id")

    _debug_print("START", f"Meminta gambar ke API | Turn ID: {current_turn_id} | Prompt: {prompt}")
    load_dotenv(override=True)
    
    assigned_name = secure_config.get_assigned_key("image_model")
    current_api_key = None
    if assigned_name:
        current_api_key = secure_config.get_api_key(assigned_name)
    if not current_api_key:
        return {"status": "error", "error": "API Key Missing. Please set an API Key for Image Gen."}
        
    try:
        client = secure_config.get_genai_client(current_api_key)
    except Exception as e:
        return {"status": "error", "error": f"Failed to init client: {str(e)}"}

    try: 
        image_config = types.ImageConfig(
            aspect_ratio=config.get("aspect_ratio", "1:1"), 
            image_size=str(config.get("resolution", "1024x1024")).upper()
        )
    except AttributeError: 
        image_config = None 

    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE")
    ]

    char_name = "Character"
    if isinstance(char_data, dict):
        char_name = char_data.get("name", "Character")
    elif isinstance(char_data, str):
        char_name = char_data

    inst_str = inst_work_img.build_prompt(name=char_name)

    generate_content_config = types.GenerateContentConfig(
        temperature=float(config.get("temperature", 1.0)),
        top_p=0.95,
        response_modalities=["IMAGE"], 
        image_config=image_config,
        safety_settings=safety_settings,
        system_instruction=inst_str
    )
    
    payload_contents = [prompt]
    
    if reference_images:
        _debug_print("PROCESS", f"Menyisipkan {len(reference_images)} gambar referensi...")
        
        for ref_name in reference_images:
            clean_ref_name = urllib.parse.unquote(ref_name)
            filename = clean_ref_name.split("/")[-1] 
            
            # Encode image using rp_core helper without compression
            b64_data = rp_core.encode_image_from_storage(char_id, session_id, filename, compress=False)
            
            if b64_data:
                try:
                    mime_type, _ = mimetypes.guess_type(filename)
                    raw_bytes = base64.b64decode(b64_data)
                    
                    payload_contents.append(f"\n[Reference Image: {filename}]")
                    payload_contents.append(
                        types.Part.from_bytes(
                            data=raw_bytes,
                            mime_type=mime_type or "image/png"
                        )
                    )
                except Exception as e:
                    _debug_print("ERROR", f"Gagal memproses referensi {filename}: {e}")
            else:
                _debug_print("ERROR", f"Gagal membaca atau encode referensi: {filename}")

    # ==========================================
    # RETRY LOOP SYSTEM
    # ==========================================
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            _debug_print("API_CALL", f"Memanggil API untuk menggambar... (Attempt {attempt + 1}/{max_retries})")
            response = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model='gemini-3-pro-image-preview', 
                    contents=payload_contents, 
                    config=generate_content_config
                ),
                timeout=90
            )

            parts_list = []
            if getattr(response, "candidates", None) and response.candidates and response.candidates[0].content.parts: 
                parts_list = response.candidates[0].content.parts
            elif getattr(response, "parts", None): 
                parts_list = response.parts

            image_found = False

            for part in parts_list:
                part_dict = {}
                if hasattr(part, "model_dump"):
                    try: part_dict = part.model_dump(by_alias=True, exclude_none=True)
                    except: pass
                if hasattr(part, "model_extra") and part.model_extra: part_dict.update(part.model_extra)

                inline_obj = getattr(part, "inline_data", None)
                inline_dict = part_dict.get("inlineData") or part_dict.get("inline_data") or {}
                
                if inline_obj or inline_dict:
                    raw_data = getattr(inline_obj, "data", None) if inline_obj else inline_dict.get("data")
                    mime_type = getattr(inline_obj, "mime_type", None) if inline_obj else inline_dict.get("mimeType", "image/png")
                    
                    if raw_data:
                        image_found = True
                        if isinstance(raw_data, str):
                            image_bytes = base64.b64decode(raw_data)
                            b64_string = raw_data
                        else:
                            image_bytes = bytes(raw_data)
                            b64_string = base64.b64encode(image_bytes).decode('utf-8')
                            
                        _debug_print("SUCCESS", "Gambar berhasil diterima dari API.")
                        
                        return {
                            "status": "success",
                            "text": "[System: Image successfully generated by engine.]",
                            "mime_type": mime_type,
                            "image_bytes": image_bytes,
                            "image_base64": b64_string
                        } 
            
            
            if not image_found:
                raise ValueError("No image data found in API response parts (Possible Safety Block or Empty Response).")

        except Exception as e:
            _debug_print("API_ERROR", f"Attempt {attempt + 1} failed: {e}")
            
            error_str = str(e).lower()
            if "429" in error_str or "resource exhausted" in error_str:
                retry_delay = max(retry_delay, 15)
            
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2 
            else:
               
                return {
                    "status": "error",
                    "text": f"[System: Image not generated after {max_retries} attempts. Details: {str(e)}]",
                    "error": str(e)
                }

    return {
        "status": "error",
        "text": "[System: Unknown error in generation loop.]",
        "error": "Unknown loop escape."
    }