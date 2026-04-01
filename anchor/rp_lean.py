import sys
import os
import json
import asyncio
from typing import List, Optional, Any, Tuple, Dict, AsyncGenerator
import gc

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from . import rp_core
from anchor.node_engine import engine_nonfunc

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

    # 2. Process Attachments & Update History
    ctx_api, ctx_history = await rp_core._process_attachments(char_id, current_session_id, user_message, attachment, turn_id=current_turn)
    ctx_api = ctx_api if ctx_api else user_message
    
    rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "user", ctx_history if ctx_history else user_message, turn_id=current_turn)

    # 3. Setup Instruction
    inst_module = rp_core._load_instruction_module(gen_config.get("instruction", "inst_work"))
    resp_inst_str = inst_module.build_prompt(
        name=char_data.get("name", "Character"), age=char_data.get("age", "Unknown"),
        personality=char_data.get("personality", "Default"), appearance=char_data.get("appearance", "Default"),
        inst_content=char_data.get("system_instruction", ""), user_data=user_data
    ) if hasattr(inst_module, 'build_prompt') else "Error: Module not loaded."

    rp_core._debug_print("RP_LEAN", f"Pipeline started (no function call)")

    # Clean history images to prevent sending LOCAL_FILE: base64 placeholders
    d_resp_resolved = rp_core._clean_history_images(d_resp)

    # ==========================================
    # SINGLE PASS STREAMING (No Tool Loop)
    # ==========================================
    collected_parts = []
    tool_requests = []  # kept for interface compatibility, will stay empty

    stream_gen = rp_core._stream_llm_response(
        ctx_api, 
        d_resp_resolved, 
        resp_inst_str, 
        gen_config, 
        None,  # no custom tools
        collected_parts, 
        tool_requests,
        engine=engine_nonfunc  # use non-function-call engine
    )

    error_encountered = None

    try:
        async for chunk in stream_gen:
            try:
                parsed = json.loads(chunk)
                if parsed.get("type") == "error":
                    error_encountered = parsed.get("content", "Unknown error")
            except Exception:
                pass
            
            if error_encountered:
                break
            
            yield chunk
        
    except Exception as e:
        error_encountered = str(e)

    if error_encountered:
        rp_core._debug_print("RP_LEAN", f"Stream error: {error_encountered}")
        yield json.dumps({"type": "error", "content": error_encountered}) + "\n"

    if collected_parts:
        rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "model", collected_parts, turn_id=current_turn)

    rp_core._debug_print("RP_LEAN", "Pipeline finished.")
    yield json.dumps({"type": "signal", "content": "done"}) + "\n"

    try: del collected_parts, tool_requests, ctx_api, ctx_history, d_resp, d_resp_resolved
    except Exception: pass
    gc.collect()
