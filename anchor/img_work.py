import sys
import os
import json
import asyncio
import time
import uuid
import copy
import base64
from typing import List, Optional, Any, Tuple, Dict, AsyncGenerator
import gc

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from . import rp_core
from anchor.node_engine import img_engine_work
from inst_data import inst_work_img

# ==========================================
# IMG_WORK: Direct Image Pipeline (No Function Calling)
# ==========================================

async def run_logic_system(
    char_id: str, session_id: Optional[str], user_message: str,
    char_data: Dict[str, Any], user_data: Dict[str, Any], gen_config: Dict[str, Any], attachment: Optional[list] = None
) -> AsyncGenerator[str, None]:

    # ==========================================
    # 1. INIT SESSION
    # ==========================================
    current_session_id, is_new, current_turn, d_resp = rp_core._handle_session_setup(char_id, session_id, user_message, char_data)
    if not current_session_id:
        yield json.dumps({"type": "error", "content": "Failed creating session"}) + "\n"
        yield json.dumps({"type": "signal", "content": "done"}) + "\n"
        return
    yield json.dumps({"session_id": current_session_id}) + "\n"
    rp_core._debug_print("IMG_WORK", f"Turn ID set to {current_turn}")

    # ==========================================
    # 2. PROCESS ATTACHMENTS
    # ==========================================
    ctx_api, ctx_history = await rp_core._process_attachments(char_id, current_session_id, user_message, attachment, turn_id=current_turn)
    ctx_api = ctx_api if ctx_api else user_message

    rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "user", ctx_history if ctx_history else user_message, turn_id=current_turn)

    # ==========================================
    # 3. SETUP INSTRUCTION (Image-specific)
    # ==========================================
    char_name = char_data.get("name", "Character")
    resp_inst_str = inst_work_img.build_prompt(name=char_name)

    rp_core._debug_print("IMG_WORK", "Pipeline started (Direct Image Mode)")

    # ==========================================
    # 4. PREPARE CONFIG FOR IMAGE ENGINE
    # ==========================================
    image_config = copy.deepcopy(gen_config)
    image_config["_char_id"] = char_id
    image_config["_session_id"] = current_session_id

    if "model" not in image_config:
        image_config["model"] = "gemini-3-pro-image-preview"

    # ==========================================
    # 5. RESOLVE HISTORY (using specialized image history resolver)
    
    # ==========================================
    resolved_history = rp_core._resolve_img_history(d_resp, char_id, current_session_id)

    # ==========================================
    # 6. CALL IMAGE ENGINE DIRECTLY
    # ==========================================
    rp_core._debug_print("IMG_WORK", "Calling img_engine_work directly...")

    collected_parts = []
    current_text_buffer = ""
    pending_signature = None
    image_count = 0

    try:
        async for chunk in img_engine_work.generate(
            context=ctx_api,
            history=resolved_history,
            instruction=resp_inst_str,
            config=image_config,
            custom_tools=None
        ):
            chunk_type = chunk.get("type")
            content = chunk.get("content")

            # Extract signature if attached to this chunk
            incoming_sig = chunk.get("thought_signature")
            if chunk_type == "thought_signature": incoming_sig = content
            if incoming_sig and chunk_type != "thought_signature": pending_signature = incoming_sig

            # --- TEXT ---
            if chunk_type == "text":
                current_text_buffer += content
                yield json.dumps(chunk) + "\n"

            # --- THOUGHT ---
            elif chunk_type == "thought":
                # Flush text buffer first
                if current_text_buffer:
                    collected_parts.append({"text": current_text_buffer})
                    current_text_buffer = ""
                # Build thought part: {text: ..., thought: True}
                new_part = {"text": content, "thought": True}
                if pending_signature:
                    # Save signature to file instead of storing massive base64 inline
                    sig_ref = rp_core.save_thought_signature(char_id, current_session_id, pending_signature, current_turn)
                    new_part["thought_signature"] = sig_ref
                    pending_signature = None
                collected_parts.append(new_part)
                yield json.dumps(chunk) + "\n"

            # --- IMAGE ---
            elif chunk_type == "image":
                # Flush text buffer first
                if current_text_buffer:
                    collected_parts.append({"text": current_text_buffer})
                    current_text_buffer = ""

                mime = content.get("mime_type", "image/png")
                b64_img = content.get("data", "")
                image_count += 1

                # Save image to storage
                image_bytes = base64.b64decode(b64_img)
                saved_info = _save_image_to_storage(char_id, current_session_id, image_bytes, mime, image_count)
                filename = saved_info["filename"]

                rp_core._debug_print("IMG_WORK", f"Image saved: {filename}")

                # Describe the image
                img_desc = await rp_core.describe_image_helper(b64_img, mime)

                # Log to log_data
                _log_image_to_data(char_id, current_session_id, current_turn, filename, mime, img_desc)

                # Add to collected parts with LOCAL_FILE tag for lightweight storage
                collected_parts.append({
                    "user_attachment": {
                        "display_name": filename,
                        "img_description": img_desc,
                        "inline_data": {
                            "mime_type": mime,
                            "data": f"LOCAL_FILE:{filename}"
                        }
                    }
                })

                # Log to log_image (full base64 archive)
                log_image_entry = {
                    "name": "img_work_generation",
                    "response": {
                        "display_name": filename,
                        "img_description": img_desc,
                        "inline_data": {
                            "mime_type": mime,
                            "data": b64_img
                        }
                    }
                }
                rp_core._log_interaction(char_id, current_session_id, "log_image", "model", log_image_entry, turn_id=current_turn)

                # Yield image chunk to UI
                yield json.dumps(chunk) + "\n"

            # --- THOUGHT SIGNATURE (orphan / standalone) ---
            elif chunk_type == "thought_signature":
                if current_text_buffer:
                    sig_ref = rp_core.save_thought_signature(char_id, current_session_id, incoming_sig, current_turn)
                    collected_parts.append({"text": current_text_buffer, "thought_signature": sig_ref})
                    current_text_buffer = ""
                    pending_signature = None
                elif collected_parts and "code_execution_result" not in collected_parts[-1]:
                    sig_ref = rp_core.save_thought_signature(char_id, current_session_id, incoming_sig, current_turn)
                    collected_parts[-1]["thought_signature"] = sig_ref
                    pending_signature = None
                else:
                    pending_signature = incoming_sig

            # --- EXECUTABLE CODE ---
            elif chunk_type == "executable_code":
                if current_text_buffer:
                    collected_parts.append({"text": current_text_buffer})
                    current_text_buffer = ""
                code_part = {"executable_code": content}
                if pending_signature:
                    sig_ref = rp_core.save_thought_signature(char_id, current_session_id, pending_signature, current_turn)
                    code_part["thought_signature"] = sig_ref
                    pending_signature = None
                collected_parts.append(code_part)
                yield json.dumps(chunk) + "\n"

            # --- CODE EXECUTION RESULT ---
            elif chunk_type == "code_execution_result":
                if current_text_buffer:
                    collected_parts.append({"text": current_text_buffer})
                    current_text_buffer = ""
                collected_parts.append({"code_execution_result": content})
                yield json.dumps(chunk) + "\n"

            # --- ERROR ---
            elif chunk_type == "error":
                rp_core._debug_print("IMG_WORK", f"Engine error: {content}")
                yield json.dumps(chunk) + "\n"

        # Flush remaining text buffer
        if current_text_buffer:
            final_part = {"text": current_text_buffer}
            if pending_signature:
                sig_ref = rp_core.save_thought_signature(char_id, current_session_id, pending_signature, current_turn)
                final_part["thought_signature"] = sig_ref
                pending_signature = None
            collected_parts.append(final_part)
        elif pending_signature and collected_parts:
            sig_ref = rp_core.save_thought_signature(char_id, current_session_id, pending_signature, current_turn)
            collected_parts[-1]["thought_signature"] = sig_ref

        # Save model response to log_final_resp
        if collected_parts:
            rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "model", collected_parts, turn_id=current_turn)

    except Exception as e:
        rp_core._debug_print("IMG_WORK", f"Error during generation: {e}")
        yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    rp_core._debug_print("IMG_WORK", f"Pipeline finished. Images generated: {image_count}")
    yield json.dumps({"type": "signal", "content": "done"}) + "\n"

    # Memory Cleanup
    try: del d_resp, resolved_history, collected_parts, ctx_api, ctx_history
    except Exception: pass
    gc.collect()


