from flask import Flask, request, jsonify
import sys
import io
import traceback
from code import InteractiveInterpreter

app = Flask(__name__)

# INI KUNCINYA: Global Interpreter
# Kita inisialisasi satu interpreter yang hidup terus selama container nyala.
# 'locals={}' adalah tempat semua variabel (x=10, df=pandas, dll) disimpan.
interpreter = InteractiveInterpreter(locals={})

@app.route('/execute', methods=['POST'])
def execute_code():
    data = request.json
    code_snippet = data.get('code', '')

    # 1. Siapkan penangkap output (Stdout & Stderr)
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    captured_stdout = io.StringIO()
    captured_stderr = io.StringIO()

    # Redirect output sistem ke penangkap kita
    sys.stdout = captured_stdout
    sys.stderr = captured_stderr

    status = "success"
    
    try:
        # 2. Eksekusi Kode
        # runsource mengembalikan True jika butuh input lagi, False jika selesai.
        # Kita jalankan per baris/blok agar behavior mirip Jupyter Notebook.
        
        # Kompilasi dulu untuk cek syntax error sebelum dijalankan
        compiled_code = compile(code_snippet, "<string>", "exec")
        
        # Eksekusi di dalam interpreter yang sudah ada (Stateful)
        # exec() digunakan disini agar bisa menangani multi-line dengan baik dalam locals yang sama
        exec(compiled_code, interpreter.locals)

    except Exception:
        # 3. Tangkap Error jika kode user salah (SyntaxError, ZeroDivision, dll)
        # traceback.print_exc() akan menulis ke sys.stderr yang sedang kita capture
        traceback.print_exc()
        status = "error"
        
    finally:
        # 4. Kembalikan stdout/stderr ke aslinya (PENTING)
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    # 5. Kirim hasil balik ke Client
    return jsonify({
        "stdout": captured_stdout.getvalue(),
        "stderr": captured_stderr.getvalue(),
        "status": status
    })

if __name__ == '__main__':
    # Threaded=False agar tidak ada race condition pada variabel global
    app.run(host='0.0.0.0', port=5000, threaded=False)