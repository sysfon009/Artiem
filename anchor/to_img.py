import sys
import os
import json
import time
import asyncio
from typing import List, Optional, Any, Tuple, Dict, AsyncGenerator
from google.genai import types
from dotenv import load_dotenv
from google import genai 
import gc
import base64
import mimetypes
import importlib
import uuid
import re
import copy 
from inst_data import inst_to_img

# ==========================================
# 0. PATH SETUP (ROOT ACCESS)
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from . import rp_core
from anchor.node_engine import engine_function
from anchor.function_executor import TOOL_MAP
from function_schema.function_tools import get_image_generator, get_image_detail

PROMPTS_DIR = os.path.join(root_dir, "prompts")

# ==========================================
# IMAGE PIPELINE (called from logic_router)
# ==========================================

async def run_pipeline(context_pack: Dict[str, Any]) -> AsyncGenerator[str, None]:
    """
    Image generation pipeline. Receives all pre-computed data from logic_router.
    Session creation & attachment processing already handled by the router.
    """
    
    # Unpack context
    char_id = context_pack["char_id"]
    current_session_id = context_pack["current_session_id"]
    current_turn = context_pack["current_turn"]
    ctx_api = context_pack["ctx_api"]
    d_resp = context_pack["d_resp"]
    gen_config = context_pack["gen_config"]
    char_data = context_pack["char_data"]
    user_message = context_pack["user_message"]
    user_data = context_pack["user_data"]

    
    resp_inst_str = inst_to_img.build_prompt(
        name=char_data.get("name", "Character"), age=char_data.get("age", "Unknown"),
        personality=char_data.get("personality", "Default"), appearance=char_data.get("appearance", "Default"),
        inst_content=char_data.get("system_instruction", ""), user_data=user_data
    ) if hasattr(inst_to_img, 'build_prompt') else "Error: Module not loaded."

    rp_core._debug_print("TO_IMG", f"Pipeline started | Intent: {context_pack.get('detected_intent')}")

    # Extract attachment filenames from ctx_api for reference
    attachment_filenames = []
    if isinstance(ctx_api, list):
        for part in ctx_api:
            if isinstance(part, dict) and "user_attachment" in part:
                fname = part["user_attachment"].get("display_name", "")
                if fname:
                    attachment_filenames.append(fname)
    
    if attachment_filenames:
        rp_core._debug_print("TO_IMG", f"Attachments available: {attachment_filenames}")

    # Prep Tools & Meta Context
    meta_context_pack = {
        "current_session_id": current_session_id, "char_id": char_id, "user_message": user_message,
        "char_data": char_data.get("name", "Character"), "current_turn_id": current_turn, "ui_image_config": gen_config.get("image_settings", {}),
        "attachment_filenames": attachment_filenames
    }
    custom_tools_list = [get_image_generator(), get_image_detail()]

    # ==========================================
    # NODE 1: MAIN LOOP (TOOL CALLING NODE)
    # ==========================================
    loop_limit = 20  
    loop_count = 0

    while loop_count < loop_limit:
        loop_count += 1
        collected_parts_node1 = []
        tool_requests = []

        # Check if the last action was generating an image
        has_generated_image = False
        generated_image_responses = []
        if len(d_resp) > 0 and d_resp[-1].get("role") == "user":
            for part in d_resp[-1].get("parts", []):
                if part.get("functionResponse", {}).get("name") == "generate_image":
                    has_generated_image = True
                    generated_image_responses.append(part.get("functionResponse", {}).get("response", {}))

        max_retries = 2 if has_generated_image else 0
        retry_count = 0
        stream_success = False

        while retry_count <= max_retries:
            collected_parts_node1.clear()
            tool_requests.clear()
            error_encountered = None

            # Stream LLM Response Node 1
            stream_gen = rp_core._stream_llm_response(
                ctx_api, 
                d_resp, 
                resp_inst_str, 
                gen_config, 
                custom_tools_list, 
                collected_parts_node1, 
                tool_requests
            )

            try:
                # Iterate through the async generator
                chunk_buffer = []
                async for chunk in stream_gen:
                    try:
                        parsed = json.loads(chunk)
                        if parsed.get("type") == "error":
                            error_encountered = parsed.get("content", "Unknown error")
                    except Exception:
                        pass
                    
                    if error_encountered:
                        break # Stop reading stream if error
                    chunk_buffer.append(chunk)

                if not error_encountered:
                    # Yield all chunks if successful
                    for c in chunk_buffer:
                        yield c
                    stream_success = True
                    break # Break retry loop

            except Exception as e:
                error_encountered = str(e)

            if error_encountered:
                rp_core._debug_print("TO_IMG", f"Stream error: {error_encountered}")
                if retry_count < max_retries:
                    retry_count += 1
                    rp_core._debug_print("TO_IMG", f"Retrying {retry_count}/{max_retries}...")
                    await asyncio.sleep(2)
                else:
                    if has_generated_image:
                        rp_core._debug_print("TO_IMG", "Max retries reached. Using fallback model response.")
                        # FALLBACK RESPONSE
                        fallback_text = "Here's the images\n"
                        # Yield the text chunk to UI
                        yield json.dumps({"type": "text", "content": fallback_text}) + "\n"
                        
                        collected_parts_node1.clear()
                        collected_parts_node1.append({"text": fallback_text})
                        
                        # Attach the images from functionResponse to the fallback model response
                        for img_resp in generated_image_responses:
                            disp_name = img_resp.get("display_name", "")
                            idata = img_resp.get("inline_data", {})
                            desc = img_resp.get("img_description", "")
                            
                            attachment_part = {
                                "user_attachment": {
                                    "display_name": disp_name,
                                    "img_description": desc,
                                    "inline_data": idata
                                }
                            }
                            collected_parts_node1.append(attachment_part)
                            # Yield fake chunk to UI just in case UI wants to see it? Actually UI reads log_final_resp mostly.
                            
                        stream_success = True
                        break # Finished fallback
                    else:
                        # No fallback available, yield the error and end
                        yield json.dumps({"type": "error", "content": error_encountered}) + "\n"
                        break

        if stream_success and collected_parts_node1:
            rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "model", collected_parts_node1, turn_id=current_turn)
            d_resp.append({"role": "model", "parts": collected_parts_node1})

        # Guard: if stream failed, stop the loop — do not execute tools
        if not stream_success:
            break

        if not tool_requests:
            break

        tasks = []
        for req in tool_requests:
            func_name, func_args = req["name"], req["args"]
            if func_name in TOOL_MAP:
                meta_context_pack["loop_index"] = loop_count - 1
                tasks.append(TOOL_MAP[func_name](func_args, meta_context=meta_context_pack))
            else:
                tasks.append(asyncio.sleep(0, result={"name": func_name, "response": {"error": "Tool not found"}}))

        results = await asyncio.gather(*tasks)
        
        has_critical_error = False
        critical_error_msg = ""
        feedback_parts = []
        for res in results:
            err = res.get("response", {}).get("error")
            if err:
                has_critical_error = True
                critical_error_msg = err
            feedback_parts.append({"functionResponse": {"name": res.get("name", "unknown"), "response": res.get("response", {})}})
            
        rp_core._log_interaction(char_id, current_session_id, "buffer_session", "user", feedback_parts, turn_id=current_turn)
        rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "user", feedback_parts, turn_id=current_turn)
        d_resp.append({"role": "user", "parts": feedback_parts})
        
        # Stop pipeline if a critical tool error occurred (e.g. Safety Block in image generation)
        if has_critical_error:
            rp_core._debug_print("TO_IMG", f"Critical tool error, stopping pipeline: {critical_error_msg}")
            yield json.dumps({"type": "error", "content": critical_error_msg}) + "\n"
            break
            
        ctx_api = [] 

    rp_core._debug_print("TO_IMG", "Pipeline finished.")

    # Memory Cleanup
    try: del collected_parts_node1, tool_requests
    except Exception: pass
    gc.collect()