import sys
import subprocess
import os
import json
import shlex
from pathlib import Path
from datetime import datetime
from mcp.server.fastmcp import FastMCP
import socket
import atexit
import time

# ==========================================
# Kernel 管理
# ==========================================
KERNEL_HOST = "127.0.0.1"

KERNEL_PORT = 9999
KERNEL_PROCESS = None

# ⚠️ 路徑設定（必須在 _start_kernel 之前定義）
BASE_DIR = Path(os.environ.get("MCP_BASE_DIR", Path(__file__).parent))
WORKSPACE_DIR = BASE_DIR / "workspace"
TEMP_DIR = BASE_DIR / "temp"

# 確保目錄存在
for d in [WORKSPACE_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

def _start_kernel():
    """啟動背景 kernel server"""
    global KERNEL_PROCESS
    
    kernel_script = BASE_DIR / "kernel_server.py"
    if not kernel_script.exists():
        print(f"WARN  kernel_server.py 不存在，使用傳統模式")
        return False
    
    # ⚠️ 檢查端口是否已被佔用（另一個 kernel 已在運行）
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect((KERNEL_HOST, KERNEL_PORT))
        sock.close()
        # 端口已被佔用 = kernel 已在運行，無需再啟動
        print(f"MEMORY Kernel 已在運行 ({KERNEL_HOST}:{KERNEL_PORT})，連接到現有 kernel")
        return True
    except:
        pass  # 端口沒被佔用，需要啟動新 kernel
    
    # 如果我們自己的 KERNEL_PROCESS 還在運行，先等待它結束
    if KERNEL_PROCESS is not None:
        if KERNEL_PROCESS.poll() is None:
            # 進程還在，嘗試終止
            try:
                KERNEL_PROCESS.terminate()
                KERNEL_PROCESS.wait(timeout=3)
            except:
                pass
        KERNEL_PROCESS = None
    
    # 啟動新 kernel（不使用 PIPE 避免 buffer 阻塞）
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    # 🔥 Force single-thread to prevent deadlocks in Windows subprocess/kernel
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["NUMEXPR_NUM_THREADS"] = "1"
    
    # 啟動新 kernel（不使用 PIPE 避免 buffer 阻塞）
    # 使用 DEVNULL 避免日誌文件累積
    try:
        KERNEL_PROCESS = subprocess.Popen(
            [sys.executable, str(kernel_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(WORKSPACE_DIR),
            env=env
        )
    except Exception as e:
        print(f"ERROR 啟動 Kernel 失敗: {e}")
        return False
    
    # 等待 kernel 啟動（只需確認可連接即可）

    for i in range(50):  # 50 次 x 0.2 秒 = 10 秒
        time.sleep(0.2)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            sock.connect((KERNEL_HOST, KERNEL_PORT))
            sock.close()
            # 連接成功，kernel 已啟動
            print(f"MEMORY Kernel 已啟動 ({KERNEL_HOST}:{KERNEL_PORT})")
            return True
        except:
            # 檢查進程是否已經結束（啟動失敗）
            if KERNEL_PROCESS.poll() is not None:
                print(f"ERROR Kernel 進程已結束（退出碼: {KERNEL_PROCESS.returncode}）")
                return False
            continue

    print("ERROR Kernel 啟動超時（10秒）")
    return False
    

def _is_kernel_running() -> bool:
    """檢查 kernel 是否真正運行中（優先檢測端口連接）"""
    global KERNEL_PROCESS
    
    # 優先檢測端口是否有服務在監聽
    try:
        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_sock.settimeout(3)  # 增加超時至 3秒，避免系統負載高時誤判
        test_sock.connect((KERNEL_HOST, KERNEL_PORT))
        test_sock.close()
        # print(f"DEBUG: Port {KERNEL_PORT} is open, kernel running")
        return True  # 端口可連接，kernel 正在運行
    except Exception as e:
        # print(f"DEBUG: Port check failed: {e}")
        pass  # 端口無法連接，繼續檢查進程狀態
    
    # 如果端口無法連接，檢查 KERNEL_PROCESS 狀態
    if KERNEL_PROCESS is None:
        # print("DEBUG: KERNEL_PROCESS is None")
        return False
    
    # 檢查進程是否還在運行
    if KERNEL_PROCESS.poll() is not None:
        # 進程已結束，更新狀態
        KERNEL_PROCESS = None
        return False
    
    # 進程存在但端口無法連接 - 可能正在啟動中
    return True

def _stop_kernel():
    """停止 kernel（包括由其他進程啟動的 kernel）"""
    global KERNEL_PROCESS
    
    # 1. 先嘗試停止我們自己的 KERNEL_PROCESS
    if KERNEL_PROCESS:
        try:
            KERNEL_PROCESS.terminate()
            KERNEL_PROCESS.wait(timeout=3)
        except:
            pass
        KERNEL_PROCESS = None
    
    # 2. 使用 psutil 查找並終止任何監聽端口 9999 的進程
    try:
        import psutil
        for conn in psutil.net_connections(kind='inet'):
            if conn.laddr.port == KERNEL_PORT and conn.status == 'LISTEN':
                try:
                    proc = psutil.Process(conn.pid)
                    proc.terminate()
                    proc.wait(timeout=3)
                    print(f"[KERNEL] 已終止監聽端口 {KERNEL_PORT} 的進程 (PID: {conn.pid})")
                except:
                    pass
    except ImportError:
        # psutil 不可用，嘗試用 socket 測試端口是否還被佔用
        pass
    except Exception as e:
        print(f"[KERNEL] 停止 kernel 時出錯: {e}")

def _restart_kernel():
    """完全重啟 kernel（會重新載入預載套件）"""
    global KERNEL_PROCESS
    _stop_kernel()

    time.sleep(2)  # 等待端口釋放
    
    # 嘗試啟動，最多重試 2 次
    for attempt in range(3):
        if _start_kernel():
            return True
        time.sleep(1)
    return False

# MCP 結束時自動停止 kernel
atexit.register(_stop_kernel)

# 信號處理：確保收到 SIGTERM/SIGINT 時也能正確清理 kernel
import signal

def _signal_handler(signum, frame):
    """處理終止信號，確保 kernel 正確關閉"""
    _stop_kernel()
    sys.exit(0)

# 註冊信號處理器
signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)

def _execute_in_kernel(code: str, timeout: int = 60, _retry: bool = True) -> str:
    """在 kernel 內執行 code（支援自動重試）"""
    global KERNEL_PROCESS
    
    # ⚠️ 使用 _is_kernel_running() 檢查，而不是直接檢查 KERNEL_PROCESS
    # 這樣可以正確處理 kernel 由其他進程啟動的情況
    if not _is_kernel_running():
        for attempt in range(3):
            success = _start_kernel()
            if success:
                break

            time.sleep(1)
        if not _is_kernel_running():
            raise RuntimeError("Kernel 啟動失敗")
    

    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((KERNEL_HOST, KERNEL_PORT))
        
        # 發送 code（添加結束標記，不使用 shutdown）
        request = json.dumps({"code": code}, ensure_ascii=False).encode("utf-8")
        sock.sendall(request + b"\n__END__\n")
        
        # 接收結果
        response = b""
        start_time = time.time()
        sock.settimeout(30)  # 每次 recv 最多等 30 秒（增加等待時間）
        
        while True:
            # 檢查總超時
            elapsed = time.time() - start_time
            if elapsed > timeout:
                sock.close()
                if response:
                    break
                return f"[TIMEOUT] 執行超時 ({timeout}s)，任務可能仍在背景執行"
            
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break  # 連線關閉
                response += chunk
                
                # 嘗試解析 JSON，如果成功就停止接收
                try:
                    json.loads(response.decode("utf-8"))
                    break  # JSON 完整了
                except:
                    continue  # 繼續接收
                    
            except socket.timeout:
                if response:
                    # 有部分資料，嘗試解析
                    try:
                        json.loads(response.decode("utf-8"))
                        break
                    except:
                        continue
                continue
            except Exception:
                break
        
        sock.close()
        
        # 空回應處理：自動重試一次
        if not response:
            if _retry:
                time.sleep(3)
                return _execute_in_kernel(code, timeout, _retry=False)
            else:
                return "[ERROR] Kernel 無回應，請稍後重試"

        result = json.loads(response.decode("utf-8"))
        
        # 格式化輸出
        if result["success"]:
            parts = ["OK 成功"]
            if result["stdout"]:
                parts.append(f"--- Output ---\n{result['stdout']}")
            if result["stderr"]:
                parts.append(f"--- Stderr ---\n{result['stderr']}")
            return "\n".join(parts) if len(parts) > 1 else "OK 成功（無輸出）"
        else:
            parts = ["ERROR 執行失敗"]
            if result["stdout"]:
                parts.append(f"--- Output ---\n{result['stdout']}")
            if result["error"]:
                parts.append(f"--- Error ---\n{result['error']}")
            return "\n".join(parts)
    
    except socket.timeout:
        return f"TIMEOUT 執行超時 ({timeout}s)"
    except ConnectionRefusedError:
        return "[ERROR] Kernel 未啟動或連線被拒絕"
    except Exception as e:
        return f"FATAL Kernel 連線錯誤: {e}"

def _send_kernel_command(action: str, **kwargs) -> dict:
    """
    發送命令到 kernel（非執行類命令）
    
    支援的 action:
    - "inspect": 檢視變數（可選 pattern 參數）
    - "reset": 重置 kernel
    - "status": 查詢狀態
    """
    global KERNEL_PROCESS

    
    # 確保 kernel 已啟動
    if KERNEL_PROCESS is None:
        success = _start_kernel()
        if not success:
            return {"success": False, "error": "Kernel 啟動失敗"}
    
    # 重試邏輯（kernel 啟動後可能還在預載中）
    max_retries = 3
    for attempt in range(max_retries):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            sock.connect((KERNEL_HOST, KERNEL_PORT))
            
            # 發送命令（使用結束標記，與 _execute_in_kernel 一致）
            request = {"action": action, **kwargs}
            sock.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n__END__\n")
            
            # 接收結果（reset 命令需要更長時間，因為要預載套件）
            response = b""
            recv_timeout = 300 if action == "reset" else 5
            sock.settimeout(recv_timeout)
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response += chunk
            except socket.timeout:
                pass
            
            sock.close()
            
            if not response:
                if attempt < max_retries - 1:
                    time.sleep(1)  # 等待 kernel 就緒
                    continue
                return {"success": False, "error": "Kernel 空回應"}
            
            return json.loads(response.decode("utf-8"))
        
        except ConnectionRefusedError:
            if attempt < max_retries - 1:
                time.sleep(1)  # 等待 kernel 就緒
                continue
            return {"success": False, "error": "Kernel 未啟動或連線被拒絕"}
        except ConnectionResetError:
            # WinError 10054: 遠端主機已強制關閉連線（kernel 繁忙）
            if attempt < max_retries - 1:
                time.sleep(2)  # 等待 kernel 處理完成
                continue
            return {"success": False, "error": "Kernel 繁忙，請稍後重試"}
        except Exception as e:
            return {"success": False, "error": f"Kernel 連線錯誤: {e}"}

# ==========================================
# 初始化
# ==========================================
mcp = FastMCP("Workspace Agent")

# （路徑設定已在文件開頭定義，無需重複）

# ⚠️ MCP 初始化時自動啟動 kernel（Gemini CLI 開啟時 kernel 就準備好）
_start_kernel()

# ==========================================
# 核心：環境與執行引擎
# ==========================================
def _get_clean_env() -> dict:
    """取得淨化後的環境變數"""
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_LFS_SKIP_SMUDGE"] = "1"
    
    # 🔥 Force single-thread for Subprocesses too (Safety Net)
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    env["NUMEXPR_NUM_THREADS"] = "1"
    
    return env

def _run_safe_process(cmd: list, timeout: int, log_prefix: str, cwd: str = None, shell: bool = False) -> dict:
    """
    通用安全執行函數 (The Vaccine Core)
    統一處理：
    1. 輸出重定向 (防止 Pipe Deadlock)
    2. 環境變數淨化 (強制單線程)
    3. 超時控制
    """
    stdout_path = TEMP_DIR / f"{log_prefix}_stdout.txt"
    stderr_path = TEMP_DIR / f"{log_prefix}_stderr.txt"
    
    # 確保 cwd
    cwd = cwd or str(WORKSPACE_DIR)
    
    try:
        with open(stdout_path, "w", encoding="utf-8") as f_out, \
             open(stderr_path, "w", encoding="utf-8") as f_err:
            
            result = subprocess.run(
                cmd,
                stdout=f_out,
                stderr=f_err,
                stdin=subprocess.DEVNULL,
                env=_get_clean_env(),
                timeout=timeout,
                cwd=cwd,
                shell=shell
            )
            
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
        
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "error": None
        }
            
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"TIMEOUT 超時 ({timeout}s)"
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "error": f"FATAL 執行錯誤: {e}"
        }


