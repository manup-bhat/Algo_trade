# RAG Architecture

Deterministic GraphRAG — no LLM required for retrieval. LLM is optional augmentation only.

---

## RAG Paradigms — Which Does pa_exp_agent Use?

Source: arXiv:2312.10997 — "RAG for LLMs: A Survey"

| Paradigm | Description | pa_exp_agent |
|---|---|---|
| **Naive RAG** | query → single retriever → answer | ✗ too simple |
| **Advanced RAG** | query → intent classify → multi-retriever → ranked → structured answer | ✓ **current implementation** |
| **Modular RAG** | pluggable retrievers, routing, evaluation, self-correction loops | ✓ **target with LangChain** |

pa_exp_agent implements **Advanced RAG** with a deterministic knowledge graph as the primary data source — no vector database, no embedding model downloads. The graph IS the knowledge representation.

---

## Is This GraphRAG?

**Yes** — pa_exp_agent implements GraphRAG without LLM, equivalent to Microsoft's GraphRAG pattern (arXiv:2404.16130) but fully deterministic:

| GraphRAG Concept | Microsoft GraphRAG | pa_exp_agent |
|---|---|---|
| Knowledge graph | LLM-extracted entities + relations | Dependency graph from scan JSON |
| Community summaries | LLM-generated text summaries | `Community` objects (Louvain algorithm) |
| Graph traversal | Structured retrieval | NetworkX BFS/DFS/shortest-path |
| Generation | LLM narrative | Rich formatted tables/trees (or LLM if `use_llm=true`) |
| Infrastructure | Azure OpenAI required | Zero external services |
| Latency | 5–30s (LLM calls) | < 100ms (all in-process) |

---

## Retrieval Routing Table — Complete

Source: `src/retrieval/hybrid_retriever.py::retrieve()`

| Intent Type | Primary Retriever | Algorithm | Key NetworkX / SQL Call | Fallback |
|---|---|---|---|---|
| `IMPACT_ANALYSIS` | GraphRetriever | BFS on reversed graph | `nx.descendants(G.reverse(), node)` | DeterministicRetriever |
| `FORWARD_LOOKUP` | DeterministicRetriever | SQL JOIN deps table | `SELECT dep FROM dependencies WHERE pkg=?` | GraphRetriever `G.successors()` |
| `REVERSE_LOOKUP` | GraphRetriever | Reversed graph neighbors | `nx.descendants(G_rev, node)` or `G_rev.neighbors()` | DeterministicRetriever |
| `TRANSITIVE_FWD` | GraphRetriever | Transitive closure forward | `nx.descendants(G, node)` | — |
| `TRANSITIVE_REV` | GraphRetriever | Transitive closure reverse | `nx.descendants(G_rev, node)` | — |
| `NTH_ORDER_LOOKUP` | GraphRetriever | BFS to depth `intent.depth` | BFS level-by-level up to N hops | — |
| `REVERSE_LOOKUP_FILTERED` | GraphRetriever | Reverse + risk filter | `nx.descendants(G_rev)` + risk_category filter | — |
| `PATH_QUERY` | GraphRetriever | Shortest path bidirectional | `nx.shortest_path(G, src, tgt)` | — |
| `CYCLE_DETECT` | GraphRetriever | Simple cycle enumeration | `list(nx.simple_cycles(G))` | — |
| `TOPO_SORT` | GraphRetriever | Topological generations | `list(nx.topological_generations(G))` | — |
| `REPO_IMPACT` | GraphRetriever | BFS per repo package | Union of `impact_analysis()` for all repo packages | — |
| `REPO_INFO` | DeterministicRetriever | Filter packages by repo | `SELECT * FROM packages WHERE repo_name=?` | — |
| `COMPARE_PACKAGES` | DeterministicRetriever | SELECT two packages | JOIN on both package names | GraphRetriever metrics |
| `AGGREGATE` | DeterministicRetriever | ORDER BY metric | `SELECT * FROM packages ORDER BY risk_score DESC LIMIT k` | GraphRetriever centrality |
| `SEMANTIC_SEARCH` | SemanticRetriever | TF-IDF cosine similarity | `cosine_similarity(q_vec, matrix)` | DeterministicRetriever LIKE |

---

## How Multi-Hop BFS Replaces LLM Reasoning

The `NTH_ORDER_LOOKUP` intent implements multi-hop retrieval deterministically:

**Problem** (from arXiv:2401.15391 — MultiHop-RAG): standard RAG fails on queries like "what are the 2nd-order dependents of package X?" because it requires chaining multiple retrieval steps.

**pa_exp_agent solution** — BFS to depth N without any LLM:
```python
# src/retrieval/graph_retriever.py::impact_analysis()
def impact_analysis(self, package_name: str, max_level: int = 5) -> Dict:
    """BFS on reversed graph — finds all packages that depend on this one, level by level."""
    G_rev = self._rev()
    visited = {package_name}
    current_level = {package_name}
    levels = []

    for level in range(1, max_level + 1):
        next_level = set()
        for node in current_level:
            for neighbor in G_rev.neighbors(node):
                if neighbor not in visited:
                    next_level.add(neighbor)
                    visited.add(neighbor)
        if not next_level:
            break
        levels.append({"level": level, "packages": sorted(next_level)})
        current_level = next_level

    return {"levels": levels, "all_affected": visited - {package_name}, "total": len(visited) - 1}
```

