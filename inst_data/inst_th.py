import json
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

JSON_DIR = os.path.join(root_dir, "json_file")
PROMPTS_DIR = os.path.join(root_dir, "prompts")

def _load_prompt(filename: str) -> str:
    """
    Membaca file text dari folder 'prompts'
    """
    target_path = os.path.join(PROMPTS_DIR, filename)
    
    if not os.path.exists(target_path):
        print("WARNING", f"Prompt file not found: {filename}")
        return ""
        
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception as e:
        print("ERROR", f"Failed reading prompt {filename}: {e}")
        return ""
def load_json_str(filename):
    """
    Membaca file JSON dari folder 'roots/json_file' dan 
    mengembalikannya sebagai string yang terformat rapi.
    """
    # Tentukan lokasi folder (sesuaikan jika struktur foldermu beda)

    file_path = os.path.join(JSON_DIR, filename)

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return json.dumps(data, indent=2, ensure_ascii=False) 
    except FileNotFoundError:
        print(f"[ERROR] File not found: {file_path}")
        return "{}" 
    except json.JSONDecodeError:
        print(f"[ERROR] Invalid JSON format in: {file_path}")
        return "{}"
    
def build_prompt(name, age, personality, appearance, inst_content, example_input="", example_output="", user_data=None, data_base=None ):
    character_json = load_json_str("character_profile_levina.json")
    world_json     = load_json_str("world_setting.json")
    user_json      = load_json_str("user_profile.json")
    thought = load_json_str("thinking_process.json")
    scenario_txt      = _load_prompt("levina.txt")
    mechanic_txt      = _load_prompt("mechanic.txt")

    # --- 1. DEBUGGING (Cek di Terminal) ---
    if user_data:
        print(f"[SYSTEM_INST] inst_def, got {user_data.get('name')}")
    else:
        print("[SYSTEM_INST] User Data is EMPTY or NONE!")
    # --------------------------------------

    u_name = "User"
    u_desc = ""
        
    if user_data:
        # Pastikan key-nya sama dengan JSON (biasanya lowercase 'name')
        u_name = user_data.get("name", "User")
        u_desc = user_data.get("description", "")

    example_section = ""
    if example_input and example_output:
        example_section = f"""
### Example Dialogue
User: {example_input}
{name}: {example_output}
"""
    return f"""
# system Instruction
CORE: WRITE YOUR REASONS AND YOUR THOUGHTS IN DETAIL AND COMPREHENSIF!
1. Analyze the current story context from the provided data. 
2. Analyze the user's input and purpose based on the context. If the user's input  is ambiguous, you need to deduce slowly and gradually.
3. analzye reasonable and logical response strategy based on the context. 
4. Create the best strategies to respond to user input.
5. analyze saturated and repetitive output that NOT important (inlcuding narrative flow structure) for revised. 
6. refine the response strategy and analysis that should be the response.
CRUCIAL: 
1. YOUR response history may contain errors, run the correct one, not the wrong one, referring to earlier data so that logic and consistency are maintained.
2. ONLY IF data is insufficient, you need to analyze slowly and in detail and then evaluate.
3. THIS DIRECTIVES FOR THE CORE YOUR BEHAVIOUR, THE OUTPUT MUST BE DETAIL, COMPREHENSIF, AND STRUCTURED WITH CONTINUOUS PART.
4. You can only take data from what's provided in the context window.
5. all must in thought=true
---
# System Data:
## 1. MAIN CHARACTER DATABASE 
The following is the base profile for the character you are {name}. another Character called NPC. Keep NPC personalities consistent. A greedy merchant acts differently than a fanatical priest.
NPC ROLE: Important NPC should be have a name, and less important NPC could just be label.
personality: {personality}
appereance: {appearance}

## 2. USER DATABASE 
The following is the base profile for the User. Treat this as the "Anchor" for the user's appearance and abilities, unless stated otherwise in the chat.
user name: {u_name}
{u_desc}
---

## 3. WORLD DATABASE (SETTING CONTEXT)
The following defines the laws, tone, and setting of the world.
CRUCIAL NOTE: YOU PROHIBITED TO ASSUME OR WRITE THAT RELATED TO RELINS OUTSIDE THIS INFORMATION, UNLESS I TELL YOU MORE INFORMATION.
{world_json}
"""