# ==========================================
# HELPER: Save Image to Storage
# ==========================================
def _save_image_to_storage(char_id: str, session_id: str, image_bytes: bytes, mime_type: str, index: int) -> dict:
    from PIL import Image
    import io

    safe_char_id = rp_core.sanitize_filename(char_id)
    safe_session_id = rp_core.sanitize_filename(session_id)

    histories_root = rp_core.get_histories_root(safe_char_id)
    storage_path = os.path.join(histories_root, safe_session_id, "storage")
    os.makedirs(storage_path, exist_ok=True)

    existing_count = 0
    try:
        existing_count = len([f for f in os.listdir(storage_path) if f.startswith("draft_")])
    except Exception:
        pass

    gen_index = existing_count + 1
    short_id = uuid.uuid4().hex[:6]
    filename = f"draft_{gen_index}_image_{short_id}.png"

    physical_filepath = os.path.join(storage_path, filename)
    image_path = f"/assets/Characters/{safe_char_id}/Histories/{safe_session_id}/storage/{filename}"

    img = Image.open(io.BytesIO(image_bytes))
    img.save(physical_filepath, format="PNG")

    return {
        "filename": filename,
        "physical_path": physical_filepath,
        "image_path": image_path
    }


# ==========================================
# HELPER: Log Image to log_data
# ==========================================
def _log_image_to_data(char_id: str, session_id: str, turn_id: int, filename: str, mime_type: str, img_desc: str):
    """Log image generation result to log_data for tracking."""
    try:
        log_data_history = rp_core.read_history_file(char_id, session_id, "log_data") or []
        exec_count = sum(1 for entry in log_data_history if entry.get("turn_id") == turn_id and "execution_result" in entry)
        execution_id = exec_count + 1
    except Exception:
        execution_id = 1

    execution_log_entry = {
        "execution_result": {
            "display_name": filename,
            "img_description": img_desc,
            "execution_id": execution_id,
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
    except Exception as e:
        print(f"[IMG_WORK] Failed to save to log_data: {e}")
