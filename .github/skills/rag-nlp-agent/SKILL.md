---
name: rag-nlp-agent
argument-hint: 'Topic (e.g. "add intent type", "BFS impact analysis", "LangGraph setup", "BM25 upgrade", "risk formula")'
description: |
  Expert general-purpose NLP, RAG, and agentic AI reference — works for ANY chatbot or
  RAG domain. Also deep reference for the pa_exp_agent Experion dependency intelligence
  codebase. Use when: designing NLU for any chatbot, building intent classifiers, slot
  filling, entity extraction, dialogue state tracking, multi-turn context management,
  building or extending a RAG system for any domain, improving NLP without LLM,
  wrapping retrievers in LangChain LCEL, building a LangGraph state machine agent,
  understanding dependency impact analysis, adding new intent types to any classifier,
  tuning TF-IDF or BM25 retrieval for any domain, designing fully offline NLP pipelines,
  integrating FastAPI with RAG engine, writing pytest for NLU components, understanding
  GraphRAG vs vector RAG vs deterministic RAG, implementing hybrid search without
  embedding models, slot filling state machine, dialogue context tracking, universal
  domain entity resolver with rapidfuzz, negation detection, RRF score fusion,
  task-oriented dialogue TOD architecture, e-commerce chatbot NLP, IT helpdesk bot,
  HR assistant, customer support bot intents, auditing pa_exp_agent architecture,
  extending the ingest pipeline, understanding the risk scoring formula and weights,
  designing deterministic agentic workflows without LLM, replacing Streamlit session state
  with LangGraph memory checkpointing, comparing existing dependency analysis tools, building
  BFS multi-hop queries, implementing community detection, handling circular dependency cycles,
  understanding topological sort for build ordering, resolving ClearCase to Git file mappings,
  transitive closure caching, hybrid TF-IDF BM25 RRF fusion retrieval, EnsembleRetriever,
  BaseRetriever subclass, LCEL chain composition, RunnableLambda, RunnableParallel,
  LangGraph StateGraph, MemorySaver, interrupt human-in-the-loop, scan merger, copy map parser,
  community detector Louvain, enricher risk score, db_builder SQLite, embedder TF-IDF index.
  Trigger on: "how does X work", "add new intent", "improve retrieval", "slot filling",
  "entity extraction", "dialogue state", "context tracking", "multi-turn chatbot",
  "NLP without LLM", "LangChain wrapper", "LangGraph agent loop", "BFS impact analysis",
  "TF-IDF vs BM25", "hybrid retrieval", "graph RAG", "intent classifier", "risk score",
  "ingest pipeline", "offline NLP", "agentic workflow", "RAG architecture", "chatbot NLU",
  "dependency graph", "package impact", "transitive dependencies", "community detection",
  "cycle detection", "topological sort", "nth order dependents", "CRITICAL packages",
  "foundation packages", "risk scoring", "scan diff", "copy map", "clarification bot".
---

# RAG · NLP · Agentic AI Skill

General-purpose expert reference for NLP, RAG, and agentic AI — works for **any chatbot or RAG domain**.
Also the deep reference for the pa_exp_agent Experion dependency intelligence system.
Every section answers one specific question. Use the Quick Reference table to jump directly to what you need.

---

## Quick Reference — Find Your Answer Fast

