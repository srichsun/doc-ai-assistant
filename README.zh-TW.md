# Dear Myself

[English](README.md) · **中文**

> 🌐 **線上展示頁 → https://srichsun.github.io/dearme/**
>
> 🚀 **線上試用 → https://heydearmyself.com**

**一個關於能量、勝利與感恩的 AI 日記。** 一天一頁。寫下來，讀回去，看清楚這幾週到底是由什麼組成的。

Dear Myself 不是一個整天跟你聊天的機器人。你把一天寫下來一次、給今天的能量打個分數、按一個按鈕。它會抽出你今天贏了什麼、對什麼心懷感激，存進一份會長大的記憶，並把你的能量畫成一條時間線 —— 在難熬的那一週裡看不見的模式，從一個月的距離看回去會非常明顯。

讓這件事成立的工程核心是**記憶**：三層設計，讓紀錄可以無限成長，而每次送出的 prompt 大小固定有上限。

## 為什麼要三層記憶

一般的聊天機器人在分頁關掉的瞬間就忘了你。把整段歷史每輪都塞給它既昂貴、最後也會撐爆 context window。Dear Myself 把記憶拆成三層，各自回答不同的問題：

| 層 | 由什麼支撐 | 回答什麼 | 用到 AI？ |
|---|---|---|---|
| **1. 日記本身** | Postgres（純 SQL） | 「發生了什麼，什麼時候？」—— 一天一列，用日期查 | 不用 AI，就是 SQL |
| **2. 語意檢索** | pgvector 裡的原子事實 | 「我知道的事情裡，哪些跟*這個問題*有關？」—— 一條一條的事實，有分類 | LLM 把一天拆成事實；embedding + 向量搜尋找回來 |
| **3. 滾動摘要** | LLM 濃縮的摘要 | 「這個人是誰？」—— 你是怎樣的人、你重複做什麼、你的能量對什麼有反應 | LLM 重新濃縮 |

每個回答都是由**滾動摘要 + 為這個問題撈回來的事實**組起來的。日記可以永遠長下去，prompt 不會，因為第 2、3 層只保留固定的一小片。

## 資料只往一個方向流

```
   你寫的日記                                  問它問題
   ─────────────────────                    ───────────────
   entries  （一天一列）                      你的問題
      │  按「Read today」— 一次 LLM              │
      ▼                                          ▼  向量 + 分類搜尋
   facts    （5–10 條單一主題，各自 embedding） ──►  跟問題有關的事實
      │  按「Read me」— 另一次 LLM               │  + 滾動摘要
      ▼                                          ▼
   profiles （你是誰 / pattern / 能量）    ─────►  回答，並說出是哪幾天
```

**沒有任何箭頭往回指。** 問問題不會寫入任何東西：不產生日記、不產生事實、不更新摘要。它對你的認識，全部來自你坐下來寫的東西，不會來自你隨口說的話。這**不是靠規矩守住的** —— 那條路徑上根本不存在寫入的呼叫，而且有一個測試刻意不去 mock 事實抽取器，所以哪天有人把它加回來，測試會直接大聲失敗。

## 值得解釋的設計決定

**記憶存的是原子事實，不是整篇。** 第一版把每輪對話整個 embedding。一碰到真實使用就壞了：一個人講三分鐘會在同一口氣裡橫跨工作、健康跟家人，把這三件事平均成同一組 1536 維向量，代表搜尋「健康」會被另外兩條線稀釋。檢索退化成「找一個氣氛相似的日子」，而不是「找到相關的那個片刻」。

所以現在每一天都由 LLM 拆成 5–10 條單一主題的事實，各自歸進十個固定分類之一（`about me`、`preferences`、`people`、`work & career`、`goals & aspirations`、`health & habits`、`beliefs`、`patterns`、`wins`、`gratitude`），並各自 embedding。**這個拆解是「改寫」不是「切開」**：「工作卡住但我還是去跑了步」會變成獨立的一句「你很累的時候還是會去跑步」，幾個月後在沒有上下文的情況下被撈出來，仍然讀得懂。檢索時，向量相似度是跟**模型自己的判斷並行**的 —— agent 會把值得搜尋的分類當成 tool 參數指定，兩邊一起縮小範圍。

也值得說清楚它**不適合**什麼：如果答案本來就在某一段文字裡（文件問答、合約的某個條款），直接切塊 embedding 更便宜、效果一樣好。事實抽取只有在答案必須從**散落的線索組裝**出來時才划算 —— 而「到底什麼在消耗我？」正是這種問題。