def _run_python(script_path: Path, args: list = None, timeout: int = 60) -> str:
    """統一的 Python 執行邏輯（subprocess 模式）"""
    args = args or []
    
    cmd = [sys.executable, str(script_path)] + args
    result = _run_safe_process(cmd, timeout, "python", cwd=str(WORKSPACE_DIR))
    
    if result["error"]:
        return result["error"]
        
    status = "OK 成功" if result["success"] else f"ERROR  失敗 (Code {result['returncode']})"
    parts = [status]
    if result["stdout"]: parts.append(f"--- Output ---\n{result['stdout']}")
    if result["stderr"]: parts.append(f"--- Errors ---\n{result['stderr']}")
    return "\n".join(parts)

# ==========================================
# 工具 1: 搜尋 (執行前必用)
# ==========================================
@mcp.tool()
def search_workspace(query: str) -> str:
    """
    搜尋 workspace 中的現有腳本（依檔名/描述/標籤）。
    
    【使用時機】
    寫新程式碼之前必呼叫！避免重複造輪子。
    
    【範例】
    search_workspace("爬蟲 ptt")
    search_workspace("api weather")
    """
    keywords = query.lower().split()
    results = []
    
    for meta_file in WORKSPACE_DIR.glob("*.meta.json"):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            script_name = meta_file.stem  # 去掉 .meta.json
            
            # 計算相關度分數
            score = 0
            searchable = f"{script_name} {meta.get('description', '')} {' '.join(meta.get('tags', []))}".lower()
            
            for kw in keywords:
                if kw in searchable:
                    score += 2 if kw in script_name.lower() else 1
            
            if score > 0:
                results.append({
                    "name": f"{script_name}.py",
                    "score": score,
                    "description": meta.get("description", ""),
                    "tags": meta.get("tags", [])
                })
        except:
            continue
    
    # 也搜尋沒有 meta 的 .py 檔 (舊檔案相容)
    for py_file in WORKSPACE_DIR.glob("*.py"):
        if not (WORKSPACE_DIR / f"{py_file.stem}.meta.json").exists():
            score = sum(2 for kw in keywords if kw in py_file.stem.lower())
            if score > 0:
                results.append({
                    "name": py_file.name,
                    "score": score,
                    "description": "(無描述 - 舊檔案)",
                    "tags": []
                })
    
    if not results:
        return "SEARCH 沒有找到相關腳本，請建立新檔案。"
    
    results.sort(key=lambda x: x["score"], reverse=True)
    output = "SEARCH 找到相關腳本:\n"
    for r in results[:5]:
        tags_str = f" [{', '.join(r['tags'])}]" if r['tags'] else ""
        output += f"- **{r['name']}** (相關度:{r['score']}){tags_str}\n  {r['description']}\n"
    return output

