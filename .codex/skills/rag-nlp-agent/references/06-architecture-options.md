# Architecture Options & Extension Guides

How to extend pa_exp_agent and which architectural tier to target.

---

## Architecture Tiers — Full Comparison

| Tier | Stack | Key Benefit | New Deps | Effort | Recommended For |
|---|---|---|---|---|---|
| **A1** (current) | Regex + TF-IDF + NetworkX + SQLite | Fully offline, zero setup, zero config | none | — | Baseline, always works |
| **A2** (BM25) | A1 + `rank_bm25` | Better keyword precision, term saturation | `rank_bm25` | 3 hrs | Higher precision on exact names |
| **A3** (LCEL) | A1 + `langchain-core` | Composable pipeline, parallel retrieval | `langchain-core` | 4 hrs | Better testability + streaming |
| **A4** (LangGraph) | A1 + `langgraph` | Stateful multi-turn, human-in-loop, persistence | `langgraph` | 8 hrs | Production multi-turn chat |
| **A5** (optimal) | A2 + A3 + A4 | Best relevance + full agent capabilities | all above | 15 hrs | Full production deployment |

**Quick decision guide**:
- Starting fresh or need reliability → **A1**
- Precision complaints on exact package names → **A2**
- Need parallel retrieval or streaming → **A3**
- Multi-turn conversations that must persist → **A4**
- Full production system → **A5**

---

## How to Add a New Intent Type (5 Steps)

**Example**: Adding `SECURITY_AUDIT` intent to find packages with known vulnerability patterns.

### Step 1 — Add regex patterns to `_PATTERNS`

File: `src/retrieval/intent_classifier.py`

```python
# Add BEFORE generic patterns that could overlap (e.g., before AGGREGATE)
_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    ...
    # ── SECURITY AUDIT — find vulnerable/outdated packages ────────────────
    (re.compile(r"\b(?:vulnerab|cve|security|exploit|attack)\b", re.I), "SECURITY_AUDIT", 0.95),
    (re.compile(r"\boutdated\b.{0,20}\bpackage\b", re.I),               "SECURITY_AUDIT", 0.90),
    ...
]
```

**Rules for placement**:
- After `CYCLE_DETECT` / `TOPO_SORT` (those are always specific enough)
- Before `AGGREGATE` (which could catch "dangerous packages")
- Test ordering: run `test_intent_classifier.py` after adding

### Step 2 — Add to Intent type documentation (optional Literal type)

File: `src/models.py`

```python
# If using Literal type validation for intent.type:
from typing import Literal
IntentType = Literal[
    "PATH_QUERY", "TOPO_SORT", "CYCLE_DETECT",
    "REPO_IMPACT", "REPO_INFO", "IMPACT_ANALYSIS",
    "TRANSITIVE_FWD", "TRANSITIVE_REV", "FORWARD_LOOKUP",
    "NTH_ORDER_LOOKUP", "REVERSE_LOOKUP_FILTERED", "REVERSE_LOOKUP",
    "COMPARE_PACKAGES", "AGGREGATE", "SEMANTIC_SEARCH",
    "SECURITY_AUDIT",    # ← add here
]
```

### Step 3 — Add handler in HybridRetriever

File: `src/retrieval/hybrid_retriever.py`

```python
def _handle_security_audit(self, intent: Intent) -> QueryResult:
    """Find packages with risk indicators matching security concerns."""
    # Query SQLite for high-risk packages with specific attributes
    packages = self._det.get_packages_by_criteria(
        risk_categories=["CRITICAL", "HIGH"],
        in_cycle=True,          # cycle = higher security risk
        min_rev_dep_count=50,   # widely used = higher impact if compromised
    )
    return QueryResult(
        intent=intent,
        packages=packages,
        message=f"Found {len(packages)} packages with security risk indicators",
    )

# Add to routing dispatch dict in retrieve():
_HANDLERS = {
    ...
    "SECURITY_AUDIT": self._handle_security_audit,
}
```

