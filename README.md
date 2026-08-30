# Samsung Phone Query and Review System

An intelligent end-to-end system that scrapes Samsung smartphone data from
GSMArena, stores it in PostgreSQL, and exposes it through a RAG-based
conversational chatbot, a multi-agent review pipeline, and a FastAPI.

---

## 1. Overview

This project was built as a Python internship assignment. It combines four
capabilities into one working application:

| Capability | What it does |
|------------|--------------|
| **Web scraping** | Scrapes 15 popular Samsung phones from GSMArena (BeautifulSoup + Requests). |
| **Structured database** | Stores phones, full specification sheets and reviews in PostgreSQL (SQLAlchemy ORM). |
| **RAG chatbot** | Retrieves relevant phone data and answers specification, comparison and ranking questions without hallucinating. |
| **Multi-agent system** | A Specification Retrieval Agent and a Product Review Agent collaborate to write detailed reviews. |
| **FastAPI** | REST API with validation, error handling, logging and interactive Swagger docs. |
| **Web UI** | A premium browser interface (chat + review + phone browser) served at `/`. |

## 2. Assignment Objective

> "Scrape Samsung phone data from GSMArena, store it in a structured database,
> build a conversational chatbot using an open-source LLM with RAG, implement a
> multi-agent system for fetching specs and generating reviews, and expose
> everything through an API."

## 3. Features

- **Scraper** — polite, retrying, duplicate-safe; handles missing fields,
  network errors and multi-line spec rows; logs progress.
- **Database** — normalized relational schema with primary keys, foreign keys,
  unique constraints and indexes; PostgreSQL primary, SQLite fallback.
- **RAG** — semantic retrieval (sentence-transformers) with a dependency-free
  hashing fallback; deterministic keyword targeting for precise grounding.
- **Chatbot** — answers spec, feature, comparison, battery, camera, performance
  and ranking questions; never invents data; returns provenance (sources).
- **Multi-agent** — spec agent → DB → typed report → review agent → persisted
  review.
- **API** — `/health`, `/phones`, `/phones/{name}`, `/query`, `/chat`, `/review`
  with Pydantic validation and clean error handling.
- **Tests** — 40 automated tests covering DB, scraper, RAG, chatbot, agents and
  API.
- **Configurable LLM** — works fully offline (grounded fallback); plug in
  Hugging Face, OpenAI-compatible or Ollama via environment variables.

## 4. Architecture

```
User Query
    │
    ▼
FastAPI  ──►  RAG Chatbot  ──►  Retriever (embeddings)  ──►  PostgreSQL
    │                                        │
    └──► Multi-Agent (Spec Agent → Review Agent) ──►  Reviews table
```

- **Scraper layer** (`app/scraper/`) fetches and parses GSMArena pages.
- **Database layer** (`app/database/`) defines models and CRUD helpers.
- **RAG layer** (`app/rag/`) builds document chunks, retrieves them, and
  generates grounded answers.
- **Agent layer** (`app/agents/`) orchestrates the multi-agent review workflow.
- **API layer** (`app/api/`, `app/main.py`) exposes everything over HTTP.

See [docs/architecture.md](docs/architecture.md) for details.

## 5. Technologies

Python 3.11+, FastAPI, Uvicorn, SQLAlchemy, PostgreSQL, psycopg2,
BeautifulSoup, lxml, Requests, sentence-transformers, scikit-learn, Pydantic,
Pytest.

## 6. Project Structure