# ==========================================
# 工具 2: 檔案操作
# ==========================================
@mcp.tool()
def list_files() -> str:
    """
    列出 workspace 中的所有檔案（含大小和描述）。
    
    【使用時機】
    對話開始時或忘記有哪些腳本時。
    """
    files = []
    for f in sorted(WORKSPACE_DIR.glob("*.py")):
        size = f.stat().st_size
        meta_path = WORKSPACE_DIR / f"{f.stem}.meta.json"
        desc = ""
        if meta_path.exists():
            try:
                desc = json.loads(meta_path.read_text(encoding="utf-8")).get("description", "")[:50]
            except:
                pass
        files.append(f"- {f.name} ({size}B) {desc}")
    
    return "FILES Workspace 檔案:\n" + "\n".join(files) if files else "FILES Workspace 是空的"

@mcp.tool()
def read_file(filename: str) -> str:
    """
     讀取 workspace 中的檔案內容。
    
    【範例】
    read_file("fetch_ptt.py")
    """
    path = WORKSPACE_DIR / filename
    if not path.exists():
        return f"ERROR 檔案不存在: {filename}"
    
    content = path.read_text(encoding="utf-8", errors="replace")
    
    # 如果有 meta，也顯示
    meta_path = WORKSPACE_DIR / f"{path.stem}.meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            header = f"# 描述: {meta.get('description', '')}\n# 標籤: {', '.join(meta.get('tags', []))}\n\n"
            return header + content
        except:
            pass
    
    return content

