# LangChain Integration

Composition and orchestration layer — zero LLM calls required.

---

## Does This Require an LLM?

**No.** `langchain-core` and `langgraph` are pure Python orchestration libraries:

```bash
pip install langchain-core    # ~2 MB pure Python, zero ML deps
pip install langgraph         # ~500 KB pure Python, zero ML deps
pip install rank_bm25         # ~30 KB pure Python (for BM25 tier)
```

None of these require internet access at runtime. No model downloads. No API keys needed unless `use_llm: true` in `config.yaml`.

---

## How to Wrap a Retriever as a LangChain BaseRetriever

Source pattern: wrap each of the three retrievers for compatibility with `EnsembleRetriever`, `ContextualCompressionRetriever`, and any other LangChain retrieval component.

```python
# src/retrieval/lc_wrappers.py (new file)
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from typing import List
from src.models import Intent
from src.retrieval.graph_retriever import GraphRetriever
from src.retrieval.deterministic_retriever import DeterministicRetriever
from src.retrieval.semantic_retriever import SemanticRetriever


class GraphBaseRetriever(BaseRetriever):
    """Wraps GraphRetriever for IMPACT_ANALYSIS / REVERSE_LOOKUP queries."""
    graph_retriever: GraphRetriever

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        # For LangChain compatibility: treat query as package name
        result = self.graph_retriever.impact_analysis(query)
        return [
            Document(
                page_content=f"{pkg} — affected by changes to {query}",
                metadata={"package": pkg, "retriever": "graph", "type": "impact"}
            )
            for pkg in result.get("all_affected", [])
        ]

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        return self._get_relevant_documents(query, run_manager=run_manager)


class SQLiteBaseRetriever(BaseRetriever):
    """Wraps DeterministicRetriever for exact/filtered queries."""
    det_retriever: DeterministicRetriever

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        packages = self.det_retriever.search_packages(query, limit=20)
        return [
            Document(
                page_content=f"{p['name']} — {p['component']} — risk: {p['risk_category']}",
                metadata=p
            )
            for p in packages
        ]

    async def _aget_relevant_documents(self, query, *, run_manager): ...


class TFIDFBaseRetriever(BaseRetriever):
    """Wraps SemanticRetriever for concept/fuzzy queries."""
    sem_retriever: SemanticRetriever

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        results = self.sem_retriever.search(query, k=10)
        return [
            Document(
                page_content=f"{r['name']} — {r['component']}",
                metadata=r
            )
            for r in results
        ]

    async def _aget_relevant_documents(self, query, *, run_manager): ...
```

---

## LCEL Chain Composition

Source: `langchain_core.runnables`

### Basic pipeline with `|` operator
```python
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from src.retrieval.intent_classifier import classify
from src.retrieval.hybrid_retriever import HybridRetriever
from src.formatting.renderer import render

# Wrap each step as Runnable
classify_step = RunnableLambda(
    lambda query: classify(query, KNOWN_PACKAGES, KNOWN_COMPONENTS, KNOWN_REPOS)
)
retrieve_step = RunnableLambda(
    lambda intent: hybrid_retriever.retrieve(intent)
)
render_step = RunnableLambda(render)

# Compose with | operator (LCEL)
rag_chain = classify_step | retrieve_step | render_step

# Execute
result = rag_chain.invoke("what breaks if I change ehbase?")
```

### Pass-through pattern (carry original query alongside intent)
```python
from langchain_core.runnables import RunnableParallel

# Keep both original query and classified intent in state
rag_chain_with_context = (
    RunnablePassthrough.assign(
        intent=lambda x: classify(x["query"], KNOWN_PACKAGES, KNOWN_COMPONENTS, KNOWN_REPOS)
    )
    | RunnablePassthrough.assign(
        result=lambda x: hybrid_retriever.retrieve(x["intent"])
    )
    | RunnableLambda(lambda x: render(x["result"]))
)

result = rag_chain_with_context.invoke({"query": "who uses ace?"})
```

### Parallel retrieval (run all 3 simultaneously)
```python
from langchain_core.runnables import RunnableParallel

parallel_retrieve = RunnableParallel(
    graph_results=RunnableLambda(lambda q: graph_retriever.impact_analysis(q)),
    sql_results=RunnableLambda(lambda q: det_retriever.search_packages(q, limit=10)),
    tfidf_results=RunnableLambda(lambda q: sem_retriever.search(q, k=10)),
)

# Returns dict with all three results simultaneously
all_results = parallel_retrieve.invoke("ehbase")
```

---

## EnsembleRetriever — RRF Score Fusion

Fuses results from all three retrievers using Reciprocal Rank Fusion.

