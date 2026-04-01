from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError 
from typing import Dict, Optional, Any
import os
import uuid
import json
import shutil
import time
import traceback
import logging

# --- IMPORT LOGIC MODULES ---
from .logic_router import run_logic_system as logic_v1
from .rp_lean import run_logic_system as logic_v2
from .img_work import run_logic_system as logic_v3
from .logic_router import run_logic_system as logic_v4
from .rp_pipe import run_logic_system as logic_beta

from . import rp_core

router = APIRouter()

# ==========================================
# Pydantic Models
# ==========================================
class ChatRequest(BaseModel):
    character_id: str
    user_message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    instruction_name: Optional[str] = "" 
    use_search: bool = False
    use_code: bool = False 
    max_tokens: int = 111000
    temperature: float = 1.0 
    top_p: float = 0.95
    top_k: int = 40
    model_version: str = "def"
    attachment: Optional[list] = None
    image_settings: Optional[Dict[str, Any]] = None

class TextModelConfiguration(BaseModel):
    use_search: bool = False
    use_code: bool = False 
    max_tokens: int = 111000
    temperature: float = 1.0 
    top_p: float = 0.95
    top_k: int = 40

class ImageModelConfiguration(BaseModel):
    image_settings: Optional[Dict[str, Any]] = None

class MessageAction(BaseModel):
    character_id: str
    index: int
    new_content: Optional[str] = None
    session_id: Optional[str] = None

class SessionAction(BaseModel):
    char_id: str
    session_id: str

class CharAction(BaseModel):
    character_id: str

class UserAction(BaseModel):
    user_id: str

class InstructionData(BaseModel):
    name: str
    content: str

class GenerateBaseRequest(BaseModel):
    char_id: str
    char_data: Dict[str, Any]     
    user_data: Dict[str, Any]     
    gen_config: Optional[Dict[str, Any]] = None 

# ==========================================
# Chat Endpoint
# ==========================================
@router.post("/api/rp/chat")
async def chat_with_character(data: ChatRequest):
    print(f"\n[ROUTER] === Incoming Chat Request ===")
    print(f"[ROUTER] Char: {data.character_id} | Session: {data.session_id}")
    print(f"[ROUTER] Instruction Mode: {data.instruction_name}")

    async def response_generator():
        try:
            safe_char_id = rp_core.sanitize_filename(data.character_id)
            folder_path = rp_core.get_character_root(safe_char_id)
            json_path = os.path.join(folder_path, "Character_Profile.json")
            
            if not os.path.exists(json_path):
                yield json.dumps({"type": "error", "content": "Profile not found"}) + "\n"
                yield json.dumps({"type": "signal", "content": "done"}) + "\n"
                return

            try:
                char_data = rp_core.load_character_profile_cached(safe_char_id, os.path.getmtime(json_path))
                if not char_data: raise Exception("Data Empty")
            except Exception as e:
                yield json.dumps({"type": "error", "content": f"Error Reading Profile: {str(e)}"}) + "\n"
                yield json.dumps({"type": "signal", "content": "done"}) + "\n"
                return

            user_data = rp_core.load_user_profile(data.user_id)
            
            # [UPDATE 1] Masukkan instruction ke gen_config
            gen_config = {
                "use_search": data.use_search,
                "use_code_execution": data.use_code,
                "max_output_tokens": data.max_tokens,
                "temperature": data.temperature,
                "top_p": data.top_p,
                "top_k": data.top_k,
                "instruction": data.instruction_name,
                "image_settings": data.image_settings or {},
            }

            # Routing Model Version
            if data.model_version == "logic_v1":
                target_logic = logic_v1            
                ver_name = "Testing"
            elif data.model_version == "logic_v2":
                target_logic = logic_v2            
                ver_name = "Enhanced Testing"
            elif data.model_version == "logic_v3":
                target_logic = logic_v3            
                ver_name = "Image"
            elif data.model_version == "logic_v4":
                target_logic = logic_v4            
                ver_name = "Agentic System"
            else: 
                target_logic = logic_beta            
                ver_name = "Beta (Default)"

            print(f"[ROUTER] Model Version: {data.model_version.upper()} -> Menggunakan {ver_name}")
            
            async for chunk in target_logic(
                char_id=safe_char_id,
                session_id=data.session_id,
                user_message=data.user_message,
                char_data=char_data,
                user_data=user_data,
                gen_config=gen_config,
                attachment=data.attachment
            ):
                yield chunk

        except ValidationError as ve:
            print(f"\n[CRITICAL ERROR] PYDANTIC VALIDATION FAILED!")
            traceback.print_exc()
            yield json.dumps({"type": "error", "content": f"Validation Failed: {str(ve)}"}) + "\n"
            yield json.dumps({"type": "signal", "content": "done"}) + "\n"
        except Exception as e:
            print(f"\n[CRITICAL ERROR] SYSTEM CRASHED IN ROUTER")
            traceback.print_exc()
            yield json.dumps({"type": "error", "content": f"System Error: {str(e)}"}) + "\n"
            yield json.dumps({"type": "signal", "content": "done"}) + "\n"

    return StreamingResponse(response_generator(), media_type="text/plain")