@mcp.tool()
def delete_file(filename: str) -> str:
    """
    刪除 workspace 中的檔案（含 metadata）。
    
    【注意】
    無法復原！確認後再刪。
    """
    path = WORKSPACE_DIR / filename
    if not path.exists():
        return f"ERROR 檔案不存在: {filename}"
    
    path.unlink()
    
    # 同時刪除 meta
    meta_path = WORKSPACE_DIR / f"{path.stem}.meta.json"
    if meta_path.exists():
        meta_path.unlink()
    
    return f"DELETE 已刪除: {filename}"

# ==========================================
# 工具 3: 儲存與執行
# ==========================================
@mcp.tool()
def save_and_run(
    filename: str, 
    code: str, 
    description: str = "",
    tags: str = "",
    args: str = "",
    timeout: int = 300,  # 5 分鐘，足夠大多數網路任務
    use_kernel: bool = False
) -> str:
    """
    儲存並執行 Python 程式碼。
    
    【⚠️ 重要：use_kernel 選擇】
    - use_kernel=False（預設）: 第一次抓取資料（import yfinance/requests 等）必須用這個！
    - use_kernel=True: 後續分析時使用，變數會保留在記憶體中
    
    【推薦工作流程】
    1. 第一次抓取：use_kernel=False，並將結果存成 .pkl 檔
    2. 後續分析：use_kernel=True，載入 .pkl 後變數保留
    
    【執行前 SOP】
    1. search_workspace() - 找現有腳本
    2. 複雜功能 - 考慮 git clone GitHub 專案（見 GEMINI.md）
    3. 簡單功能 - 自己寫
    
    【參數】
    - filename: 用有意義的名稱（如 fetch_ptt.py）
    - description: 功能描述（搜尋依據，必填）
    - tags: 逗號分隔（如 "爬蟲,ptt,api"）
    - timeout: 60s(一般) | 300s(下載/爬蟲/安裝)
    - args: 執行參數（支援引號，如 '"hello world" 123'）
    
    【範例】
    # 第一次抓取（必須 use_kernel=False）
    save_and_run("fetch_data.py", code, use_kernel=False)  # 存成 data.pkl
    
    # 後續分析（use_kernel=True，變數保留）
    save_and_run("analyze.py", "df = pd.read_pickle('data.pkl'); print(df.head())", use_kernel=True)
    """
    if not filename.endswith(".py"):
        filename += ".py"
    
    script_path = WORKSPACE_DIR / filename
    
    # 加入 UTF-8 header（給 subprocess 模式使用）
    # Kernel 模式會直接執行原始 code，不需要這個 header
    subprocess_header = "# -*- coding: utf-8 -*-\nimport sys; sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')\n"
    script_path.write_text(subprocess_header + code, encoding="utf-8")
    
    # 儲存 metadata
    meta = {
        "description": description or "未提供描述",
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat()
    }
    meta_path = WORKSPACE_DIR / f"{script_path.stem}.meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    
    # 解析參數
    try:
        cmd_args = shlex.split(args) if args else []
    except:
        cmd_args = args.split() if args else []
    
    # 執行
    mode_msg = ""
    if use_kernel:
        try:
            # Kernel 模式：直接執行原始 code（不加 header，因為 StringIO 不支援 reconfigure）
            result = _execute_in_kernel(code, timeout=timeout)
            mode_msg = " (Kernel)"
        except Exception as e:
            # 降級到 subprocess
            result = f"[WARN] Kernel 失敗: {e}\n" + _run_python(script_path, args=cmd_args, timeout=timeout)
            mode_msg = " (Subprocess - Fallback)"
    else:
        result = _run_python(script_path, args=cmd_args, timeout=timeout)
        mode_msg = " (Subprocess)"
    
    return f"[SAVED] 已儲存: {filename}{mode_msg}\n{result}"

