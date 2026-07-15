# Daily Coach

[English](README.md) · **中文**

> 🌐 **線上展示頁 / Live showcase → https://srichsun.github.io/doc-ai-assistant/**

一個你每天用講的來聊的 **語音 AI 人生教練**。你開口說，它聽、把聽到的重點反映回來，
幫你注意到自己的小小成就和生活的模式 —— 而且跟無狀態的聊天機器人不一樣，它會
**記得**。你可以回頭看任何一天、看著成就一點一點累積，久了它是真的越來越懂你。

核心概念是 **三層記憶**，讓教練能扛著一份不斷變大的歷史，卻讓每次 prompt 維持固定、
有上限的大小 —— 不管你用多久，成本和 context 都不會爆掉。

## 為什麼要三層記憶

一般聊天機器人在你關掉分頁的那一刻就把你忘了。而每一輪都把整段歷史塞給它，既貴、
最後還會撐爆 context。Daily Coach 把記憶拆成三層，每一層回答不同的問題：

| 層 | 底層 | 回答什麼 | 用 AI？ |
|----|------|----------|---------|
| **1. 結構化日誌** | Postgres（純 SQL） | 「什麼時候發生了什麼」—— 回顧某一天、這個月的成就、心情趨勢 | 不用 AI，純 SQL |
| **2. 語意回想** | pgvector + OpenAI embedding | 「跟*現在*相關的過去片刻是哪個」—— 對話中拉回相似的舊紀錄 | embedding + 向量搜尋 |
| **3. 滾動 profile** | LLM 濃縮的摘要 | 「這個人是誰」—— 目標、習慣、地雷、什麼對他有用 —— 每次回覆都注入 | 由 LLM 重新濃縮 |

每次 prompt 都由 **profile + 相關的回想 + 今天的脈絡** 組起來。Postgres 裡的日誌可以
無限長，但 prompt 不會，因為第 2、3 層只留它固定的一小片。這個會滾動的 profile ——
教練持續學習你是誰 —— 正是無狀態聊天機器人做不到的事。

## 跟教練聊一天，流程長怎樣

```
  你開口 ──► Whisper（語音轉文字）──► LangChain 人生教練 agent
                                          │
             ┌────────────────────────────┼───────────────────────────┐
             │ 注入 profile                │ search_past_entries 工具  │
             │（第 3 層，每一輪）           │ → pgvector（第 2 層）      │
             └────────────────────────────┼───────────────────────────┘
                                          ▼
                                     Claude 回覆
                                          │
                       ┌──────────────────┴──────────────────┐
                       ▼                                      ▼
              ElevenLabs（語音合成）              存進 Postgres（第 1 層）
              把回覆唸出來                        + embed 進 pgvector（第 2 層）
                                                  + 定期重新濃縮 profile（第 3 層）
```

所以一次對話同時做兩件事：**當下回應你**，並且 **餵養三層記憶** 供下一次使用。

## 引擎蓋底下有什麼

- **語音進來** —— OpenAI **Whisper** 把你錄的音檔轉成文字。
- **教練本體** —— 一個 LangChain agent（`create_agent`），由 **Claude**
  （`ChatAnthropic`）驅動，帶一個 `search_past_entries` 工具；只要回想過去片刻有幫助，
  它就會自己呼叫。profile 則透過 dynamic prompt 每一輪注入。
- **語音出去** —— 回覆用 **ElevenLabs**（溫暖的英式嗓音）唸出來；OpenAI TTS 是同一個
  `speak()` 後面可直接替換的備援。
- **帳號** —— 瀏覽器用 **Firebase Auth（Google 登入）**。後端用 Firebase Admin SDK
  驗證 ID token，把每一筆紀錄、每一次回想、以及 profile 都綁到那個人。受保護的
  endpoint 都需要登入。
- **可觀測性** —— **LangSmith** 追蹤每一次 chain 與 agent 呼叫。

## 隱私

公開的 repo、展示頁、以及部署的 demo 都只用 **種子 / 假資料**。真實的日誌留在你自己的
機器上、已被 gitignore，repo 裡沒有任何 API key，部署的 `/talk` endpoint 也擋在登入
之後 —— 所以沒有人會花到你的 key，也讀不到你的日誌。

## 技術棧

