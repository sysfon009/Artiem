import sys
import os
import json
import time
import re
import importlib
import shutil
from typing import List
import base64
from PIL import Image
import io
import copy
from typing import List, Optional, Any, Tuple, Dict, AsyncGenerator
import uuid
from anchor.node_engine import engine_unstream
from anchor.node_engine import engine_function


def _debug_print(section, message, data=None):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] [CORE][{section}] {message}")
    if data:
        print(f"   >>> DATA: {data}")

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

ASSETS_DIR = os.path.join(root_dir, "assets")
if not os.path.exists(ASSETS_DIR):
    potential_assets = os.path.join(os.path.dirname(root_dir), "assets")
    if os.path.exists(potential_assets):
        ASSETS_DIR = potential_assets

DIRS = {
    "users": os.path.join(ASSETS_DIR, "user_profiles"),
    "chars": os.path.join(ASSETS_DIR, "Characters"),
    
}

HISTORY_FILES = [
    "log_final_resp", # untuk final output dan yang ditampilkan di UI.
    "buffer_session", 
    "log_data",
    "log_sessions", 
    "story_progress",  
    "log_fdata", 
    "log_simulation",
    "log_goal", 
    "log_tools",
    "log_eval",
    "log_image", 
]


def ensure_folders_exist():
    for key, path in DIRS.items():
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
            _debug_print("SETUP", f"Created folder: {path}")

ensure_folders_exist()

def sanitize_filename(name):
    if not name: return f"unnamed_{int(time.time())}"
    clean_name = re.sub(r'[^\w\s-]', '', str(name)).strip().replace(' ', '_')
    if not clean_name:
        return f"unnamed_{int(time.time())}"
    return clean_name
# Di dalam rp_core.py

def sanitize_filename_keep_ext(filename: str) -> str:
    if not filename: return "untitled"
    name_part, ext_part = os.path.splitext(filename)
    safe_name = sanitize_filename(name_part)
    if not safe_name: 
        safe_name = "file"
        
    return f"{safe_name}{ext_part}"