@mcp.tool()
def run_file(filename: str, args: str = "", timeout: int = 300, use_kernel: bool = False) -> str:
    """
    執行 workspace 中的現有腳本。
    
    【參數】
    - filename: 檔名（可省略 .py）
    - args: 執行參數（支援引號）
    - timeout: 超時秒數
    - use_kernel: 是否使用持久 kernel 執行
    
    【範例】
    run_file("fetch_ptt.py", args='"Gossiping" 10', timeout=120, use_kernel=True)
    """
    if not filename.endswith(".py"):
        filename += ".py"
    
    script_path = WORKSPACE_DIR / filename
    if not script_path.exists():
        return f"ERROR 檔案不存在: {filename}"
    
    # 更新 metadata 的 updated 時間
    meta_path = WORKSPACE_DIR / f"{script_path.stem}.meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["updated"] = datetime.now().isoformat()
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except:
            pass
    
    try:
        cmd_args = shlex.split(args) if args else []
    except:
        cmd_args = args.split() if args else []

    if use_kernel:
        code = script_path.read_text(encoding="utf-8")
        # 移除 subprocess header（因為 StringIO 不支援 reconfigure）
        # Header 格式: # -*- coding: utf-8 -*-\nimport sys; sys.stdout.reconfigure...\n
        if code.startswith("# -*- coding: utf-8 -*-"):
            lines = code.split("\n", 2)  # 分成最多 3 部分
            if len(lines) >= 3 and "reconfigure" in lines[1]:
                code = lines[2]  # 只取第三行之後的內容
        try:
            result = _execute_in_kernel(code, timeout=timeout)
        except Exception as e:
            result = f"[WARN] Kernel 失敗: {e}\n" + _run_python(script_path, args=cmd_args, timeout=timeout)
    else:
        result = _run_python(script_path, args=cmd_args, timeout=timeout)
    return f"RUN 執行: {filename}\n{result}"

