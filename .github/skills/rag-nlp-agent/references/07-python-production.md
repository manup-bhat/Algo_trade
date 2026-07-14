# Production Python Best Practices

Design patterns, performance, testing, and security for pa_exp_agent.

---

## Design Patterns Already in Use

| Pattern | Where Used | Python Idiom |
|---|---|---|
| **Singleton** | `RAGEngine` — one instance per process | `@lru_cache(maxsize=1)` on `get_engine()` |
| **Facade** | `RAGEngine.answer()` hides all complexity | Single public method wrapping 4 layers |
| **Strategy** | Swappable retrievers (`Det`, `Graph`, `Semantic`) | Duck-typed — same `retrieve(intent)` interface |
| **Template Method** | `renderer.py::render()` dispatches per intent type | `match result.intent.type` dispatch |
| **Lazy Initialization** | `_ensure_loaded()` in `RAGEngine` | Check `if self._hybrid is not None: return` |
| **Null Object** | `SemanticRetriever._enabled = False` | Returns empty list silently when disabled |
| **Repository** | `DeterministicRetriever` wraps all SQLite access | All SQL in one class, not scattered |

---

## Design Patterns to Add

| Pattern | Where to Apply | Benefit |
|---|---|---|
| **Chain of Responsibility** | Intent fallback chain | `exact → fuzzy → semantic → "not found"` — no if-else cascade |
| **Observer** | Scan diff events after ingest | `ui/app.py` reloads automatically when new ingest completes |
| **Factory** | `RetrieverFactory.create(config)` | Wire all three retrievers from config without touching `rag.py` |
| **Command** | Wrap each retrieval as a `Command` object | Enables undo, queuing, logging per retrieval |

### Chain of Responsibility — entity fallback
```python
# src/retrieval/entity_resolver.py (new file)
from abc import ABC, abstractmethod

class EntityResolver(ABC):
    def __init__(self, next_resolver: "EntityResolver | None" = None):
        self._next = next_resolver

    def resolve(self, query: str, known: set) -> str | None:
        result = self._try_resolve(query, known)
        if result is not None:
            return result
        if self._next:
            return self._next.resolve(query, known)
        return None

    @abstractmethod
    def _try_resolve(self, query: str, known: set) -> str | None: ...

class ExactResolver(EntityResolver):
    def _try_resolve(self, query, known):
        for token in query.lower().split():
            if token in {n.lower() for n in known}:
                return token
        return None

class FuzzyResolver(EntityResolver):
    def _try_resolve(self, query, known):
        from rapidfuzz import process, fuzz
        result = process.extractOne(query, known, scorer=fuzz.ratio, score_cutoff=80)
        return result[0] if result else None

# Wire the chain
resolver = ExactResolver(next_resolver=FuzzyResolver())
entity = resolver.resolve(user_query, known_packages)
```

---

## NetworkX Performance Optimization

Source: `src/retrieval/graph_retriever.py`

### Transitive closure cache strategy
```python
# Current threshold: pre-compute only for graphs ≤ 5000 nodes
# For larger graphs: BFS on-demand

# Performance characteristics:
# Pre-compute time:  ~2s for 1000 nodes, ~30s for 5000 nodes
# Pre-compute memory: ~100 MB for 5000 nodes (worst case dense graph)
# On-demand BFS: O(V+E) per query, ~5ms for 1000-node graph

# When to lower threshold:
#   Memory pressure → set threshold to 2000
# When to raise threshold:
#   Fast SSD, lots of RAM, many repeated transitive queries → raise to 10000
```

### Zero-copy reverse graph
```python
# Already in use — correct pattern:
self._G_rev = self._G.reverse(copy=False)    # view, not copy

# WARNING: copy=False means _G_rev is invalidated if _G is modified
# After any graph mutation: set self._G_rev = None to force rebuild
```

### Adjacency view (not copy)
```python
# Correct — returns a view:
for neighbor in G.neighbors(node):         # O(degree) iteration
for neighbor in G.successors(node):        # directed graph forward
for neighbor in G.predecessors(node):      # directed graph backward

# Wrong — creates a list copy unnecessarily:
for neighbor in list(G.neighbors(node)):   # adds O(degree) allocation
```