# ==========================================
# History & Session Management
# ==========================================
@router.get("/api/rp/history/{character_id}")
def get_chat_history(character_id: str, response: Response, session_id: Optional[str] = None):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    history = rp_core.read_history_file(character_id, session_id, "log_final_resp")
    return {"status": "success", "data": history}

@router.post("/api/rp/delete_message")
async def delete_message(data: MessageAction):
    success = rp_core.delete_history_turns(data.character_id, data.session_id, data.index)
    
    if success:
        return {"status": "success", "message": f"Message at index {data.index} and below deleted."}
    else:
        return {"status": "error", "message": "Failed to delete."}

@router.get("/api/rp/get_history_sessions")
def get_history_sessions(char_id: str):
    histories_dir = rp_core.get_histories_root(char_id)
    if not os.path.exists(histories_dir): return {"status": "success", "data": []}
    
    sessions = []
    latest_path = rp_core.get_latest_session_path(char_id)
    active_folder = os.path.basename(latest_path) if latest_path else None

    for folder_name in os.listdir(histories_dir):
        full_path = os.path.join(histories_dir, folder_name)
        if os.path.isdir(full_path):
            mod_time = os.path.getmtime(full_path)
            time_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(mod_time))
            sessions.append({
                "folder": folder_name, "name": f"{folder_name.replace('_', ' ')} ({time_str})",
                "timestamp": mod_time, "is_active": (folder_name == active_folder)
            })
    sessions.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"status": "success", "data": sessions}

@router.post("/api/rp/delete_history_session")
def delete_history_session(data: SessionAction):
    session_path = os.path.join(rp_core.get_histories_root(data.char_id), data.session_id)
    if os.path.exists(session_path):
        shutil.rmtree(session_path, ignore_errors=True)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Session not found")

@router.post("/api/rp/delete_character")
def delete_character(data: CharAction):
    char_id = data.character_id
    if not char_id:
        raise HTTPException(status_code=400, detail="character_id is required")
    safe_id = rp_core.sanitize_filename(char_id)
    char_path = os.path.join(rp_core.DIRS["chars"], safe_id)
    hist_path = rp_core.get_histories_root(safe_id)
    deleted = False
    if os.path.exists(char_path):
        shutil.rmtree(char_path, ignore_errors=True)
        deleted = True
    if os.path.exists(hist_path):
        shutil.rmtree(hist_path, ignore_errors=True)
        deleted = True
    if deleted:
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Character not found")

@router.post("/api/rp/delete_user")
def delete_user(data: UserAction):
    user_id = data.user_id
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    safe_id = rp_core.sanitize_filename(user_id)
    user_path = os.path.join(rp_core.DIRS["users"], safe_id)
    if os.path.exists(user_path):
        shutil.rmtree(user_path, ignore_errors=True)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="User not found")