# ==========================================
# 工具 4: Shell 命令 (系統操作用)
# ==========================================
@mcp.tool()
def run_shell(command: str, timeout: int = 300) -> str:
    """
    執行 Shell 命令（Git / pip / 系統指令）。
    
    【常見用途】
    - Git 下載：git clone --depth 1 https://github.com/xxx/xxx
    - 套件安裝：pip install requests pandas
    - 檔案操作：dir（Windows）/ ls（Linux）
    - 系統資訊：ipconfig / ping google.com
    
    【Git 專案安裝 SOP】
    1. git clone --depth 1 <repo_url>
    2. cd <repo_name>
    3. pip install -r requirements.txt
    4. python main.py（或參考 README.md）
    
    【注意】
    - Git clone 會自動淨化環境（禁止互動提示）
    - 預設 timeout 300s（適合下載大型專案）
    
    【範例】
    run_shell("git clone --depth 1 https://github.com/scrapy/scrapy")
    run_shell("pip install beautifulsoup4 lxml")
    """
    result = _run_safe_process(command, timeout, "shell", shell=True)
    
    if result["error"]:
        return result["error"]
        
    status = "OK" if result["success"] else f"ERROR Code {result['returncode']}"
    parts = [status]
    if result["stdout"]: parts.append(f"--- Stdout ---\n{result['stdout']}")
    if result["stderr"]: parts.append(f"--- Stderr ---\n{result['stderr']}")
    return "\n".join(parts)

# ==========================================
# 工具 5: 套件管理
# ==========================================

def _check_package_installed(package: str) -> bool:
    """
    檢查套件是否已安裝（無需維護映射表）
    
    Returns:
        True: 已安裝
        False: 未安裝
    """
    # 方法 1: 使用 importlib.metadata（推薦，Python 3.8+）
    try:
        from importlib.metadata import distribution
        distribution(package)
        return True
    except Exception:
        pass
    
    # 方法 2: 直接嘗試 import（處理名稱不一致的情況）
    import importlib.util
    import_name = package.replace("-", "_").lower()
    try:
        spec = importlib.util.find_spec(import_name)
        if spec is not None:
            return True
    except (ImportError, ModuleNotFoundError, ValueError):
        pass
    
    return False


@mcp.tool()
def check_packages(packages: str) -> str:
    """
    快速檢查套件是否已安裝（不安裝，不啟動 subprocess）。
    
    【參數】
    packages: 空格分隔（如 "requests pandas numpy"）
    
    【返回】
    已安裝清單 + 未安裝清單
    
    【範例】
    check_packages("requests beautifulsoup4 lxml")
    """
    pkgs = packages.split()
    if not pkgs:
        return "ERROR 請提供套件名稱"
    
    installed = []
    missing = []
    
    for pkg in pkgs:
        if _check_package_installed(pkg):
            installed.append(pkg)
        else:
            missing.append(pkg)
    
    output = []
    if installed:
        output.append(f"✓ 已安裝: {', '.join(installed)}")
    if missing:
        output.append(f"✗ 未安裝: {', '.join(missing)}")
    
    return "\n".join(output) if output else "ERROR 檢查失敗"