For `NTH_ORDER_LOOKUP` with `depth=2`: return only `levels[0]` (direct, 1 hop) and `levels[1]` (2nd order, 2 hops). This is equivalent to what MultiHop-RAG benchmarks try to solve with LLMs.

---

## Transitive Cache — Performance Design

Source: `src/retrieval/graph_retriever.py::_ensure_cache()`

**Pre-computation**: At startup (first query), if `n_nodes <= 5000`, pre-compute for ALL nodes:
- `_all_deps_cache[node]` = `nx.descendants(G, node)` (forward transitive closure)
- `_impact_cache[node]` = `nx.descendants(G_rev, node)` (reverse transitive closure)

**Result**: O(1) lookup for all TRANSITIVE_FWD, TRANSITIVE_REV, IMPACT_ANALYSIS queries after warm-up.

**Large graph fallback**: If `n_nodes > 5000`, skips pre-computation; each query runs BFS on-demand (O(V+E)).

**Memory estimate**: For 1000 nodes × avg 100 descendants per node × 8 bytes/pointer ≈ 800 KB. Acceptable.

---

## GraphML vs Pickle — When to Use Which

| Format | Load Time | Portability | Human-Readable | Use When |
|---|---|---|---|---|
| `graph.graphml` | ~500ms for 1000 nodes | ✓ XML standard | ✓ | Default; use for all production graphs |
| `graph.pkl` | ~50ms | ✗ Python-version tied | ✗ | Dev only; faster iteration; never commit |

**Loading logic** in `src/rag.py::RAGEngine._ensure_loaded()`:
```python
G = load_graph(cfg.graph_path)  # tries .graphml first, .pkl as fallback
```

---

## Ingest Pipeline Deep-Dive

Source: `src/ingest/ingest_runner.py::run_ingest()`

```
Step 1: scan_merger.py::merge_scans()
        Merges data/github_scan.json + data/uploads/experion_full_scan.json
        → data/merged_scan.json

Step 2: parser.py::parse_scan()
        JSON → List[RawRepository] with full Pydantic validation
        Raises on malformed input (fail-fast at boundary)

Step 3: graph_builder.py::build_graph()
        RawRepositories → nx.DiGraph
        Node attrs: raw_name, repo_name, repo_path, root_component, package_type, package_manager
        Edge: (package_a, package_b) means "a depends on b"
        Hybrid packages: node_id = f"{raw_name}::{pkg_manager}"

Step 4: enricher.py::enrich_packages()
        DiGraph → List[Package] with:
        - risk_score (weighted formula)
        - risk_category (threshold bucketing)
        - topo_level (topological generation index)
        - in_cycle (nx.simple_cycles membership)
        - is_foundation (out_degree == 0)

Step 5: community_detector.py::detect_communities()
        Louvain algorithm on undirected projection → List[Community]
        Assigns community_id to each Package

Step 6: db_builder.py::build_db()
        Writes enriched packages + communities to SQLite
        Tables: packages, dependencies, file_mappings, communities, scan_history, scan_diffs

Step 7: embedder.py::build_tfidf_index()
        List[Package] + List[Community] → TF-IDF matrix → db/tfidf.json

Step 8: graph_builder.py::save_graph()
        nx.DiGraph → db/graph.graphml (+ optional db/graph.pkl)
```

---

## RAG Evaluation — Offline (No LLM Judge)

### Intent Classification Accuracy
```python
# tests/test_intent_classifier.py pattern — table-driven tests
@pytest.mark.parametrize("query,expected_type,expected_pkg", [
    ("what breaks if I change ehbase?",   "IMPACT_ANALYSIS",  "ehbase"),
    ("who uses ctrllib?",                 "REVERSE_LOOKUP",   "ctrllib"),
    ("2nd order dependents of ace",       "NTH_ORDER_LOOKUP", "ace"),
    ("show me riskiest packages",         "AGGREGATE",        None),
    ("error handling packages",           "SEMANTIC_SEARCH",  None),
])
def test_classify(query, expected_type, expected_pkg):
    intent = classify(query, KNOWN_PACKAGES, set(), set())
    assert intent.type == expected_type
    if expected_pkg:
        assert intent.package_name == expected_pkg
```

### Retrieval Precision@k
```python
# For IMPACT_ANALYSIS: known ground-truth affected packages from scan
ground_truth = {"pkgB", "pkgC", "pkgD"}
result = hybrid.retrieve(intent)
retrieved = {p.name for p in result.packages[:10]}
precision_at_10 = len(retrieved & ground_truth) / 10
```

### Confidence Score Calibration
- High-confidence intents (≥ 0.95): exact match expected > 90% of time
- Low-confidence intents (< 0.70): should route to SemanticRetriever as fallback
- Monitor: track `intent.confidence` distribution across real user queries

---

## Community Detection

Source: `src/ingest/community_detector.py`

Uses **Louvain algorithm** (`nx.community.louvain_communities()`) on the undirected projection of the dependency graph. Each `Package` gets a `community_id` integer. Communities represent clusters of tightly interdependent packages — useful for:
- Understanding component boundaries
- Identifying packages that should be co-deployed
- Finding cohesive subsystems for targeted refactoring

Community metadata in SQLite `communities` table: `community_id`, `member_count`, `avg_risk_score`, `key_packages` (top-5 by risk), `description`.