def save_uploaded_file(upload_file, destination_folder, new_filename):
    if not upload_file: return None
    file_path = os.path.join(destination_folder, new_filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        return new_filename
    except Exception as e:
        _debug_print("FILE", f"Error saving file: {e}")
        return None

def get_character_root(char_id: str):
    safe_id = sanitize_filename(char_id)
    path = os.path.join(DIRS["chars"], safe_id)
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

def get_histories_root(char_id: str):
    char_root = get_character_root(char_id)
    path = os.path.join(char_root, "Histories")
    if not os.path.exists(path): os.makedirs(path, exist_ok=True)
    return path

def get_latest_session_path(char_id: str):
    histories_dir = get_histories_root(char_id)
    if not os.path.exists(histories_dir): return None
    subfolders = [f.path for f in os.scandir(histories_dir) if f.is_dir()]
    if not subfolders: 
        return None
    try:
        latest = max(subfolders, key=os.path.getmtime)
        return latest
    except Exception as e:
        return None

def resolve_session_path(char_id: str, session_id: str = None):
    histories_dir = get_histories_root(char_id)
    
    if not session_id or session_id == "new_chat_mode":
        return None

    target_path = os.path.join(histories_dir, session_id)
    if os.path.exists(target_path):
        return target_path
    
    return get_latest_session_path(char_id)

### HELPER BUFFER

def get_turn_count(session_path: str) -> int:
    log_data_dir = os.path.join(session_path, "log_data")
    if not os.path.exists(log_data_dir):
        return 1
    
    # Mencari file dengan pola buffer_session_N.json
    files = [f for f in os.listdir(log_data_dir) if f.startswith("buffer_session_") and f.endswith(".json")]
    if not files:
        return 1
    
    # Ekstrak angka turn dari nama file
    turn_numbers = []
    for f in files:
        try:
            # Mengambil angka di antara 'buffer_session_' dan '.json'
            num = int(f.replace("buffer_session_", "").replace(".json", ""))
            turn_numbers.append(num)
        except ValueError:
            continue
            
    return max(turn_numbers) + 1 if turn_numbers else 1

def archive_and_clear_buffers(char_id: str, session_id: str):
    session_path = resolve_session_path(char_id, session_id)
    if not session_path:
        return False

    log_data_dir = os.path.join(session_path, "log_data")
    os.makedirs(log_data_dir, exist_ok=True)

    turn_num = get_turn_count(session_path)
    buffers_to_archive = ["buffer_session", "buffer_simulation"]
    
    success_count = 0
    for buf_name in buffers_to_archive:
        src_path = os.path.join(session_path, f"{buf_name}.json")
        dst_path = os.path.join(log_data_dir, f"{buf_name}_{turn_num}.json")

        if os.path.exists(src_path) and os.path.getsize(src_path) > 0:
            try:
                # Menggunakan SimpleFileLock agar aman saat proses pemindahan
                with SimpleFileLock(src_path):
                    # 1. Copy file (Archive)
                    shutil.copy2(src_path, dst_path)
                    
                    # 2. Validasi Ukuran File
                    if os.path.exists(dst_path) and os.path.getsize(dst_path) == os.path.getsize(src_path):
                        # 3. Kosongkan Buffer (Truncate)
                        with open(src_path, 'w', encoding='utf-8') as f:
                            f.write("[]") 
                        success_count += 1
                        _debug_print("ARCHIVE", f"Archived {buf_name} to turn {turn_num}")
            except Exception as e:
                _debug_print("ERROR", f"Failed to archive {buf_name}: {e}")
                
    return success_count > 0
def read_archived_buffer(char_id: str, session_id: str, buffer_type: str, turn_num: int) -> List[dict]:
    """
    Membaca file buffer yang sudah diarsip di dalam folder log_data.
    buffer_type: 'buffer_session' atau 'buffer_simulation'
    """
    folder = resolve_session_path(char_id, session_id)
    if not folder:
        return []

    # Konstruksi path ke sub-folder log_data
    file_path = os.path.join(folder, "log_data", f"{buffer_type}_{turn_num}.json")
    
    if os.path.exists(file_path):
        try:
            with SimpleFileLock(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.seek(0, os.SEEK_END)
                    if f.tell() == 0:
                        return []
                    f.seek(0)
                    data = json.load(f)
                    return data if isinstance(data, list) else []
        except Exception as e:
            _debug_print("READ_ARCHIVE", f"Error reading archived file {file_path}: {e}")
    
    return []
#-------
_CHAR_CACHE = {}

def load_character_profile_cached(char_id: str, current_mtime: float):
    if char_id in _CHAR_CACHE:
        cached_data, cached_mtime = _CHAR_CACHE[char_id]
        if cached_mtime == current_mtime:
            return cached_data

    folder = get_character_root(char_id)
    json_path = os.path.join(folder, "Character_Profile.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _CHAR_CACHE[char_id] = (data, current_mtime)
                return data
        except Exception as e:
            _debug_print("PROFILE", f"Error loading char profile: {e}")
            return None
    return None

def load_user_profile(user_id: str):
    if not user_id: return None
    safe_id = sanitize_filename(user_id)
    user_folder = os.path.join(DIRS["users"], safe_id)
    json_path = os.path.join(user_folder, "user_profile.json")
    
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            _debug_print("PROFILE", f"Error loading user profile: {e}")
            return None
    return None

class SimpleFileLock:
    def __init__(self, file_path, timeout=5.0):
        self.lock_file = file_path + ".lock"
        self.timeout = timeout
        
    def __enter__(self):
        start_time = time.time()
        while True:
            try:
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL)
                os.close(fd)
                return
            except FileExistsError:
                # Stale lock cleanup: if lock file is older than 30 seconds, remove it
                try:
                    lock_age = time.time() - os.path.getmtime(self.lock_file)
                    if lock_age > 30:
                        _debug_print("LOCK", f"Removing stale lock ({lock_age:.0f}s old): {os.path.basename(self.lock_file)}")
                        os.remove(self.lock_file)
                        continue
                except (OSError, FileNotFoundError):
                    continue
                if time.time() - start_time > self.timeout:
                    _debug_print("LOCK", f"Lock timeout for {os.path.basename(self.lock_file)}")
                    raise TimeoutError(f"Gagal mendapatkan lock file: {self.lock_file}")
                time.sleep(0.05)
            except Exception as e:
                raise e

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if os.path.exists(self.lock_file):
                os.remove(self.lock_file)
        except Exception:
            pass

def create_new_session(char_id: str, trigger_message: str = "init"):
    clean_text = re.sub(r'[^\w\s-]', '', str(trigger_message)).strip()
    
    session_name = f"session_{int(time.time())}"
    if clean_text:
        words = clean_text.split()
        safe_words = "_".join(words[:5])
        session_name = safe_words[:50].replace(" ", "_")
    
    histories_dir = get_histories_root(char_id)
    session_path = os.path.join(histories_dir, session_name)
    
    if os.path.exists(session_path):
        session_path = f"{session_path}_{int(time.time())}"
        
    try:
        os.makedirs(session_path, exist_ok=True)
        os.makedirs(os.path.join(session_path, "storage"), exist_ok=True)
        
        for fname in HISTORY_FILES:
            file_path = os.path.join(session_path, f"{fname}.json")
            with open(file_path, 'w', encoding='utf-8') as f:
                pass
        
        _debug_print("SESSION", f"New session created: {os.path.basename(session_path)}")
        return session_path
    except Exception as e:
        _debug_print("SESSION", f"Error creating session: {e}")
        return None

def read_history_file(char_id: str, session_id: str, target_file: str) -> List[dict]:
    if target_file not in HISTORY_FILES:
        _debug_print("READ", f"Invalid target file requested: {target_file}")
        return []

    folder = resolve_session_path(char_id, session_id)
    if not folder:
        return []

    file_path = os.path.join(folder, f"{target_file}.json") # Pastikan ekstensinya .json
    
    if os.path.exists(file_path):
        try:
            with SimpleFileLock(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    f.seek(0, os.SEEK_END)
                    if f.tell() == 0:
                        return []
                    f.seek(0) 
                    
                    data = json.load(f)
                    
                    if isinstance(data, list):
                        return data
                    else:
                        _debug_print("READ", f"Format error in {target_file}: expected list")
                        return []

        except json.JSONDecodeError as e:
            _debug_print("READ", f"JSON Decode Error in {target_file}: {e}")
            return []
        except Exception as e:
            _debug_print("READ", f"Error reading {target_file}: {e}")
            return []
    
    return []

def append_to_history_file(char_id: str, session_id: str, target_file: str, data_payload: dict):
    if target_file not in HISTORY_FILES:
        _debug_print("WRITE", f"Invalid target file: {target_file}")
        return False

    folder = resolve_session_path(char_id, session_id)
    if not folder:
        # Session belum ada atau invalid
        return False

    file_path = os.path.join(folder, f"{target_file}.json")
    # File sementara untuk atomic write
    temp_path = os.path.join(folder, f"{target_file}.tmp") 
    
    try:
        with SimpleFileLock(file_path):
            current_data = []

            # 1. BACA DATA LAMA (Load)
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        loaded_data = json.load(f)
                        if isinstance(loaded_data, list):
                            current_data = loaded_data
                        else:
                            _debug_print("WRITE", f"Warning: {target_file} structure invalid (not a list). Resetting.")
                except json.JSONDecodeError:
                    _debug_print("WRITE", f"Warning: {target_file} is corrupt. Resetting to empty list to recover.")
            
            current_data.append(data_payload)


            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(current_data, f, ensure_ascii=False, indent=2)
            
            os.replace(temp_path, file_path)
            
        return True

    except Exception as e:
        _debug_print("WRITE", f"Critical Error writing {target_file}: {e}")
        # Bersihkan temp file jika gagal
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return False
    
def delete_history_turns(char_id: str, session_id: str, target_index: int):
    import re 
    
    folder = resolve_session_path(char_id, session_id)
    if not folder:
        _debug_print("DELETE", "Session folder not found.")
        return False

    log_final_path = os.path.join(folder, "log_final_resp.json")
    cutoff_timestamp = None
    target_turn_id = None
    
    # ==========================================
    # 1. CARI TIMESTAMP ABSOLUT DARI INDEX UI
    # ==========================================
    if os.path.exists(log_final_path):
        try:
            with open(log_final_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Ambil timestamp dari index persis yang diklik user
                if isinstance(data, list) and 0 <= target_index < len(data):
                    cutoff_timestamp = data[target_index].get("timestamp")
                    target_turn_id = data[target_index].get("turn_id")
        except Exception as e:
            _debug_print("DELETE", f"Error reading log_final_resp: {e}")

    # Jika index meleset/tidak ketemu, batalkan agar tidak menghapus seluruh chat secara brutal
    if cutoff_timestamp is None:
        _debug_print("DELETE", "Cutoff timestamp tidak ditemukan. Aborting delete.")
        return False

    success_any = False
    images_to_delete = set() 

    # ==========================================
    # 2. EXTRACTOR NAMA GAMBAR ANTI-MELESET
    # ==========================================
    def extract_images_from_data(deleted_items):
        for item in deleted_items:
            parts = item.get("parts", [])
            if isinstance(parts, list):
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                        
                    # 1. Hapus gambar yang dihasilkan oleh tool (direct/fallback format)
                    if part.get("name") in ["generate_image", "get_image_detail"]:
                        resp = part.get("response", {})
                        if isinstance(resp, dict) and "display_name" in resp:
                            images_to_delete.add(resp["display_name"])
                            
                    # 2. Hapus gambar dari response AI functionResponse
                    if "functionResponse" in part and isinstance(part["functionResponse"], dict):
                        resp = part["functionResponse"].get("response", {})
                        if isinstance(resp, dict) and "display_name" in resp:
                            images_to_delete.add(resp["display_name"])
                            
                    # 3. Hapus gambar lampiran dari user/AI (umumnya di dalam parts)
                    if "user_attachment" in part and isinstance(part["user_attachment"], dict):
                        disp = part["user_attachment"].get("display_name")
                        if disp:
                            images_to_delete.add(disp)
                            
                    # 4. Format execution result lainnya
                    if "execution_result" in part and isinstance(part["execution_result"], dict):
                        disp = part["execution_result"].get("display_name")
                        if disp:
                            images_to_delete.add(disp)
                            
            # Jika menggunakan format lama di mana user_attachment ada di level item
            if "user_attachment" in item and isinstance(item["user_attachment"], dict):
                disp = item["user_attachment"].get("display_name")
                if disp:
                    images_to_delete.add(disp)

    # ==========================================
    # 3. PROSES SINKRONISASI PENGHAPUSAN FILE
    # ==========================================
    for fname in HISTORY_FILES:
        file_path = os.path.join(folder, f"{fname}.json")
        if not os.path.exists(file_path):
            continue

        try:
            with SimpleFileLock(file_path):
                current_data = []
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        current_data = json.load(f)
                    except json.JSONDecodeError:
                        continue

                if not isinstance(current_data, list) or len(current_data) == 0:
                    continue

                kept_data = []
                deleted_data = []
                
                for item in current_data:
                    item_ts = item.get("timestamp", 0)
                    item_turn = item.get("turn_id")
                    
                    # HAPUS berdasarkan turn_id jika ada, JIKA tidak fallback ke timestamp
                    if (target_turn_id is not None and item_turn is not None and item_turn >= target_turn_id):
                        deleted_data.append(item)
                    elif (item_ts >= cutoff_timestamp):
                        deleted_data.append(item)
                    else:
                        kept_data.append(item)
                        
                extract_images_from_data(deleted_data)

                # Simpan ulang hanya data yang selamat
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(kept_data, f, ensure_ascii=False, indent=2)
                
                success_any = True

        except Exception as e:
            _debug_print("DELETE", f"Error modifying {fname}: {e}")

    # ==========================================
    # 4. HAPUS FILE GAMBAR FISIK (STORAGE)
    # ==========================================
    storage_path = os.path.join(folder, "storage")
    if os.path.exists(storage_path) and images_to_delete:
        for img_name in images_to_delete:
            img_path = os.path.join(storage_path, img_name)
            if os.path.exists(img_path):
                try:
                    os.remove(img_path)
                    _debug_print("DELETE", f"Removed physical image: {img_name}")
                except Exception as e:
                    _debug_print("DELETE", f"Failed to remove image {img_name}: {e}")

    return success_any
    
def encode_image_from_storage(char_id: str, session_id: str, filename: str, compress: bool = True) -> str:
    
    safe_char_id = sanitize_filename(char_id)
    safe_session_id = sanitize_filename(session_id)
    
    histories_root = get_histories_root(safe_char_id)
    physical_filepath = os.path.join(histories_root, safe_session_id, "storage", filename)
    
    if not os.path.exists(physical_filepath):
        print(f"[HELPER_ERROR] File tidak ditemukan saat encode: {physical_filepath}")
        return None
        
    try:
        if compress:
            # Buka gambar menggunakan Pillow
            with Image.open(physical_filepath) as img:
                
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                
                buffer = io.BytesIO()
                
                img.save(buffer, format="JPEG", quality=85)
                
                image_bytes = buffer.getvalue()
        else:
            # Buka file as raw bytes (uncompressed)
            with open(physical_filepath, "rb") as f:
                image_bytes = f.read()
                
        status_msg = "SUCCESS ENCODING & COMPRESSING" if compress else "SUCCESS ENCODING (UNCOMPRESSED)"
        print(f"[CORE_HELPER] {status_msg} {filename}")
        return base64.b64encode(image_bytes).decode('utf-8')
        
    except Exception as e:
        print(f"[HELPER_ERROR] ENCODE FAILED {filename}: {e}")
        return None

async def describe_image_helper(image_b64: str, mime_type: str) -> str:
    config = {
        "model": "gemini-3-flash-preview",
        "temperature": 1.0,
        "top_p": 0.95,
        "top_k": 40
    }
    instruction = "make detailed description of the image max 200 words without assumptions. describe the image such as art style, quality of the images, the detailed contents, accessories, features, etc. ONLY based on the image content, do not add any extra information or assumption."
    context = [{"inline_data": {"mime_type": mime_type, "data": image_b64}}]
    
    import asyncio
    max_retries = 2
    for attempt in range(max_retries + 1):
        full_text = ""
        try:
            chunks = await engine_unstream.generate_unstream(
                context=context,
                instruction=instruction,
                history=[],
                config=config,
                custom_tools=None
            )
            for chunk in chunks:
                if chunk.get("type") == "text":
                    full_text += chunk.get("content", "")
                elif chunk.get("type") == "error":
                    raise Exception(chunk.get("content", "Unknown error"))
            
            if full_text.strip():
                return full_text.strip()
            else:
                raise Exception("Empty description returned")
                
        except Exception as e:
            _debug_print("DESCRIBE_IMG", f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(2)
            else:
                return "Generated image"
    
async def non_stream_llm_response(
    context, 
    history, 
    instruction, 
    config, 
    custom_tools, 
    out_collected_parts: list, 
    out_tool_reqs: list
):
    """
    Versi Non-Streaming: Menunggu seluruh respons AI selesai di-generate,
    lalu memetakan hasilnya ke format parts standar untuk history dan eksekusi tool.
    """
    
    # 1. Tunggu engine bekerja sampai tuntas (Tidak pakai async for)
    all_parts = await engine_unstream.generate_unstream(
        context=context, 
        history=history, 
        instruction=instruction, 
        config=config, 
        custom_tools=custom_tools
    )
    
    # 2. Iterasi hasil matang dan masukkan ke daftar pengumpulan
    for part in all_parts:
        part_type = part.get("type")
        content = part.get("content")
        
        # Ambil signature jika menempel pada part tersebut
        signature = part.get("thought_signature")

        if part_type == "text":
            new_part = {"text": content}
            if signature: new_part["thought_signature"] = signature
            out_collected_parts.append(new_part)
            
        elif part_type == "thought":
            new_part = {"text": content, "thought": True}
            if signature: new_part["thought_signature"] = signature
            out_collected_parts.append(new_part)
            
        elif part_type == "function_call":
            out_tool_reqs.append(content) 
            
            new_part = {"functionCall": content}
            if signature: new_part["thought_signature"] = signature
            out_collected_parts.append(new_part)
            
        elif part_type == "executable_code":
            new_part = {"executable_code": content}
            if signature: new_part["thought_signature"] = signature
            out_collected_parts.append(new_part)
            
        elif part_type == "code_execution_result":
            out_collected_parts.append({"code_execution_result": content})
            
        elif part_type == "thought_signature":
            # Jika ada signature yang terpisah (orphan), tempelkan ke part sebelumnya
            if out_collected_parts and "code_execution_result" not in out_collected_parts[-1]:
                out_collected_parts[-1]["thought_signature"] = content
            else:
                out_collected_parts.append({"text": "", "thought_signature": content})
                
        elif part_type == "error":
            # Tangkap error dari engine agar bisa di-log atau di-debug
            print(f"[NON_STREAM_ERROR] AI Engine Error: {content}")
            out_collected_parts.append({"text": f"\n[System Error: {content}]\n"})
    
def _log_interaction(char_id, session_id, filename, role, content, signature=None, turn_id=None):
    final_parts = []
    
    def _normalize_part(item):
        if isinstance(item, str): return {"text": item}
        if not isinstance(item, dict): return {"text": str(item)}
        
        item = copy.deepcopy(item)

        if item.get("type") == "thought":
            return {"text": item.get("content", ""), "thought": True}
        if item.get("thought") is True and "content" in item:
            item["text"] = item.pop("content")

        if "user_attachment" in item and "inline_data" in item["user_attachment"]:
            idata = item["user_attachment"]["inline_data"]
            data_val = idata.get("data", "")
            
            if isinstance(data_val, str) and len(data_val) > 1000 and not data_val.startswith("LOCAL_FILE:"):
                filename_safe = item["user_attachment"].get("display_name", "omitted_image")
                idata["data"] = f"LOCAL_FILE:{filename_safe}"
                
        valid_keys = [
            "text", "thought", "thought_signature", "user_attachment",
            "functionCall", "functionResponse", 
            "executable_code", "code_execution_result"
        ]
        
        clean_item = {k: v for k, v in item.items() if k in valid_keys}
        
        if not clean_item and item: 
            return {"text": json.dumps(item, ensure_ascii=False)}
            
        return clean_item

    try:
        items_to_process = content if isinstance(content, list) else [content]
        
        for item in items_to_process:
            final_parts.append(_normalize_part(item))

        if signature and role == "model" and final_parts:
            signature_already_exists = any("thought_signature" in part for part in final_parts)
            if not signature_already_exists:
                attached = False
                for part in reversed(final_parts):
                    if any(k in part for k in ["executable_code", "functionCall", "text"]) or part.get("thought") is True:
                        part["thought_signature"] = signature
                        attached = True
                        break
                if not attached: 
                    final_parts[-1]["thought_signature"] = signature

        # Strip inline_data ONLY for log_final_resp saves
        if filename == "log_final_resp":
            for part in final_parts:
                # 1. user_attachment
                if "user_attachment" in part and isinstance(part["user_attachment"], dict):
                    ua = part["user_attachment"]
                    ua_idata = ua.get("inline_data", {})
                    if isinstance(ua_idata, dict):
                        data_val = ua_idata.get("data", "")
                        if not (isinstance(data_val, str) and data_val.startswith("LOCAL_FILE:")):
                            disp = ua.get("display_name")
                            if disp:
                                ua["inline_data"] = {"mime_type": ua_idata.get("mime_type", "image/png"), "data": f"LOCAL_FILE:{disp}"}
                            else:
                                ua.pop("inline_data", None)
                                
                # 2. functionResponse.response
                if "functionResponse" in part and isinstance(part["functionResponse"], dict):
                    fr_resp = part["functionResponse"].get("response", {})
                    if isinstance(fr_resp, dict):
                        # Support for generate_image (direct keys)
                        if "inline_data" in fr_resp:
                            fr_idata = fr_resp["inline_data"]
                            data_val = fr_idata.get("data", "")
                            if not (isinstance(data_val, str) and data_val.startswith("LOCAL_FILE:")):
                                disp = fr_resp.get("display_name")
                                if disp:
                                    fr_resp["inline_data"] = {"mime_type": fr_idata.get("mime_type", "image/png"), "data": f"LOCAL_FILE:{disp}"}
                                else:
                                    fr_resp.pop("inline_data", None)
                        
                        # Support for get_image_detail (nested execution_result or user_attachment)
                        for nested_key in ["execution_result", "user_attachment"]:
                            if nested_key in fr_resp and isinstance(fr_resp[nested_key], dict):
                                nested = fr_resp[nested_key]
                                if "inline_data" in nested:
                                    n_idata = nested["inline_data"]
                                    data_val = n_idata.get("data", "")
                                    if not (isinstance(data_val, str) and data_val.startswith("LOCAL_FILE:")):
                                        disp = nested.get("display_name")
                                        if disp:
                                            nested["inline_data"] = {"mime_type": n_idata.get("mime_type", "image/png"), "data": f"LOCAL_FILE:{disp}"}
                                        else:
                                            nested.pop("inline_data", None)

        if final_parts:
            entry = {"role": role, "parts": final_parts, "timestamp": time.time()}
            if turn_id is not None: entry["turn_id"] = turn_id
            
            append_to_history_file(char_id, session_id, filename, entry)
            
    except Exception as e:
        print(f"[ERROR] Failed to log interaction: {e}")

# ==========================================
# 2. LOGIC MODULAR HELPERS
# ==========================================
def _handle_session_setup(char_id: str, session_id: Optional[str], user_message: str, char_data: Dict[str, Any]) -> Tuple[str, bool, int, list]:
    """Handles session creation, greetings, and turn ID calculation."""
    current_session_id = session_id
    session_path_exists = resolve_session_path(char_id, current_session_id)
    is_new_session = False
    
    if not current_session_id or current_session_id == "new_chat_mode" or not session_path_exists:
        session_path = create_new_session(char_id, user_message)
        if session_path:
            current_session_id = os.path.basename(session_path)
            is_new_session = True

    if is_new_session:
        raw_greeting = char_data.get("initial_message")
        if raw_greeting and raw_greeting.strip():
            _log_interaction(char_id, current_session_id, "log_final_resp", "model", raw_greeting, turn_id=1)

    d_resp = read_history_file(char_id, current_session_id, "log_final_resp") or []
    last_turn_id = d_resp[-1].get("turn_id", 0) if isinstance(d_resp, list) and len(d_resp) > 0 else 0
    current_turn_id = last_turn_id + 1
    
    return current_session_id, is_new_session, current_turn_id, d_resp

async def _process_attachments(char_id: str, session_id: str, user_message: str, attachment: Optional[list], turn_id: int = 1) -> Tuple[list, list]:
    """Handles file saving, image encoding, creates API & History JSON parts, logs to log_data, and describes images."""
    final_api = []
    final_history = []
    has_text = bool(user_message and user_message.strip())

    if attachment and isinstance(attachment, list):
        safe_char_id = sanitize_filename(char_id)
        safe_session_id = sanitize_filename(session_id)
        storage_path = os.path.join(get_histories_root(safe_char_id), safe_session_id, "storage")
        os.makedirs(storage_path, exist_ok=True)
        
        existing_images = len([f for f in os.listdir(storage_path) if f.startswith("attachment_")]) if os.path.exists(storage_path) else 0

        # --- TAMBAHAN PERSIAPAN: Hitung attachment_id awal untuk log_data ---
        current_attachment_id = 1
        try:
            log_data_history = read_history_file(char_id, session_id, "log_data") or []
            current_attachment_id = sum(1 for entry in log_data_history if entry.get("turn_id") == turn_id and "user_attachment" in entry) + 1
        except Exception:
            pass
        # --------------------------------------------------------------------

        for idx, att in enumerate(attachment):
            b64_data = att.get("data")
            mime_type = att.get("mime_type", "image/jpeg")
            
            if b64_data:
                try:
                    saved_filename = f"attachment_{existing_images + idx + 1}_{str(uuid.uuid4())[:8]}.png"
                    filepath = os.path.join(storage_path, saved_filename)

                    # Selalu simpan sebagai PNG (lossless) untuk menjaga kualitas
                    img_bytes = base64.b64decode(b64_data)
                    img = Image.open(io.BytesIO(img_bytes))
                    img.save(filepath, format="PNG")

                    compressed_b64 = encode_image_from_storage(char_id, session_id, saved_filename)
                    final_b64 = compressed_b64 if compressed_b64 else b64_data

                    # Describe the image
                    img_desc = await describe_image_helper(final_b64, mime_type)

                    # --- TAMBAHAN PROSES: HANYA UNTUK SAVE KE log_data.json ---
                    attachment_log_entry = {
                        "user_attachment": {
                            "display_name": saved_filename,
                            "img_description": img_desc,
                            "attachment_id": current_attachment_id,
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": f"LOCAL_FILE:{saved_filename}"
                            }
                        },
                        "turn_id": turn_id,
                        "timestamp": time.time()
                    }
                    try:
                        append_to_history_file(char_id, session_id, "log_data", attachment_log_entry)
                        current_attachment_id += 1  # Naikkan ID untuk iterasi berikutnya
                    except Exception as e:
                        print(f"[System] Failed to save attachment to log_data: {e}")
                    # ----------------------------------------------------------

                    # Kode asli tetap utuh
                    api_part = {"user_attachment": {"display_name": saved_filename, "img_description": img_desc, "inline_data": {"mime_type": mime_type, "data": final_b64}}}
                    history_part = {"user_attachment": {"display_name": saved_filename, "img_description": img_desc, "inline_data": {"mime_type": mime_type, "data": f"LOCAL_FILE:{saved_filename}"}}}


                    if idx == 0 and has_text:
                        api_part["text"] = user_message
                        history_part["text"] = user_message

                    final_api.append(api_part)
                    final_history.append(history_part)
                except Exception as e:
                    err = {"text": f"\n[System: Failed to process image {idx+1}. Error: {e}]"}
                    final_api.append(err); final_history.append(err)
    elif has_text:
        final_api.append({"text": user_message})
        final_history.append({"text": user_message})

    return final_api, final_history

def _clean_history_images(d_resp: list) -> list:
    """Reads history and removes LOCAL_FILE pointers so API doesn't crash on invalid base64."""
    resolved = copy.deepcopy(d_resp)
    for turn in resolved:
        for part in turn.get("parts", []):
            targets = [part.get("functionResponse", {}).get("response", {}), part]
            # Also check inside user_attachment for nested inline_data
            if isinstance(part, dict) and "user_attachment" in part:
                att = part["user_attachment"]
                if isinstance(att, dict):
                    targets.append(att)
            for target in targets:
                if isinstance(target, dict) and "inline_data" in target:
                    idata = target["inline_data"]
                    if isinstance(idata.get("data"), str) and idata["data"].startswith("LOCAL_FILE:"):
                        # Remove inline_data completely so API doesn't crash
                        del target["inline_data"]
    return resolved

def save_thought_signature(char_id: str, session_id: str, sig_b64: str, turn_id: int) -> str:
    """
    Saves a thought_signature (base64 string) to a binary file in storage.
    Returns LOCAL_FILE:filename tag for lightweight storage in log_final_resp.
    Image models return thought_signatures that contain the generated image itself,
    so these can be multi-MB and must not be stored inline in JSON logs.
    """
    safe_char_id = sanitize_filename(char_id)
    safe_session_id = sanitize_filename(session_id)
    
    histories_root = get_histories_root(safe_char_id)
    storage_path = os.path.join(histories_root, safe_session_id, "storage")
    os.makedirs(storage_path, exist_ok=True)
    
    # Count existing sig files for this turn
    existing_sigs = len([f for f in os.listdir(storage_path) if f.startswith(f"thought_sig_{turn_id}_")])
    short_id = uuid.uuid4().hex[:6]
    filename = f"thought_sig_{turn_id}_{existing_sigs + 1}_{short_id}.bin"
    filepath = os.path.join(storage_path, filename)
    
    try:
        raw_bytes = base64.b64decode(sig_b64)
        with open(filepath, 'wb') as f:
            f.write(raw_bytes)
        _debug_print("SIG_SAVE", f"Saved thought_signature to {filename} ({len(raw_bytes)} bytes)")
        return f"LOCAL_FILE:{filename}"
    except Exception as e:
        _debug_print("SIG_SAVE", f"Failed to save thought_signature: {e}")
        return sig_b64  # fallback: keep original

def _load_thought_signature(char_id: str, session_id: str, filename: str) -> str:
    """Loads a thought_signature binary file and returns it as a base64 string."""
    safe_char_id = sanitize_filename(char_id)
    safe_session_id = sanitize_filename(session_id)
    
    histories_root = get_histories_root(safe_char_id)
    filepath = os.path.join(histories_root, safe_session_id, "storage", filename)
    
    if not os.path.exists(filepath):
        _debug_print("SIG_LOAD", f"Signature file not found: {filename}")
        return None
    
    try:
        with open(filepath, 'rb') as f:
            raw_bytes = f.read()
        return base64.b64encode(raw_bytes).decode('utf-8')
    except Exception as e:
        _debug_print("SIG_LOAD", f"Failed to load thought_signature {filename}: {e}")
        return None

def _resolve_img_history(d_resp: list, char_id: str, session_id: str) -> list:
    """
    Resolves history for image pipeline. Specialized version that:
    1. Resolves thought_signature LOCAL_FILE: references back to base64 (these contain the generated images)
    2. Resolves user_attachment inline_data LOCAL_FILE: references (input images from user)
    3. Does NOT re-resolve generated image inline_data — thought_signature already carries that context
    """
    resolved = copy.deepcopy(d_resp)
    for turn in resolved:
        for part in turn.get("parts", []):
            # 1. Resolve thought_signature LOCAL_FILE references
            raw_sig = part.get("thought_signature")
            if isinstance(raw_sig, str) and raw_sig.startswith("LOCAL_FILE:"):
                fname = raw_sig.replace("LOCAL_FILE:", "")
                loaded_sig = _load_thought_signature(char_id, session_id, fname)
                if loaded_sig:
                    part["thought_signature"] = loaded_sig
                else:
                    # Can't load — remove signature rather than send broken data
                    del part["thought_signature"]
            
            # 2. Resolve user_attachment inline_data (input images from user)
            if "user_attachment" in part and isinstance(part["user_attachment"], dict):
                att = part["user_attachment"]
                if "inline_data" in att:
                    idata = att["inline_data"]
                    if isinstance(idata.get("data"), str) and idata["data"].startswith("LOCAL_FILE:"):
                        fname = idata["data"].replace("LOCAL_FILE:", "")
                        b64_str = encode_image_from_storage(char_id, session_id, fname, compress=False)
                        if b64_str:
                            idata["data"] = b64_str
                        else:
                            # Can't load — remove inline_data
                            del att["inline_data"]

            # 3. For generated image inline_data (in functionResponse or direct),
            #    just strip them — thought_signature carries the image context
            if "functionResponse" in part:
                resp = part["functionResponse"].get("response", {})
                if isinstance(resp, dict) and "inline_data" in resp:
                    idata = resp["inline_data"]
                    if isinstance(idata.get("data"), str) and idata["data"].startswith("LOCAL_FILE:"):
                        del resp["inline_data"]
            
            if "inline_data" in part and not "user_attachment" in part:
                idata = part["inline_data"]
                if isinstance(idata.get("data"), str) and idata["data"].startswith("LOCAL_FILE:"):
                    del part["inline_data"]

    return resolved

async def _stream_llm_response(context, history, instruction, config, custom_tools, out_collected_parts: list, out_tool_reqs: list, engine=None) -> AsyncGenerator[str, None]:
    """Core generator that streams LLM chunks and parses them cleanly.
    
    Args:
        engine: Optional engine module to use. Must have a generate() async generator.
                Defaults to engine_function if not provided.
    """
    if engine is None:
        engine = engine_function
    
    current_text_buffer = ""
    pending_signature = None

    try:
        async for chunk in engine.generate(
            context=context, 
            history=history, 
            instruction=instruction, 
            config=config, 
            custom_tools=custom_tools
        ):
            chunk_type = chunk.get("type")
            content = chunk.get("content")
            
            incoming_sig = chunk.get("thought_signature")
            if chunk_type == "thought_signature": incoming_sig = content
            if incoming_sig and chunk_type != "thought_signature": pending_signature = incoming_sig

            if chunk_type == "text": 
                current_text_buffer += content
                yield json.dumps(chunk) + "\n"
            
            elif chunk_type == "thought":
                if current_text_buffer: out_collected_parts.append({"text": current_text_buffer}); current_text_buffer = ""
                new_part = {"text": content, "thought": True}
                if pending_signature: new_part["thought_signature"] = pending_signature; pending_signature = None 
                out_collected_parts.append(new_part)
                yield json.dumps(chunk) + "\n"

            elif chunk_type == "function_call":
                if current_text_buffer: out_collected_parts.append({"text": current_text_buffer}); current_text_buffer = ""
                out_tool_reqs.append(content)
                tool_part = {"functionCall": content}
                if pending_signature: tool_part["thought_signature"] = pending_signature; pending_signature = None
                out_collected_parts.append(tool_part)
                if isinstance(content, dict) and content.get("name") == "generate_image":
                    yield json.dumps({"type": "generating_image"}) + "\n"
                yield json.dumps(chunk) + "\n"

            elif chunk_type == "executable_code":
                if current_text_buffer: out_collected_parts.append({"text": current_text_buffer}); current_text_buffer = ""
                code_part = {"executable_code": content}
                if pending_signature: code_part["thought_signature"] = pending_signature; pending_signature = None
                out_collected_parts.append(code_part)
                yield json.dumps(chunk) + "\n"

            elif chunk_type == "code_execution_result":
                if current_text_buffer: out_collected_parts.append({"text": current_text_buffer}); current_text_buffer = ""
                out_collected_parts.append({"code_execution_result": content})
                yield json.dumps(chunk) + "\n"
            
            elif chunk_type == "thought_signature":
                if current_text_buffer:
                    out_collected_parts.append({"text": current_text_buffer, "thought_signature": incoming_sig})
                    current_text_buffer = ""; pending_signature = None 
                elif out_collected_parts and "code_execution_result" not in out_collected_parts[-1]:
                    out_collected_parts[-1]["thought_signature"] = incoming_sig; pending_signature = None
                else: pending_signature = incoming_sig

    except Exception as e:
        yield json.dumps({"type": "error", "content": str(e)}) + "\n"

    if current_text_buffer:
        final_part = {"text": current_text_buffer}
        if pending_signature: final_part["thought_signature"] = pending_signature
        out_collected_parts.append(final_part)
    elif pending_signature and out_collected_parts:
        out_collected_parts[-1]["thought_signature"] = pending_signature

def _load_instruction_module(inst_name: str):
    default_module = "inst_work"
    if not inst_name:
        inst_name = default_module
    inst_name = inst_name.replace("..", "").replace("/", "").strip()
    try:
        module_path = f"inst_data.{inst_name}"
        mod = importlib.import_module(module_path)
        return mod
    except ImportError:
        _debug_print("WARNING", f"Instruction module '{inst_name}' not found. Falling back to {default_module}.")
        try:
            return importlib.import_module(f"inst_data.{default_module}")
        except ImportError:
            _debug_print("ERROR", "CRITICAL: Default instruction module missing!")
            return None