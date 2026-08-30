# Architecture

This document describes the architecture of the Samsung Phone Query and Review
System in enough detail for a reviewer or new contributor to understand how the
layers fit together.

## High-level flow

```
                ┌─────────────────────────────────────────────────┐
                │                    GSMArena                      │
                └───────────────────────┬─────────────────────────┘
                                        │ requests + BeautifulSoup
                                        ▼
                    ┌───────────────────────────────────────┐
                    │   Scraper (app/scraper)               │
                    │   gsmarena_scraper.py / parser.py     │
                    └───────────────────┬───────────────────┘
                                        │ structured dicts
                                        ▼
                    ┌───────────────────────────────────────┐
                    │   Database (app/database)             │
                    │   PostgreSQL via SQLAlchemy           │
                    │   phones / specifications / reviews   │
                    └───────┬───────────────────┬───────────┘
                            │                   │
              ┌─────────────▼───────┐   ┌───────▼─────────────────┐
              │  RAG (app/rag)      │   │  Agents (app/agents)    │
              │  chunks → embeddings│   │  spec → review workflow │
              │  → retriever        │   │                         │
              │  → chatbot + LLM    │   │                         │
              └─────────┬───────────┘   └───────┬─────────────────┘
                        │                       │
                        └───────────┬───────────┘
                                    ▼
                        ┌────────────────────────┐
                        │   FastAPI (app/main)   │
                        │   routes (app/api)     │
                        └────────────────────────┘
```

## Layers

### 1. Scraper (`app/scraper/`)

- `gsmarena_scraper.py` — network I/O: brand-listing discovery, per-phone
  fetching, retries with exponential backoff, politeness delay, per-phone error
  isolation.
- `parser.py` — pure functions turning HTML into structured dicts; also
  numeric extractors (mAh, inches, MP, GB, grams, USD). Pure so it is testable
  offline.

### 2. Database (`app/database/`)

- `connection.py` — engine/session factory, `init_db`/`reset_db`. PostgreSQL
  primary, SQLite supported for tests/dev.
- `models.py` — `Phone`, `Specification`, `Review`. Denormalized numeric
  columns on `Phone` enable ranking queries without parsing text at runtime.
- `crud.py` — upsert (idempotent, duplicate-safe by slug), `resolve_phone`
  (fuzzy name → record), ranking queries, review persistence.

### 3. RAG (`app/rag/`)

- `embeddings.py` — `SentenceTransformerEmbedder` (default) and a dependency-free
  `HashEmbedder` fallback behind a common interface.
- `retriever.py` — turns phones into chunks (overview + per-category) with
  provenance metadata; cosine-similarity search with optional phone filtering.
- `llm.py` — pluggable LLM providers (fallback / Hugging Face / OpenAI /
  Ollama) behind a `complete(prompt)` interface.
- `comparison.py` — structured side-by-side comparison tables.
- `chatbot.py` — intent detection (ranking / comparison / specification /
  open), grounding, and answer composition.

### 4. Agents (`app/agents/`)

- `specification_agent.py` — resolves the phone and produces a typed
  `SpecificationReport`.
- `review_agent.py` — consumes the report and writes the review.
- `crew.py` — orchestrates the two and persists the result.

### 5. API (`app/api/`, `app/main.py`, `app/schemas/`)

- `routes.py` — endpoint handlers; `schemas.py` — Pydantic request/response
  models; `main.py` — app factory, lifespan logging, global exception handler.

## Key design decisions

- **Denormalized numeric columns** — ranking questions ("best battery") are
  answered with exact `ORDER BY` queries rather than fuzzy retrieval.
- **Tolerant phone resolution** — `resolve_phone` maps short aliases ("s23",
  "z flip5") to the right record, preferring exact matches and fewest extra
  tokens (so "s23" picks the base model over Ultra/FE).
- **Category-targeted retrieval** — for spec questions, the chatbot
  deterministically includes the relevant spec category so answers stay
  grounded regardless of embedding quality.
- **Offline-first LLM** — the system is fully functional without any API key;
  LLMs are an optional enhancement, never a hard dependency.
- **Testability** — the parser and retrieval layers are pure/fast; the test
  suite runs against SQLite with a hash embedder for speed.

## Data model

```
phones 1 ──── * specifications
phones 1 ──── * reviews
```

- `phones.slug` and `phones.name` are unique.
- `specifications` unique on `(phone_id, category, key)`.
- Foreign keys cascade on delete.
