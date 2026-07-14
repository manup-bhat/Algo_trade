# pa_exp_agent Codebase Map

Complete architecture reference for the Experion dependency intelligence system.

---

## 9-Layer Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│ LAYER 0 — Entry Points                                               │
│  run_ingest.py · run_fetch_github.py · run_api.bat · run_web.bat     │
│  run_cli.bat · run_validate.bat · run_nextjs.bat                     │
├──────────────────────────────────────────────────────────────────────┤
│ LAYER 1 — Interfaces                                                 │
│  api/main.py (FastAPI REST)  ·  ui/app.py (Streamlit)                │
│  ui/cli.py (Rich terminal)  ·  web/src/** (Next.js frontend)         │
├──────────────────────────────────────────────────────────────────────┤
│ LAYER 2 — RAG Engine                                                 │
│  src/rag.py — RAGEngine singleton + @lru_cache(maxsize=1)            │
├──────────────────────────────────────────────────────────────────────┤
│ LAYER 3 — Retrieval                                                  │
│  src/retrieval/hybrid_retriever.py   ← intent router                │
│  src/retrieval/deterministic_retriever.py  ← SQLite                 │
│  src/retrieval/graph_retriever.py    ← NetworkX                     │
│  src/retrieval/semantic_retriever.py ← TF-IDF                       │
│  src/retrieval/intent_classifier.py  ← NLP (regex + fuzzy)          │
├──────────────────────────────────────────────────────────────────────┤
│ LAYER 4 — Ingest Pipeline (src/ingest/)                              │
│  ingest_runner.py  →  parser.py  →  graph_builder.py                │
│  enricher.py  →  community_detector.py  →  db_builder.py            │
│  embedder.py  ·  copy_map_parser.py  ·  scan_merger.py              │
├──────────────────────────────────────────────────────────────────────┤
│ LAYER 5 — GitHub Fetcher (src/github/)                               │
│  copy_map_fetcher.py  →  client.py                                   │
├──────────────────────────────────────────────────────────────────────┤
│ LAYER 6 — Foundation                                                 │
│  src/config.py · src/models.py · src/llm.py                         │
├──────────────────────────────────────────────────────────────────────┤
│ LAYER 7 — Formatting     │ LAYER 8 — Validation                     │
│  src/formatting/renderer.py │  src/validation/store_validator.py    │
├──────────────────────────────────────────────────────────────────────┤
│ LAYER 9 — Data Stores (runtime artefacts, not committed)             │
│  db/experion.db (SQLite)  ·  db/graph.graphml  ·  db/tfidf.json     │
│  db/graph.pkl (optional binary cache)                                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Module Inventory

### Foundation (Layer 6)

| File | Purpose | Key Symbol | Blast Radius |
|---|---|---|---|
| `src/config.py` | YAML config loader, paths | `Config`, `get_config()`, `RiskThresholds`, `RiskWeights` | HIGH — everything imports it |
| `src/models.py` | All Pydantic data models | `Intent`, `QueryResult`, `Package`, `Community`, `RawScan` | HIGHEST — 10+ direct importers |
| `src/llm.py` | Azure OpenAI client (optional) | `get_llm_client()`, `ask_llm()` | LOW — only api/main.py + ui/app.py |

### Ingest Layer (Layer 4)

| File | Purpose | Key Symbol | Depends On |
|---|---|---|---|
| `src/ingest/parser.py` | JSON scan → `RawScan` Pydantic validation | `parse_scan()` | `src.models` |
| `src/ingest/graph_builder.py` | Build `nx.DiGraph` + save/load GraphML | `build_graph()`, `load_graph()`, `save_graph()` | `src.models` |
| `src/ingest/enricher.py` | Compute risk scores, topo levels, cycle flags | `enrich_packages()` | `src.config`, `src.models` |
| `src/ingest/community_detector.py` | Louvain community detection | `detect_communities()` | `src.models` |
| `src/ingest/db_builder.py` | Write enriched data to SQLite | `build_db()` | `src.models` |
| `src/ingest/embedder.py` | Build TF-IDF index → tfidf.json | `build_tfidf_index()`, `_make_chunk()` | `src.models` |
| `src/ingest/copy_map_parser.py` | Parse ClearCase copy_map.txt files | `parse_copy_map()` | — |
| `src/ingest/scan_merger.py` | Merge github_scan + experion_full_scan | `merge_scans()` | — |
| `src/ingest/ingest_runner.py` | Orchestrate all ingest steps | `run_ingest()` | all above |

### Retrieval Layer (Layer 3)

| File | Purpose | Key Symbol | Algorithm |
|---|---|---|---|
| `src/retrieval/intent_classifier.py` | NLP → structured `Intent` | `classify()`, `_PATTERNS` | Ordered regex first-match + rapidfuzz |
| `src/retrieval/deterministic_retriever.py` | SQLite-backed exact/filtered queries | `DeterministicRetriever` | SQL SELECT + JOIN |
| `src/retrieval/graph_retriever.py` | NetworkX graph traversal | `GraphRetriever`, `_ensure_cache()` | BFS/DFS, transitive closure |
| `src/retrieval/semantic_retriever.py` | TF-IDF cosine similarity search | `SemanticRetriever`, `search()` | Cosine similarity, scipy sparse |
| `src/retrieval/hybrid_retriever.py` | Route Intent to correct retriever | `HybridRetriever.retrieve()`, `_resolve_package_from_path()` | Intent dispatch table |

### RAG Engine + Interfaces

| File | Purpose | Key Symbol |
|---|---|---|
| `src/rag.py` | Singleton RAG engine | `RAGEngine`, `get_engine()`, `.answer(query)` |
| `src/formatting/renderer.py` | QueryResult → Rich renderables | `render()` |
| `api/main.py` | FastAPI REST endpoints | `/api/v1/query`, `/api/v1/ingest` |
| `ui/app.py` | Streamlit web UI | `main()`, session state management |
| `ui/cli.py` | Rich terminal interface | `cli()` Click command |

### Standalone rag_scan/ Module (Legacy/Research)

| File | Purpose | Notes |
|---|---|---|
| `rag_scan/intent_detector.py` | Simpler intent detector | Different intent set from `src/` — uses IMPACT/DEPENDENCIES/etc. |
| `rag_scan/query_executor.py` | Graph query executor | Handler dispatch pattern (reference) |
| `rag_scan/graph_builder.py` | Graph build + pickle cache | `build_and_save()`, `load_cache()` |
| `rag_scan/visualizer.py` | vis.js HTML graph generation | `render_direct_expandable()` |

---

## Pydantic Model Glossary

```python
# src/models.py — all data models

# ── Raw input models (validated from JSON) ────────────────────────────
class RawScan:         scan_date, base_path, total_repositories, repositories: List[RawRepository]
class RawRepository:   repo_name, root_component, repo_path, packages: List[RawPackage]
class RawPackage:      package_name, package_manager, dependencies: List[str], file_mappings: List[FileMapping]
class FileMapping:     cc_path, git_path, file_type

# ── Enriched package model (after ingest pipeline) ────────────────────
class Package:
    name, component, repo_name, repo_path, package_manager
    fwd_dep_count: int          # how many packages this depends on (out-degree)
    rev_dep_count: int          # how many packages depend on this (in-degree)
    risk_score: float           # 0–100 weighted score
    risk_category: RiskCategory # CRITICAL | HIGH | MEDIUM | LOW
    is_foundation: bool         # True when fwd_dep_count == 0 (no dependencies)
    community_id: Optional[int] # Louvain community
    topo_level: int             # 0 = foundation/leaf; higher = more downstream
    in_cycle: bool              # participates in circular dependency

class RiskCategory(str, Enum): CRITICAL = "CRITICAL" | HIGH | MEDIUM | LOW

# ── Query models ──────────────────────────────────────────────────────
class Intent:
    type: str                   # see intent types in SKILL.md
    package_name: Optional[str] # primary entity
    package_name_b: Optional[str]    # secondary (PATH_QUERY)
    component_name: Optional[str]    # COMPONENT_FILTER
    repo_name_target: Optional[str]  # REPO_IMPACT, REPO_INFO
    aggregate_kind: Optional[str]    # riskiest | foundation | isolated | overview
    raw_query: str
    confidence: float           # 0.0–1.0
    negated: bool               # "what does X NOT depend on"
    extra_packages: List[str]   # multi-package queries
    depth: Optional[int]        # BFS level target (1=direct, 0=full transitive)
    risk_filter: Optional[List[str]]  # ["CRITICAL","HIGH"] for REVERSE_LOOKUP_FILTERED

class QueryResult:
    intent: Intent
    # ... retriever-populated fields (packages, graph_edges, stats, message)

# ── Scan history / diff models ────────────────────────────────────────
class ScanHistory:  scan_id, scan_date, json_hash, total_packages, total_edges, avg_risk
class ScanDiff:     scan_id, change_type, entity_name, old_value, new_value
class Community:    community_id, member_count, avg_risk_score, key_packages, description
```

---

## Config Reference

File: `config.yaml` (root of project). Loaded once via `src/config.py::load_config()`, exposed as `Config` singleton via `get_config()`.

```yaml
json_input: data/merged_scan.json     # scan data source
use_text_search: true                 # enable TF-IDF semantic search (fully offline)
use_llm: false                        # enable Azure OpenAI augmentation (optional)

risk_thresholds:
  CRITICAL: 25.0                      # score >= 25 → CRITICAL
  HIGH:     15.0                      # score >= 15 → HIGH
  MEDIUM:    5.0                      # score >= 5  → MEDIUM
  LOW:       0.0                      # score < 5   → LOW

risk_weights:
  w_rev: 3.0            # weight for reverse-dep count (how many things break)
  w_fwd: 1.0            # weight for forward-dep count (how many things this needs)
  cycle_bonus: 20.0     # bonus score when package participates in a cycle
```

**Generated paths** (auto-set from BASE_DIR):
```
db_path:    db/experion.db
graph_path: db/graph.graphml
tfidf_path: db/tfidf.json
```

**Impact of config changes**:
- `use_text_search` — affects `SemanticRetriever` initialization; requires re-ingest to rebuild index
- Risk thresholds — affects `risk_category` bucketing; requires re-ingest to recompute
- Risk weights — affects `risk_score` formula; requires re-ingest to recompute

---

## Risk Scoring Formula

Source: `src/ingest/enricher.py::enrich_packages()`

$$\text{risk\_score} = \frac{w_{rev} \times \text{rev\_count} + w_{fwd} \times \text{fwd\_count}}{(w_{rev} + w_{fwd}) \times N} \times 100$$

Where:
- `rev_count` = `G.in_degree(node)` — packages that depend on this one
- `fwd_count` = `G.out_degree(node)` — packages this one depends on
- `N` = total number of graph nodes
- `w_rev`, `w_fwd`, `cycle_bonus` = from `config.yaml` → `RiskWeights`

After base score: if `node in cycle_nodes`, add `cycle_bonus` (capped at 100).

Category thresholds from `config.yaml::risk_thresholds`:
- `CRITICAL` ≥ 25.0 | `HIGH` ≥ 15.0 | `MEDIUM` ≥ 5.0 | `LOW` < 5.0

**Example**: A package used by 300 packages (rev=300) with 0 forward deps, in a graph of 968 nodes, weights w_rev=3, w_fwd=1:
```
raw   = 3 * 300 + 1 * 0 = 900
max   = (3 + 1) * 968  = 3872
score = (900 / 3872) * 100 = 23.2  → HIGH (just below CRITICAL threshold of 25)
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| TF-IDF instead of dense embeddings | 100% offline, no model downloads, < 2s build time for ~1000 packages |
| SQLite + GraphML (not a graph DB) | Zero infrastructure, portable files, full NetworkX algorithm access |
| `@lru_cache(maxsize=1)` singleton | All three stores loaded once, reused across requests |
| Transitive cache threshold = 5000 nodes | Pre-compute closures only for manageable graphs; O(n) BFS otherwise |
| `orjson` for JSON parsing | 5–10× faster than stdlib `json` for large scan files |
| Pydantic v2 for all models | Validation at system boundaries only; internal code uses typed dicts |
