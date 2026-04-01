import requests
import json

# URL Sandbox (Arahkan ke Docker container)
SANDBOX_URL = "http://localhost:5000/execute"

def execute_python(code: str) -> str:
    """
    Executes Python code in a stateful, isolated sandbox environment.
    
    Args:
        code (str): The Python code snippet to execute.
    
    Returns:
        str: The combined stdout and stderr from the execution, or an error message.
    """
    payload = {"code": code}
    
    try:
        # Kirim kode ke Docker Container via HTTP
        response = requests.post(SANDBOX_URL, json=payload, timeout=30)
        
        # Cek jika koneksi berhasil tapi server error (500)
        if response.status_code != 200:
            return f"System Error: Sandbox returned status {response.status_code}"
            
        result = response.json()
        
        # Format output agar enak dibaca oleh LLM / User
        output_parts = []
        
        if result['stdout']:
            output_parts.append(f"OUTPUT:\n{result['stdout']}")
        
        if result['stderr']:
            output_parts.append(f"ERROR:\n{result['stderr']}")
            
        if not output_parts:
            return "Code executed successfully (No Output)."
            
        return "\n".join(output_parts)

    except requests.exceptions.ConnectionError:
        return "Connection Error: Could not connect to the sandbox. Is the Docker container running?"
    except Exception as e:
        return f"Execution failed: {str(e)}"

if __name__ == "__main__":
    print("--- Test 1: Variable Assignment ---")
    print(execute_python("x = 50"))
    
    print("\n--- Test 2: Calculation using Variable (Stateful Check) ---")
    print(execute_python("print(f'Nilai x dikali 2 adalah {x * 2}')"))
    
    print("\n--- Test 3: Error Handling ---")
    print(execute_python("print(variable_ngawur)"))