"""
持久 Python Kernel（類似 Jupyter）
接收 code，在同一個 Python 進程內執行，變數/import 都持續存在
"""
import sys
import os
import json
import traceback
import socket
import threading
import time
from io import StringIO, BytesIO
try:
    import psutil
except ImportError:
    pass


# === Windows UTF-8 修復（必須在最開頭）===
if sys.platform == 'win32':
    import io
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    if hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# ⚠️ 關鍵修復：強制 numpy/pandas 底層數學庫使用單線程
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["TQDM_DISABLE"] = "1"

# === 💉 MONKEY PATCH: 強制 yfinance 單線程 (治本方案) ===
# 這能防止用戶即使忘記寫 threads=False 也能安全執行

try:
    import yfinance as yf
    original_download = yf.download
    
    def safe_download(*args, **kwargs):
        # 強制覆蓋 threads 參數為 False
        kwargs['threads'] = False
        # 如果沒有 timeout，加上 timeout 避免掛起
        if 'timeout' not in kwargs:
            kwargs['timeout'] = 30
        return original_download(*args, **kwargs)
        
    yf.download = safe_download
    sys.modules['yfinance'] = yf
except ImportError:
    pass
# ========================================================



class SafeStringIO(StringIO):
    """增強版 StringIO，提供 buffer 和 fileno 模擬，防止 C 擴展崩潰"""
    def fileno(self):
        return 1  # 模擬 stdout
    
    @property
    def buffer(self):
        return self  # 簡單返回自己，配合 write 處理 bytes
        
    @property
    def encoding(self):
        return 'utf-8'
        
    def write(self, s):
        if isinstance(s, bytes):
            # 嘗試解碼 bytes 寫入
            try:
                s = s.decode('utf-8', errors='replace')
            except:
                s = str(s)
        return super().write(s)


# 禁用 tqdm 進度條（避免 stdout 捕獲死鎖問題）
os.environ["TQDM_DISABLE"] = "1"

# 全域 namespace（變數會保留在這裡）
global_namespace = {"__name__": "__main__"}

# Kernel 啟動時間（用於 status）
KERNEL_START_TIME = time.time()

# 追蹤超時但仍在運行的任務（防止 GIL 阻塞）
pending_threads = []

# 日誌路徑 (已移除)

def get_var_size(obj) -> str:
    """估算變數大小（KB/MB 友善顯示）"""
    try:
        size = sys.getsizeof(obj)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
    except:
        return "?"

def handle_inspect(pattern: str = "") -> dict:
    """檢視 kernel 中的變數"""
    vars_info = []
    for name, value in global_namespace.items():
        # 跳過內建和 dunder
        if name.startswith("_"):
            continue
        # 如果有 pattern，過濾
        if pattern and pattern.lower() not in name.lower():
            continue
        
        var_type = type(value).__name__
        var_size = get_var_size(value)
        
        # 簡短預覽
        try:
            preview = repr(value)[:50]
            if len(repr(value)) > 50:
                preview += "..."
        except:
            preview = "<無法預覽>"
        
        vars_info.append({
            "name": name,
            "type": var_type,
            "size": var_size,
            "preview": preview
        })
    
    return {
        "success": True,
        "action": "inspect",
        "count": len(vars_info),
        "variables": vars_info
    }

def handle_reset() -> dict:
    """重置 kernel（清空所有變數）"""
    global global_namespace
    global_namespace = {"__name__": "__main__"}
    
    return {
        "success": True,
        "action": "reset",
        "message": "Kernel 已重置，所有變數已清空"
    }

def handle_status() -> dict:
    """查詢 kernel 狀態"""
    uptime = time.time() - KERNEL_START_TIME
    
    # 變數數量（排除 dunder）
    var_count = len([k for k in global_namespace.keys() if not k.startswith("_")])
    
    # 記憶體使用（如果有 psutil）
    try:
        process = psutil.Process()
        memory_mb = process.memory_info().rss / (1024 * 1024)
        memory_info = f"{memory_mb:.1f} MB"
    except:
        memory_info = "無法取得（需安裝 psutil）"
    
    return {
        "success": True,
        "action": "status",
        "uptime_seconds": round(uptime, 1),
        "uptime_human": f"{int(uptime // 60)} 分 {int(uptime % 60)} 秒",
        "variable_count": var_count,
        "memory_usage": memory_info
    }

def execute_code(code: str, timeout: int = 300) -> dict:
    """執行 code，返回 stdout/stderr/錯誤"""
    # 結果容器
    result = {"success": False, "stdout": "", "stderr": "", "error": None}
    
    # 保存原始 stdout/stderr
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # 建立捕獲用的 StringIO
    capture_stdout = SafeStringIO()
    capture_stderr = SafeStringIO()
    
    sys.stdout = capture_stdout
    sys.stderr = capture_stderr
    
    try:
        # 在同一個 namespace 執行（變數會保留）
        exec(code, global_namespace)
        
        result = {
            "success": True,
            "stdout": capture_stdout.getvalue(),
            "stderr": capture_stderr.getvalue(),
            "error": None
        }
    except Exception:
        result = {
            "success": False,
            "stdout": capture_stdout.getvalue(),
            "stderr": capture_stderr.getvalue(),
            "error": traceback.format_exc()
        }
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
    
    return result

def handle_client(conn, addr):
    """處理單個請求"""
    try:
        # 接收數據（使用結束標記判斷完成）
        data = b""
        conn.settimeout(30)  # 接收超時
        while True:
            try:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                
                # 檢查結束標記
                if b"\n__END__\n" in data:
                    data = data.replace(b"\n__END__\n", b"")
                    break
                    
                # 也嘗試解析 JSON（兼容舊版）
                try:
                    json.loads(data.decode("utf-8"))
                    break
                except:
                    continue
            except socket.timeout:
                if data:
                    data = data.replace(b"\n__END__\n", b"")
                break
        
        if not data:
            return
        
        request = json.loads(data.decode("utf-8"))
        
        # 根據 action 分發請求
        action = request.get("action", "execute")
        
        if action == "inspect":
            pattern = request.get("pattern", "")
            result = handle_inspect(pattern)
        elif action == "reset":
            result = handle_reset()
        elif action == "status":
            result = handle_status()
        else:
            # 預設：執行 code
            code = request.get("code", "")
            result = execute_code(code)
        
        response = json.dumps(result, ensure_ascii=False).encode("utf-8")
        
        # 嘗試發送回應
        try:
            conn.sendall(response)
        except:
            pass
        
    except Exception as e:
        error_response = {
            "success": False,
            "stdout": "",
            "stderr": "",
            "error": f"Kernel error: {e}"
        }
        try:
            conn.sendall(json.dumps(error_response).encode("utf-8"))
        except:
            pass
    finally:
        try:
            conn.close()
        except:
            pass

def start_kernel_server(host="127.0.0.1", port=9999):
    """啟動 kernel server"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server.bind((host, port))
        server.listen(5)
        
        print(f"[KERNEL] Server started at {host}:{port}", file=sys.stderr, flush=True)
        
        while True:
            conn, addr = server.accept()
            # 單線程處理（避免 import 死鎖問題）
            handle_client(conn, addr)
            
    except Exception as e:
        print(f"[KERNEL] ERROR: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

if __name__ == "__main__":
    start_kernel_server()
