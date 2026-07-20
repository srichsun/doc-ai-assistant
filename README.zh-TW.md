# Minerva

[English](README.md) · **中文**

> 🌐 **線上展示頁 / Live showcase → https://srichsun.github.io/Minerva/**
>
> 🚀 **線上試用 / Live app → https://daily-coach-592904365774.asia-east1.run.app/**

**一個陪你度過難熬時刻的語音 AI 朋友。** 你開口說，她聽。

Minerva 是為了那些真正會毀掉一天的時刻而做的 —— 恐懼上來的時候、混沌到無法做決定的
時候、忘記自己有多少能耐的時候。她穩住你、陪你把事情想清楚、提醒你自己的紀錄早已證明
的那些事 —— 讓你回到平靜，也回到工作。

她能做到這些，靠的是 **記憶**。跟無狀態的聊天機器人不同，她記得你的整個故事；而這個
專案的技術核心，就是讓這件事成立：用 **三層記憶** 扛住一份不斷變大的歷史，同時讓每次
prompt 維持固定、有上限的大小 —— 不管你用多久，成本和 context 都不會爆掉。

## 為什麼要三層記憶

一般聊天機器人在你關掉分頁的那一刻就把你忘了。而每一輪都把整段歷史塞給它，既貴、
最後還會撐爆 context。Minerva 把記憶拆成三層，每一層回答不同的問題：

| 層 | 底層 | 回答什麼 | 用 AI？ |
|----|------|----------|---------|
| **1. 結構化日誌** | Postgres（純 SQL） | 「什麼時候發生了什麼」—— 回顧某一天、這個月的成就、心情趨勢 | 不用 AI，純 SQL |
| **2. 語意回想** | pgvector + OpenAI embedding | 「跟*現在*相關的過去片刻是哪個」—— 對話中拉回相似的舊紀錄 | embedding + 向量搜尋 |
| **3. 滾動 profile** | LLM 濃縮的摘要 | 「這個人是誰」—— 目標、習慣、地雷、什麼對他有用 —— 每次回覆都注入 | 由 LLM 重新濃縮 |

每次 prompt 都由 **profile + 相關的回想 + 今天的脈絡** 組起來。Postgres 裡的日誌可以
無限長，但 prompt 不會，因為第 2、3 層只留它固定的一小片。這個會滾動的 profile ——
Minerva 持續學習你是誰 —— 正是無狀態聊天機器人做不到的事。

## 兩個值得說明的設計決定

**這裡沒有「對話記憶」這個元件。** 早期版本用 LangGraph 的 checkpointer 讓 agent 記住
當前對話，後來把它拿掉了：每一輪對話本來就已經寫進 Postgres，再維護一份記憶體副本等於
多一個真相來源 —— 而且那份會隨重啟消失、也跨不了裝置。現在每一輪都直接從資料庫重播
今天的對話。**拿掉一個元件，比多加一個框架更能證明想清楚了。**

**「一串對話」用 uid + 日期定義，不是用瀏覽器 session。** `session_id` 存在
localStorage，換一台裝置就會無聲無息地重新開始。日期則用 **台灣時間**
（`app/core/clock.py`）—— 用 UTC 換日會在早上 8 點把對話切斷，正好切在一個念頭的中間。

## 一次對話的流程長怎樣

```
  你開口 ──► gpt-4o-mini-transcribe（語音轉文字）──► LangChain agent
                                                            │
             ┌──────────────────────────────────────────────┼───────────────────────────┐
             │ 注入 profile + strengths + mantras            │ search_past_entries 工具  │
             │（第 3 層，每一輪）                             │ → pgvector（第 2 層）      │
             └──────────────────────────────────────────────┼───────────────────────────┘
                                                            ▼
                                              gpt-5.3-chat-latest 回覆
                                                            │
                       ┌────────────────────────────────────┴─────────────────┐
                       ▼                                                       ▼
              Google Cloud TTS（語音合成）                       存進 Postgres（第 1 層）
              把回覆唸出來                                       + embed 進 pgvector（第 2 層）
                                                                 + 定期重新濃縮 profile（第 3 層）
```

所以一次對話同時做兩件事：**當下回應你**，並且 **餵養三層記憶** 供下一次使用。

## 引擎蓋底下有什麼

- **語音進來** —— OpenAI **`gpt-4o-mini-transcribe`** 把你錄的音檔轉成文字。錄音格式
  由瀏覽器自己回報（Chrome 錄 webm、iOS Safari 錄 mp4），不是寫死一種。
