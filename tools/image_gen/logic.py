import sys
import os
import time
import base64
import uuid
import mimetypes
import urllib.parse
from typing import Dict, Any, List, Tuple
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

def _extract_and_save_image(b64_str: str, mime_type: str, char_id: str, session_id: str) -> str:
    """Menyimpan gambar fisik ke dalam folder 'storage' sesi rp_core.
       Returns: absolute_filepath
    """
    safe_char_id = rp_core.sanitize_filename(char_id)
    safe_session_id = rp_core.sanitize_filename(session_id)
    histories_root = rp_core.get_histories_root(safe_char_id)
    
    storage_path = os.path.join(histories_root, safe_session_id, "storage")
    os.makedirs(storage_path, exist_ok=True)
    
    existing_gen_count = 0
    try:
        existing_gen_count = len([f for f in os.listdir(storage_path) if f.startswith("draft_")])
    except Exception:
        pass
        
    current_gen_index = existing_gen_count + 1
    ext = mime_type.split('/')[-1] if '/' in mime_type else "png"
    short_id = uuid.uuid4().hex[:6] 
    
    filename = f"draft_{current_gen_index}_image_{short_id}.{ext}"
    filepath = os.path.join(storage_path, filename)
    
    try:
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(b64_str))
            
        local_web_url = f"/assets/Characters/{safe_char_id}/Histories/{safe_session_id}/storage/{filename}"
        return local_web_url # <-- RETURN RELATIVE WEB URL
        
    except Exception as e:
        _debug_print("FILE_ERROR", f"Gagal menyimpan gambar: {e}")
        return None

