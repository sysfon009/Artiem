import sys
import os
import json
import time
import asyncio
import uuid
import re
import base64
import mimetypes
from typing import List, Optional, Any, Tuple, Dict, AsyncGenerator
from google.genai import types
from dotenv import load_dotenv
from google import genai 
import gc

# ==========================================
# 0. PATH SETUP (ROOT ACCESS)
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)


from anchor import rp_core
from anchor.node_engine import engine_function
from anchor.node_engine import engine_img
from node_schema.sc_img_analysis import ImageAnalysis


def _debug_print(section, message, data=None):
    rp_core._debug_print(section, message, data)

PROMPTS_DIR = os.path.join(root_dir, "prompts")

def _load_prompt(filename: str) -> str:
    """
    Membaca file text dari folder 'prompts'
    """
    target_path = os.path.join(PROMPTS_DIR, filename)
    
    if not os.path.exists(target_path):
        _debug_print("WARNING", f"Prompt file not found: {filename}")
        return ""
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        _debug_print("ERROR", f"Failed reading prompt {filename}: {e}")
        return ""

    
def _extract_json_string(text: str) -> str:
    """Helper to robustly extract JSON from mixed text/markdown output."""
    clean_text = text.replace('\\"', '"').replace('\\n', '\n')
    # Try to find JSON pattern (object or array)
    json_match = re.search(r'[\{\[].*[\}\]]', clean_text, re.DOTALL)
    if json_match:
        return json_match.group(0).strip()
    # Fallback to manual parsing
    start_brace = clean_text.find('{')
    start_bracket = clean_text.find('[')
    if start_brace == -1 and start_bracket == -1:
        return clean_text
    start_idx = start_brace if start_bracket == -1 else (start_bracket if start_brace == -1 else min(start_brace, start_bracket))
    is_array = clean_text[start_idx] == '['
    end_char = ']' if is_array else '}'
    end_idx = clean_text.rfind(end_char)
    if end_idx != -1 and end_idx > start_idx:
        return clean_text[start_idx:end_idx+1]
    return clean_text



