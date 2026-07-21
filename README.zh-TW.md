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
| **1. 結構化日誌** | Postgres（純 SQL） | 「什麼時候發生了什麼」—— 依序回顧任何一天 | 不用 AI，純 SQL |
| **2. 語意回想** | pgvector 裡的原子事實 | 「我知道的事情裡，跟*現在*相關的是哪些」—— 拉回一條條依分類歸檔的事實 | 由 LLM 把每輪拆成事實；再用 embedding + 向量搜尋找出來 |
| **3. 滾動 profile** | LLM 濃縮的摘要 | 「這個人是誰」—— 目標、習慣、地雷、什麼對他有用 —— 每次回覆都注入 | 由 LLM 重新濃縮 |

每次 prompt 都由 **profile + 相關的回想 + 今天的脈絡** 組起來。Postgres 裡的日誌可以
無限長，但 prompt 不會，因為第 2、3 層只留它固定的一小片。這個會滾動的 profile ——
Minerva 持續學習你是誰 —— 正是無狀態聊天機器人做不到的事。

## 三個值得說明的設計決定

**記憶存的是原子事實，不是整輪對話。** 第一版把每一輪整段拿去 embedding，一碰到真實
使用就露餡：一個人用語音講三分鐘，工作、健康、家人會混在同一段話裡，三個主題被平均進
同一組 1536 維向量之後，搜「健康」就會被另外兩條線稀釋。檢索品質退化成「找一天氣氛
相似的」，而不是「找到那個相關的片刻」。

所以現在每次對話都由 LLM 拆成 5–10 條單一主題的事實，各自歸進九個固定分類之一
（`about me`、`preferences`、`people`、`work & career`、`goals & aspirations`、
`health & habits`、`beliefs`、`patterns`、`wins`），再各自 embedding。這個拆解是**改寫**而不是
切開：「工作卡住但還是去跑了步」會變成獨立成立的「很累的時候還是會去跑步」—— 幾個月後
被檢索回來、脫離上下文也讀得懂。檢索時，向量相似度和模型自己的判斷**同時**發揮作用：
agent 會把它認為該搜的分類當成工具參數填進去，兩邊一起收斂範圍。

也值得說清楚這招**不適合**什麼：如果答案本來就躺在某一段文字裡（文件問答、合約的某一
條），直接切塊丟進向量庫更便宜、效果也一樣好。事實抽取只有在答案必須從散落的線索
**組裝**出來時才划算 —— 而「我壓力大的時候是什麼樣子」正是這種問題。

**這裡沒有「對話記憶」這個元件。** 早期版本用 LangGraph 的 checkpointer 讓 agent 記住
當前對話，後來把它拿掉了：每一輪對話本來就已經寫進 Postgres，再維護一份記憶體副本等於
多一個真相來源 —— 而且那份會隨重啟消失、也跨不了裝置。現在每一輪都直接從資料庫重播
今天的對話。**拿掉一個元件，比多加一個框架更能證明想清楚了。**

**「一串對話」用 uid + 日期定義，不是用瀏覽器 session。** 後端完全不認得瀏覽器，
所以同一個人換任何一台裝置登入，接的都是同一串對話。日期則用 **台灣時間**
（`app/core/clock.py`）—— 用 UTC 換日會在早上 8 點把對話切斷，正好切在一個念頭的中間。

## 一次對話的流程長怎樣

```
  你開口 ──► gpt-4o-mini-transcribe（語音轉文字）──► LangChain agent
                                                            │
             ┌──────────────────────────────────────────────┼───────────────────────────┐
             │ 注入 profile + mantras                        │ search_past_entries 工具  │
             │（第 3 層，每一輪）                             │ → pgvector（第 2 層）      │
             └──────────────────────────────────────────────┼───────────────────────────┘
                                                            ▼
                                              gpt-5.3-chat-latest 回覆
                                                            │
                       ┌────────────────────────────────────┴─────────────────┐
                       ▼                                                       ▼
              Google Cloud TTS（語音合成）                       存進 Postgres（第 1 層）
              把回覆唸出來                                       + 拆成原子事實，各自 embed
                                                                   進 pgvector（第 2 層）
                                                                 + 定期重新濃縮 profile（第 3 層）
```

所以一次對話同時做兩件事：**當下回應你**，並且 **餵養三層記憶** 供下一次使用。

## 引擎蓋底下有什麼

- **語音進來** —— OpenAI **`gpt-4o-mini-transcribe`** 把你錄的音檔轉成文字。錄音格式
  由瀏覽器自己回報（Chrome 錄 webm、iOS Safari 錄 mp4），不是寫死一種。
- **Minerva 本體** —— 一個 LangChain agent（`create_agent`），由 **OpenAI
  `gpt-5.3-chat-latest`** 驅動，帶一個 `search_past_entries` 工具；只要回想過去片刻
  有幫助，它就會自己呼叫。這個工具可以額外收一組分類，讓模型自己縮小搜尋範圍，不必
  單靠向量距離。Claude 是支援的替代選項，設 `LLM_PROVIDER=anthropic` 即可。
  profile 和你收藏的 mantra 都透過 dynamic prompt 每一輪注入。