| Query | Reference File | Section |
|---|---|---|
| Architecture layers, module map, data flow | [01-codebase-map.md](./references/01-codebase-map.md) | All |
| What does file X do? | [01-codebase-map.md](./references/01-codebase-map.md) | Module Inventory |
| Risk scoring formula | [01-codebase-map.md](./references/01-codebase-map.md) | Risk Formula |
| Pydantic models (`Intent`, `QueryResult`, …) | [01-codebase-map.md](./references/01-codebase-map.md) | Model Glossary |
| Config knobs (`config.yaml`) | [01-codebase-map.md](./references/01-codebase-map.md) | Config Reference |
| Universal NLU architecture (any domain) | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Universal NLU Architecture |
| How to design an intent taxonomy | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Designing Your Intent Taxonomy |
| How intent classification works | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Layer 1: Intent Classification |
| Intent examples for e-commerce / IT / HR | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Domain Examples — Intent Tables |
| How to design slots and entity filling | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Layer 2: Slot / Entity Filling |
| Slot filling state machine | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Slot Filling State Machine |
| Domain entity resolver (fuzzy + exact) | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | DomainEntityResolver |
| Dialogue state tracking, multi-turn context | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Layer 3: Dialogue State Tracking |
| Context-aware entity resolution ("it", "that") | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Context-Aware Entity Resolution |
| All pa_exp_agent intent types | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | [pa_exp_agent] Intent Pattern Table |
| How TF-IDF semantic search works (any domain) | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Semantic / Fallback Search |
| TF-IDF vs BM25 — which to use? | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | TF-IDF vs BM25 |
| How to improve NLP (all tiers) | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | NLP Improvement Tiers |
| Multi-turn conversation example | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Multi-Turn Example |
| Negation detection ("not", "without", "exclude") | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Negation Detection |
| NLP anti-patterns and fixes | [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) | Anti-Patterns |
| Which retriever handles which intent? | [03-rag-architecture.md](./references/03-rag-architecture.md) | Retrieval Routing Table |
| How GraphRAG works without a vector DB | [03-rag-architecture.md](./references/03-rag-architecture.md) | GraphRAG Pattern |
| How multi-hop BFS replaces LLM reasoning | [03-rag-architecture.md](./references/03-rag-architecture.md) | Multi-Hop BFS |
| RAG paradigm (Naive/Advanced/Modular) | [03-rag-architecture.md](./references/03-rag-architecture.md) | RAG Paradigms |
| How to evaluate RAG offline | [03-rag-architecture.md](./references/03-rag-architecture.md) | RAG Evaluation |
| Current agent loop diagram | [04-agentic-patterns.md](./references/04-agentic-patterns.md) | Agent Loop |
| LangGraph state machine design | [04-agentic-patterns.md](./references/04-agentic-patterns.md) | LangGraph Design |
| Multi-turn session memory | [04-agentic-patterns.md](./references/04-agentic-patterns.md) | Session Memory |
| Compound query decomposition | [04-agentic-patterns.md](./references/04-agentic-patterns.md) | Multi-Intent |
| Confidence-gated fallback | [04-agentic-patterns.md](./references/04-agentic-patterns.md) | Confidence Gate |
| Wrap a retriever as LangChain BaseRetriever | [05-langchain-integration.md](./references/05-langchain-integration.md) | BaseRetriever |
| LCEL chain composition | [05-langchain-integration.md](./references/05-langchain-integration.md) | LCEL Chains |
| EnsembleRetriever + RRF fusion | [05-langchain-integration.md](./references/05-langchain-integration.md) | EnsembleRetriever |
| LangGraph StateGraph + MemorySaver | [05-langchain-integration.md](./references/05-langchain-integration.md) | LangGraph |
| Human-in-the-loop with interrupt() | [05-langchain-integration.md](./references/05-langchain-integration.md) | Human-in-the-Loop |
| Does any of this need an LLM? | [05-langchain-integration.md](./references/05-langchain-integration.md) | LLM Requirement |
| Architecture tiers A1–A5 comparison | [06-architecture-options.md](./references/06-architecture-options.md) | Architecture Tiers |
| Add a new Intent type (5 steps) | [06-architecture-options.md](./references/06-architecture-options.md) | Add Intent Type |
| Add a new Retriever | [06-architecture-options.md](./references/06-architecture-options.md) | Add Retriever |
| Extend the Ingest Pipeline | [06-architecture-options.md](./references/06-architecture-options.md) | Extend Ingest |
| Upgrade from TF-IDF to BM25 | [06-architecture-options.md](./references/06-architecture-options.md) | BM25 Upgrade |
| Design patterns in use | [07-python-production.md](./references/07-python-production.md) | Design Patterns |
| NetworkX performance optimization | [07-python-production.md](./references/07-python-production.md) | NetworkX Performance |
| SQLite production setup | [07-python-production.md](./references/07-python-production.md) | SQLite Production |
| FastAPI + RAGEngine integration | [07-python-production.md](./references/07-python-production.md) | FastAPI Patterns |
| Testing patterns for this system | [07-python-production.md](./references/07-python-production.md) | Testing |
| Security checklist | [07-python-production.md](./references/07-python-production.md) | Security |
| pa_exp_agent vs SciTools / GraphRAG | [08-existing-systems.md](./references/08-existing-systems.md) | Comparison Table |
| Common mistakes and anti-patterns | [08-existing-systems.md](./references/08-existing-systems.md) | Anti-Patterns |