```
samsung-phone-query-review-system/
├── app/
│   ├── main.py                 # FastAPI app + web UI + error handling
│   ├── config.py               # settings from .env
│   ├── logging_setup.py        # central logging
│   ├── static/index.html       # premium web UI (chat + review + browser)
│   ├── api/routes.py           # REST endpoints
│   ├── database/
│   │   ├── connection.py       # engine/session
│   │   ├── models.py           # Phone / Specification / Review
│   │   └── crud.py             # upsert, resolve, ranking, reviews
│   ├── scraper/
│   │   ├── gsmarena_scraper.py # network + discovery
│   │   └── parser.py           # HTML -> structured data
│   ├── rag/
│   │   ├── embeddings.py       # sentence-transformers + hash fallback
│   │   ├── retriever.py        # chunking + semantic search
│   │   ├── llm.py              # pluggable LLM providers
│   │   ├── comparison.py       # side-by-side comparison
│   │   └── chatbot.py          # intent handling + grounding
│   ├── agents/
│   │   ├── specification_agent.py
│   │   ├── review_agent.py
│   │   └── crew.py             # orchestration
│   └── schemas/schemas.py      # Pydantic models
├── scripts/
│   ├── init_db.py              # create tables
│   ├── scrape_data.py          # scrape + store + export
│   └── seed_data.py            # load shipped dataset
├── data/
│   └── samsung_phones.json     # shipped dataset (15 phones)
├── tests/                      # pytest suite
├── docs/architecture.md
├── requirements.txt
├── .env.example
└── README.md
```

## 7. Data Scraping

The scraper (`app/scraper/gsmarena_scraper.py`) discovers phones from the
Samsung brand listing and scrapes each detail page. It captures ~45–50 spec
fields per phone across 14 GSMArena categories (Network, Launch, Body, Display,
Platform, Memory, Main Camera, Selfie camera, Sound, Comms, Features, Battery,
Misc, Our Tests), including price.

The parser (`app/scraper/parser.py`) also extracts numeric fields for sorting:
battery mAh, display inches, main camera MP, RAM GB, weight grams and USD price.

Robustness: 3 retries with backoff, per-page `try/except`, missing-field
handling ("Not available" / `None`), duplicate prevention via unique slug, and
logging throughout.

## 8. Database Design

Three tables (PostgreSQL, SQLAlchemy ORM):

- **phones** — one row per phone; unique `name` and `slug`; raw text columns
  (`announced`, `released`, `price`, `chipset`, `os`) plus denormalized numeric
  columns (`battery_capacity_mah`, `display_size_inches`, `main_camera_mp`,
  `ram_gb`, `weight_g`, `price_usd`) to power ranking queries.
- **specifications** — full spec sheet; unique on `(phone_id, category, key)`;
  indexed by `phone_id` and `category`; FK → phones with cascade delete.
- **reviews** — generated reviews; FK → phones; indexed by `phone_id`.

## 9. RAG Workflow

1. Each phone is turned into document chunks (an overview chunk + one chunk per
   spec category), each carrying provenance metadata (`phone_id`, `phone_name`).
2. Chunks are embedded (sentence-transformers `all-MiniLM-L6-v2`, with a
   hashing fallback) and stored in an in-memory vector index.
3. On query, the top-k chunks are retrieved by cosine similarity (optionally
   filtered to a specific phone).
4. The chatbot deterministically includes the spec categories the user asked
   about (camera → Main Camera, etc.), then composes an answer strictly from the
   retrieved facts.

## 10. Chatbot Workflow

```
User Query → intent detection → (ranking | comparison | spec | open)
            → resolve phone(s) from DB → retrieve chunks → grounded answer
```

- **Ranking** ("best battery", "largest display") → exact ordered DB query.
- **Comparison** → side-by-side table from both phones' data.
- **Spec** → category-targeted retrieval for a single resolved phone.
- **Open** → broad retrieval across all phones.

The fallback generator never invents facts; when an LLM is configured it is
prompted to answer only from the provided facts.

## 11. Multi-Agent Workflow

```
User Query → SpecificationAgent (resolve phone, read DB, structured report)
           → ReviewAgent (display/cameras/performance/battery/design/price,
                          strengths/weaknesses, overall assessment)
           → review persisted to the reviews table
```

The agents communicate through a typed `SpecificationReport` contract. When an
LLM is configured the ReviewAgent uses it to polish prose; otherwise it
assembles a fully grounded review from the specs.

## 12. API Documentation

Interactive Swagger UI: **`http://localhost:8000/docs`**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Web UI (chat + review + phone browser) |
| GET | `/health` | Liveness + DB check |
| GET | `/phones` | List all phones (summary) |
| GET | `/phones/{phone_name}` | Full spec sheet for one phone (fuzzy name) |
| POST | `/query` | Free-text question |
| POST | `/chat` | RAG chat (returns intent + sources) |
| POST | `/review` | Multi-agent review generation |

## 13. Installation