- **事實抽取** —— 回覆送出之後，用一次小型的 structured output 呼叫把這次對話拆成
  單一主題的事實，各自歸進固定分類（`app/services/facts.py`）。它跑在回覆路徑之外，
  所以使用者不會多等。`scripts/backfill_facts.py` 對「事實機制出現前」的舊紀錄做同樣的
  事，並且會把每筆原本的日期一起帶過去。
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
| 日誌儲存 | **Postgres + pgvector** | 一個資料庫同時放紀錄、抽出來的事實、以及它們的向量（LangChain `PGVector`）。 |
| Embedding | **OpenAI** `text-embedding-3-small` | 一條事實一個向量，讓搜尋只命中單一主題。 |
| 認證 | **Firebase Auth**（Google） | 這邊不碰密碼；用驗過的 uid 做逐人隔離。 |
| 追蹤 | **LangSmith** | 每一次 chain/agent 呼叫都被追蹤。 |
| 前端 | **React（Vite）** | 對話、Mantra 兩個畫面，含麥克風錄音 + 語音回覆。 |
| Lint | **ruff** | 檢查和排版一個工具搞定，而且很快。 |
| CI/CD | **GitHub Actions** | 每次 push 跑 ruff + pytest；main 過了就自動部署。 |
| 部署 | **Google Cloud** | Cloud Run + Cloud SQL（Postgres + pgvector）+ Secret Manager。 |

## 專案結構

```
app/
  main.py            FastAPI 進入點：掛載 router、建表、提供打包好的前端
  api/
    router.py        把每個路由模組收在一起
    deps.py          CurrentUid —— 標上它的路由就需要登入
    routes/          health · coach · voice · journal · profile · mantras
  services/
    agent.py         LangChain agent（create_agent + 工具 + prompt 注入）
    chat_model.py    依 LLM_PROVIDER 建出對應的 chat model
    facts.py         把每次對話拆成原子事實，依分類歸檔
    recall.py        語意回想 —— search_past_entries，跑在 pgvector 上（第 2 層）
    profile.py       滾動的、LLM 濃縮的 profile（第 3 層）
    entries.py       純 SQL 日誌：存檔、回顧某天（第 1 層）
    mantras.py       你收藏的句子，以及它們的 prompt 文字
    voice.py         語音轉文字 + 文字轉語音
  models/            SQLAlchemy 資料表：Entry、Fact、Profile、Mantra
  schemas/           request / response 模型
  core/
    config.py        從 env / .env 讀設定
    db.py            SQLAlchemy engine + session
    security.py      Firebase ID token 驗證、逐人隔離
    clock.py         定義「今天」是什麼（台灣時間）
migrations/          Alembic：一次 schema 變更一個檔案，依序套用
scripts/
  init_db.py         把 schema 更新到最新（等同 alembic upgrade head）
  backfill_facts.py  對事實機制出現前的舊紀錄補抽事實
  deploy_gcp.sh      首次建置用：架好 Cloud Run + Cloud SQL + Secret Manager
frontend/            React（Vite）UI，擋在 Google 登入 gate 之後
Dockerfile           給 Cloud Run 用的容器映像
.gcloudignore        讓 node_modules 不會被上傳到部署流程
.github/workflows/ci.yml   ruff + pytest，main 綠燈後自動部署
```

## 安裝與啟動

```bash
# 1. 安裝依賴（uv 依 lockfile 建 venv）
uv sync

# 2. 啟動本地 Postgres（pgvector 映像）並跑 migration
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
| POST | `/agent`             | ✅ | 打字聊天。`{"question"}` → 回覆；這次對話會存成一筆日誌。 |
| POST | `/agent/stream`      | ✅ | 同 `/agent`，但逐字串流回覆。 |
| POST | `/transcribe`        | ✅ | 上傳錄音 → 轉成文字。 |
| POST | `/speak`             | ✅ | 文字 → 語音（mp3），給瀏覽器播。 |
| GET  | `/entries?day=`      | ✅ | 回顧某一天的紀錄（`YYYY-MM-DD`，預設今天，台灣時間）。 |
| GET  | `/profile`           | ✅ | 她替你建立的長期 profile。 |
| POST | `/profile/refresh`   | ✅ | 強制重新濃縮 profile（正常情況每幾筆自動做）。 |
| GET  | `/mantras`           | ✅ | 你收藏的句子。 |
| POST | `/mantras`           | ✅ | 收藏一句新的。 |
| PATCH | `/mantras/{id}`     | ✅ | 改寫其中一句。 |
| DELETE | `/mantras/{id}`    | ✅ | 刪掉其中一句。 |

受保護的 endpoint 需要帶 `Authorization: Bearer <Firebase ID token>`。

## Web UI

`frontend/` 的 React（Vite）前端有兩個畫面 —— 對話、Mantra ——
全部擋在 Google 登入 gate 之後。API 跑著的時候，另開一個 terminal 啟動它：

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

它會打 `http://127.0.0.1:8000` 的 API（已透過 CORS 放行）。上線時同一份 React
build 是由 FastAPI 自己從映像裡提供的。

## 改 schema

Schema 用 **Alembic** 版本控管。改完 model 之後：

```bash
uv run alembic revision --autogenerate -m "改了什麼"   # 產生 migration
uv run alembic upgrade head                            # 套用
uv run alembic downgrade -1                            # 退回一步
uv run alembic check                                   # 比對 model 和資料庫
```

App 啟動時會跑 `alembic upgrade head`，所以部署會自己遷移，全新的資料庫也能從
零建起來。

`migrations/env.py` 會把 LangChain 的 `langchain_pg_*` 表擋在 autogenerate 之外。
那些表不在 `Base.metadata` 裡（是 LangChain 自己建的），沒有這個過濾器的話，每次
產生的 migration 都會想刪掉它們——連同裡面所有的向量。

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