### Avoid `nx.convert_node_labels_to_integers`
```python
# String labels (package names) are fine for NetworkX — don't convert
# Conversion would break all string-based lookups and SQLite joins
```

---

## SQLite Production Setup

Source: `src/ingest/db_builder.py`, `src/retrieval/deterministic_retriever.py`

### WAL mode + PRAGMA optimize
```python
# In db_builder.py::build_db() — run once after schema creation
conn.execute("PRAGMA journal_mode = WAL")         # concurrent reads during writes
conn.execute("PRAGMA synchronous = NORMAL")        # balance safety vs speed
conn.execute("PRAGMA cache_size = -64000")         # 64 MB page cache
conn.execute("PRAGMA temp_store = MEMORY")         # temp tables in RAM
conn.execute("PRAGMA mmap_size = 268435456")       # 256 MB memory-mapped I/O

# After ingest completion — let SQLite choose its own indexes
conn.execute("PRAGMA optimize")
conn.execute("ANALYZE")
```

### Required indexes
```sql
-- In db_builder.py schema — indexes for all common query patterns
CREATE INDEX IF NOT EXISTS idx_packages_risk ON packages(risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_packages_repo ON packages(repo_name);
CREATE INDEX IF NOT EXISTS idx_packages_component ON packages(component);
CREATE INDEX IF NOT EXISTS idx_deps_package ON dependencies(package_name);
CREATE INDEX IF NOT EXISTS idx_fm_cc_path ON file_mappings(cc_path);
CREATE INDEX IF NOT EXISTS idx_fm_git_path ON file_mappings(git_path);
```

### Thread-safe connections
```python
# src/retrieval/deterministic_retriever.py — connection per thread
import threading

class DeterministicRetriever:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._local = threading.local()    # thread-local storage

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            self._local.conn = sqlite3.connect(
                str(self._db_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn
```

### Parameterized queries (security — no SQL injection possible)
```python
# Correct — always parameterized:
cursor.execute("SELECT * FROM packages WHERE name = ?", (package_name,))
cursor.execute(
    "SELECT * FROM packages WHERE risk_score >= ? ORDER BY risk_score DESC LIMIT ?",
    (threshold, limit)
)

# Wrong — never string format:
cursor.execute(f"SELECT * FROM packages WHERE name = '{package_name}'")  # SQL injection
```

---

## FastAPI Production Patterns

Source: `api/main.py`

### Lifespan event for RAGEngine warm-up
```python
# api/main.py — warm up the engine before first request
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: pre-load all stores
    engine = get_engine()
    try:
        engine._ensure_loaded()
        print("[startup] RAGEngine loaded successfully")
    except Exception as e:
        print(f"[startup] WARNING: RAGEngine not ready: {e}")
    yield
    # Shutdown: nothing to clean up (SQLite closes on process exit)

app = FastAPI(lifespan=lifespan)
```

### Dependency injection for engine
```python
from fastapi import Depends
from src.rag import RAGEngine, get_engine

def get_rag_engine() -> RAGEngine:
    engine = get_engine()
    if not engine.is_ready():
        raise HTTPException(503, "Data stores not built. Run ingest first.")
    return engine

@app.post("/api/v1/query")
async def query(request: QueryRequest, engine: RAGEngine = Depends(get_rag_engine)):
    result = engine.answer(request.query)
    return {"result": str(result)}
```

### Background ingest task
```python
from fastapi import BackgroundTasks
import asyncio

@app.post("/api/v1/ingest")
async def trigger_ingest(background_tasks: BackgroundTasks):
    """Trigger ingest in background; return immediately."""
    background_tasks.add_task(_run_ingest_and_clear_cache)
    return {"status": "ingest started"}

async def _run_ingest_and_clear_cache():
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, run_ingest, get_config())  # run sync ingest in thread
    get_engine.cache_clear()    # force RAGEngine reload on next request
```

---