- **Minerva 本體** —— 一個 LangChain agent（`create_agent`），由 **OpenAI
  `gpt-5.3-chat-latest`** 驅動，帶一個 `search_past_entries` 工具；只要回想過去片刻
  有幫助，它就會自己呼叫。Claude 是支援的替代選項，設 `LLM_PROVIDER=anthropic` 即可。
  profile、strengths 和你收藏的 mantra 都透過 dynamic prompt 每一輪注入。
- **語音出去** —— 回覆用 **Google Cloud TTS** 唸出來
  （`en-GB-Chirp3-HD-Callirrhoe`，是真的英國腔）。ElevenLabs 和 OpenAI TTS 在同一個
  `speak()` 後面，用 `TTS_PROVIDER` 切換。合成延遲隨長度**超線性**成長，所以前端把
  回覆切成約 220 字元的句子，播一段的同時去抓下一段 —— 第一聲大約 1 秒就出來。
- **帳號** —— 瀏覽器用 **Firebase Auth（Google 登入）**。後端用 Firebase Admin SDK
  驗證 ID token，把每一筆紀錄、每一次回想、以及 profile 都綁到那個人。除了
  `/health` 以外，所有 endpoint 都需要登入。
- **可觀測性** —— **LangSmith** 追蹤每一次 chain 與 agent 呼叫。

## 她能為你做什麼

| 功能 | 是什麼 |
|------|--------|
| **對話** | 語音或打字，逐字串流回來並唸出來。 |
| **Wins** | 從每次對話萃取出來的、你今天真的做了什麼的短句事實。 |
| **You** | 一段關於「你是怎樣的人」的白話文字，由 LLM 讀完你整份成就紀錄後寫成。給那些你忘記自己是誰的日子看。 |
| **Mantra** | 你自己留下來的句子。完整 CRUD，而且會注入她的 prompt，讓她能用你自己的話回敬你。 |

## 隱私

公開的 repo、展示頁、以及部署的 demo 都只用 **種子 / 假資料**。真實的日誌留在你自己的
機器上、已被 gitignore，repo 裡沒有任何 API key，所有花錢的 endpoint 都擋在登入
之後 —— 所以沒有人會花到你的 key，也讀不到你的日誌。

## 技術棧

| 部位 | 選擇 | 為什麼 |
|------|------|--------|
| Web 框架 | **FastAPI** | Async、型別、自動 Swagger；做 API 很輕。 |
| 套件管理 | **uv** | 一個工具搞定 venv + lockfile，比 pip/poetry 快很多。 |
| 編排 | **LangChain** | Agent + RAG + 記憶一套業界標準搞定，不用自己手刻工具迴圈。 |
| LLM | **OpenAI** `gpt-5.3-chat-latest` | 驅動 ChatGPT 本身的那個家族；用 `LLM_PROVIDER` 可換 Claude。 |
| 語音轉文字 | **OpenAI** `gpt-4o-mini-transcribe` | 比 `whisper-1` 新、更準，價格相近。 |
| 文字轉語音 | **Google Cloud TTS** | 真正的英國腔、免費額度大方；ElevenLabs / OpenAI 在同一個介面後面。 |
| 日誌儲存 | **Postgres + pgvector** | 一個資料庫同時放 SQL 紀錄和向量（LangChain `PGVector`）。 |
| Embedding | **OpenAI** `text-embedding-3-small` | 驅動語意回想。 |
| 認證 | **Firebase Auth**（Google） | 這邊不碰密碼；用驗過的 uid 做逐人隔離。 |
| 追蹤 | **LangSmith** | 每一次 chain/agent 呼叫都被追蹤。 |
| 前端 | **React（Vite）** | 對話、Wins、You、Mantra 四個畫面，含麥克風錄音 + 語音回覆。 |
| Lint | **ruff** | 檢查和排版一個工具搞定，而且很快。 |
| CI/CD | **GitHub Actions** | 每次 push 跑 ruff + pytest；main 過了就自動部署。 |
| 部署 | **Google Cloud** | Cloud Run + Cloud SQL（Postgres + pgvector）+ Secret Manager。 |

## 專案結構