### Step 4 — Register in dispatch table

File: `src/retrieval/hybrid_retriever.py::retrieve()`

```python
def retrieve(self, intent: Intent) -> QueryResult:
    handlers = {
        "PATH_QUERY":               self._handle_path_query,
        # ... all existing handlers ...
        "SECURITY_AUDIT":           self._handle_security_audit,   # ← add
    }
    handler = handlers.get(intent.type, self._handle_semantic_search)
    return handler(intent)
```

### Step 5 — Write tests

File: `tests/test_intent_classifier.py`

```python
@pytest.mark.parametrize("query,expected", [
    ("find vulnerable packages", "SECURITY_AUDIT"),
    ("packages with CVE risk",   "SECURITY_AUDIT"),
    ("show outdated packages",   "SECURITY_AUDIT"),
    ("riskiest packages",        "AGGREGATE"),    # should NOT match SECURITY_AUDIT
])
def test_security_audit_intent(query, expected, known_packages):
    intent = classify(query, known_packages, set(), set())
    assert intent.type == expected
```

---

## How to Add a New Retriever

**Example**: Adding a `FilePathRetriever` that searches packages by their source file paths.

### Interface contract (must implement)

```python
# Pattern: follow the same interface as existing retrievers
class FilePathRetriever:
    """Search packages by ClearCase or Git file path."""

    def __init__(self, db_path: Path) -> None:
        self._conn: sqlite3.Connection | None = None
        self._db_path = db_path

    def _ensure_connected(self) -> None:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)

    def find_by_path(self, path_fragment: str) -> List[dict]:
        """Return packages whose file mappings match path_fragment."""
        self._ensure_connected()
        cursor = self._conn.execute(
            "SELECT DISTINCT p.* FROM packages p "
            "JOIN file_mappings fm ON p.name = fm.package_name "
            "WHERE fm.cc_path LIKE ? OR fm.git_path LIKE ?",
            (f"%{path_fragment}%", f"%{path_fragment}%"),
        )
        return [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
```

### Wire into HybridRetriever

```python
# src/retrieval/hybrid_retriever.py
class HybridRetriever:
    def __init__(self, det, graph, sem, file_path=None):
        ...
        self._file_path = file_path  # optional

# src/rag.py — pass to HybridRetriever constructor
self._hybrid = HybridRetriever(
    det=self._det,
    graph=self._graph,
    sem=self._sem,
    file_path=FilePathRetriever(cfg.db_path),
)
```

---

## How to Extend the Ingest Pipeline (4-Step Pattern)

**Example**: Adding a `VulnerabilityEnricher` that flags packages with known CVE patterns.

### Step 1 — Create enricher module

File: `src/ingest/vuln_enricher.py`

```python
# Pattern: pure function, takes List[Package], returns modified List[Package]
# No I/O, no database calls — all data comes from graph or package list
def enrich_vulnerability_flags(packages: List[Package]) -> List[Package]:
    """Flag packages matching known vulnerability name patterns."""
    VULNERABLE_PATTERNS = re.compile(r"\bssl|openssl|libcurl|zlib\b", re.I)
    result = []
    for pkg in packages:
        # Attach extra flag (if using Package with extra fields) or log it
        if VULNERABLE_PATTERNS.search(pkg.name):
            # Boost risk score or set a flag
            pkg = pkg.model_copy(update={"risk_score": min(pkg.risk_score + 10, 100.0)})
        result.append(pkg)
    return result
```

### Step 2 — Add to ingest_runner.py

File: `src/ingest/ingest_runner.py`

```python
from src.ingest.vuln_enricher import enrich_vulnerability_flags

def run_ingest(cfg: Config) -> dict:
    ...
    packages = enrich_packages(raw_pkgs, G, ...)     # existing enricher
    packages = enrich_vulnerability_flags(packages)   # ← new step
    communities = detect_communities(packages, G)
    ...
```