**改產品直接讓一個架構問題消失，而不是去解決它。** 在聊天版裡，事實抽取每輪都要跑，等於在人跟他的回覆之間插進一次 LLM 呼叫加一輪 embedding。解法看起來會是任務佇列：Celery、Redis、一個不能縮到零的常駐 worker —— 每個月大約一千多塊台幣的基礎設施，只為了藏起一段延遲。**把產品變成日記之後，抽取被移到一個使用者主動按的按鈕後面，整個問題就沒了。** 不用佇列、不用 broker、不用 worker。**延遲問題最便宜的解法，常常是產品決定，不是基礎設施。**

**沒有「對話記憶」這個元件。** 早期版本留著 LangGraph 的 checkpointer，讓 agent 記得當下這段對話。後來拿掉了：每個問題本來就已經寫進 Postgres，記憶體裡那份等於第二個真相來源，重啟就消失、也跨不了裝置。現在每一輪都從資料庫重放今天的對話。**移除一個元件，比多加一個框架更能證明想清楚了。**

**一天的定義是 uid + 日期，不是瀏覽器 session** —— 而且日期用**台灣時間**（`app/core/clock.py`）。用 UTC 換日會在早上 8 點把一天切斷，正好切在一個早晨的中間。同一個定義順便免費給了日記最核心的規則：**一個人一天最多一篇，由 unique 索引擋住，不是靠 service 層的判斷式**。同一天想寫第二篇不是被拒絕，是不可能。而且只有今天可以寫，也沒有任何 endpoint 收「要寫哪一天」，所以想補一篇漏掉的日記不是被禁止，是根本沒有入口。

**寫日記免費，分析才計次。** 額度原本是編輯文字跟重跑分析共用。真的用起來才發現那是收錯了錢 —— 一天是分好幾次寫完的，中午記一筆、剩下的半夜補，計次等於在懲罰你跟上自己的日子。存文字不花錢，所以寫日記無限次。**一天三次的額度整個移到分析上**：那才是花掉一次模型呼叫的動作，也才是那個「一天過完就該定案」的動作。

**能量自評是十段，不是一百段。** 顯示成百分比，但是從 1–10 選。沒有人分得出自己今天是 67 還是 71，刻度細過判斷力，只會讓圖表看起來很精確而意義變少。**沒打分數的日子畫成空白**，不是 0、也不連線 —— 連線等於宣稱中間那幾天正走在從這個數字到那個數字的路上，而那是在替根本沒有評分的日子說話。

## 四個畫面

| 畫面 | 是什麼 |
|---|---|
| **Record** | 7 天或 30 天的能量圖、今天的日記（打字或口述），以及後面每天一張摺疊卡，帶著那天的勝利與感恩。 |
| **Reading** | 你是怎樣的人、你重複做什麼、你的能量對什麼有反應。只有你按了才重建。 |
| **Ask** | 針對自己日記的提問，串流輸出並可朗讀，每個回答都會說出它翻了哪幾天。只讀不寫，而且對話隨當天結束。 |
| **Mantras** | 你替自己留下的句子，會注入 prompt，讓你自己的話被還給你。 |

## 底層是什麼

- **寫入** —— 可以打字，也可以口述：**OpenAI `gpt-4o-mini-transcribe`** 把錄音轉成文字並**接在**今天的內容後面，所以一篇日記可以分好幾次講完。錄音格式是問瀏覽器實際產出什麼（Chrome 給 webm、iOS Safari 給 mp4），而不是程式碼自己假設一種。
- **分析** —— 一次 structured-output 呼叫把一天拆成單一主題的事實，各自歸進固定分類（`app/services/facts.py`）。**重跑分析會把那天的事實在 Postgres 跟 pgvector 兩邊都換掉**，而不是讓同一天的兩種讀法同時留在記憶裡。
- **提問** —— 一個 LangChain agent（`create_agent`），由 **OpenAI `gpt-5.3-chat-latest`** 驅動，只有一個 `search_past_entries` 工具，由它自己決定何時呼叫。工具收一個選填的分類清單，所以模型能自己縮小範圍，而不是只靠向量距離。**每條事實回來時都帶著它被寫下的那個日記日期** —— 這個日期是從 SQL 那一列讀的，不是向量的 metadata，所以重新分析某一天，永遠不會讓它引用「重讀的那天」。Claude 也支援：`LLM_PROVIDER=anthropic`。
- **朗讀** —— 回答用 **Google Cloud TTS** 唸出來（`en-GB-Chirp3-HD-Callirrhoe`）。ElevenLabs 與 OpenAI TTS 藏在同一個 `speak()` 後面，用 `TTS_PROVIDER` 切換。合成延遲隨長度**超線性**成長，所以前端把回覆切成約 220 字的句子，播一段的同時去拿下一段 —— 第一個聲音大約一秒就出來。
- **帳號** —— 瀏覽器端用 **Firebase Auth（Google 登入）**。後端用 Firebase Admin SDK 驗證 ID token，並把每一篇日記、每一次檢索、那份摘要都限定在那一個人身上。**用 id 查資料時 uid 是寫在查詢裡的**，所以猜一個 id 的結果是「查無此筆」，而不是先載出來再拒絕。
- **可觀測性** —— **LangSmith** 追蹤每一次 chain 與 agent 呼叫。