## Testing Patterns

### Table-driven intent tests
```python
# tests/test_intent_classifier.py
import pytest
from src.retrieval.intent_classifier import classify

KNOWN_PACKAGES = frozenset(["ehbase", "ace", "ctrllib", "blockext", "alm"])

@pytest.fixture(scope="module")
def known_pkgs():
    return KNOWN_PACKAGES

@pytest.mark.parametrize("query,expected_type,expected_pkg,min_confidence", [
    ("what breaks if I change ehbase?",    "IMPACT_ANALYSIS",  "ehbase",    0.85),
    ("who uses ace?",                       "REVERSE_LOOKUP",   "ace",       0.90),
    ("2nd order dependents of ctrllib",     "NTH_ORDER_LOOKUP", "ctrllib",   0.95),
    ("full dependency tree of blockext",    "TRANSITIVE_FWD",   "blockext",  0.90),
    ("circular dependencies in the graph",  "CYCLE_DETECT",     None,        1.00),
    ("error handling packages",             "SEMANTIC_SEARCH",  None,        0.0),
])
def test_classify(query, expected_type, expected_pkg, min_confidence, known_pkgs):
    intent = classify(query, known_pkgs, set(), set())
    assert intent.type == expected_type, f"Got {intent.type!r} for: {query!r}"
    assert intent.confidence >= min_confidence
    if expected_pkg:
        assert intent.package_name == expected_pkg
```

### Graph retriever fixture
```python
# tests/conftest.py
import networkx as nx
import pytest
from src.retrieval.graph_retriever import GraphRetriever

@pytest.fixture(scope="module")
def test_graph():
    """Minimal test graph: A → B → C, A → D, E isolated."""
    G = nx.DiGraph()
    G.add_edges_from([("A", "B"), ("B", "C"), ("A", "D")])
    G.add_node("E")   # isolated
    for node in G.nodes():
        G.nodes[node].update({"risk_score": 10.0, "risk_category": "LOW"})
    return G

@pytest.fixture(scope="module")
def graph_retriever(test_graph):
    return GraphRetriever(test_graph)

def test_impact_analysis(graph_retriever):
    result = graph_retriever.impact_analysis("C")
    assert "B" in result["all_affected"]
    assert "A" in result["all_affected"]
    assert result["total"] == 2

def test_bfs_levels(graph_retriever):
    result = graph_retriever.impact_analysis("C", max_level=2)
    assert result["levels"][0]["packages"] == ["B"]   # level 1: direct dependent
    assert "A" in result["levels"][1]["packages"]     # level 2: indirect
```

---

## Security Checklist

| Risk | Location | Current State | Fix Required |
|---|---|---|---|
| SQL injection | `deterministic_retriever.py` | ✓ All queries parameterized | None |
| Pickle from untrusted source | `graph_retriever.py`, `semantic_retriever.py` | ⚠ Loaded from local `db/` path only | Verify path is within project root |
| Secrets in code | `.env` + `python-dotenv` | ✓ No hardcoded keys | Keep `.env` in `.gitignore` |
| Path traversal | `config.py` file paths | ⚠ User-supplied config paths | Validate paths stay within BASE_DIR |
| Input length | `api/main.py` query endpoint | ⚠ No length limit | Add `query: str = Query(max_length=2000)` |
| CORS | `api/main.py` | ⚠ Check allowed origins | Set `allow_origins` to known UI origins |
| File upload | `api/main.py` `/ingest` | ⚠ Accepts any JSON file | Validate file size, JSON schema, no exec |

### Input length limit (fix for api/main.py)
```python
from fastapi import Query

class QueryRequest(BaseModel):
    query: str = Field(max_length=2000, min_length=1)
    session_id: str = Field(default="default", max_length=64)
```

### Path validation (fix for config.py)
```python
def _validate_path_within_project(path: Path) -> Path:
    resolved = path.resolve()
    base_resolved = BASE_DIR.resolve()
    if not str(resolved).startswith(str(base_resolved)):
        raise ValueError(f"Path {path} is outside project root")
    return resolved
```