@mcp.tool()
def install_packages(packages: str, skip_installed: bool = True) -> str:
    """
    安裝 Python 套件（pip install）。
    
    【參數】
    packages: 空格分隔（如 "requests pandas numpy"）
    skip_installed: True=跳過已安裝（預設，快），False=強制重裝
    
    【範例】
    install_packages("beautifulsoup4 lxml requests")
    install_packages("numpy", skip_installed=False)  # 強制重裝
    """
    pkgs = packages.split()
    if not pkgs:
        return "ERROR 請提供套件名稱"
    
    # 先快速檢查哪些需要安裝（不啟動 subprocess）
    if skip_installed:
        to_install = []
        already_installed = []
        
        for pkg in pkgs:
            if _check_package_installed(pkg):
                already_installed.append(pkg)
            else:
                to_install.append(pkg)
        
        if not to_install:
            return f"OK 所有套件已安裝: {', '.join(already_installed)}"
        
        pkgs = to_install  # 只安裝缺少的
        status_msg = f"✓ 跳過已安裝: {', '.join(already_installed)}\n" if already_installed else ""
    else:
        status_msg = ""
    
    # 安裝套件
    cmd = [sys.executable, "-m", "pip", "install"] + pkgs
    
    # 💉 The Vaccine: 使用統一發射器 (Standard Pip)
    result = _run_safe_process(cmd, 300, "install")

    if result["success"]:
        return f"{status_msg}✓ 已安裝: {', '.join(pkgs)}\n{result['stdout']}"
    else:
        return f"{status_msg}✗ 安裝失敗:\n{result['stderr']}\n--- Output ---\n{result['stdout']}"


