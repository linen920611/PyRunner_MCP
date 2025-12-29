# Workspace Agent 使用指南

## 🎯 核心定位
**PyRunner MCP 是專為 Python 腳本型開發優化的 Persistent Kernel 工作台**

與 Gemini CLI 原生功能的差異：
- ✅ **Persistent Kernel**：變數跨執行保留（Gemini CLI 沒有）
- ✅ **Kernel 管理工具**：檢視變數、重置、狀態監控
- ✅ **語意化搜尋**：用描述和標籤找腳本

---

## 🔥 Persistent Kernel（核心功能）
系統會啟動一個持久的 Python kernel（類似 Jupyter notebook）：
- ✅ 變數在多次執行間保留（如 `x=100` 執行後，下次可直接用 `x`）
- ✅ import 的模組會留在記憶體（pandas/torch 只需載入一次）
- ✅ 適合：重複測試、資料分析、需要保留狀態的任務

### ⚠️ 極重要：Kernel 變數重用規則
**在 Kernel 模式下，第一個腳本建立的變數會保留，後續腳本必須直接使用！**

**✅ 正確方式**（後續腳本直接使用變數）：
```python
# 第一個腳本 (fetch_data.py)
import yfinance as yf
tsmc_data = yf.download("2330.TW", ...)  # 存入變數

# 第二個腳本 (calculate_ma.py) - 不需要重新 import 和抓取！
df = tsmc_data  # 直接使用上一個腳本的變數
df['MA20'] = df['Close'].rolling(20).mean()
```

**❌ 錯誤方式**（重複 import 和抓取）：
```python
# 第二個腳本 - 這樣寫就失去了 kernel 的意義！
import yfinance as yf  # ❌ 不需要
tsmc_data = yf.download(...)  # ❌ 不需要重新抓取
```

### Kernel 管理工具
| 工具 | 用途 | 使用時機 |
|------|------|----------|
| `kernel_status()` | 查看運行狀態、記憶體使用 | 確認 kernel 健康狀態 |
| `inspect_kernel_vars()` | 列出所有變數（類型、大小） | 查看目前有哪些變數 |
| `inspect_kernel_vars("df")` | 過濾顯示特定變數 | 只看 DataFrame 相關 |
| `reset_kernel()` | 重置，清空所有變數 | 需要乾淨環境時 |


### Subprocess 模式（乾淨環境）
每次執行都是全新的 Python 進程：
- ✅ 環境乾淨，不受之前執行影響
- ✅ 適合：獨立腳本、一次性任務

### ⚠️ 智能執行策略（更新版）

由於我們已修復了 Kernel 環境變數（強制單線程防止死鎖），現在**強烈建議直接使用 Kernel 模式**！

### ⚠️ 智能執行策略（最終完美版）

我們已在系統層 `kernel_server.py` 實作了 **Monkey Patch** 防護網：
1.  **自動強制單線程**：即使你忘記寫 `threads=False`，系統也會自動攔截並修正，徹底杜絕死鎖。
2.  **端口隔離**：使用 Port 10000 避開舊進程干擾。

**✅ 唯一推薦流程（Direct Kernel）**：
現在你可以放心大膽地使用 Kernel 模式，享受變數保留的便利，無需任何額外顧慮。

```python
# fetch_data.py (use_kernel=True)
import yfinance as yf
# 系統現在會自動保護這個請求，不會卡死！
tsmc = yf.download("2330.TW", period="2y")
print(tsmc.tail())
```

**不再需要**：
- ❌ 不需要 `threads=False` (系統自動加)
- ❌ 不需要 `fetch_bypass.py` (pandas read_csv)
- ❌ 不需要 `kill_kernel.py` (自動避開僵屍)

**簡單來說：Just Run It in Kernel!**

### Timeout 建議

### Timeout 建議

| 任務類型 | 建議 timeout |
|---------|-------------|
| 簡單計算、變數操作 | 60（預設）|
| 資料分析（本地檔案） | 120 |
| 網路請求（API、爬蟲） | 120 |
| 下載檔案、git clone | 300 |
| 大型資料處理、ML 訓練 | 600 |