# ==========================================
# File Upload
# ==========================================
@router.post("/api/rp/upload_file")
async def upload_file(
    file: UploadFile = File(...),
    character_id: str = Form(...),
    session_id: str = Form(...)
):
    try:
        safe_char_id = rp_core.sanitize_filename(character_id)
        real_session_id = session_id
        if not session_id or session_id in ["new_chat_mode", "new_session", "undefined", "null"]:
            real_session_id = f"Session_{int(time.time())}"
        
        safe_session_id = rp_core.sanitize_filename(real_session_id)
        histories_root = rp_core.get_histories_root(safe_char_id)
        session_path = os.path.join(histories_root, safe_session_id)
        storage_path = os.path.join(session_path, "storage")

        if not os.path.exists(storage_path):
            os.makedirs(storage_path, exist_ok=True)

        original_name = file.filename
        name_part, ext_part = os.path.splitext(original_name)
        safe_name = rp_core.sanitize_filename(name_part) or "file"
        unique_id = str(uuid.uuid4())[:8]
        safe_filename = f"{safe_name}_{unique_id}{ext_part}"
        final_path = os.path.join(storage_path, safe_filename)

        with open(final_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "status": "success", 
            "filename": safe_filename, 
            "session_id": safe_session_id,
            "local_path": final_path
        }
    except Exception as e:
        traceback.print_exc()
        return {"status": "error", "message": str(e)}

# ==========================================
# Character Management
# ==========================================
@router.post("/api/rp/save_character")
async def save_character(
    name: str = Form(...), original_id: Optional[str] = Form(None),
    age: str = Form(""), personality: str = Form(""), appearance: str = Form(""),     
    initial_message: str = Form(""), example_input: str = Form(""), example_output: str = Form(""),
    avatar: UploadFile = File(None), bg: UploadFile = File(None)
):
    try:
        new_safe_name = rp_core.sanitize_filename(name)
        new_folder_path = os.path.join(rp_core.DIRS["chars"], new_safe_name)
        if original_id and original_id != new_safe_name:
            old_path = os.path.join(rp_core.DIRS["chars"], original_id)
            if os.path.exists(old_path) and not os.path.exists(new_folder_path): os.rename(old_path, new_folder_path)

        if not os.path.exists(new_folder_path): os.makedirs(new_folder_path)
        json_path = os.path.join(new_folder_path, "Character_Profile.json")
        current_avatar, current_bg = "default_avatar.png", "default_bg.png"
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as f:
                    old = json.load(f).get("images", {})
                    current_avatar = old.get("avatar", current_avatar)
                    current_bg = old.get("background", current_bg)
            except: pass

        import time

        if avatar:
            # Delete old avatar
            if current_avatar and current_avatar != "default_avatar.png":
                old_path = os.path.join(new_folder_path, current_avatar)
                if os.path.exists(old_path): os.remove(old_path)
            ext = avatar.filename.split(".")[-1]
            timestamp = int(time.time())
            current_avatar = rp_core.save_uploaded_file(avatar, new_folder_path, f"{new_safe_name}_avatar_{timestamp}.{ext}")
            
        if bg:
            # Delete old bg
            if current_bg and current_bg != "default_bg.png":
                old_path = os.path.join(new_folder_path, current_bg)
                if os.path.exists(old_path): os.remove(old_path)
            ext = bg.filename.split(".")[-1]
            timestamp = int(time.time())
            current_bg = rp_core.save_uploaded_file(bg, new_folder_path, f"{new_safe_name}_bg_{timestamp}.{ext}")

        char_data = {
            "name": name, "folder_id": new_safe_name, "age": age, "personality": personality,
            "appearance": appearance, "initial_message": initial_message,
            "example_chat": {"input": example_input, "output": example_output},
            "images": {"avatar": current_avatar, "background": current_bg}
        }
        with open(json_path, "w", encoding="utf-8") as f: json.dump(char_data, f, indent=4)
        return {"status": "success", "path": new_folder_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.get("/api/rp/get_characters")
def get_characters():
    char_list = []
    if os.path.exists(rp_core.DIRS["chars"]):
        for folder in os.listdir(rp_core.DIRS["chars"]):
            folder_path = os.path.join(rp_core.DIRS["chars"], folder)
            if os.path.isdir(folder_path):
                # Fetch minimal preview data
                json_path = os.path.join(folder_path, "Character_Profile.json")
                name = folder.replace("_", " ")
                avatar = None
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            name = data.get("name", name)
                            avatar = data.get("images", {}).get("avatar")
                    except: pass
                char_list.append({"id": folder, "name": name, "avatar": avatar})
                
    # Sort alphabetically by name
    char_list.sort(key=lambda x: x["name"].lower())
    return {"status": "success", "data": char_list}

@router.get("/api/rp/get_character_detail")
def get_character_detail(folder_id: str):
    safe_id = rp_core.sanitize_filename(folder_id)
    path = os.path.join(rp_core.DIRS["chars"], safe_id, "Character_Profile.json")
    
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: 
            return {"status": "success", "data": json.load(f)}
    
    # Fallback raw path
    raw_path = os.path.join(rp_core.DIRS["chars"], folder_id, "Character_Profile.json")
    if os.path.exists(raw_path):
        with open(raw_path, 'r', encoding='utf-8') as f: 
            return {"status": "success", "data": json.load(f)}

    raise HTTPException(status_code=404, detail="JSON not found")

# ==========================================
# Instruction Logic 
# ==========================================
@router.get("/api/rp/get_instructions")
def get_instructions():
    current_router_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_router_dir)
    target_dir = os.path.join(root_dir, "inst_data")
    print(f"\n[DEBUG] Router Position: {current_router_dir}")
    print(f"[DEBUG] Root Calculated: {root_dir}")
    print(f"[DEBUG] Scanning Target: {target_dir}")
    # --------------------------------

    files = []
    
    if os.path.exists(target_dir):
        # Scan file .py
        for f in os.listdir(target_dir):
            if f.endswith(".py") and f != "__init__.py":
                
                files.append(f.replace(".py", ""))
        
        
        files.sort()
        print(f"[DEBUG] Files Found: {files}")
        return {"status": "success", "data": files}
    else:
      
        print(f"[DEBUG] Folder not found at root. Checking sibling directory...")
        sibling_dir = os.path.join(current_router_dir, "inst_data")
        if os.path.exists(sibling_dir):
             for f in os.listdir(sibling_dir):
                if f.endswith(".py") and f != "__init__.py":
                    files.append(f.replace(".py", ""))
             files.sort()
             return {"status": "success", "data": files}

        print(f"[ERROR] 'inst_data' folder not found anywhere.")
        return {"status": "success", "data": []} 