```
app/
  main.py            FastAPI 進入點：掛載 router、建表、提供打包好的前端
  api/
    router.py        把每個路由模組收在一起
    deps.py          CurrentUser —— 標上它的路由就需要登入
    routes/          health · coach · voice · journal · profile · mantras
  services/
    agent.py         LangChain agent（create_agent + 工具 + prompt 注入）
    chat_model.py    依 LLM_PROVIDER 建出對應的 chat model
    recall.py        語意回想 —— search_past_entries，跑在 pgvector 上（第 2 層）
    profile.py       滾動的、LLM 濃縮的 profile（第 3 層）
    strengths.py     「You」那段文字，從整份成就紀錄寫出來
    entries.py       純 SQL 日誌：存檔、回顧某天、列出成就（第 1 層）
    mantras.py       你收藏的句子，以及它們的 prompt 文字
    voice.py         語音轉文字 + 文字轉語音
  models/            SQLAlchemy 資料表：Entry、Profile、Mantra
  schemas/           request / response 模型
  core/
    config.py        從 env / .env 讀設定
    db.py            SQLAlchemy engine + session
    security.py      Firebase ID token 驗證、逐人隔離
    clock.py         定義「今天」是什麼（台灣時間）
scripts/
  init_db.py         建立資料表
  deploy_gcp.sh      架好 Cloud Run + Cloud SQL + Secret Manager
frontend/            React（Vite）UI，擋在 Google 登入 gate 之後
Dockerfile           給 Cloud Run 用的容器映像
.gcloudignore        讓 node_modules 不會被上傳到部署流程
.github/workflows/ci.yml   ruff + pytest，main 綠燈後自動部署
```

## 安裝與啟動

```bash
# 1. 安裝依賴（uv 依 lockfile 建 venv）
uv sync

# 2. 啟動本地 Postgres（pgvector 映像）並建表
docker compose up -d
uv run python -m scripts.init_db

# 3. 填入 key
cp .env.example .env    # 編輯 .env：OPENAI_API_KEY（若要換供應商再填
                        # ANTHROPIC / ELEVENLABS）、FIREBASE_CREDENTIALS、
                        # 選填的 LANGSMITH_API_KEY

# 4. 啟動 API
uv run uvicorn app.main:app --reload
```

打開 http://127.0.0.1:8000/docs 就是互動式 Swagger 介面。

## Endpoints

| Method | Path | 認證 | 說明 |
|--------|------|------|------|
| GET  | `/health`            | — | 存活檢查；不需 key。 |
| POST | `/agent`             | ✅ | 打字聊天。`{"question", "session_id?"}` → 回覆；這次對話會存成一筆日誌。 |
| POST | `/agent/stream`      | ✅ | 同 `/agent`，但逐字串流回覆。 |
| POST | `/transcribe`        | ✅ | 上傳錄音 → 轉成文字。 |
| POST | `/speak`             | ✅ | 文字 → 語音（mp3），給瀏覽器播。 |
| GET  | `/entries?day=`      | ✅ | 回顧某一天的紀錄（`YYYY-MM-DD`，預設今天，台灣時間）。 |
| GET  | `/wins`              | ✅ | 最近幾筆有記到成就的紀錄。 |
| GET  | `/strengths`         | ✅ | 「You」那段文字，從你的成就紀錄寫成。 |
| POST | `/strengths/refresh` | ✅ | 強制重寫那段文字。 |
| GET  | `/profile`           | ✅ | 她替你建立的長期 profile。 |
| POST | `/profile/refresh`   | ✅ | 強制重新濃縮 profile（正常情況每幾筆自動做）。 |
| GET  | `/mantras`           | ✅ | 你收藏的句子。 |
| POST | `/mantras`           | ✅ | 收藏一句新的。 |
| PATCH | `/mantras/{id}`     | ✅ | 改寫其中一句。 |
| DELETE | `/mantras/{id}`    | ✅ | 刪掉其中一句。 |

受保護的 endpoint 需要帶 `Authorization: Bearer <Firebase ID token>`。

## Web UI

`frontend/` 的 React（Vite）前端有四個畫面 —— 對話、Wins、You、Mantra ——
全部擋在 Google 登入 gate 之後。API 跑著的時候，另開一個 terminal 啟動它：

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

它會打 `http://127.0.0.1:8000` 的 API（已透過 CORS 放行）。上線時同一份 React
build 是由 FastAPI 自己從映像裡提供的。

## 測試與 lint

```bash
uv run pytest
uv run ruff check .
```

LLM、語音、向量庫都被 mock，整套測試跑在記憶體內的 SQLite 上，所以不需 API key、也不用
起 Postgres。

## 部署

推上 `main` 就會自動部署：GitHub Actions 跑 ruff + pytest，綠燈後 build 並推上
Cloud Run。它用 **Workload Identity Federation** 認證 —— GitHub 用一個短效的 OIDC
token 證明自己是誰，Google 回一組短效憑證，所以**任何地方都不存在服務帳號金鑰**。

`scripts/deploy_gcp.sh` 則是從零把整套架起來：一個 Cloud Run 服務跑 API、
**Cloud SQL**（帶 pgvector 的 Postgres）存日誌與向量、**Secret Manager** 放所有
key 和 Firebase 服務帳號。執行前先 `gcloud auth login`。