### 執行任務的決策樹
1. **先搜尋**：用 `search_workspace("關鍵字")` 找現有腳本
2. **考慮開源**：複雜功能優先考慮 GitHub 現成工具
3. **再開發**：簡單功能（<30 行）才自己寫
### 何時用 GitHub 開源專案
遇到以下需求，優先 `git clone` 而非從零寫：
- **爬蟲**：scrapy, beautifulsoup4, playwright
- **Web API**：fastapi, flask, django
- **遊戲開發**：pygame, arcade, panda3d
- **資料分析**：pandas, numpy, matplotlib
- **自動化**：selenium, pyautogui, playwright
- **機器學習**：scikit-learn, transformers
- **其他大型複雜專案** 
**SOP**：
- git clone --depth 1 https://github.com/<author>/<repo>
- cd <repo>
- pip install -r requirements.txt
- 閱讀 README.md 了解用法
---
## 🧠 人類意圖映射（Human Intent Mapping）
你是主動的私人助理，不是終端機。當使用者表達模糊意圖時，直接採取數位行動。
### 生理需求（吃/喝/買）
| 使用者說 | 你的行動 |
|---------|---------|
| "我想吃鹹酥雞" | `webbrowser.open('https://www.google.com/maps/search/鹹酥雞')` |
| "想買顯卡" | `webbrowser.open('https://shopee.tw/search?keyword=顯卡')` |
| "肚子餓了" | 開外送平台（Foodpanda/UberEats）|

### 資訊獲取（看/聽/查）
| 使用者說 | 你的行動 |
|---------|---------|
| "我想聽周杰倫" | `webbrowser.open('https://youtube.com/results?search_query=周杰倫')` |
| "最近新聞" | `webbrowser.open('https://news.google.com')` |
| "查天氣" | `webbrowser.open('https://weather.com')` |

### 情緒表達（無聊/累了）
| 使用者說 | 你的行動 |
|---------|---------|
| "好無聊" | 開 Reddit/PTT 或播隨機音樂 |
| "想放鬆" | 開冥想音樂/白噪音 |
---
## ⚙️ 技術偏好（預設選擇）
### 網路爬蟲
- ✅ **優先**：`requests` + `BeautifulSoup`（速度快、穩定）
- ⚠️ **次選**：`selenium` / `playwright`（僅當需要 JS 渲染或登入）

### ⚠️ yfinance 特別規則 (Windows MCP 環境)
- ✅ **必須使用**：`yf.download("2330.TW", ...)` (已驗證可用)
- ❌ **絕對禁止**：`yf.Ticker("2330.TW").history(...)` (會導致 Kernel 死鎖!)
- **原因**：`history()` 使用的底層線程機制在 MCP 子進程中會卡死，而 `download()` 配合我們強制單線程的 fix 是穩定的。

### 開啟網頁/網址
- ✅ **優先**：`webbrowser.open(url)`（背景執行、跨平台）
- ❌ **避免**：`subprocess.run(['chrome.exe', url])`（會跳 cmd 視窗）
### GUI 程式
- ⚠️ 提醒使用者「需要圖形環境」
- 或使用 headless 模式：
- import os
- os.environ['SDL_VIDEODRIVER'] = 'dummy' # pygame
### 檔案命名
- ✅ **好**：`fetch_ptt_hot.py`, `sync_notion.py`
- ❌ **壞**：`test.py`, `script1.py`, `draft.py`
---
## 📋 對話開始時的檢查清單
每次新對話開始時：
1. `kernel_status()` - 確認 kernel 狀態
2. `recall()` - 載入長期記憶
3. `list_files()` - 了解現有資產
---
## 🛡️ 環境特性
- stdout/stderr 自動重定向到檔案（防 pipe 死鎖）
- 環境變數已淨化（移除 Proxy、Git 互動提示）
- 執行目錄：workspace/（所有相對路徑基於此）