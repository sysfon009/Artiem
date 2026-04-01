import os
import json
from cryptography.fernet import Fernet
from typing import Dict, Optional, Any

# File paths
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_FILE = os.path.join(ROOT_DIR, ".secret.key")
CONFIG_FILE = os.path.join(ROOT_DIR, "config_secure.json")

def get_or_create_key() -> bytes:
    """Gets the existing encryption key or creates a new one if it doesn't exist."""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        return key

# Initialize fernet
fernet = Fernet(get_or_create_key())

def _load_data() -> Dict[str, Any]:
    """Loads and decrypts the config data."""
    if not os.path.exists(CONFIG_FILE):
        return {}
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        decrypted_data = {}
        for k, v in data.items():
            if k == "api_keys":
                decrypted_keys = {}
                for name, encrypted_key in v.items():
                    try:
                        decrypted_keys[name] = fernet.decrypt(encrypted_key.encode()).decode()
                    except Exception as e:
                        print(f"[SECURE CONFIG] Error decrypting key {name}: {e}")
                decrypted_data["api_keys"] = decrypted_keys
            else:
                decrypted_data[k] = v
        return decrypted_data
    except Exception as e:
        print(f"[SECURE CONFIG] Error loading config: {e}")
        return {}

def _save_data(data: Dict) -> None:
    """Encrypts and saves the config data."""
    encrypted_data = {}
    for k, v in data.items():
        if k == "api_keys":
            encrypted_keys = {}
            for name, plaintext_key in v.items():
                encrypted_keys[name] = fernet.encrypt(plaintext_key.encode()).decode()
            encrypted_data["api_keys"] = encrypted_keys
        else:
            encrypted_data[k] = v
            
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(encrypted_data, f, indent=4)

def get_assignments() -> Dict[str, str]:
    """Returns mapping of roles to API key names."""
    data = _load_data()
    return data.get("assignments", {})

def get_assigned_key(role: str) -> Optional[str]:
    """Returns the API key name assigned to a specific role."""
    assignments = get_assignments()
    return assignments.get(role)

def assign_key(role: str, name: str) -> None:
    """Assigns an API key name to a role."""
    data = _load_data()
    if "assignments" not in data:
        data["assignments"] = {}
    data["assignments"][role] = name
    _save_data(data)

def get_all_api_keys_info() -> list[dict]:
    """Returns a list of info dictionaries for all saved API keys."""
    data = _load_data()
    keys = data.get("api_keys", {})
    info = []
    for name, key in keys.items():
        key_str = str(key)
        if key_str.startswith("VERTEX_AI:"):
            key_type = "Vertex AI"
            parts = key_str[10:].split("|", 2)
            info.append({
                "name": name, 
                "type": key_type,
                "path": parts[0],
                "project_id": parts[1] if len(parts) > 1 else "",
                "location": parts[2] if len(parts) > 2 else "us-central1"
            })
        elif key_str.startswith("JSON_PATH:"):
            key_type = "Service Account JSON"
            path = key_str[10:]
            info.append({
                "name": name,
                "type": key_type,
                "path": path
            })
        else:
            key_type = "API Key"
            info.append({"name": name, "type": key_type, "is_secret": True})
    return info

def get_all_api_key_names() -> list[str]:
    """Returns a list of all saved API key names."""
    data = _load_data()
    return list(data.get("api_keys", {}).keys())

def get_api_key(name: str) -> Optional[str]:
    """Retrieves the plaintext API key by name."""
    data = _load_data()
    return data.get("api_keys", {}).get(name)

def get_default_api_key() -> Optional[str]:
    """Retrieves the first available API key, or None if empty."""
    data = _load_data()
    keys = data.get("api_keys", {})
    if not keys:
        return None
    # Return the first key
    return list(keys.values())[0]

def save_api_key(name: str, key: str) -> None:
    """Saves a new API key or updates an existing one."""
    data = _load_data()
    if "api_keys" not in data:
        data["api_keys"] = {}
    data["api_keys"][name] = key
    _save_data(data)

def rename_and_update_api_key(old_name: str, new_name: str, new_key: Optional[str] = None) -> bool:
    """Updates an API key, including its name. Also updates assignments if renamed."""
    data = _load_data()
    if "api_keys" not in data or old_name not in data["api_keys"]:
        return False
        
    old_value = data["api_keys"][old_name]
    
    # Delete the old key entry and insert the new one
    del data["api_keys"][old_name]
    data["api_keys"][new_name] = new_key if new_key else old_value
    
    # Update any assignments that referenced the old name
    if "assignments" in data:
        for role, assigned_name in data["assignments"].items():
            if assigned_name == old_name:
                data["assignments"][role] = new_name
                
    _save_data(data)
    return True

def delete_api_key(name: str) -> bool:
    """Deletes an API key by name. Returns True if deleted, False if not found."""
    data = _load_data()
    deleted = False
    if "api_keys" in data and name in data["api_keys"]:
        del data["api_keys"][name]
        deleted = True
        
    # Remove from assignments as well
    if "assignments" in data:
        for role, assigned_name in list(data["assignments"].items()):
            if assigned_name == name:
                del data["assignments"][role]
                
    if deleted:
        _save_data(data)
    return deleted

def get_genai_client(api_key_or_path: str):
    """
    Returns a configured google.genai.Client.
    Supports Vertex AI via JSON Path (format VERTEX_AI:path|project_id|location),
    or standard API keys.
    """
    from google import genai
    import json
    
    if api_key_or_path and api_key_or_path.startswith("VERTEX_AI:"):
        # Format: VERTEX_AI:path|project_id|location
        data = api_key_or_path[10:]
        parts = data.split("|", 2)
        path = parts[0]
        project_id = parts[1] if len(parts) > 1 else None
        location = parts[2] if len(parts) > 2 else "us-central1"
        
        if not os.path.exists(path):
            raise FileNotFoundError(f"Service account JSON file not found: {path}")
            
        with open(path, "r", encoding="utf-8") as f:
            sa_info = json.load(f)
            
        if not project_id:
            project_id = sa_info.get("project_id")
            
        if not project_id:
            raise ValueError("Invalid Service Account JSON: 'project_id' missing and not provided.")
            
        from google.oauth2 import service_account
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
        
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
            credentials=credentials
        )
        return client
        
    elif api_key_or_path and api_key_or_path.startswith("JSON_PATH:"):
        # Backwards compatibility for old saved JSON_PATH keys
        path = api_key_or_path[10:]
        if not os.path.exists(path):
            raise FileNotFoundError(f"Service account JSON file not found: {path}")
            
        with open(path, "r", encoding="utf-8") as f:
            sa_info = json.load(f)
            
        project_id = sa_info.get("project_id")
        if not project_id:
            raise ValueError("Invalid Service Account JSON: 'project_id' missing.")
            
        from google.oauth2 import service_account
        scopes = ["https://www.googleapis.com/auth/cloud-platform"]
        credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
        
        # Determine location from an environment variable or default to us-central1
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        
        client = genai.Client(
            vertexai=True,
            project=project_id,
            location=location,
            credentials=credentials
        )
        return client
    else:
        client = genai.Client(api_key=api_key_or_path)
        return client

