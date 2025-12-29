# PyRunner MCP

<div align="center">

**Persistent Kernel for Python Scripts**

專為 Python 腳本型開發優化的 MCP Server | 變數跨執行保留 | 類 Jupyter 體驗

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io)

</div>

---

## 📖 什麼是 PyRunner MCP？

**PyRunner MCP** 是一個 [Model Context Protocol (MCP)](https://modelcontextprotocol.io) Server，讓 AI 助手（如 Gemini CLI）能夠：

🔥 **執行 Python 程式碼** - 在持久化的 Kernel 中執行，變數跨多次執行保留  
📦 **管理 Python 套件** - 快速檢查、自動安裝依賴  
🔍 **語意化搜尋腳本** - 用描述和標籤找出之前寫的腳本  
🧠 **長期記憶** - 記住你的偏好、專案背景、常用指令  
🛠️ **執行 Shell 命令** - Git clone、pip install、系統指令  

### 核心特色：Persistent Kernel

類似 **Jupyter Notebook** 的體驗，但在命令列中：
- 載入 10GB 的 DataFrame 一次，後續分析不用重讀
- import 大型套件（pandas、torch）一次，後續執行秒開
- 變數、函式、類別都持續存在



https://github.com/user-attachments/assets/4b63e67b-a7dc-4b75-ab78-07ea6aa67314


---

## 🤔 為什麼需要這個？

### 2025 年的 AI 工具已經很強大

| 工具 | 能力 |
|------|------|
| **Gemini CLI** | 執行程式碼、記憶對話、讀寫檔案、安裝套件 |
| **VS Code Copilot** | Agent Mode、@workspace、跨檔案操作 |

**那 PyRunner MCP 的價值在哪？**

### 🎯 核心差異：Persistent Kernel

```
┌─────────────────────────────────────────────────────────────┐
│  Gemini CLI / Copilot          PyRunner MCP                 │
│  ─────────────────────          ────────────                │
│  每次執行 = 全新進程            變數跨執行保留                 │
│                                                             │
│  x = 100  ──執行──►  x 消失     x = 100  ──執行──►  x 還在   │
│  print(x) ──執行──►  ❌ 錯誤    print(x) ──執行──►  ✅ 100  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🆚 功能對比

| 功能 | Gemini CLI | VS Code Copilot | **PyRunner MCP** |
|------|:----------:|:---------------:|:----------------:|
| 執行 Python | ✅ | ✅ | ✅ |
| 安裝套件 | ✅ | ✅ | ✅ |
| 讀寫檔案 | ✅ | ✅ | ✅ |
| 跨檔案操作 | ✅ | ✅ | ✅ |
| **變數跨執行保留** | ❌ | ❌ | ✅ |
| **Kernel 狀態監控** | ❌ | ❌ | ✅ |
| **變數檢視/重置** | ❌ | ❌ | ✅ |
| **長時間任務不阻塞** | ⚠️ 可能卡住 | ⚠️ 可能卡住 | ✅ |
| 語意化腳本搜尋 | ⚠️ 檔名搜尋 | ✅ @workspace | ✅ metadata |

---

## ⚡ 獨特優勢

### 1. stdout/stderr 重定向（不會卡住！）

**問題**：執行 SSH 連線、ping 監控、網路爬蟲等長時間任務時，原生工具可能因 pipe buffer 滿載而卡住。

**PyRunner 解決方案**：
```python
# 輸出自動重定向到檔案，不會阻塞
stdout → temp/stdout.txt
stderr → temp/stderr.txt
```

**適用場景**：
- SSH 遠端執行（netmiko、paramiko）
- 網路監控（ping、traceroute）
- 大量輸出的爬蟲任務
- 循環任務和 daemon

---

### 2. 套件檢查極速（微秒級）

| 方式 | 速度 |
|------|------|
| `pip list \| grep` | ~500ms（啟動 subprocess）|
| Gemini CLI shell | ~300ms |
| **PyRunner `check_packages()`** | **~0.1ms**（同進程檢查）|

```python
# 直接在 MCP 進程內檢查，不啟動 subprocess
check_packages("pandas numpy torch")
# ✓ 已安裝: pandas, numpy
# ✗ 未安裝: torch
```

---

### 3. 記憶系統（結構化 JSON）

| 特性 | Gemini CLI `save_memory` | **PyRunner `remember()`** |
|------|--------------------------|---------------------------|
| 格式 | 純文字 | JSON（結構化）|
| 分類 | ❌ | ✅ preference / project / command |
| 搜尋 | 全文 | 關鍵字 + 分類 |

```python
remember("使用者偏好 Black 格式化", category="preference")
remember("Project X 的 API: https://api.x.com", category="project")

recall("API")  # 只找相關記憶
```

---

### 4. Shell 命令淨化環境

```python
run_shell("git clone https://github.com/xxx/yyy")
```

**自動處理**：
- `GIT_TERMINAL_PROMPT=0`（禁用互動提示）
- `GIT_LFS_SKIP_SMUDGE=1`（跳過大檔案）
- 統一工作目錄（`BASE_DIR`）

---

## 💡 適用場景

### ✅ 適合 PyRunner MCP

- **資料分析**：讀取 10GB CSV 一次，後續分析不用重讀
- **機器學習**：載入模型一次，反覆測試推論
- **互動式開發**：類 Jupyter Notebook 的 CLI 體驗
- **大量獨立腳本**：用 metadata 管理和搜尋

### ❌ 不適合（用原生工具更好）

- 完整專案開發（有 src/, tests/ 結構）→ **Copilot @workspace**
- 團隊協作、PR review、CI/CD → **GitHub Copilot Workspace**
- 多語言專案 → **原生 Gemini CLI**

---

## 🚀 快速開始

### 前置需求
- Python 3.8+
- Gemini CLI（[安裝指南](https://github.com/google-gemini/gemini-cli)）

### 安裝

```bash
# 1. Clone 專案
git clone https://github.com/YOUR_USERNAME/PyRunner_MCP.git
cd PyRunner_MCP

# 2. 安裝依賴
pip install fastmcp psutil
```

### 配置 MCP Server

編輯 `~/.gemini/settings.json`：

```json
{
  "mcpServers": {
    "PyRunner_MCP": {
      "command": "python",
      "args": ["C:/path/to/PyRunner_MCP/PyRunner_MCP.py"],
      "env": {
        "MCP_BASE_DIR": "C:/path/to/PyRunner_MCP"
      }
    }
  }
}
```

### 啟動

```bash
cd /path/to/PyRunner_MCP
gemini chat
```

看到這個就成功了：
```
✓ Connected to MCP server: PyRunner_MCP (16 tools)
```

### 設定 GEMINI.md（AI 行為指南）

將 `GEMINI.md` 放在專案根目錄，它告訴 AI：
- 如何使用 PyRunner 的工具
- 你的開發習慣和技術偏好
- 執行任務的優先順序

```markdown
# GEMINI.md 主要內容

## 核心功能
- 預設使用 Persistent Kernel（use_kernel=True）
- 使用者說「重置」時用 reset_kernel()

## 對話開始檢查清單
1. kernel_status() - 確認 kernel 狀態
2. recall() - 載入長期記憶
3. list_files() - 了解現有資產

## 技術偏好
- 爬蟲優先用 requests + BeautifulSoup
- 開啟網頁用 webbrowser.open()
```

### kernel_server.py 說明

這是背景執行的 **Persistent Kernel 進程**，無需手動啟動：

```
┌──────────────────┐      socket       ┌──────────────────┐
│  PyRunner_MCP.py │  ◄───────────►    │ kernel_server.py │
│   (MCP Server)   │   127.0.0.1:9999  │  (Python Kernel) │
└──────────────────┘                   └──────────────────┘
                                              │
                                              ▼
                                    global_namespace = {}
                                    （變數都存在這裡）
```

**🛡️ 安全防護（Auto-Safe Mode）**：
**🛡️ 安全防護（Auto-Safe Mode - "The Vaccine"）**：
- **Unified Process Core**：所有子進程（Python/Pip/Shell）皆由統一核心驅動，強制輸出重定向與環境淨化。
- **Deadlock Immunity**：徹底解決 Windows 下因 Pipe Buffer 滿載或 DLL 鎖定導致的死鎖問題。
- **Auto Monkey Patch**：自動攔截 `yfinance` 等庫的多線程行為，確保 Kernel 穩定。

> **💡 建議**：現在推薦所有任務都使用 `use_kernel=True`（Direct Kernel Mode）。系統已內建防護，無需再擔心死鎖問題。

---

## 🔥 核心功能示範

### Persistent Kernel

```python
# 第一次執行
你: 載入 sales.csv
AI: save_and_run("load.py", "import pandas as pd; df = pd.read_csv('sales.csv')", use_kernel=True)
✓ 成功

# 第二次執行（df 還在！）
你: 顯示前 5 行
AI: save_and_run("show.py", "print(df.head())", use_kernel=True)
✓ [顯示 DataFrame]

# 不用重讀 CSV！
```

### Kernel 管理工具

```python
# 查看狀態
kernel_status()
# 🟢 KERNEL 狀態
# ├─ 運行時間: 15 分 32 秒
# ├─ 變數數量: 8 個
# └─ 記憶體使用: 45.2 MB

# 檢視變數
inspect_kernel_vars()
# 📦 KERNEL 變數（共 3 個）
# ├─ df (DataFrame, 15.2 MB)
# ├─ model (Sequential, 102.5 MB)
# └─ config (dict, 1.2 KB)

# 重置
reset_kernel()
# 🔄 Kernel 已重置，所有變數已清空
```

### 語意化搜尋

```python
search_workspace("PTT 爬蟲")
# → fetch_ptt.py (相關度:4) [crawler, ptt]
#   爬取 PTT 八卦版最新文章
```

---

## 🛠️ 完整工具列表

| 類別 | 工具 | 說明 |
|------|------|------|
| **Kernel** | `kernel_status()` | 查看狀態 |
| | `inspect_kernel_vars()` | 檢視變數 |
| | `reset_kernel()` | 重置 |
| **執行** | `save_and_run()` | 儲存並執行 |
| | `run_file()` | 執行現有腳本 |
| **檔案** | `list_files()` | 列出腳本 |
| | `read_file()` | 讀取內容 |
| | `delete_file()` | 刪除 |
| | `update_file_meta()` | 更新描述 |
| | `search_workspace()` | 語意搜尋 |
| **套件** | `install_packages()` | 安裝 |
| | `check_packages()` | 檢查 |
| **系統** | `run_shell()` | Shell 命令 |
| **記憶** | `remember()` / `recall()` / `forget()` | 長期記憶 |

---

## 📁 專案結構

```
PyRunner_MCP/
├── PyRunner_MCP.py       # MCP Server 主程式
├── kernel_server.py      # Persistent Kernel 進程
├── GEMINI.md             # AI 行為指南
├── workspace/            # 腳本儲存區
│   ├── *.py              # Python 腳本
│   └── *.meta.json       # Metadata（搜尋用）
├── temp/                 # 暫存（stdout/stderr）
└── memory.json           # 長期記憶
```

---

## 🤝 貢獻

歡迎 PR！需要幫助的領域：
- [ ] 更智慧的語意搜尋（embedding-based）
- [ ] Web UI 視覺化 workspace
- [ ] 多語言支援
- [ ] Docker 容器化

---

## 📞 聯絡方式 (Contact)

有任何問題或建議，歡迎聯繫我：

- **Instagram**: [@linyilun.0611](https://www.instagram.com/linyilun.0611?igsh=OW1zcGw1bTA5MHMx&utm_source=qr)
- **Email**: linen920611r@gmail.com

---

## 📜 License

MIT

---

<div align="center">

**如果覺得有用，請給個 ⭐ Star！**


</div>