@router.get("/api/rp/get_instruction_content")
def get_instruction_content(name: str):
    # TODO: Nanti update ini jika mau fitur View/Edit file .py
    path = os.path.join(rp_core.DIRS["base"], f"{rp_core.sanitize_filename(name)}.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f: return {"status": "success", "content": f.read()}
    return {"status": "error", "message": "Content view not available for modules yet."}

@router.post("/api/shared/save_instruction")
def save_instruction(data: InstructionData):
    # TODO: Nanti update ini jika mau fitur Save file .py
    path = os.path.join(rp_core.DIRS["base"], f"{rp_core.sanitize_filename(data.name)}.txt")
    with open(path, "w", encoding="utf-8") as f: f.write(data.content)
    return {"status": "success", "message": "Instruction saved"}

# ==========================================
# User Profile Management
# ==========================================
@router.get("/api/rp/get_users")
def get_user_profiles():
    path = rp_core.DIRS["users"]
    users = []
    if os.path.exists(path):
        for folder in os.listdir(path):
            folder_path = os.path.join(path, folder)
            if os.path.isdir(folder_path):
                json_path = os.path.join(folder_path, "user_profile.json")
                name = folder.replace("_", " ")
                avatar = None
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            name = data.get("name", name)
                            avatar = data.get("avatar")
                    except: pass
                users.append({"id": folder, "name": name, "avatar": avatar})
                
    users.sort(key=lambda x: x["name"].lower())
    return {"status": "success", "data": users}

@router.post("/api/rp/save_user")
async def save_user_profile(
    name: str = Form(...), description: str = Form(""), 
    avatar: UploadFile = File(None), original_id: Optional[str] = Form(None)
):
    new_safe_id = rp_core.sanitize_filename(name)
    users_root = rp_core.DIRS["users"]
    new_user_folder = os.path.join(users_root, new_safe_id)

    if original_id and original_id != new_safe_id:
        old_user_folder = os.path.join(users_root, original_id)
        if os.path.exists(old_user_folder):
            if not os.path.exists(new_user_folder): os.rename(old_user_folder, new_user_folder)
    
    if not os.path.exists(new_user_folder): os.makedirs(new_user_folder, exist_ok=True)

    json_path = os.path.join(new_user_folder, "user_profile.json")
    avatar_filename = "default_user.png"
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                avatar_filename = json.load(f).get("avatar", avatar_filename)
        except: pass

    import time

    if avatar:
        # Delete old avatar
        if avatar_filename and avatar_filename != "default_user.png":
            old_path = os.path.join(new_user_folder, avatar_filename)
            if os.path.exists(old_path): os.remove(old_path)
            
        ext = avatar.filename.split(".")[-1]
        timestamp = int(time.time())
        saved_name = rp_core.save_uploaded_file(avatar, new_user_folder, f"avatar_{timestamp}.{ext}")
        if saved_name: avatar_filename = saved_name

    data = { "name": name, "description": description, "avatar": avatar_filename }
    with open(json_path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)
    return {"status": "success", "new_id": new_safe_id, "avatar_url": f"/assets/user_profiles/{new_safe_id}/{avatar_filename}"}

@router.get("/api/rp/get_user_detail")
def get_user_detail(folder_id: str = None, user_id: str = None):
    target_id = folder_id or user_id
    if not target_id: raise HTTPException(status_code=400, detail="folder_id or user_id is required")

    safe_id = rp_core.sanitize_filename(target_id)
    path = os.path.join(rp_core.DIRS["users"], safe_id, "user_profile.json")
    
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: 
            return {"status": "success", "data": json.load(f)}
            
    raise HTTPException(status_code=404, detail="User not found")

# ==========================================
# Settings & API Key Management
# ==========================================
from . import secure_config

class ApiKeyAction(BaseModel):
    name: str
    key: Optional[str] = None

class ApiKeyEditAction(BaseModel):
    old_name: str
    new_name: str
    new_key: Optional[str] = None

class ApiKeyAssignAction(BaseModel):
    role: str
    name: str

@router.get("/api/rp/settings/api_keys")
def get_api_keys():
    keys_info = secure_config.get_all_api_keys_info()
    assignments = secure_config.get_assignments()
    return {"status": "success", "data": {"keys": keys_info, "assignments": assignments}}

@router.post("/api/rp/settings/api_key_assign")
def assign_api_key(data: ApiKeyAssignAction):
    if not data.role or not data.name:
        raise HTTPException(status_code=400, detail="Role and Name are required")
    # if name is "_unassign", we remove it
    if data.name == "_unassign":
        secure_config.assign_key(data.role, "")
    else:
        secure_config.assign_key(data.role, data.name)
    return {"status": "success"}

@router.post("/api/rp/settings/api_key")
def add_api_key(data: ApiKeyAction):
    if not data.name or not data.key:
        raise HTTPException(status_code=400, detail="Name and Key are required")
    secure_config.save_api_key(data.name, data.key)
    return {"status": "success"}

@router.post("/api/rp/settings/edit_api_key")
def edit_api_key(data: ApiKeyEditAction):
    if not data.old_name or not data.new_name:
        raise HTTPException(status_code=400, detail="Old name and new name are required")
    success = secure_config.rename_and_update_api_key(data.old_name, data.new_name, data.new_key)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="API Key not found")

@router.post("/api/rp/settings/delete_api_key")
def remove_api_key(data: ApiKeyAction):
    if not data.name:
        raise HTTPException(status_code=400, detail="Name is required")
    success = secure_config.delete_api_key(data.name)
    if success:
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="API Key not found")