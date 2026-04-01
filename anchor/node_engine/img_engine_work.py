import sys
import os
import time
import base64
import mimetypes
import urllib.parse
import asyncio
import copy
from typing import Dict, Any, List, AsyncGenerator, Optional, Union
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ==========================================
# PATH SETUP
# ==========================================
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(current_dir))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from anchor import rp_core
from anchor import secure_config

def _debug_print(section: str, message: str, data=None):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [IMG_ENGINE_WORK][{section}] {message}")
    if data:
        str_data = str(data)
        if len(str_data) > 200: str_data = str_data[:200] + "... [TRUNCATED]"
        print(f"   >>> {str_data}")


# ==========================================
# DIRECT IMAGE GENERATION (Streaming Yield)
# ==========================================
async def generate(
    context: Union[str, list],
    instruction: str,
    history: list = None,
    config: dict = None,
    custom_tools: Optional[list] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Direct image generation engine (streaming).
    Yields chunks: {type: "text"/"thought"/"image"/"thought_signature"/"error"/"finish_reason", content: ...}
    Modeled after engine_function.py streaming pattern but specialized for image generation.
    """
    load_dotenv(override=True)
    if not config: config = {}

    # -----------------------------------------------------------
    # A. API KEY & CLIENT
    # -----------------------------------------------------------
    assigned_name = secure_config.get_assigned_key("image_model")
    current_api_key = None
    if assigned_name:
        current_api_key = secure_config.get_api_key(assigned_name)
    if not current_api_key:
        yield {"type": "error", "content": "API Key Missing. Please set an API Key for Image Gen."}
        return

    try:
        client = secure_config.get_genai_client(current_api_key)
    except Exception as e:
        yield {"type": "error", "content": f"Failed to init client: {str(e)}"}
        return

    # -----------------------------------------------------------
    # B. IMAGE CONFIGURATION
    # -----------------------------------------------------------
    image_settings = config.get("image_settings", {})
    aspect_ratio = image_settings.get("aspect_ratio", "1:1")
    resolution = image_settings.get("resolution", "1024x1024")
    temperature = float(image_settings.get("temperature", config.get("temperature", 1.0)))

    try:
        image_config = types.ImageConfig(
            aspect_ratio=aspect_ratio,
            image_size=str(resolution).upper()
        )
    except AttributeError:
        image_config = None

    safety_settings = [
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE")
    ]

    gen_thinking_config = types.ThinkingConfig(include_thoughts=True)

    generate_content_config = types.GenerateContentConfig(
        temperature=temperature,
        top_p=0.95,
        response_modalities=["TEXT", "IMAGE"],
        image_config=image_config,
        safety_settings=safety_settings,
        system_instruction=instruction
    )

    model_name = config.get("model", "gemini-3-pro-image-preview")

    # -----------------------------------------------------------
    # C. BUILD CONTENTS FROM HISTORY
    # -----------------------------------------------------------
    final_contents = []

    char_id = config.get("_char_id", "")
    session_id = config.get("_session_id", "")

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

                    # Decode signature: b64 string -> bytes for API
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
                        att_data = p["user_attachment"]
                        display_name = att_data.get("display_name", "")
                        img_desc = att_data.get("img_description", "")
                        if display_name:
                            desc_text = f" - Description: {img_desc}" if img_desc else ""
                            parts.append(types.Part.from_text(text=f"[Attached Image: {display_name}{desc_text}]"))
                        # inline_data already resolved by _resolve_img_history
                        if "inline_data" in att_data:
                            idat = att_data["inline_data"]
                            data_val = idat.get("data", "")
                            if data_val and not data_val.startswith("LOCAL_FILE:") and len(data_val) > 100:
                                parts.append(types.Part.from_bytes(
                                    data=base64.b64decode(data_val),
                                    mime_type=idat.get("mime_type", "image/png")
                                ))
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
    # D. CONTEXT (Current Turn)
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
                    att_data = item["user_attachment"]
                    display_name = att_data.get("display_name", "")
                    img_desc = att_data.get("img_description", "")
                    if display_name:
                        desc_text = f" - Description: {img_desc}" if img_desc else ""
                        current_parts.append(types.Part.from_text(text=f"[Attached Image: {display_name}{desc_text}]"))
                    if "inline_data" in att_data:
                        idat = att_data["inline_data"]
                        data_val = idat.get("data", "")
                        if isinstance(data_val, str) and data_val.startswith("LOCAL_FILE:"):
                            fname = data_val.replace("LOCAL_FILE:", "")
                            b64 = rp_core.encode_image_from_storage(char_id, session_id, fname, compress=False)
                            if b64:
                                current_parts.append(types.Part.from_bytes(
                                    data=base64.b64decode(b64),
                                    mime_type=idat.get("mime_type", "image/png")
                                ))
                        elif data_val and len(data_val) > 100:
                            current_parts.append(types.Part.from_bytes(
                                data=base64.b64decode(data_val),
                                mime_type=idat.get("mime_type", "image/png")
                            ))
                    if "text" in item:
                        current_parts.append(types.Part(text=item["text"], thought=thought))

                elif "text" in item:
                    current_parts.append(types.Part(text=item["text"], thought=thought))

                elif "inline_data" in item:
                    idat = item["inline_data"]
                    data_val = idat.get("data", "")
                    if isinstance(data_val, str) and data_val.startswith("LOCAL_FILE:"):
                        fname = data_val.replace("LOCAL_FILE:", "")
                        b64 = rp_core.encode_image_from_storage(char_id, session_id, fname, compress=False)
                        if b64:
                            current_parts.append(types.Part.from_bytes(
                                data=base64.b64decode(b64),
                                mime_type=idat.get("mime_type", "image/png")
                            ))
                    elif data_val and len(data_val) > 100:
                        current_parts.append(types.Part.from_bytes(
                            data=base64.b64decode(data_val),
                            mime_type=idat.get("mime_type", "image/png")
                        ))

                elif "data" in item and "mime_type" in item:
                    current_parts.append(types.Part.from_bytes(
                        data=base64.b64decode(item["data"]),
                        mime_type=item["mime_type"]
                    ))

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
            _debug_print("API_CALL", f"Calling image API stream... (Attempt {attempt + 1}/{max_retries})")
            response_stream = await asyncio.wait_for(
                client.aio.models.generate_content_stream(
                    model=model_name,
                    contents=final_contents,
                    config=generate_content_config
                ),
                timeout=120
            )

            yielded_any_content = False
            async for chunk in response_stream:
                yielded_any_content = True
                if not chunk.candidates: continue

                for cand in chunk.candidates:
                    if cand.finish_reason:
                        yield {"type": "finish_reason", "content": cand.finish_reason}

                    # =========================================================
                    # GLOBAL SIGNATURE SEARCH (same as engine_function)
                    # =========================================================
                    extracted_signature = None

                    if hasattr(cand, "thought_signature") and cand.thought_signature:
                        extracted_signature = cand.thought_signature

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
                        except Exception as e:
                            print(f"[IMG_ENGINE] Signature Decode Error: {e}")

                    def _attach_sig(payload):
                        if final_sig_str:
                            payload["thought_signature"] = final_sig_str
                        return payload

                    signature_consumed = False

                    if not cand.content or not cand.content.parts:
                        if final_sig_str:
                            yield {"type": "thought_signature", "content": final_sig_str}
                        continue

                    # =========================================================
                    # LOOP PARTS (Standard Handling — matches engine_function)
                    # =========================================================
                    for part in cand.content.parts:
                        try:
                            # A. Thought (check BEFORE text — thought parts also have .text)
                            if getattr(part, "thought", False):
                                yield _attach_sig({
                                    "type": "thought",
                                    "content": part.text
                                })
                                signature_consumed = True

                            # B. Text
                            elif part.text:
                                yield _attach_sig({
                                    "type": "text",
                                    "content": part.text
                                })
                                signature_consumed = True

                            # C. Image (inline_data)
                            elif part.inline_data:
                                _debug_print("SUCCESS", "Image received from API stream.")
                                raw_data = part.inline_data.data
                                mime_type = part.inline_data.mime_type

                                if isinstance(raw_data, str):
                                    b64_string = raw_data
                                else:
                                    b64_string = base64.b64encode(bytes(raw_data)).decode('utf-8')

                                yield {
                                    "type": "image",
                                    "content": {
                                        "mime_type": mime_type,
                                        "data": b64_string
                                    }
                                }

                            # D. Executable Code (unlikely for image model but handle anyway)
                            elif part.executable_code:
                                yield _attach_sig({
                                    "type": "executable_code",
                                    "content": {
                                        "language": part.executable_code.language,
                                        "code": part.executable_code.code
                                    }
                                })
                                signature_consumed = True

                            # E. Code Execution Result
                            elif part.code_execution_result:
                                yield {
                                    "type": "code_execution_result",
                                    "content": {
                                        "outcome": part.code_execution_result.outcome,
                                        "output": part.code_execution_result.output
                                    }
                                }

                        except Exception as inner_e:
                            print(f"[IMG_ENGINE PART ERROR]: {inner_e}")
                            continue

                    # =========================================================
                    # ORPHAN SIGNATURE HANDLING
                    # =========================================================
                    if final_sig_str and not signature_consumed:
                        yield {
                            "type": "thought_signature",
                            "content": final_sig_str
                        }

            return

        except Exception as e:
            _debug_print("API_ERROR", f"Attempt {attempt + 1} failed: {e}")

            if yielded_any_content:
                yield {"type": "error", "content": f"Connection dropped mid-stream: {str(e)}"}
                return

            error_str = str(e).lower()
            if "429" in error_str or "resource exhausted" in error_str:
                retry_delay = max(retry_delay, 15)

            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay)
                retry_delay *= 2
            else:
                yield {"type": "error", "content": f"Image generation failed after {max_retries} attempts: {str(e)}"}