## 隱私

公開的 repo、展示頁與線上 demo 只用**種子／假資料**。真實日記留在自己機器上並且被 gitignore，repo 裡沒有任何 API key，每個會花錢的 endpoint 都擋在登入後面 —— 所以沒有人能花你的 key 或讀你的日記。

## 技術選型

| 項目 | 選擇 | 為什麼 |
|---|---|---|
| Web 框架 | **FastAPI** | 非同步、型別註記、自動 Swagger 文件；當 API 夠輕。 |
| 套件管理 | **uv** | venv 加 lockfile 一個工具搞定，比 pip/poetry 快得多。 |
| 編排 | **LangChain** | agent 與 tool loop 用業界標準的一套，而不是自己手刻。 |
| LLM | **OpenAI** `gpt-5.3-chat-latest` | 撐起 ChatGPT 本身的那個模型家族；Claude 可用 `LLM_PROVIDER` 切換。 |
| 語音轉文字 | **OpenAI** `gpt-4o-mini-transcribe` | 比 `whisper-1` 新、更準，價格相近。 |
| 文字轉語音 | **Google Cloud TTS** | 真正的英國腔，免費額度大方；ElevenLabs / OpenAI 在同一個呼叫後面。 |
| 日記儲存 | **Postgres + pgvector** | 同一個資料庫同時放日記、抽出來的事實、以及它們的向量（LangChain `PGVector`）。 |
| Embedding | **OpenAI** `text-embedding-3-small` | 一條原子事實一個向量，所以搜尋命中的是單一主題。 |
| 認證 | **Firebase Auth**（Google） | 這裡不碰任何密碼；用驗證過的 uid 做逐人隔離。 |
| 追蹤 | **LangSmith** | 每次 chain/agent 呼叫都有 trace。 |
| 前端 | **React（Vite）** | 四個手機優先的畫面；能量圖用 **Recharts**。 |
| Lint | **ruff** | 一個快工具同時做 lint 跟 format。 |
| CI/CD | **GitHub Actions** | 每次 push 跑 ruff + pytest；main 綠燈自己部署。 |
| 部署 | **Google Cloud** | Cloud Run + Cloud SQL（Postgres + pgvector）+ Secret Manager。 |

## 專案結構

```
app/
  main.py            FastAPI app：掛上 router、開機跑 migration、serve 打包好的前端
  api/
    router.py        把每個 route 模組收在一起
    deps.py          CurrentUid —— route 標上它就代表需要登入
    routes/          health · journal · coach · questions · profile · mantras · voice
  services/
    entries.py       日記：一天一列，只有今天可寫（第 1 層）
    facts.py         把一天拆成原子事實，各自歸類
    recall.py        語意檢索 —— pgvector 上的 search_past_entries（第 2 層）
    profile.py       滾動摘要，三個段落（第 3 層）
    questions.py     問答紀錄 —— 讀取路徑唯一可以寫的表
    agent.py         LangChain agent（create_agent + 工具 + prompt 注入）
    chat_model.py    依 LLM_PROVIDER 建出對應的 chat model
    mantras.py       你留下的句子，以及它們的 prompt 文字
    voice.py         語音轉文字 + 文字轉語音
  models/            SQLAlchemy 資料表：Entry、Fact、Profile、Question、Mantra
  schemas/           request / response 模型
  core/
    config.py        從 env / .env 讀設定
    db.py            SQLAlchemy engine + session
    security.py      Firebase ID token 驗證、逐人隔離
    clock.py         定義「今天」是什麼（台灣時間）
migrations/          Alembic：一次 schema 變更一個檔案，依序套用
scripts/
  backfill_facts.py  對還沒有事實的日記補抽
  deploy_gcp.sh      首次建置用：架好 Cloud Run + Cloud SQL + Secret Manager
frontend/src/
  App.jsx            外殼：登入、四個 tab
  tabs/              Record · Insights · Ask · Mantras
  EnergyChart.jsx    一天一根長條的圖（Recharts）
  energy.js          一個分數長什麼樣：色帶、顏色、百分比
  speech.js          錄音與朗讀
  api.js             帶認證的 fetch
Dockerfile           給 Cloud Run 用的容器映像
.github/workflows/ci.yml   ruff + pytest，main 綠燈後自動部署
```