@mcp.tool()
def update_file_meta(filename: str, description: str = "", tags: str = "") -> str:
    """
    更新檔案的描述和標籤（不修改程式碼）。
    
    【使用時機】
    補充舊檔案的 metadata，方便日後搜尋。
    
    【範例】
    update_file_meta("old_script.py", description="爬蟲工具", tags="crawler,ptt")
    """
    if not filename.endswith(".py"):
        filename += ".py"
    
    script_path = WORKSPACE_DIR / filename
    if not script_path.exists():
        return f"ERROR 檔案不存在: {filename}"
    
    meta_path = WORKSPACE_DIR / f"{script_path.stem}.meta.json"
    
    # 讀取或建立 meta
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    else:
        meta = {"created": datetime.now().isoformat()}
    
    if description:
        meta["description"] = description
    if tags:
        meta["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    meta["updated"] = datetime.now().isoformat()
    
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"OK 已更新 {filename} 的 metadata"

# ==========================================
# 工具 6: Kernel 管理（核心差異化功能）
# ==========================================
@mcp.tool()
def kernel_status() -> str:
    """
    查看 Persistent Kernel 的運行狀態。
    
    【返回資訊】
    - 運行時間（uptime）
    - 變數數量
    - 記憶體使用量
    
    【使用時機】
    - 確認 kernel 是否正常運作
    - 檢查記憶體使用是否過高
    - Debug 時了解 kernel 狀態
    
    【範例】
    kernel_status()
    # → 運行: 15 分 32 秒 | 變數: 8 個 | 記憶體: 45.2 MB
    """
    # 如果 kernel 沒有運行，返回友好訊息
    if not _is_kernel_running():
        return "🔴 KERNEL 未運行\n（執行程式碼時會自動啟動）"
    
    result = _send_kernel_command("status")
    
    if not result.get("success"):
        return f"ERROR {result.get('error', 'Kernel 狀態查詢失敗')}"
    
    return (
        f"🟢 KERNEL 狀態\n"
        f"├─ 運行時間: {result['uptime_human']}\n"
        f"├─ 變數數量: {result['variable_count']} 個\n"
        f"└─ 記憶體使用: {result['memory_usage']}"
    )


@mcp.tool()
def inspect_kernel_vars(pattern: str = "") -> str:
    """
    檢視 Kernel 中的所有變數（名稱、類型、大小、預覽）。
    
    【參數】
    pattern: 可選，過濾變數名（如 "df" 只顯示包含 df 的變數）
    
    【使用時機】
    - 查看目前有哪些變數在記憶體中
    - 資料分析時確認 DataFrame 是否還在
    - Debug 時檢視變數狀態
    
    【範例】
    inspect_kernel_vars()         # 列出所有變數
    inspect_kernel_vars("df")     # 只顯示名稱含 "df" 的變數
    
    【典型輸出】
    df (DataFrame, 15.2 MB): <preview>
    model (Sequential, 102.5 MB): <preview>
    config (dict, 1.2 KB): {'api_key': '...'}
    """
    # 如果 kernel 沒有運行，返回友好訊息
    if not _is_kernel_running():
        return "📦 INSPECT Kernel 未運行，沒有變數可檢視\n（執行程式碼後才會有變數）"
    
    result = _send_kernel_command("inspect", pattern=pattern)
    
    if not result.get("success"):
        return f"ERROR {result.get('error', '變數檢視失敗')}"
    
    if result["count"] == 0:
        if pattern:
            return f"INSPECT 沒有找到符合 '{pattern}' 的變數"
        return "INSPECT Kernel 中沒有變數（可能剛重置或尚未執行任何程式碼）"
    
    output = [f"📦 KERNEL 變數（共 {result['count']} 個）"]
    for var in result["variables"]:
        output.append(f"├─ {var['name']} ({var['type']}, {var['size']})")
        output.append(f"│   └─ {var['preview']}")
    
    return "\n".join(output)


@mcp.tool()
def reset_kernel() -> str:
    """
    重置 Persistent Kernel，清空所有變數和 import。
    
    【效果】
    - 清除所有變數（df, model, config 等）
    - 清除所有 import（需重新 import pandas, torch 等）
    - Kernel 回到初始狀態
    
    【使用時機】
    - 變數太多、記憶體不足時
    - 需要乾淨環境重新開始時
    - 使用者說「重新開始」、「清空」、「重置」時
    
    【注意】
    ⚠️ 此操作不可復原！所有變數都會消失。
    
    【範例】
    reset_kernel()
    # → ✓ Kernel 已重置，所有變數已清空
    """
    # 如果 kernel 沒有運行，直接返回成功（無需重置）
    if not _is_kernel_running():
        return "🔄 RESET Kernel 未運行，無需重置"
    
    result = _send_kernel_command("reset")
    
    if not result.get("success"):
        return f"ERROR {result.get('error', 'Kernel 重置失敗')}"
    
    return "🔄 RESET Kernel 已重置，所有變數和 import 已清空\n（下次執行需重新 import 套件）"


# 工具 deleted: manage_preload

# ==========================================
# 工具 7: 記憶系統 [LEGACY - 建議使用 GEMINI.md]
# ==========================================
MEMORY_FILE = BASE_DIR / "memory.json"

def _load_memories() -> list:
    """載入記憶"""
    if MEMORY_FILE.exists():
        try:
            return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except:
            return []
    return []

def _save_memories(memories: list):
    """儲存記憶"""
    MEMORY_FILE.write_text(
        json.dumps(memories, ensure_ascii=False, indent=2), 
        encoding="utf-8"
    )

@mcp.tool()
def remember(content: str, category: str = "general") -> str:
    """
    儲存重要資訊到長期記憶。
    
    【使用時機】
    - 使用者說「記住...」
    - 重要偏好（如：我喜歡用 Python 3.11）
    - 專案背景（如：目前在開發 XXX）
    
    【分類】
    general / preference / project / command
    
    【範例】
    remember("使用者喜歡用繁體中文", category="preference")
    """
    memories = _load_memories()
    
    new_memory = {
        "id": len(memories) + 1,
        "content": content,
        "category": category,
        "created": datetime.now().isoformat()
    }
    memories.append(new_memory)
    _save_memories(memories)
    
    return f"MEMORY 已記住: {content}"

@mcp.tool()
def recall(query: str = "") -> str:
    """
    回憶記憶內容（支援關鍵字搜尋）。
    
    【使用時機】
    - 對話開始時必呼叫（載入上下文）
    - 需要特定資訊時搜尋
    
    【範例】
    recall()  # 列出所有記憶
    recall("python 偏好")  # 搜尋相關記憶
    """
    memories = _load_memories()
    
    if not memories:
        return "MEMORY 記憶是空的。"
    
    if query:
        # 關鍵字搜尋
        keywords = query.lower().split()
        filtered = [
            m for m in memories 
            if any(kw in m["content"].lower() for kw in keywords)
        ]
        if not filtered:
            return f"MEMORY 找不到與 '{query}' 相關的記憶。"
        memories = filtered
    
    output = "MEMORY 記憶內容:\n"
    for m in memories[-20:]:  # 最多顯示 20 條
        output += f"- [{m['category']}] {m['content']}\n"
    
    return output

@mcp.tool()
def forget(memory_id: int) -> str:
    """
    刪除指定 ID 的記憶。
    
    【範例】
    forget(3)  # 刪除 #3 號記憶
    """
    memories = _load_memories()
    memories = [m for m in memories if m.get("id") != memory_id]
    _save_memories(memories)
    return f"MEMORY 已遺忘記憶 #{memory_id}"

# ==========================================
# 啟動
# ==========================================
if __name__ == "__main__":
    mcp.run()