---

## pa_exp_agent at a Glance

### What is the overall system architecture?

9-layer stack — entry points at the top, immutable data stores at the bottom:

```
Layer 0  Entry Points        run_ingest.py · run_fetch_github.py · run_api.bat · run_web.bat
Layer 1  Interfaces          api/main.py (FastAPI) · ui/app.py (Streamlit) · ui/cli.py (Rich)
Layer 2  RAG Engine          src/rag.py — RAGEngine singleton, .answer(query)
Layer 3  Retrieval           src/retrieval/ — HybridRetriever → Det + Graph + Semantic
Layer 4  Ingest Pipeline     src/ingest/ — parser → graph_builder → enricher → db_builder → embedder
Layer 5  GitHub Fetcher      src/github/ — copy_map_fetcher → client
Layer 6  Foundation          src/config.py · src/models.py · src/llm.py
Layer 7  Formatting          src/formatting/renderer.py — Rich Panel/Table/Tree
Layer 8  Validation          src/validation/store_validator.py
Layer 9  Data Stores         db/experion.db · db/graph.graphml · db/tfidf.json
```

**Key principle**: deterministic-first (no LLM required). LLM is optional augmentation via `use_llm: true` in `config.yaml`.

**Files**: [DEPENDENCY_IMPACT_ANALYSIS.md](../../DEPENDENCY_IMPACT_ANALYSIS.md) — full blast-radius map. [src/rag.py](../../src/rag.py) — engine. → See [01-codebase-map.md](./references/01-codebase-map.md) for the full module inventory.

---

### What is the full query-to-answer data flow?

```
User query (str)
  │
  ▼ src/rag.py — RAGEngine.answer()
  ├─ src/retrieval/intent_classifier.py — classify(query, known_packages, known_components)
  │    ├─ Regex pattern match → Intent.type
  │    ├─ Token matching → Intent.package_name (exact) → rapidfuzz (fuzzy)
  │    └─ Returns: Intent (type, package_name, confidence, negated, depth, risk_filter)
  │
  ▼ src/retrieval/hybrid_retriever.py — HybridRetriever.retrieve(intent)
  ├─ Routes to DeterministicRetriever (SQLite) for SQL-answerable queries
  ├─ Routes to GraphRetriever (NetworkX) for graph traversal
  └─ Routes to SemanticRetriever (TF-IDF) for concept/fuzzy search
  │
  ▼ src/models.py — QueryResult (packages, graph_data, stats, message)
  │
  ▼ src/formatting/renderer.py — render(result) → Rich Panel/Table/Tree
```

**Files**: [src/rag.py](../../src/rag.py), [src/retrieval/hybrid_retriever.py](../../src/retrieval/hybrid_retriever.py)

---

### What is the full ingest-to-stores data flow?

```
data/merged_scan.json
  │
  ▼ src/ingest/parser.py        — JSON → List[RawRepository] (Pydantic validation)
  ▼ src/ingest/graph_builder.py — builds nx.DiGraph (nodes=packages, edges=deps)
  ▼ src/ingest/enricher.py      — computes risk_score, topo_level, in_cycle, is_foundation
  ▼ src/ingest/community_detector.py — Louvain community IDs
  ▼ src/ingest/db_builder.py    — writes db/experion.db (SQLite)
  ▼ src/ingest/embedder.py      — builds TF-IDF index → db/tfidf.json
  ▼ src/ingest/graph_builder.py — saves db/graph.graphml
```

**Files**: [src/ingest/ingest_runner.py](../../src/ingest/ingest_runner.py) — orchestrator calling all steps.

---

## NLP Without LLM — Quick Answers

### How does intent classification work? (any domain)

Ordered regex pattern table — first-match wins, each with a pre-assigned confidence score. Works identically for e-commerce, IT helpdesk, HR bots, or dependency analysis. The same `DomainEntityResolver` class handles fuzzy entity matching for any domain (product names, package names, ticket IDs, employee names).

