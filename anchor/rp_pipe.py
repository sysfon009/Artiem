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
from anchor.function_executor import TOOL_MAP
from function_schema.function_tools import get_image_generator, get_image_detail

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

    rp_core._debug_print("RP_PIPE", f"Pipeline started")

    # Extract attachment filenames from ctx_api for reference
    attachment_filenames = []
    if isinstance(ctx_api, list):
        for part in ctx_api:
            if isinstance(part, dict) and "user_attachment" in part:
                fname = part["user_attachment"].get("display_name", "")
                if fname:
                    attachment_filenames.append(fname)

    # Prep Tools & Meta Context
    meta_context_pack = {
        "current_session_id": current_session_id, "char_id": char_id, "user_message": user_message,
        "char_data": char_data.get("name", "Character"), "current_turn_id": current_turn, "ui_image_config": gen_config.get("image_settings", {}),
        "attachment_filenames": attachment_filenames
    }
    custom_tools_list = [get_image_generator(), get_image_detail()]

    # Clean history images to prevent sending LOCAL_FILE: base64 placeholders
    d_resp_resolved = rp_core._clean_history_images(d_resp)

    # ==========================================
    # NODE 1: MAIN LOOP (TOOL CALLING NODE)
    # ==========================================
    loop_limit = 20  
    loop_count = 0

    while loop_count < loop_limit:
        loop_count += 1
        collected_parts_node1 = []
        tool_requests = []

        # Stream LLM Response Node 1
        stream_gen = rp_core._stream_llm_response(
            ctx_api, 
            d_resp_resolved, 
            resp_inst_str, 
            gen_config, 
            custom_tools_list, 
            collected_parts_node1, 
            tool_requests
        )

        error_encountered = None
        stream_success = False

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
            
            if not error_encountered:
                stream_success = True
        except Exception as e:
            error_encountered = str(e)

        if error_encountered:
            rp_core._debug_print("RP_PIPE", f"Stream error: {error_encountered}")
            yield json.dumps({"type": "error", "content": error_encountered}) + "\n"
            break

        if stream_success and collected_parts_node1:
            rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "model", collected_parts_node1, turn_id=current_turn)
            d_resp.append({"role": "model", "parts": collected_parts_node1})
            # update d_resp_resolved for next tool loop if applicable
            d_resp_resolved = rp_core._clean_history_images(d_resp)

        if not stream_success or not tool_requests:
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
            
        rp_core._log_interaction(char_id, current_session_id, "log_final_resp", "user", feedback_parts, turn_id=current_turn)
        d_resp.append({"role": "user", "parts": feedback_parts})
        d_resp_resolved = rp_core._clean_history_images(d_resp)
        
        if has_critical_error:
            rp_core._debug_print("RP_PIPE", f"Critical tool error, stopping pipeline: {critical_error_msg}")
            yield json.dumps({"type": "error", "content": critical_error_msg}) + "\n"
            break
            
        ctx_api = [] 

    rp_core._debug_print("RP_PIPE", "Pipeline finished.")
    yield json.dumps({"type": "signal", "content": "done"}) + "\n"

    try: del collected_parts_node1, tool_requests, ctx_api, ctx_history, d_resp, d_resp_resolved
    except Exception: pass
    gc.collect()
