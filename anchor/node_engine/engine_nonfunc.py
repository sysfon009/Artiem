import os
import json
import asyncio
import base64
from typing import AsyncGenerator, Dict, Any, Union, Optional
from dotenv import load_dotenv
from google import genai
from google.genai import types


# ==========================================
# 2. GENERATE FUNCTION (NON-FUNCTION-CALL)
# ==========================================
async def generate(
    context: Union[str, list], 
    instruction: str,
    history: list = None,
    config: dict = None,
    custom_tools: Optional[list] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Engine tanpa function calling. Google Search dan Code Execution
    diaktifkan langsung dari UI config (use_search, use_code_execution).
    custom_tools parameter tetap ada untuk kompatibilitas interface 
    dengan _stream_llm_response, tapi diabaikan di engine ini.
    """
    
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
        yield {"type": "error", "content": "API Key Missing. Please set an API Key in the Settings page."}
        return
    try:
        local_client = secure_config.get_genai_client(current_api_key)
    except Exception as e:
        yield {"type": "error", "content": f"Failed to init client: {str(e)}"}
        return

    # -----------------------------------------------------------
    # A. TOOL CONFIGURATION (Native Tools Only)
    # -----------------------------------------------------------
    active_tools = []

    if config.get("use_search"):
        print("[DEBUG] Tool: Google Search -> ON") 
        active_tools.append(types.Tool(google_search=types.GoogleSearch()))
    
    if config.get("use_code_execution"):
        print("[DEBUG] Tool: Code Execution -> ON")
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
        max_output_tokens=config.get("max_output_tokens", 8192),
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
# C. HISTORY HANDLING (Text, Files, Code, Results)
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
                            try:
                                signature = base64.b64decode(val)
                            except Exception:
                                signature = val
                        else:
                            signature = val

                    
                    if "user_attachment" in p:
                        # Handle user_attachment FIRST — may coexist with "text"
                        att_data = p["user_attachment"]
                        display_name = att_data.get("display_name", "")
                        img_desc = att_data.get("img_description", "")
                        if display_name:
                            desc_text = f" - Description: {img_desc}" if img_desc else ""
                            parts.append(types.Part.from_text(text=f"[Attached Image: {display_name}{desc_text}]"))
                        if "inline_data" in att_data:
                            idat = att_data["inline_data"]
                            parts.append(types.Part.from_bytes(
                                data=base64.b64decode(idat["data"]),
                                mime_type=idat["mime_type"]
                            ))
                        # Also add text if it coexists
                        if "text" in p:
                            parts.append(types.Part(
                                text=p["text"],
                                thought=thought,
                                thought_signature=signature
                            ))

                    elif "functionCall" in p:
                        fc_data = p["functionCall"]
                        parts.append(types.Part(
                            function_call=types.FunctionCall(
                                name=fc_data["name"],
                                args=fc_data["args"]
                            ),
                            thought=thought,
                            thought_signature=signature
                        ))

                    elif "functionResponse" in p:
                        fr_data = p["functionResponse"]
                        parts.append(types.Part(
                            function_response=types.FunctionResponse(
                                name=fr_data["name"],
                                response=fr_data["response"]
                            )
                        ))
                    
                    elif "executable_code" in p:
                        ec = p["executable_code"]
                        parts.append(types.Part(
                            executable_code=types.ExecutableCode(
                                code=ec.get("code"),
                                language=ec.get("language")
                            ),
                            thought=thought,
                            thought_signature=signature
                        ))

                    elif "code_execution_result" in p:
                        cr = p["code_execution_result"]
                        parts.append(types.Part(
                            code_execution_result=types.CodeExecutionResult(
                                outcome=cr.get("outcome"),
                                output=cr.get("output")
                            )
                        ))

                    elif "data" in p and "mime_type" in p:
                        parts.append(types.Part.from_bytes(
                            data=base64.b64decode(p["data"]), 
                            mime_type=p["mime_type"]
                        ))

                    elif "text" in p:
                        parts.append(types.Part(
                            text=p["text"],
                            thought=thought,
                            thought_signature=signature
                        ))
                    
                    elif thought: 
                        parts.append(types.Part(
                            text="", 
                            thought=thought,
                            thought_signature=signature
                        ))

            if parts:
                final_contents.append(types.Content(role=msg.get("role", "user"), parts=parts))

    # -----------------------------------------------------------
    # D. CONTEXT & FILE UPLOAD HANDLING (Active Turn)
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
                
                if "user_attachment" in item:
                    # Handle user_attachment FIRST — it may coexist with "text"
                    att_data = item["user_attachment"]
                    display_name = att_data.get("display_name", "")
                    img_desc = att_data.get("img_description", "")
                    if display_name:
                        desc_text = f" - Description: {img_desc}" if img_desc else ""
                        current_parts.append(types.Part.from_text(text=f"[Attached Image: {display_name}{desc_text}]"))
                    if "inline_data" in att_data:
                        idat = att_data["inline_data"]
                        current_parts.append(types.Part.from_bytes(
                            data=base64.b64decode(idat["data"]),
                            mime_type=idat["mime_type"]
                        ))
                    # Also add text if it exists alongside the attachment
                    if "text" in item:
                        current_parts.append(types.Part(text=item["text"], thought=thought))

                elif "text" in item:
                    current_parts.append(types.Part(text=item["text"], thought=thought))
                
                elif "inline_data" in item:
                    idat = item["inline_data"]
                    current_parts.append(types.Part.from_bytes(
                        data=base64.b64decode(idat["data"]),
                        mime_type=idat["mime_type"]
                    ))
                
                elif "data" in item and "mime_type" in item:
                    current_parts.append(types.Part.from_bytes(
                        data=base64.b64decode(item["data"]),
                        mime_type=item["mime_type"]
                    ))
                # -----------------------------------------------------------------------

                elif "file_data" in item: 
                    fd = item["file_data"]
                    if "file_uri" in fd:
                        current_parts.append(types.Part.from_uri(file_uri=fd["file_uri"], mime_type=fd["mime_type"]))
                
                elif "functionResponse" in item:
                    fr = item["functionResponse"]
                    current_parts.append(types.Part.from_function_response(name=fr["name"], response=fr["response"]))
               

    if current_parts:
        final_contents.append(types.Content(role="user", parts=current_parts))


        # -----------------------------------------------------------
    # E. EXECUTION & STREAMING
    # -----------------------------------------------------------
    max_retries = 3
    retry_delay = 2
    yielded_any_content = False
    for attempt in range(max_retries):
        try:
            response_stream = await asyncio.wait_for(
                local_client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=final_contents, 
                    config=gen_config
                ),
                timeout=60
            )

            yielded_any_content = False
            last_chunk_time = asyncio.get_event_loop().time()
            
            async for chunk in response_stream:
                last_chunk_time = asyncio.get_event_loop().time()
                yielded_any_content = True
                if not chunk.candidates: continue
                
                for cand in chunk.candidates:
                    if cand.finish_reason:
                        yield {"type": "finish_reason", "content": cand.finish_reason}

                    # =========================================================
                    # [CRITICAL UPDATE] GLOBAL SIGNATURE SEARCH
                    # =========================================================
                    extracted_signature = None
                    
                    if hasattr(cand, "thought_signature") and cand.thought_signature:
                        raw_sig = cand.thought_signature
                        extracted_signature = raw_sig

                    if not extracted_signature and cand.content and cand.content.parts:
                        for p in cand.content.parts:
                            if hasattr(p, "thought_signature") and p.thought_signature:
                                extracted_signature = p.thought_signature
                                break 

            
                    final_sig_str = None
                    if extracted_signature:
                        try:
                            final_sig_str = base64.b64encode(
                                extracted_signature if isinstance(extracted_signature, bytes) else str(extracted_signature).encode()
                            ).decode()
                            print(f"\033[93m[ENGINE_NONFUNC] !!! SIGNATURE FOUND !!! Len: {len(final_sig_str)}\033[0m")
                        except Exception as e:
                            print(f"[ENGINE_NONFUNC] Signature Decode Error: {e}")

                    def _attach_sig(payload):
                        if final_sig_str:
                            payload["thought_signature"] = final_sig_str
                        return payload
                    
                    signature_consumed = False

                    if not cand.content or not cand.content.parts: 
                        if final_sig_str:
                            yield { "type": "thought_signature", "content": final_sig_str }
                        continue

                    # =========================================================
                    # LOOP PARTS (Standard Handling)
                    # =========================================================
                    for part in cand.content.parts:
                        try:
                            # A. Executable Code
                            if part.executable_code:
                                yield _attach_sig({
                                    "type": "executable_code",
                                    "content": {
                                        "language": part.executable_code.language,
                                        "code": part.executable_code.code
                                    }
                                })
                                signature_consumed = True

                            # B. Code Result
                            elif part.code_execution_result:
                                yield {
                                    "type": "code_execution_result",
                                    "content": {
                                        "outcome": part.code_execution_result.outcome,
                                        "output": part.code_execution_result.output
                                    }
                                }

                            # C. Thought (Attribute .thought)
                            elif getattr(part, "thought", False): 
                                yield _attach_sig({ 
                                    "type": "thought", 
                                    "content": part.text 
                                })
                                signature_consumed = True

                            # D. Text Biasa
                            elif part.text:
                                yield _attach_sig({ 
                                    "type": "text", 
                                    "content": part.text 
                                })
                                signature_consumed = True

                            # E. Image
                            elif part.inline_data:
                                yield {
                                    "type": "image",
                                    "content": {
                                        "mime_type": part.inline_data.mime_type,
                                        "data": base64.b64encode(part.inline_data.data).decode('utf-8') 
                                    }
                                }

                        except Exception as inner_e:
                            print(f"[PART ERROR]: {inner_e}")
                            continue

                    # =========================================================
                    # ORPHAN HANDLING (Last resort)
                    # =========================================================
                    if final_sig_str and not signature_consumed:
                        yield { 
                            "type": "thought_signature", 
                            "content": final_sig_str 
                        }

            return 

        except Exception as e:
            print(f"[ENGINE_NONFUNC_WARN] Attempt {attempt+1} failed: {e}")
            
            if yielded_any_content:
                # Caching mechanism removed
                yield {"type": "error", "content": f"Connection dropped mid-stream: {str(e)}"}
                return
                
            error_str = str(e).lower()
            if "429" in error_str or "resource exhausted" in error_str:
                retry_delay = max(retry_delay, 15)
                
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2 
            else:
                # Caching mechanism removed
                yield {"type": "error", "content": f"Max retries reached. Error: {str(e)}"}