**Universal pipeline**:
```
query → lowercase → scan _PATTERNS → first match = intent + confidence
      → DomainEntityResolver.resolve() → entity (exact → fuzzy → context fallback)
      → negation detection → structured result
```

**[pa_exp_agent] files**: [src/retrieval/intent_classifier.py](../../src/retrieval/intent_classifier.py) — `_PATTERNS`, `classify()`. → See [02-nlp-intent-pipeline.md — Layer 1](./references/02-nlp-intent-pipeline.md) for universal classifier pattern and domain examples (e-commerce, IT, HR).

---

### How does slot filling work? (any domain)

A **slot** is a required parameter for an intent. When slots are missing, generate a clarification question and wait for the user's answer before routing.

```
intent classified → SlotDefinition[] for that intent
                 → extract slots: regex (dates/IDs) + fuzzy (entities) + dict (enums)
                 → missing required slots? → clarify_node
                 → all slots filled? → route to handler
```

→ See [02-nlp-intent-pipeline.md — Layer 2](./references/02-nlp-intent-pipeline.md) for `DomainEntityResolver`, `SlotFillingState`, and slot tables by domain.

---

### How does multi-turn context work? (any domain)

`DialogueState` tracks `current_entity`, `slots`, `intent_history` across turns. When the user says "it" or "that", resolve to `state.current_entity`. Slots **accumulate** across turns — user can provide them incrementally.

→ See [02-nlp-intent-pipeline.md — Layer 3](./references/02-nlp-intent-pipeline.md) for `DialogueState` schema, `resolve_with_context()`, and the multi-turn example.

---

### What are all the Intent types? ([pa_exp_agent])

| Intent Type | Trigger Example | Primary Retriever |
|---|---|---|
| `PATH_QUERY` | "path from A to B" | GraphRetriever |
| `TOPO_SORT` | "build order for X" | GraphRetriever |
| `CYCLE_DETECT` | "circular dependencies" | GraphRetriever |
| `REPO_IMPACT` | "if I change repo X" | GraphRetriever |
| `REPO_INFO` | "packages in repo X" | DeterministicRetriever |
| `IMPACT_ANALYSIS` | "what breaks if I change X" | GraphRetriever (BFS reversed) |
| `TRANSITIVE_FWD` | "full dependency tree of X" | GraphRetriever `descendants()` |
| `TRANSITIVE_REV` | "everything that depends on X" | GraphRetriever reversed |
| `FORWARD_LOOKUP` | "what does X depend on" | DeterministicRetriever + Graph |
| `NTH_ORDER_LOOKUP` | "2nd order dependents of X" | GraphRetriever (BFS depth N) |
| `REVERSE_LOOKUP_FILTERED` | "critical dependents of X" | GraphRetriever + risk filter |
| `REVERSE_LOOKUP` | "who uses X" | GraphRetriever |
| `COMPARE_PACKAGES` | "X vs Y risk" | DeterministicRetriever |
| `AGGREGATE` | "riskiest packages" | DeterministicRetriever |
| `SEMANTIC_SEARCH` | "error handling packages" | SemanticRetriever |

**Files**: [src/retrieval/intent_classifier.py](../../src/retrieval/intent_classifier.py), [src/retrieval/hybrid_retriever.py](../../src/retrieval/hybrid_retriever.py)

---

### How does TF-IDF semantic search work?

Package metadata is serialized to a keyword-rich text chunk via `_make_chunk()`, indexed with `TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True)`, stored as a COO sparse matrix in `db/tfidf.json`. At query time: vectorize query → cosine similarity against all document vectors → return top-k.

**Files**: [src/ingest/embedder.py](../../src/ingest/embedder.py) — `_make_chunk()`, `build_tfidf_index()`. [src/retrieval/semantic_retriever.py](../../src/retrieval/semantic_retriever.py) — `search()`.

→ See [02-nlp-intent-pipeline.md](./references/02-nlp-intent-pipeline.md) for NLP improvement tiers (BM25, LSI, RRF fusion).

---

## RAG & Graph — Quick Answers

### Which retriever handles which intent?

→ See [03-rag-architecture.md — Retrieval Routing Table](./references/03-rag-architecture.md) for the complete routing table with algorithms and fallbacks.

---

### Is this GraphRAG? How?