```python
from langchain.retrievers import EnsembleRetriever

# Instantiate LangChain-wrapped retrievers
graph_lc = GraphBaseRetriever(graph_retriever=graph_retriever)
sql_lc   = SQLiteBaseRetriever(det_retriever=det_retriever)
tfidf_lc = TFIDFBaseRetriever(sem_retriever=sem_retriever)

# Combine with configurable weights [graph, sql, tfidf]
# Higher weight = more influence on final ranking
ensemble = EnsembleRetriever(
    retrievers=[graph_lc, sql_lc, tfidf_lc],
    weights=[0.5, 0.3, 0.2],    # graph dominates for dependency queries
)

# Use in chain
docs = ensemble.invoke("error handling packages that are widely used")
```

**Tuning weights**:
- `[0.5, 0.3, 0.2]` — default, graph-heavy (good for dependency queries)
- `[0.2, 0.2, 0.6]` — semantic-heavy (good for concept queries like "logging infrastructure")
- `[0.1, 0.8, 0.1]` — SQL-heavy (good for exact package name lookups)

The `EnsembleRetriever` uses RRF internally: $\text{RRF}(d) = \sum \frac{1}{60 + \text{rank}(d)}$

---

## ContextualCompressionRetriever — Trim Large Result Sets

When impact analysis returns 500+ affected packages, compress to the most relevant:

```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import EmbeddingsFilter
from langchain_community.embeddings import FakeEmbeddings  # or any local embedding

# Use TF-IDF similarity as the compressor (no model needed)
# Custom compressor using SemanticRetriever scores
from langchain.retrievers.document_compressors.base import BaseDocumentCompressor

class TFIDFCompressor(BaseDocumentCompressor):
    sem_retriever: SemanticRetriever
    threshold: float = 0.1

    def compress_documents(self, documents, query, callbacks=None):
        top_names = {r["name"] for r in self.sem_retriever.search(query, k=50)}
        return [d for d in documents if d.metadata.get("package") in top_names]

compressor = TFIDFCompressor(sem_retriever=sem_retriever, threshold=0.1)
compressed_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=graph_lc,
)
# Returns only the semantically relevant subset of impact results
results = compressed_retriever.invoke("error handling")
```

---

## LangGraph StateGraph — Full Setup

See `04-agentic-patterns.md` for the complete node/edge design. Here is the implementation skeleton:

```python
# src/agent/graph_agent.py (new file)
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite import SqliteSaver  # for persistent sessions

# State, nodes, and edges defined in 04-agentic-patterns.md

# Compile with SQLite persistence (survives process restarts)
db_path = "db/agent_sessions.db"
checkpointer = SqliteSaver.from_conn_string(f"sqlite:///{db_path}")

app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["clarify"]    # pause for human input when needed
)

# Usage
def answer(query: str, session_id: str) -> dict:
    config = {"configurable": {"thread_id": session_id}}
    return app.invoke({"query": query}, config=config)

# Streaming (for FastAPI StreamingResponse)
async def answer_stream(query: str, session_id: str):
    config = {"configurable": {"thread_id": session_id}}
    async for chunk in app.astream({"query": query}, config=config):
        yield chunk
```

### FastAPI integration with streaming
```python
# api/main.py addition
from fastapi.responses import StreamingResponse
import json

@app.post("/api/v1/query/stream")
async def query_stream(request: QueryRequest):
    async def event_generator():
        async for chunk in answer_stream(request.query, request.session_id):
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## LangSmith Observability (Optional, Zero Code Changes)

```bash
# Set environment variables — no code changes required
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=lsv2_...    # free tier available
export LANGSMITH_PROJECT=pa_exp_agent

# All RAGEngine.answer() calls are automatically traced when using LCEL chains
# Provides: latency breakdown, intent classification accuracy, retrieval quality
```

**What it traces per query**:
- Intent classification step (query → Intent, latency, confidence score)
- Each retriever invocation (algorithm, result count, latency)
- Rendering step
- Any LLM calls (if `use_llm: true`)

**Eval with LangSmith** (useful for tuning intent patterns):
```python
from langsmith import evaluate
# Define a dataset of ground-truth query→intent pairs
# Run evaluate() to measure classification accuracy across versions
```

---

## LangChain Integration Anti-Patterns

| Anti-Pattern | Problem | Correct Approach |
|---|---|---|
| Use `LLMChain` / `ChatModel` with `use_llm: false` | Unnecessary dependency, fails without API key | Use LCEL `RunnableLambda` wrappers instead |
| Use Chroma/FAISS vector stores | Heavy ML deps, downloads required | SQLite + TF-IDF is already production-grade for ~1000 docs |
| Replace `HybridRetriever` with `EnsembleRetriever` immediately | Loses ClearCase path resolution and entity disambiguation logic | Wrap existing retrievers as `BaseRetriever` adapters; keep routing logic |
| `applyTo: "**"` in instructions | Loads entire skill into every context window | Use skill with specific trigger description |
| Put all content in SKILL.md | Large flat file is hard for Copilot to extract from | Use references/ subfolder pattern (this design) |
| Store LangGraph state in Streamlit session_state | State lost on page refresh, not portable | Use `SqliteSaver` checkpointer for persistent sessions |