## 安裝與啟動

```bash
# 1. 安裝依賴（uv 依 lockfile 建 venv）
uv sync

# 2. 啟動本地 Postgres（pgvector 映像）並跑 migration
docker compose up -d
uv run alembic upgrade head

# 3. 填入 key
cp .env.example .env    # 編輯 .env：OPENAI_API_KEY（若要換供應商再填
                        # ANTHROPIC / ELEVENLABS）、FIREBASE_CREDENTIALS、
                        # 選填的 LANGSMITH_API_KEY

# 4. 啟動 API
uv run uvicorn app.main:app --reload
```

打開 http://127.0.0.1:8000/docs 就是可互動的 Swagger UI。

## API 端點

| 方法 | 路徑 | 需登入 | 說明 |
|---|---|---|---|
| GET | `/health` | — | 存活檢查，不需要 key。 |
| POST | `/entries` | ✅ | 寫或改寫今天。不計次。 |
| GET | `/entries?days=7` | ✅ | 最近 N 天的日記，由舊到新，各自帶著勝利與感恩。 |
| POST | `/entries/{id}/analyze` | ✅ | 從寫下的內容抽出當天的事實。一天三次，之後回 `409`。 |
| GET | `/profile` | ✅ | 滾動摘要，以及它落後了幾天。 |
| POST | `/profile/refresh` | ✅ | 重建它。只有被要求時才跑。 |
| POST | `/agent/stream` | ✅ | 針對日記提問，回答逐字串流。除了問題本身什麼都不寫。 |
| GET | `/questions?day=` | ✅ | 某一天的問答（預設今天）。 |
| GET | `/questions/days` | ✅ | 有提問過的日子 —— 紀錄列表。 |
| POST | `/transcribe` | ✅ | 上傳錄音 → 文字。 |
| POST | `/speak` | ✅ | 文字 → 語音（mp3），給瀏覽器播。 |
| GET | `/mantras` | ✅ | 你留下的句子。 |
| POST | `/mantras` | ✅ | 留下新的一句。 |
| PATCH | `/mantras/{id}` | ✅ | 改寫其中一句。 |
| DELETE | `/mantras/{id}` | ✅ | 放掉其中一句。 |

需登入的端點要帶 `Authorization: Bearer <Firebase ID token>`。

## 前端

`frontend/` 裡的 React（Vite）前端有四個手機優先的畫面，擋在 Google 登入之後。API 跑起來之後，另開一個終端機：

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

它會打 `http://127.0.0.1:8000`（CORS 已允許）。正式環境下同一份 React build 是由 FastAPI 自己從映像裡 serve 出去的。

## Schema 變更

Schema 用 **Alembic** 做版本管理。改完 model 之後：

```bash
uv run alembic revision --autogenerate -m "改了什麼"   # 產生 migration
uv run alembic upgrade head                            # 套用
uv run alembic downgrade -1                            # 回退
uv run alembic check                                   # 比對 model 與資料庫
```

App 開機會跑 `alembic upgrade head`，所以一次部署就自己完成遷移，全新的資料庫也能從空的建起來。**這也代表 push 到 `main` 會把你的 migration 直接套到正式環境** —— 中間沒有第二次確認，所以有資料遷移的 migration 請先在還原出來的副本上跑過。

`migrations/env.py` 會把 LangChain 的 `langchain_pg_*` 表排除在 autogenerate 之外。那些表不在 `Base.metadata` 裡（是 LangChain 自己建的），沒有這個過濾的話每次 migration 都會想 drop 掉它們 —— 連同裡面所有 embedding。

## 測試與 Lint

```bash
uv run pytest
uv run ruff check .
```

LLM、語音、向量庫都被 mock 掉，整套測試跑在 in-memory SQLite 上，所以不需要 API key、也不需要跑著的 Postgres。

## 部署

push 到 `main` 就會自己部署：GitHub Actions 跑 ruff + pytest，綠燈後建置並推上 Cloud Run。認證用 **Workload Identity Federation** —— GitHub 用短效的 OIDC token 證明身分，Google 換回一組短效憑證，**所以任何地方都不存在 service account 金鑰**。

`scripts/deploy_gcp.sh` 會在 **Google Cloud** 上從零把整套建起來：一個 Cloud Run 服務跑 API、**Cloud SQL**（帶 pgvector 的 Postgres）放日記與向量、**Secret Manager** 放所有 key 與 Firebase service account。`gcloud auth login` 之後執行即可。