### Step 3 — Update db_builder.py if new fields needed

File: `src/ingest/db_builder.py`

Add new column to `packages` table schema and `INSERT` statement if your enricher adds new fields.

### Step 4 — Update Package model if needed

File: `src/models.py`

```python
class Package(BaseModel):
    ...
    has_known_cve: bool = False    # ← add new optional field
```

---

## BM25 Upgrade Guide (A2)

### Installation
```bash
pip install rank_bm25    # pure Python, no build deps
# Add to requirements.txt:
rank_bm25>=0.2.2
```

### Build BM25 index during ingest

File: `src/ingest/embedder.py` — add alongside existing TF-IDF build:

```python
from rank_bm25 import BM25Okapi
import pickle

def build_bm25_index(bm25_path: Path, packages: List[Package]) -> None:
    """Build BM25 index from package chunks. Runs in < 1s for ~1000 packages."""
    tokenized_docs = [_make_chunk(p).lower().split() for p in packages]
    pkg_meta = [{"name": p.name, "component": p.component,
                 "risk_score": p.risk_score, "risk_category": p.risk_category.value,
                 "rev_dep_count": p.rev_dep_count} for p in packages]
    bm25 = BM25Okapi(tokenized_docs)
    with open(bm25_path, "wb") as f:
        pickle.dump({"bm25": bm25, "meta": pkg_meta}, f)  # internal file only
```

### Add BM25 search to SemanticRetriever

File: `src/retrieval/semantic_retriever.py` — add method:

```python
def bm25_search(self, query: str, k: int = 10) -> List[Dict]:
    """BM25 keyword search — complements TF-IDF cosine similarity."""
    if not hasattr(self, "_bm25") or self._bm25 is None:
        return []
    tokenized_query = query.lower().split()
    scores = self._bm25.get_scores(tokenized_query)
    top_indices = scores.argsort()[-k:][::-1]
    return [self._bm25_meta[i] for i in top_indices if scores[i] > 0]
```

### Wire RRF fusion in HybridRetriever

File: `src/retrieval/hybrid_retriever.py`:

```python
def _semantic_search_with_rrf(self, intent: Intent) -> QueryResult:
    query = intent.raw_query
    k = 60  # RRF constant

    tfidf_names = [r["name"] for r in self._sem.search(query, k=20)]
    bm25_names  = [r["name"] for r in self._sem.bm25_search(query, k=20)]
    sql_names   = [p["name"] for p in self._det.search_packages_like(query, limit=20)]

    # RRF fusion
    scores: dict[str, float] = {}
    for ranked_list in [tfidf_names, bm25_names, sql_names]:
        for rank, name in enumerate(ranked_list):
            scores[name] = scores.get(name, 0.0) + 1.0 / (k + rank + 1)

    fused = sorted(scores, key=scores.get, reverse=True)[:10]
    packages = [self._det.get_package(n) for n in fused if self._det.get_package(n)]
    return QueryResult(intent=intent, packages=packages)
```

---

## How to Tune Risk Score Thresholds

File: `config.yaml` — adjust `risk_thresholds` and `risk_weights`:

```yaml
# More aggressive — surface more CRITICAL packages
risk_thresholds:
  CRITICAL: 20.0    # was 25.0
  HIGH:     10.0    # was 15.0

# Down-weight forward deps, up-weight reverse deps
risk_weights:
  w_rev: 4.0        # was 3.0 — packages with many dependents are more critical
  w_fwd: 0.5        # was 1.0 — having many deps is less of a risk indicator
  cycle_bonus: 25.0 # was 20.0 — cycles are more dangerous in this codebase
```

After changing thresholds or weights: **must re-run ingest** (`run_ingest.bat`) to recompute all risk scores. The `RAGEngine` singleton must also be cleared (`get_engine.cache_clear()`).