async def generate_image_tool(
    char_id: str, 
    session_id: str, 
    prompt: str, 
    reference_images: List[str] = None, 
    config: Dict[str, Any] = None,
    char_data: Any = None,
    meta_context: Dict[str, Any] = None 
) -> Dict[str, Any]:
    """Fungsi Tool khusus untuk generate gambar."""
    if reference_images is None:
        reference_images = []
    if config is None:
        config = {}
        
    # Ambil turn_id dari meta_context (default ke 1 jika tidak ada)
    current_turn_id = 1
    if meta_context:
        current_turn_id = meta_context.get("current_turn_id", 1)
        # Jika char_id/session_id kosong dari args, coba ambil dari meta_context
        if not char_id: char_id = meta_context.get("char_id")
        if not session_id: session_id = meta_context.get("current_session_id")

    _debug_print("START", f"Membuat gambar untuk sesi {session_id} | Turn ID: {current_turn_id} | Prompt: {prompt}")
    load_dotenv(override=True)
    
    assigned_name = secure_config.get_assigned_key("image_model")
    current_api_key = None
    if assigned_name:
        current_api_key = secure_config.get_api_key(assigned_name)
    if not current_api_key:
        return {"error": "API Key Missing. Please set an API Key for Image Gen."}
        
    try:
        client = secure_config.get_genai_client(current_api_key)
    except Exception as e:
        return {"error": f"Failed to init client: {str(e)}"}

    # Use specified model or default for image generation
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

    # ==========================================
    # SYSTEM INSTRUCTION HANDLING
    # ==========================================
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

    result_payload = {
        "title": f"Hasil Gambar: {prompt[:40]}...",
        "status": "failed",
        "absolute_path": None,
        "image_data": None
    }
    
    payload_contents = [prompt]
    
    if reference_images:
        _debug_print("PROCESS", f"Menyisipkan {len(reference_images)} gambar referensi...")
        
        safe_char_id = rp_core.sanitize_filename(char_id)
        safe_session_id = rp_core.sanitize_filename(session_id)
        storage_path = os.path.join(rp_core.get_histories_root(safe_char_id), safe_session_id, "storage")
        
        for ref_name in reference_images:
            clean_ref_name = urllib.parse.unquote(ref_name)
            filename = clean_ref_name.split("/")[-1] 
            target_path = os.path.join(storage_path, filename)
            
            if os.path.exists(target_path):
                try:
                    with open(target_path, "rb") as f:
                        raw_bytes = f.read() 
                    mime_type, _ = mimetypes.guess_type(target_path)
                    
                    # Memberitahu Gemini: "Gambar di bawah ini adalah file X"
                    payload_contents.append(f"\n[Reference Image: {filename}]")
                    
                    payload_contents.append(
                        types.Part.from_bytes(
                            data=raw_bytes,
                            mime_type=mime_type or "image/jpeg"
                        )
                    )
                    _debug_print("PROCESS", f"Berhasil menyisipkan referensi berlabel: {filename}")
                except Exception as e:
                    _debug_print("ERROR", f"Gagal membaca referensi {target_path}: {e}")
                    
    try:
        _debug_print("API_CALL", "Memanggil Gemini API untuk menggambar...")
        response = await client.aio.models.generate_content(
            model='gemini-3-pro-image-preview', 
            contents=payload_contents, 
            config=generate_content_config
        )

        parts_list = []
        if getattr(response, "candidates", None) and response.candidates and response.candidates[0].content.parts: 
            parts_list = response.candidates[0].content.parts
        elif getattr(response, "parts", None): 
            parts_list = response.parts

        saved_url = None
        saved_abs_path = None

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
                    b64_data = raw_data if isinstance(raw_data, str) else base64.b64encode(raw_data if isinstance(raw_data, bytes) else bytes(raw_data)).decode('utf-8')
                    
                    if not saved_abs_path:
                        # Dapatkan absolute path
                        saved_abs_path = _extract_and_save_image(b64_data, mime_type, char_id, session_id)
                        
                        result_payload["status"] = "success"
                        result_payload["absolute_path"] = saved_abs_path
                        # --- PERUBAHAN PENTING: "data" diisi dengan absolute path, bukan base64 ---
                        result_payload["image_data"] = {
                            "mimeType": mime_type,
                            "data": saved_abs_path 
                        }
                        _debug_print("SUCCESS", f"Gambar berhasil di-save: {saved_abs_path}")
                        break 
        
        if result_payload["status"] == "success":
            
            try:
                current_execution_id = meta_context.get("current_execution_id")
                
                if not current_execution_id:
                    log_data_history = rp_core.read_history_file(char_id, session_id, "log_data") or []
                    exec_count_for_turn = 0
                    for entry in log_data_history:
                        if entry.get("turn_id") == current_turn_id and "execution_result" in entry:
                            exec_count_for_turn += 1
                    current_execution_id = exec_count_for_turn + 1
                
                actual_filename = os.path.basename(saved_abs_path) if saved_abs_path else "unknown_image"
                actual_mime_type = result_payload.get("image_data", {}).get("mimeType", "image/png")
                
                execution_log_entry = {
                    "execution_result": {
                        "title": actual_filename,
                        "image_path": saved_abs_path, 
                        "execution_id": current_execution_id,
                        "type": actual_mime_type
                    },
                    "turn_id": current_turn_id,
                    "timestamp": time.time(),
                }
                rp_core.append_to_history_file(char_id, session_id, "log_data", execution_log_entry)
                _debug_print("LOG_DATA", f"Saved execution_result ID {current_execution_id} for turn {current_turn_id}")
            except Exception as e:
                _debug_print("ERROR", f"Failed to save execution_result to log_data: {e}")


            
            filename = os.path.basename(saved_abs_path)
            
            try:
                gen_index = filename.split("_")[1]
            except IndexError:
                gen_index = "1"

            # RETURN JIKA SUKSES
            return {
                "text": f"[Draft Image {gen_index}] Generated successfully at {saved_abs_path}",
                "file_data": {
                    "local_path": saved_abs_path,
                    "mime_type": result_payload.get("image_data", {}).get("mimeType", "image/png")
                },
                "inline_data_payload": result_payload.get("image_data") 
            } 
            
            
    except Exception as e:
        _debug_print("API_ERROR", f"Gagal membuat gambar: {e}")
        result_payload["error"] = str(e)

    # ==========================================
    # FALLBACK SYSTEM (JIKA GAGAL / ERROR)
    # ==========================================
    error_detail = result_payload.get("error", "Unknown API Error or Blocked by Safety Filters")
    _debug_print("FALLBACK", f"Mengirim pesan error ke model: {error_detail}")
    
    return {
        "text": f"[System: Image not generated due some error. Details: {error_detail}]",
        "file_data": None,
        "inline_data_payload": None
    }