def _load_image_from_storage(char_id: str, session_id: str, image_title: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Helper untuk memuat file gambar dari direktori storage lokal
    berdasarkan judul gambar. Supports multiple filename patterns:
    - Exact match: "attachment_1_089735f9.jpeg"
    - Prefix match: "attachment_1_" 
    - Substring match: partial name within filename
    """
    try:
        safe_char = rp_core.sanitize_filename(char_id)
        safe_session = rp_core.sanitize_filename(session_id)
        storage_path = os.path.join(rp_core.get_histories_root(safe_char), safe_session, "storage")

        if not os.path.exists(storage_path):
            return None, None

        # Ekstrak nama file saja, jaga-jaga kalau AI mengirim absolute/relative path
        clean_title = os.path.basename(image_title).strip()
        all_files = os.listdir(storage_path)
        
        # Strategy 1: Exact match
        if clean_title in all_files:
            filepath = os.path.join(storage_path, clean_title)
            mime_type, _ = mimetypes.guess_type(filepath)
            with open(filepath, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode('utf-8')
            return b64_data, mime_type or "image/jpeg"
        
        # Strategy 2: Extract attachment index and match prefix (attachment_N_)
        match = re.search(r"attachment[_\s]*(\d+)", clean_title)
        if match:
            idx = match.group(1)
            target_prefix = f"attachment_{idx}_"
            for filename in all_files:
                if filename.startswith(target_prefix):
                    filepath = os.path.join(storage_path, filename)
                    mime_type, _ = mimetypes.guess_type(filepath)
                    with open(filepath, "rb") as f:
                        b64_data = base64.b64encode(f.read()).decode('utf-8')
                    return b64_data, mime_type or "image/jpeg"
        
        # Strategy 3: Substring/prefix match (for draft_ or other patterns)
        for filename in all_files:
            if filename.startswith(clean_title) or clean_title in filename:
                filepath = os.path.join(storage_path, filename)
                mime_type, _ = mimetypes.guess_type(filepath)
                with open(filepath, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode('utf-8')
                return b64_data, mime_type or "image/jpeg"
        
        _debug_print("LOAD_IMG", f"No match found for '{clean_title}' in storage. Available: {all_files[:5]}")
                
    except Exception as e:
        print(f"[EXECUTOR] Error loading image from storage: {e}")
    return None, None

def save_generated_image(char_id: str, session_id: str, image_bytes: bytes, mime_type: str) -> dict:
    """
    Menyimpan bytes gambar ke folder storage dan mengembalikan path fisik & path aset.
    Selalu menyimpan sebagai PNG (lossless) untuk menjaga kualitas gambar.
    """
    from PIL import Image
    import io
    
    safe_char_id = rp_core.sanitize_filename(char_id)
    safe_session_id = rp_core.sanitize_filename(session_id)
    
    # Path fisik untuk proses 'write' (save file di OS)
    histories_root = rp_core.get_histories_root(safe_char_id)
    storage_path = os.path.join(histories_root, safe_session_id, "storage")
    os.makedirs(storage_path, exist_ok=True)
    
    # Hitung draft yang sudah ada untuk penomoran
    existing_gen_count = 0
    try:
        existing_gen_count = len([f for f in os.listdir(storage_path) if f.startswith("draft_")])
    except Exception:
        pass
        
    current_gen_index = existing_gen_count + 1
    
    # Generate UUID pendek agar nama file unik
    short_id = uuid.uuid4().hex[:6] 
    filename = f"draft_{current_gen_index}_image_{short_id}.png"
    
    # 1. Path Fisik (Absolute) -> Untuk simpan/baca file di hardisk
    physical_filepath = os.path.join(storage_path, filename)
    
    # 2. Image Path (Relative) -> Untuk dikirim ke UI/log_data
    image_path = f"/assets/Characters/{safe_char_id}/Histories/{safe_session_id}/storage/{filename}"
    
    # Selalu simpan sebagai PNG (lossless) untuk menjaga kualitas
    img = Image.open(io.BytesIO(image_bytes))
    img.save(physical_filepath, format="PNG")
        
    return {
        "filename": filename,
        "physical_path": physical_filepath,
        "image_path": image_path 
    }

# ==========================================
# 2. HELPER: LOG DATA HISTORY
# ==========================================
def log_execution_result(char_id: str, session_id: str, turn_id: int, filename: str, mime_type: str, img_desc: str, meta_context: dict = None) -> bool:
    """
    Mencatat riwayat eksekusi gambar khusus ke dalam log_data.
    """
    current_execution_id = meta_context.get("current_execution_id") if meta_context else None
        
    # Kalkulasi execution_id jika tidak disuplai
    if not current_execution_id:
        try:
            log_data_history = rp_core.read_history_file(char_id, session_id, "log_data") or []
            exec_count_for_turn = 0
            for entry in log_data_history:
                if entry.get("turn_id") == turn_id and "execution_result" in entry:
                    exec_count_for_turn += 1
            current_execution_id = exec_count_for_turn + 1
        except Exception:
            current_execution_id = 1
            
    # Format JSON disesuaikan agar strukturnya mirip dengan buffer_payload
    execution_log_entry = {
        "execution_result": {
            "display_name": filename,
            "img_description": img_desc,
            "execution_id": current_execution_id,
            "inline_data": {
                "mime_type": mime_type,
                "data": f"LOCAL_FILE:{filename}"
            }
        },
        "turn_id": turn_id,
        "timestamp": time.time()
    }
    
    try:
        rp_core.append_to_history_file(char_id, session_id, "log_data", execution_log_entry)
        return True
    except Exception as e:
        print(f"[HELPER_ERROR] Gagal menyimpan ke log_data: {e}")
        return False



#----------------------------------------------------------------------------------

async def generate_image_wrapper(args: dict, meta_context: dict = None) -> dict:
    print(f"\n[EXECUTOR] 🎨 Starting Image Generation. Args: {args}")
    
    if not meta_context:
        return {"name": "generate_image", "response": {"error": "Meta Context Missing"}}

    current_session_id = meta_context["current_session_id"]
    char_id = meta_context["char_id"]
    current_turn_id = meta_context.get("current_turn_id", 1)
    
    prompt = args.get("prompt", "")
    char_name = meta_context.get("char_data", "Character")
    ref_images = args.get("reference_images", [])

    # ==========================================
    # Setup Konfigurasi (Resolusi & Aspect Ratio)
    # ==========================================
    ui_config = meta_context.get("ui_image_config", {
        "aspect_ratio": "Auto", 
        "resolution": "Auto", 
        "temperature": 1.0
    })

    ui_ratio = ui_config.get("aspect_ratio", "Auto")
    ai_ratio_choice = args.get("aspect_ratio", "1:1") 
    
    if str(ui_ratio).lower() == "auto":
        final_ratio = ai_ratio_choice
        print(f"[EXECUTOR] Aspect Ratio: AUTO dipicu, menggunakan pilihan AI -> {final_ratio}")
    else:
        final_ratio = ui_ratio
        print(f"[EXECUTOR] Aspect Ratio: Terkunci dari UI -> {final_ratio}")

    ui_config["aspect_ratio"] = final_ratio

    ui_res = ui_config.get("resolution", "Auto")
    ai_resolution_choice = args.get("resolution", "1k")
    
    if str(ui_res).lower() == "auto":
        final_resolution = ai_resolution_choice
        print(f"[EXECUTOR] Resolution: AUTO dipicu, menggunakan pilihan AI -> {final_resolution}")
    else:
        final_resolution = ui_res
        print(f"[EXECUTOR] Resolution: Terkunci dari UI -> {final_resolution}")
        
    ui_config["resolution"] = final_resolution

    # ==========================================
    # 1. Panggil Engine Murni 
    # ==========================================
    engine_result = await engine_img.generate_image_tool(
        char_id=char_id,
        session_id=current_session_id, 
        prompt=prompt, 
        reference_images=ref_images, 
        config=ui_config,
        char_data=char_name,
        meta_context=meta_context 
    )

    if engine_result.get("status") != "success":
        print(f"[EXECUTOR] ❌ Image Generation Failed: {engine_result.get('error')}")
        return {
            "name": "generate_image", 
            "response": {"error": engine_result.get("error", "Unknown API Error")} 
        }

    # ==========================================
    # 2. Proses Penyimpanan Fisik & Log Data
    # ==========================================
    image_bytes = engine_result["image_bytes"]
    image_base64 = engine_result["image_base64"]
    mime_type = engine_result["mime_type"]

    # Simpan file ke hardisk (menggunakan helper)
    saved_info = save_generated_image(char_id, current_session_id, image_bytes, mime_type)
    filename = saved_info["filename"]
    # image_path sudah tidak dikirim lagi ke helper karena diganti dengan inline_data

    # Describe the generated image
    img_desc = await rp_core.describe_image_helper(image_base64, mime_type)

    # Catat ke log_data (Memakai format baru dengan inline_data)
    log_execution_result(
        char_id=char_id, 
        session_id=current_session_id, 
        turn_id=current_turn_id, 
        filename=filename, 
        mime_type=mime_type, 
        img_desc=img_desc,
        meta_context=meta_context
    )

    # ==========================================
    # 4. Log ke log_image (Berisi BASE64 asli untuk arsip)
    # ==========================================
    log_image_entry = {
        "name": "generate_image",
        "response": {
            "display_name": filename,
            "img_description": img_desc,
            "inline_data": {
                "mime_type": mime_type,
                "data": image_base64  
            }
        },
    }
    rp_core._log_interaction(char_id, current_session_id, "log_image", "user", log_image_entry, turn_id=current_turn_id)

    # ==========================================
    # 5. Return ke Pemanggil / API (Berisi FLAG LOCAL_FILE)
    # ==========================================
    print(f"[EXECUTOR] 📤 Returning filename reference to caller/API: {filename}")
    return {
        "name": "generate_image",
        "response": {
            "display_name": filename,
            "img_description": img_desc,
            "inline_data": {
                "mime_type": mime_type,
                "data": f"LOCAL_FILE:{filename}"
            }
        },
    }



async def get_input_enhancement_wrapper(args: dict, meta_context: dict = None) -> dict:
    print(f"\n[EXECUTOR] 🧠 Enhancing Input.")
    
    target_input = meta_context.get("ctx_node_input", meta_context.get("user_message", ""))
    
    context = [{"text": "Below is the original input that needs to be enhanced:"}]
    
    if isinstance(target_input, list):
        context.extend(target_input)
    else:
        context.append({"text": str(target_input)})
        
    context.append({"text": "Task: Enhance this input contextually so it fills any holes or ambiguity based on standard prompt engineering principles."})
    
    enhancement_instruction = "Process and enhance the input objectively, completely, and accurately based on the prompt engineering requirements. Output only the enhanced result without any conversational filler."
    
    collected_parts = []
    tool_reqs = []
    
    await rp_core.non_stream_llm_response(
        context=context, 
        history=[], 
        instruction=enhancement_instruction,
        config={"temperature": 0.7, "max_output_tokens": 4096},
        custom_tools=None,
        out_collected_parts=collected_parts,
        out_tool_reqs=tool_reqs
    )
    
    # Extract text output from collected parts (skip thoughts)
    output_text = ""
    for part in collected_parts:
        if part.get("thought"):
            continue
        if "text" in part and part["text"]:
            output_text += part["text"]
    
    if not output_text:
        output_text = "[Enhancement failed: no output]"
    
    char_id = meta_context.get("char_id")
    session_id = meta_context.get("current_session_id")
    
    # ==========================================
    # Log ke log_tools
    # ==========================================
    current_turn_id = meta_context.get("current_turn_id", 1)
    
    log_format = {
        "parts": {
            "user_input_used": str(target_input)[:500] + ("..." if len(str(target_input)) > 500 else ""),
            "tools": {
                "user_input_enhancement": {
                    "output": output_text
                }
            }
        }
    }
    
    rp_core._log_interaction(char_id, session_id, "log_tools", "model", log_format, turn_id=current_turn_id)
    
    # ==========================================
    # Save ke log_data (Request Enhancement Result)
    # ==========================================
    try:
        request_enhancement_data = {
            "request_enchancement_result": {
                "user_input_enhancement": output_text
            },
            "timestamp": time.time(),
            "turn_id": current_turn_id
        }
        rp_core.append_to_history_file(
            char_id, 
            session_id, 
            "log_data", 
            request_enhancement_data
        )
        print(f"[EXECUTOR] ✅ Saved request enhancement result to log_data")
    except Exception as e:
        print(f"[EXECUTOR] ⚠️  Warning: Could not save to log_data: {e}")
    
    return {
        "name": "get_input_enhancement",
        "response": {"result": output_text}
    }

async def get_image_analysis_wrapper(args: dict, meta_context: dict = None) -> dict:
    # 1. Pastikan input jadi list
    image_titles = args.get("image_title", [])
    if isinstance(image_titles, str):
        image_titles = [image_titles]
        
    char_id = meta_context.get("char_id")
    session_id = meta_context.get("current_session_id")
    current_turn_id = meta_context.get("current_turn_id", 1)
    
    print(f"\n[EXECUTOR] 🔍 Analyzing Images: {image_titles}")
    
    # 2. Siapkan Context Awal menggunakan sy_img_analysis.txt
    instruction_text = _load_prompt("sy_img_analysis.txt")
    if not instruction_text:
        instruction_text = "Analyze the following images comprehensively. Describe the visual elements, style, subject, and any relevant details for each."
        print("[EXECUTOR] ⚠️ WARNING: sy_img_analysis.txt file not found. Using default instructions.")
        
    context = []
    
    # 3. Looping untuk load tiap gambar dan tempel ke context
    for title in image_titles:
        b64_data, mime_type = _load_image_from_storage(char_id, session_id, title)
        
        if b64_data:
            context.append({"text": f"Image Title: {title}"})
            context.append({"inline_data": {"mime_type": mime_type, "data": b64_data}})
        else:
            context.append({"text": f"Image Title: {title} (Note: Local image data could not be loaded, please infer the analysis based on its title or prior context)."})
    
    collected_parts = []
    tool_reqs = []
    
    await rp_core.non_stream_llm_response(
        context=context, 
        history=[], 
        instruction=instruction_text,
        config={
            "response_mime_type": "application/json",
            "response_schema": ImageAnalysis
        },
        custom_tools=None,
        out_collected_parts=collected_parts,
        out_tool_reqs=tool_reqs
    )
    
    # Extract text output from collected parts (skip thoughts)
    output_text = ""
    for part in collected_parts:
        if part.get("thought"):
            continue
        if "text" in part and part["text"]:
            output_text += part["text"]
    
    if not output_text:
        output_text = "[Analysis failed: no output]"
    
    # Simpan ke log_tools
    log_format = {
        "parts": {
            "image_title": image_titles,
            "tools": {
                "image_analysis": {
                    "output": output_text
                }
            }
        }
    }
    rp_core._log_interaction(char_id, session_id, "log_tools", "model", log_format, turn_id=current_turn_id)
    
    # --- TAMBAHAN PENYIMPANAN KE LOG_DATA AGAR KONSISTEN ---
    try:
        analysis_data = {
            "image_analysis_result": {
                "images": image_titles,
                "analysis": output_text
            },
            "timestamp": time.time(),
            "turn_id": current_turn_id
        }
        rp_core.append_to_history_file(
            char_id, 
            session_id, 
            "log_data", 
            analysis_data
        )
        print(f"[EXECUTOR] ✅ Saved image analysis result to log_data")
    except Exception as e:
        print(f"[EXECUTOR] ⚠️ Warning: Could not save image analysis to log_data: {e}")
    
    return {
        "name": "get_image_analysis",
        "response": {"result": output_text}
    }


async def get_image_detail_wrapper(args: dict, meta_context: dict = None) -> dict:
    display_name = args.get("display_name", "")
    char_id = meta_context.get("char_id")
    session_id = meta_context.get("current_session_id")
    current_turn_id = meta_context.get("current_turn_id", 1)
    
    print(f"\n[EXECUTOR] 🔍 Getting Image Detail for: {display_name}")
    
    log_data_history = rp_core.read_history_file(char_id, session_id, "log_data") or []
    
    target_entry = None
    target_type = None
    
    # Retrieve the inline data using matching display_name on either execution_result or user_attachment
    for entry in reversed(log_data_history):
        if "execution_result" in entry and entry["execution_result"].get("display_name") == display_name:
            target_entry = entry["execution_result"]
            target_type = "execution_result"
            break
        elif "user_attachment" in entry and entry["user_attachment"].get("display_name") == display_name:
            target_entry = entry["user_attachment"]
            target_type = "user_attachment"
            break

    if not target_entry:
        return {"name": "get_image_detail", "response": {"error": f"Image {display_name} not found in log_data."}}

    inline_data = target_entry.get("inline_data", {})
    mime_type = inline_data.get("mime_type", "image/jpeg")
    
    b64_data = rp_core.encode_image_from_storage(char_id, session_id, display_name)
    if not b64_data:
        b64_data, mt = _load_image_from_storage(char_id, session_id, display_name)
        if mt: mime_type = mt
    
    if b64_data:
        result_data = {
            "display_name": display_name,
            "inline_data": {
                "mime_type": mime_type,
                "data": b64_data
            }
        }
        
        if target_type == "execution_result":
            result_data["execution_id"] = target_entry.get("execution_id")
            final_response = {"execution_result": result_data}
        else:
            result_data["attachment_id"] = target_entry.get("attachment_id", target_entry.get("user_attachment_id"))
            final_response = {"user_attachment": result_data}
            
        final_response["turn_id"] = target_entry.get("turn_id", current_turn_id)
        final_response["timestamp"] = time.time()

        # Save ke log_image (versi lengkap dengan inline_data)
        full_log_entry = {
            "name": "get_image_detail",
            "response": final_response,
        }
        rp_core._log_interaction(char_id, session_id, "log_image", "user", full_log_entry, turn_id=current_turn_id)

        # Log ke log_tools
        log_format = {
            "parts": {
                "display_name": display_name,
                "tools": {
                    "get_image_detail": {
                        "status": "success",
                        "found_type": target_type
                    }
                }
            }
        }
        rp_core._log_interaction(char_id, session_id, "log_tools", "model", log_format, turn_id=current_turn_id)

        # ==========================================
        # Return ke API (berisi BASE64 lengkap)
        # ==========================================
        return {
            "name": "get_image_detail",
            "response": final_response
        }
    else:
        return {"name": "get_image_detail", "response": {"error": "Failed to load image base64 data from storage."}}


TOOL_MAP = {
    "generate_image": generate_image_wrapper,
    "get_input_enhancement": get_input_enhancement_wrapper,
    "get_image_analysis": get_image_analysis_wrapper,
    "get_image_detail": get_image_detail_wrapper
}