```bash
# 1. clone
git clone https://github.com/meherabmehu/samsung-phone-query-review-system.git
cd samsung-phone-query-review-system

# 2. create virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. install dependencies
pip install -r requirements.txt
```

## 14. Environment Setup

```bash
cp .env.example .env
# edit .env and fill in real values (see .env.example for explanations)
```

The project runs with **zero external API keys** (grounded fallback). To use a
real LLM, set `LLM_PROVIDER` plus the matching key/URL.

## 15. PostgreSQL Setup

```bash
# Ubuntu / Debian
sudo apt-get install postgresql
sudo service postgresql start

sudo -u postgres psql -c "CREATE ROLE app LOGIN PASSWORD 'app_pass';"
sudo -u postgres createdb -O app samsung_phones
```

Then set `DATABASE_URL` in `.env`:
```
DATABASE_URL=postgresql+psycopg2://app:app_pass@localhost:5432/samsung_phones
```

> No PostgreSQL? Set `DATABASE_URL=sqlite:///./data/samsung_phones.db` — the
> app works identically on SQLite.

## 16. Database Initialization

```bash
python -m scripts.init_db
```

## 17. Scraping Instructions

```bash
# scrape the curated default set of 15 phones (and store + export JSON)
python -m scripts.scrape_data

# or load the shipped dataset without scraping
python -m scripts.seed_data
```

The dataset is exported to `data/samsung_phones.json`. To regenerate it, re-run
`python -m scripts.scrape_data`.

## 18. Running the Chatbot

```bash
python - <<'PY'
from app.database.connection import get_session
from app.rag.chatbot import Chatbot
bot = Chatbot(get_session)
print(bot.answer("What are the camera specs of the Samsung Galaxy S23?").answer)
PY
```

## 19. Running FastAPI

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# open http://localhost:8000/docs
```

The app also ships with a **web UI** at `http://localhost:8000/` — a premium
chat interface where you can browse the scraped phones, ask questions, generate
comparisons and run multi-agent reviews, all backed by the same API. Swagger
(`/docs`) remains available for the raw API.

## 20. Running Tests

```bash
python -m pytest tests/ -q
```

## 21. Sample Queries

```
What are the camera specs of the Samsung Galaxy S23?
Which Samsung phone has the best battery life?
How does the Galaxy S23 compare to the S22 in terms of performance?
What is the screen size of the Galaxy S22?
Compare Galaxy S23 and Galaxy S24.
Which phone has the highest battery capacity?
Which phone has the largest display?
Compare the cameras of Galaxy S22 and S23.
Give me a detailed review of Galaxy S23.
What processor does the Galaxy S24 use?
Which Samsung phone has the best camera among the scraped devices?
```

## 22. Example API Requests

```bash
curl http://localhost:8000/phones
curl "http://localhost:8000/phones/Galaxy%20S23"

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Compare Galaxy S23 and Galaxy S24"}'

curl -X POST http://localhost:8000/review \
  -H "Content-Type: application/json" \
  -d '{"phone_name":"Galaxy S23"}'
```

## 23. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `OperationalError: connection refused` | Start PostgreSQL and check `DATABASE_URL`. |
| `No module named '...'` | Activate venv and `pip install -r requirements.txt`. |
| Embedding model download fails | It falls back to the hash embedder automatically. |
| LLM returns nothing | Ensure `LLM_PROVIDER` matches a configured key/URL. |
| Scraper returns 0 phones | Check internet access; GSMArena may rate-limit — increase `SCRAPE_DELAY`. |

## 24. Limitations

- The shipped dataset is a snapshot; scrape again for the latest data.
- Some phones have no USD price on GSMArena (raw price text is preserved, the
  numeric column is `NULL`).
- The offline fallback generator produces grounded but plain (non-prose)
  answers; a configured LLM produces fluent prose.
- Retrieval is in-memory and rebuilt per process (fine for this dataset size).

## 25. Future Improvements

- Persistent vector store (ChromaDB/FAISS) with incremental indexing.
- Scheduled re-scraping to keep prices fresh.
- Streaming chat responses and multi-turn conversation memory.
- Docker Compose for one-command PostgreSQL + API startup.
- More phones and additional retailers for richer price data.
