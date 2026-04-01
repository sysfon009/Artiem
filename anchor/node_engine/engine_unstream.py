import os
import json
import asyncio
import base64
from typing import Dict, Any, Union, Optional, List
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ==========================================
# NON-STREAMING GENERATE FUNCTION
# ==========================================
async def generate_unstream(
    context: Union[str, list], 
    instruction: str,
    history: list = None,
    config: dict = None,
    custom_tools: Optional[list] = None
) -> List[Dict[str, Any]]:
    
    load_dotenv(override=True)
    if not config: config = {}
    
    # Init Client
    from anchor import secure_config
    
    current_api_key = config.get("api_key")
    assigned_name = secure_config.get_assigned_key("main_model")
    if not current_api_key and assigned_name:
        current_api_key = secure_config.get_api_key(assigned_name)
    if not current_api_key:
        current_api_key = secure_config.get_default_api_key() or os.environ.get("KEY_POPR")
        
    if not current_api_key:
        return [{"type": "error", "content": "API Key Missing. Please set an API Key in the Settings page."}]
    try:
        local_client = secure_config.get_genai_client(current_api_key)
    except Exception as e:
        return [{"type": "error", "content": f"Failed to init client: {str(e)}"}]

    # -----------------------------------------------------------
    # A. TOOL CONFIGURATION
    # -----------------------------------------------------------
    active_tools = []
    using_custom_tools = False

    if custom_tools and isinstance(custom_tools, list):
        print(f"[DEBUG_UNSTREAM] Custom Tools Injected: {len(custom_tools)} tools.")
        active_tools.extend(custom_tools)
        using_custom_tools = True
    
    if config.get("use_search"):
        active_tools.append(types.Tool(google_search=types.GoogleSearch()))
    
    if not using_custom_tools and config.get("use_code_execution"):
        active_tools.append(types.Tool(code_execution=types.ToolCodeExecution()))
    
    final_tools = active_tools if active_tools else None

    # -----------------------------------------------------------
    # B. MODEL CONFIGURATION
    # -----------------------------------------------------------
    gen_thinking_config = types.ThinkingConfig(include_thoughts=True, thinking_level="HIGH")

    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
    ]

    gen_config = types.GenerateContentConfig(
        temperature=config.get("temperature"),
        top_p=config.get("top_p"),
        top_k=config.get("top_k"),
        max_output_tokens=config.get("max_output_tokens", 16540),
        response_mime_type=config.get("response_mime_type"), 
        response_schema=config.get("response_schema"),
        thinking_config=gen_thinking_config,
        safety_settings=safety_settings,
        system_instruction=instruction,
        tools=final_tools
    )

    model_name = config.get("model", "gemini-3.1-pro-preview") 
    final_contents = []

    # -----------------------------------------------------------
    # C. HISTORY HANDLING 
    # -----------------------------------------------------------
    if history and isinstance(history, list):
        for msg in history:
            parts = []
            raw_parts = msg.get("parts", [])
            if isinstance(raw_parts, str): raw_parts = [raw_parts]
            
            for p in raw_parts:
                if isinstance(p, str): 
                    parts.append(types.Part.from_text(text=p))
                elif isinstance(p, dict):
                    thought = p.get("thought")
                    raw_sig = p.get("thoughtSignature") or p.get("thought_signature")
                    
                    signature = raw_sig
                    if raw_sig:
                        val = raw_sig[0] if isinstance(raw_sig, list) and raw_sig else raw_sig
                        if isinstance(val, str) and len(val) > 100:
                            try: signature = base64.b64decode(val)
                            except Exception: signature = val
                        else: signature = val

                    if "functionCall" in p:
                        fc_data = p["functionCall"]
                        parts.append(types.Part(
                            function_call=types.FunctionCall(name=fc_data["name"], args=fc_data["args"]),
                            thought=thought, thought_signature=signature
                        ))
                    elif "functionResponse" in p:
                        fr_data = p["functionResponse"]
                        parts.append(types.Part(function_response=types.FunctionResponse(name=fr_data["name"], response=fr_data["response"])))
                    elif "executable_code" in p:
                        ec = p["executable_code"]
                        parts.append(types.Part(executable_code=types.ExecutableCode(code=ec.get("code"), language=ec.get("language")), thought=thought, thought_signature=signature))
                    elif "code_execution_result" in p:
                        cr = p["code_execution_result"]
                        parts.append(types.Part(code_execution_result=types.CodeExecutionResult(outcome=cr.get("outcome"), output=cr.get("output"))))
                    # --- FIX: Support untuk user_attachment di History ---
                    elif "user_attachment" in p and "inline_data" in p["user_attachment"]:
                        display_name = p["user_attachment"].get("display_name", "")
                        img_desc = p["user_attachment"].get("img_description", "")
                        if display_name:
                            desc_text = f" - Description: {img_desc}" if img_desc else ""
                            parts.append(types.Part.from_text(text=f"[Attached Image: {display_name}{desc_text}]"))
                        parts.append(types.Part.from_bytes(
                            data=base64.b64decode(p["user_attachment"]["inline_data"]["data"]), 
                            mime_type=p["user_attachment"]["inline_data"]["mime_type"]
                        ))
                    elif "data" in p and "mime_type" in p:
                        parts.append(types.Part.from_bytes(data=base64.b64decode(p["data"]), mime_type=p["mime_type"]))
                    elif "text" in p:
                        parts.append(types.Part(text=p["text"], thought=thought, thought_signature=signature))
                    elif thought: 
                        parts.append(types.Part(text="", thought=thought, thought_signature=signature))

            if parts:
                final_contents.append(types.Content(role=msg.get("role", "user"), parts=parts))

    # -----------------------------------------------------------
    # D. CONTEXT & FILE UPLOAD HANDLING 
    # -----------------------------------------------------------
    current_parts = []
    if isinstance(context, str) and context:
        current_parts.append(types.Part.from_text(text=context))
    elif isinstance(context, list):
        for item in context:
            if isinstance(item, str):
                current_parts.append(types.Part.from_text(text=item))
            elif isinstance(item, dict):
                thought = item.get("thought")
                if "text" in item:
                    current_parts.append(types.Part(text=item["text"], thought=thought))
                # --- FIX: Support untuk user_attachment di Context ---
                elif "user_attachment" in item and "inline_data" in item["user_attachment"]:
                    display_name = item["user_attachment"].get("display_name", "")
                    img_desc = item["user_attachment"].get("img_description", "")
                    if display_name:
                        desc_text = f" - Description: {img_desc}" if img_desc else ""
                        current_parts.append(types.Part.from_text(text=f"[Attached Image: {display_name}{desc_text}]"))
                    idat = item["user_attachment"]["inline_data"]
                    current_parts.append(types.Part.from_bytes(
                        data=base64.b64decode(idat["data"]),
                        mime_type=idat["mime_type"]
                    ))
                elif "inline_data" in item:
                    current_parts.append(types.Part.from_bytes(data=base64.b64decode(item["inline_data"]["data"]), mime_type=item["inline_data"]["mime_type"]))
                elif "data" in item and "mime_type" in item:
                    current_parts.append(types.Part.from_bytes(data=base64.b64decode(item["data"]), mime_type=item["mime_type"]))
                elif "file_data" in item and "file_uri" in item["file_data"]: 
                    current_parts.append(types.Part.from_uri(file_uri=item["file_data"]["file_uri"], mime_type=item["file_data"]["mime_type"]))
                elif "functionResponse" in item:
                    current_parts.append(types.Part.from_function_response(name=item["functionResponse"]["name"], response=item["functionResponse"]["response"]))

    if current_parts:
        final_contents.append(types.Content(role="user", parts=current_parts))

    # -----------------------------------------------------------
    # E. EXECUTION & PARSING (NON-STREAMING)
    # -----------------------------------------------------------
    max_retries = 3
    retry_delay = 2
    parsed_results = []

    for attempt in range(max_retries):
        try:
            response = await asyncio.wait_for(
                local_client.aio.models.generate_content(
                    model=model_name,
                    contents=final_contents, 
                    config=gen_config
                ),
                timeout=30
            )

            if not response.candidates:
                return [{"type": "error", "content": "No candidates returned from model."}]

            cand = response.candidates[0]

            if cand.finish_reason and cand.finish_reason.name != "STOP":
                parsed_results.append({"type": "finish_reason", "content": cand.finish_reason.name})

            # =========================================================
            # GLOBAL SIGNATURE SEARCH
            # =========================================================
            extracted_signature = getattr(cand, "thought_signature", None)
            
            if not extracted_signature and cand.content and cand.content.parts:
                for p in cand.content.parts:
                    if getattr(p, "thought_signature", None):
                        extracted_signature = p.thought_signature
                        break 

            final_sig_str = None
            if extracted_signature:
                try:
                    final_sig_str = base64.b64encode(
                        extracted_signature if isinstance(extracted_signature, bytes) else str(extracted_signature).encode()
                    ).decode()
                    print(f"\033[96m[UNSTREAM_ENGINE] !!! SIGNATURE FOUND !!! Len: {len(final_sig_str)}\033[0m")
                except Exception as e:
                    print(f"[UNSTREAM_ENGINE] Signature Decode Error: {e}")

            def _attach_sig(payload):
                if final_sig_str: payload["thought_signature"] = final_sig_str
                return payload
            
            signature_consumed = False

            if not cand.content or not cand.content.parts: 
                if final_sig_str:
                    parsed_results.append({ "type": "thought_signature", "content": final_sig_str })
                return parsed_results

            # =========================================================
            # LOOP PARTS (Standard Handling)
            # =========================================================
            for part in cand.content.parts:
                try:
                    if part.function_call:
                        fc_args = part.function_call.args
                        args_dict = {k: v for k, v in fc_args.items()} if fc_args else {}
                        parsed_results.append(_attach_sig({
                            "type": "function_call",
                            "content": {"name": part.function_call.name, "args": args_dict}
                        }))
                        signature_consumed = True

                    elif part.executable_code:
                        parsed_results.append(_attach_sig({
                            "type": "executable_code",
                            "content": {"language": part.executable_code.language, "code": part.executable_code.code}
                        }))
                        signature_consumed = True

                    elif part.code_execution_result:
                        parsed_results.append({
                            "type": "code_execution_result",
                            "content": {"outcome": part.code_execution_result.outcome, "output": part.code_execution_result.output}
                        })

                    elif getattr(part, "thought", False): 
                        parsed_results.append(_attach_sig({"type": "thought", "content": part.text}))
                        signature_consumed = True

                    elif part.text:
                        parsed_results.append(_attach_sig({"type": "text", "content": part.text}))
                        signature_consumed = True

                except Exception as inner_e:
                    print(f"[PART ERROR]: {inner_e}")
                    continue

            # =========================================================
            # ORPHAN HANDLING
            # =========================================================
            if final_sig_str and not signature_consumed:
                parsed_results.append({ "type": "thought_signature", "content": final_sig_str })

            # Jika berhasil sampai sini, return hasilnya dan keluar dari loop retry
            return parsed_results

        except Exception as e:
            print(f"[UNSTREAM_WARN] Attempt {attempt+1} failed: {e}")
            error_str = str(e).lower()
            if "429" in error_str or "resource exhausted" in error_str:
                retry_delay = max(retry_delay, 15)
                
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2 
            else:
                # Caching mechanism removed
                return [{"type": "error", "content": f"Max retries reached. Error: {str(e)}"}]

    return parsed_results