Yes — pa_exp_agent is a deterministic GraphRAG system (no LLM required for graph traversal):
- **Knowledge graph** = `db/graph.graphml` (packages as nodes, dependencies as edges, node attributes = risk metadata)
- **Graph traversal** = `GraphRetriever` with BFS/DFS via NetworkX
- **Community summaries** = `Community` objects from `community_detector.py` (Louvain algorithm)
- **Augmentation** = structured `QueryResult` passed to `renderer.py` (or optionally to LLM for narrative)

→ See [03-rag-architecture.md](./references/03-rag-architecture.md) for comparison with Microsoft GraphRAG.

---

## LangChain — Quick Answers

### Does pa_exp_agent need an LLM to use LangChain?

**No.** `langchain-core` and `langgraph` are pure Python orchestration libraries — zero ML dependencies, zero model downloads, zero internet required at runtime. LLM calls remain optional and config-gated.

```
pip install langchain-core   # ~2 MB, pure Python
pip install langgraph        # ~500 KB, pure Python
```

→ See [05-langchain-integration.md](./references/05-langchain-integration.md) for all integration patterns.

---

### What does LangChain add without an LLM?

| LangChain Component | What It Adds | Applied To |
|---|---|---|
| `BaseRetriever` | Standard interface, works with EnsembleRetriever | All three retrievers |
| `RunnableLambda` + LCEL `\|` | Composable, testable pipeline | classify → retrieve → render |
| `RunnableParallel` | Run all retrievers simultaneously | HybridRetriever |
| `EnsembleRetriever` | RRF score fusion with configurable weights | Multi-retriever fusion |
| `LangGraph StateGraph` | Stateful agent loop, persistence, human-in-loop | RAGEngine loop |
| `MemorySaver` | Checkpointed multi-turn memory | Replaces `st.session_state` |

---

## Extending the System — Quick Answers

### How do I add a new Intent type? (5 steps)

1. Add regex pattern to `_PATTERNS` in [src/retrieval/intent_classifier.py](../../src/retrieval/intent_classifier.py)
2. Add intent string to `Intent.type` valid values in [src/models.py](../../src/models.py) (if using Literal type)
3. Add handler method in [src/retrieval/hybrid_retriever.py](../../src/retrieval/hybrid_retriever.py) — `_handle_MY_INTENT(self, intent: Intent) -> QueryResult`
4. Add routing entry in `HybridRetriever.retrieve()` dispatch dict
5. Add test cases in [tests/test_intent_classifier.py](../../tests/test_intent_classifier.py)

→ See [06-architecture-options.md — Add Intent Type](./references/06-architecture-options.md) for the full guide with code templates.

---

### What are the architecture upgrade tiers?

| Tier | Stack | Key Benefit | New Deps |
|---|---|---|---|
| A1 (current) | Regex + TF-IDF + NetworkX + SQLite | Fully offline, zero setup | none |
| A2 | + `rank_bm25` | Better keyword precision than TF-IDF | `rank_bm25` |
| A3 | + `langchain-core` LCEL | Composable, parallel retrieval | `langchain-core` |
| A4 | + `langgraph` | Stateful multi-turn, human-in-loop | `langgraph` |
| A5 (optimal) | A2 + A3 + A4 + EnsembleRetriever | Best relevance + full agent capabilities | all above |

→ See [06-architecture-options.md](./references/06-architecture-options.md) for full trade-off analysis and upgrade guides.

---

## Common Mistakes

### What breaks after re-ingest?

1. **Stale `RAGEngine` singleton** — call `get_engine.cache_clear()` after ingest, or restart the process
2. **Pickle backward-compat** — if graph schema changes, old `graph.graphml` + new code may mismatch; always regenerate both graph and tfidf in one ingest run
3. **TF-IDF cold start** — if `db/tfidf.json` is missing, `SemanticRetriever` silently disables itself; check `_enabled` flag

### What causes entity ambiguity?

Hybrid packages use `node_id = f"{raw_name}::{pkg_manager}"` — a query for `"mypackage"` may not match `"mypackage::conan"`. The `_resolve_package_from_path()` method in `HybridRetriever` handles this via cc_path lookup → git_path → path-component fallback.

→ See [08-existing-systems.md — Anti-Patterns](./references/08-existing-systems.md) for the full list.