| 部位 | 選擇 | 為什麼 |
|------|------|--------|
| Web 框架 | **FastAPI** | Async、型別、自動 Swagger；做 API 很輕。 |
| 套件管理 | **uv** | 一個工具搞定 venv + lockfile，比 pip/poetry 快很多。 |
| 編排 | **LangChain** | Agent + RAG + 記憶一套業界標準搞定，不用自己手刻工具迴圈。 |
| LLM | **Claude**（`ChatAnthropic`） | 教練的回覆，以及濃縮 profile 的呼叫。 |
| 語音轉文字 | **OpenAI Whisper** | 對錄音的轉錄穩定可靠。 |
| 文字轉語音 | **ElevenLabs** | 溫暖擬真的嗓音；OpenAI TTS 當備援。 |
| 日誌儲存 | **Postgres + pgvector** | 一個資料庫同時放 SQL 紀錄和向量（LangChain `PGVector`）。 |
| Embedding | **OpenAI** `text-embedding-3-small` | 驅動語意回想。 |
| 認證 | **Firebase Auth**（Google） | 這邊不碰密碼；用驗過的 uid 做逐人隔離。 |
| 追蹤 | **LangSmith** | 每一次 chain/agent 呼叫都被追蹤。 |
| 前端 | **React（Vite）** | 極簡聊天畫面，含麥克風錄音 + 語音回覆。 |
| CI | **GitHub Actions** | 每次 push 跑 ruff + pytest。 |
| 部署 | **Google Cloud** | Cloud Run + Cloud SQL（Postgres + pgvector）+ Secret Manager。 |

## 專案結構

```
app/
  main.py      FastAPI 路由：/health /agent /talk /speak /entries /wins /profile
  agent.py     LangChain 人生教練 agent（create_agent + Claude + 搜尋工具 + profile 注入）
  recall.py    語意回想 —— search_past_entries 工具，跑在 pgvector 上（第 2 層）
  profile.py   滾動的、LLM 濃縮的 profile（第 3 層）
  entries.py   純 SQL 日誌：存檔、回顧某天、列出成就（第 1 層）
  voice.py     Whisper（STT）+ ElevenLabs / OpenAI（TTS）
  auth.py      Firebase ID token 驗證、逐人隔離
  db.py        SQLAlchemy engine + session
  models.py    Entry 與 Profile 資料表
  config.py    從 env / .env 讀設定
scripts/
  init_db.py     建立資料表
  deploy_gcp.sh  部署到 Cloud Run + Cloud SQL + Secret Manager
frontend/        React（Vite）聊天 UI，含麥克風 + Google 登入 gate
Dockerfile       給 Cloud Run 用的容器映像
.github/workflows/ci.yml   ruff + pytest
```

## 安裝與啟動

```bash
# 1. 安裝依賴（uv 依 lockfile 建 venv）
uv sync

# 2. 啟動本地 Postgres（pgvector 映像）並建表
docker compose up -d
uv run python -m scripts.init_db

# 3. 填入 key
cp .env.example .env    # 編輯 .env：ANTHROPIC / OPENAI / ELEVENLABS key、
                        # FIREBASE_CREDENTIALS、選填的 LANGSMITH_API_KEY

# 4. 啟動 API
uv run uvicorn app.main:app --reload
```

打開 http://127.0.0.1:8000/docs 就是互動式 Swagger 介面。

## Endpoints

| Method | Path | 認證 | 說明 |
|--------|------|------|------|
| GET  | `/health`          | — | 存活檢查；不需 key。 |
| POST | `/agent`           | ✅ | 打字聊天。`{"question", "session_id?"}` → 回覆；這次對話會存成一筆日誌。 |
| POST | `/talk`            | ✅ | 上傳錄音 → Whisper 轉錄 → 教練回覆；同時回傳轉錄文字。 |
| POST | `/speak`           | — | 文字 → 語音（mp3），給瀏覽器播。 |
| GET  | `/entries?day=`    | ✅ | 回顧某一天的紀錄（`YYYY-MM-DD`，預設今天）。 |
| GET  | `/wins`            | ✅ | 最近幾筆有記到成就的紀錄。 |
| GET  | `/profile`         | ✅ | 教練幫你建立的長期 profile。 |
| POST | `/profile/refresh` | ✅ | 強制重新濃縮 profile（正常情況每幾筆自動做）。 |

受保護的 endpoint 需要帶 `Authorization: Bearer <Firebase ID token>`。

## Web UI

`frontend/` 有一個極簡的 React（Vite）前端：一個聊天畫面，含麥克風錄音與語音回覆，
擋在 Google 登入 gate 之後。API 跑著的時候，另開一個 terminal 啟動它：

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

它會打 `http://127.0.0.1:8000` 的 API（已透過 CORS 放行）。

## 測試

```bash
uv run pytest
```

LLM、語音、向量庫都被 mock，整套測試跑在記憶體內的 SQLite 上，所以不需 API key、也不用
起 Postgres。CI（GitHub Actions）每次 push 跑 `ruff check` + `pytest`。

## 部署

`scripts/deploy_gcp.sh` 會在 **Google Cloud** 上把整套架起來：一個 Cloud Run 服務跑
API、**Cloud SQL**（帶 pgvector 的 Postgres）存日誌與向量、**Secret Manager** 放所有
key 和 Firebase 服務帳號。執行前先 `gcloud auth login`。
