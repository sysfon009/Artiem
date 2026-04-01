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
from function_schema.function_tools import get_image_generator
from node_schema.sc_img_intent import UserIntentDetection

from anchor import to_img
from anchor import to_text

PROMPTS_DIR = os.path.join(root_dir, "prompts")

# ==========================================
# 3. MAIN RUNNER 
# ==========================================
async def run_logic_system(
    char_id: str, session_id: Optional[str], user_message: str,
    char_data: Dict[str, Any], user_data: Dict[str, Any], gen_config: Dict[str, Any], attachment: Optional[list] = None
) -> AsyncGenerator[str, None]:
    
    # 1. Init Session
    current_session_id, is_new, current_turn, d_resp = rp_core._handle_session_setup(char_id, session_id, user_message, char_data)
    if not current_session_id:
        yield json.dumps({"type": "error", "content": "Failed creating session"}) + "\n"
        yield json.dumps({"type": "signal", "content": "done"}) + "\n"
        return
    yield json.dumps({"session_id": current_session_id}) + "\n"
    rp_core._debug_print("TURN", f"Turn ID set to {current_turn}")


    # 3. Process Attachments & Update History
    ctx_api, ctx_history = await rp_core._process_attachments(char_id, current_session_id, user_message, attachment, turn_id=current_turn)
    ctx_api = ctx_api if ctx_api else user_message
    
    rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "user", ctx_history if ctx_history else user_message, turn_id=current_turn)
    # resolved_history removed as intent detection doesn't need it and sub-pipelines use d_resp

    # ==========================================
    # NODE 1: Intent Detection (Structured Output)
    # ==========================================
    rp_core._debug_print("INTENT", "Starting intent detection...")
    
    intent_history = []
    if d_resp:
        for entry in reversed(d_resp):
            if entry.get("role") == "model":
                intent_history.append(entry)
                break
    
    # Tambahkan debug agar terlihat jelas
    rp_core._debug_print("INTENT", f"Extracted history length: {len(intent_history)}")
    if intent_history:
        try:
            parts = intent_history[0].get("parts", [])
            sample = parts[0].get("text", "")[:50] if parts else ""
            rp_core._debug_print("INTENT", f"History model sample: {sample}...")
        except Exception:
            pass
                
    intent_config = {
        "model": gen_config.get("model", "gemini-3-flash-preview"),
        "response_mime_type": "application/json",
        "response_schema": UserIntentDetection,
    }
    
    collected_parts_intent = []
    tool_reqs_intent = []  # not used for structured output, but required by the function
    
    await rp_core.non_stream_llm_response(
        context=ctx_api,
        history=intent_history,
        instruction="Analyze the user's message and determine the intent. Classify as: create_image (user wants to generate a new image), image_to_image (user provides an image and wants it modified), discussion (general conversation), or unspecified (unclear intent).",
        config=intent_config,
        custom_tools=None,
        out_collected_parts=collected_parts_intent,
        out_tool_reqs=tool_reqs_intent
    )
    
    # Parse intent result
    detected_intent = None
    intent_raw_text = None
    
    for part in collected_parts_intent:
        # Skip thought parts — they contain thinking output, not the structured JSON
        if part.get("thought"):
            continue
        if "text" in part and part["text"]:
            intent_raw_text = part["text"]
            break
    
    if intent_raw_text:
        try:
            intent_data = json.loads(intent_raw_text)
            intent_item = intent_data.get("user_intents_detection", {})
            detected_intent = intent_item.get("intent")
            confidence = intent_item.get("confidence", 0)
            snippet = intent_item.get("snippet", "")
            rp_core._debug_print("INTENT", f"Detected: {detected_intent} | Confidence: {confidence} | Snippet: {snippet}")
        except (json.JSONDecodeError, AttributeError, KeyError) as e:
            rp_core._debug_print("INTENT", f"Failed to parse intent JSON: {e}")
            rp_core._debug_print("INTENT", f"Raw text was: {intent_raw_text}")
    else:
        # Check if there was an error in the response
        for part in collected_parts_intent:
            if "text" in part and "Error" in part.get("text", ""):
                rp_core._debug_print("INTENT", f"Intent detection returned error: {part['text']}")
                break
    
    # Log intent result to buffer_session (NOT log_final_resp)
    if collected_parts_intent:
        rp_core._log_interaction(char_id, current_session_id, "buffer_session", "model", collected_parts_intent, turn_id=current_turn)
    
    # ==========================================
    # NODE 2: Route based on intent
    # ==========================================
    if not detected_intent:
        rp_core._debug_print("ROUTE", "Intent detection failed. Defaulting to 'discussion' to keep pipeline alive.")
        detected_intent = "discussion"
    
    # Clean history images to prevent sending LOCAL_FILE: base64 placehodlers
    d_resp_resolved = rp_core._clean_history_images(d_resp)
    
    context_pack = {
        "char_id": char_id,
        "current_session_id": current_session_id,
        "current_turn": current_turn,
        "d_resp": d_resp_resolved,
        "ctx_api": ctx_api,
        "ctx_history": ctx_history,
        "gen_config": gen_config,
        "char_data": char_data,
        "user_data": user_data,
        "user_message": user_message,
        "detected_intent": detected_intent,
    }
    
    if detected_intent in ("create_image", "image_to_image"):
        rp_core._debug_print("ROUTE", f"Routing to TO_IMG pipeline (intent: {detected_intent})")
        async for chunk in to_img.run_pipeline(context_pack):
            yield chunk
    
    elif detected_intent in ("discussion", "unspecified"):
        rp_core._debug_print("ROUTE", f"Routing to TO_TEXT pipeline (intent: {detected_intent})")
        async for chunk in to_text.run_pipeline(context_pack):
            yield chunk
    
    else:
        rp_core._debug_print("ROUTE", f"Unknown intent: {detected_intent}. Stopping.")
        yield json.dumps({"type": "error", "content": f"Unknown intent: {detected_intent}"}) + "\n"

    rp_core._debug_print("RPLC", "RESPONSE DONE!")
    yield json.dumps({"type": "signal", "content": "done"}) + "\n"

    # 4. Memory Cleanup
    try: del d_resp, d_resp_resolved, collected_parts_intent, ctx_api, ctx_history, context_pack
    except Exception: pass
    gc.collect()