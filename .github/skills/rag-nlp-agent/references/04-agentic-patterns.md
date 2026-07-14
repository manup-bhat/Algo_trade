# Agentic Patterns

Deterministic agent design — no LLM required in the core loop. LLM is optional augmentation.

---

## What Is the Current Agent Loop?

Source: `src/rag.py::RAGEngine.answer()`, `ui/app.py`

```
User query (str)
      │
      ▼  RAGEngine.answer()
      ├─ _ensure_loaded()        ← lazy store initialization (once per process)
      │
      ├─ classify(query, ...)    ← Intent classifier (NLP) → Intent
      │       ├─ Regex pattern match
      │       ├─ Entity extraction (exact + fuzzy + path)
      │       └─ Returns: Intent{type, package_name, confidence, negated, depth}
      │
      ├─ HybridRetriever.retrieve(intent)   ← routing + multi-store query
      │       ├─ Route to DeterministicRetriever (SQLite)
      │       ├─     or GraphRetriever (NetworkX BFS/DFS)
      │       └─     or SemanticRetriever (TF-IDF cosine)
      │
      └─ render(QueryResult)     ← Rich Panel/Table/Tree (or LLM narrative if use_llm=true)
```

This is a **routing workflow** (Anthropic terminology): query is classified and directed to a specialized handler. Each handler is deterministic — same input always produces same output.

---

## How Session Memory Currently Works

Source: `ui/app.py` — Streamlit session state

```python
# Current approach: Streamlit session dict (ad-hoc, not persistent)
st.session_state.current_entity    # last resolved package name
st.session_state.conversation      # list of {query, answer} dicts
st.session_state.chat_title        # auto-generated title

# Multi-turn context: if no entity found in current query, reuse previous
if not intent.package_name and st.session_state.current_entity:
    intent = intent.copy(update={"package_name": st.session_state.current_entity})
```

**Limitations**: memory is per-browser-tab, lost on refresh, no persistence across sessions.

---

## How to Handle Low-Confidence Queries (Confidence Gate)

When `intent.confidence < threshold`, the system should ask for clarification rather than guess.

**Current behavior**: routes to `SEMANTIC_SEARCH` as fallback.

**Improved pattern**:
```python
# In RAGEngine.answer() or HybridRetriever.retrieve()
CONFIDENCE_THRESHOLD = 0.60

if intent.confidence < CONFIDENCE_THRESHOLD:
    # 1. Try SemanticRetriever for fuzzy match
    sem_results = self._sem.search(intent.raw_query, k=3)
    if sem_results:
        # Return suggestions instead of an answer
        return QueryResult(
            intent=intent,
            message=f"Low confidence ({intent.confidence:.0%}). Did you mean one of these?",
            suggestions=[r["name"] for r in sem_results],
        )
    # 2. Return clarification request
    return QueryResult(intent=intent, message="Please clarify: what package are you asking about?")
```

---

## How to Decompose Compound Queries (Multi-Intent)

For queries like "who uses X AND what does Y need?":

**Detection pattern**:
```python
# Check for compound connectors
COMPOUND_PATTERN = re.compile(r"\band\b|\balso\b|\bplus\b|\bfurthermore\b", re.I)
is_compound = bool(COMPOUND_PATTERN.search(query))
# Check for multiple entity mentions
n_entities = len(intent.extra_packages) + (1 if intent.package_name else 0)
```

**Split strategy**:
```python
# src/retrieval/intent_classifier.py — compound query decomposition
def split_compound_query(query: str) -> List[str]:
    """Split on 'and', 'also', ';' at clause boundaries."""
    parts = re.split(r"\band\b|\balso\b|;", query, flags=re.I)
    return [p.strip() for p in parts if p.strip()]

# Then classify each sub-query independently
sub_intents = [classify(part, known_pkgs, ...) for part in split_compound_query(query)]
# Execute each, merge results
results = [hybrid.retrieve(i) for i in sub_intents]
```

---

## LangGraph State Machine Design

The optimal agentic architecture for pa_exp_agent. No LLM required.

### State Schema
```python
from typing import TypedDict, Optional, List, Annotated
from langgraph.graph import StateGraph, END
import operator

class AgentState(TypedDict):
    # Inputs
    query: str
    thread_id: str                      # for session isolation

    # NLP outputs
    intent: Optional[dict]              # serialized Intent
    entity: Optional[str]
    confidence: float

    # Retrieval output
    result: Optional[dict]              # serialized QueryResult
    suggestions: List[str]             # for clarification

    # Session memory
    session_history: Annotated[List[dict], operator.add]   # accumulates
    current_entity: Optional[str]       # persisted across turns

    # Control flow
    needs_clarification: bool
    clarification_answer: Optional[str]
```

### Graph Nodes
```python
def preprocess_node(state: AgentState) -> AgentState:
    """Normalize query, inject session context."""
    query = state["query"].strip()
    # Inject previous entity if query is contextual ("what about its dependents?")
    if state.get("current_entity") and not _has_entity(query):
        query = f"{query} (referring to {state['current_entity']})"
    return {**state, "query": query}

def classify_node(state: AgentState) -> AgentState:
    """NLP intent classification + entity extraction."""
    intent = classify(state["query"], KNOWN_PACKAGES, KNOWN_COMPONENTS, KNOWN_REPOS)
    return {**state,
            "intent": intent.model_dump(),
            "entity": intent.package_name,
            "confidence": intent.confidence}

def retrieve_node(state: AgentState) -> AgentState:
    """Route Intent → HybridRetriever → QueryResult."""
    intent = Intent(**state["intent"])
    result = hybrid_retriever.retrieve(intent)
    return {**state,
            "result": result.model_dump(),
            "current_entity": intent.package_name or state.get("current_entity")}

def clarify_node(state: AgentState) -> AgentState:
    """Generate clarification message from TF-IDF suggestions."""
    suggestions = semantic_retriever.search(state["query"], k=3)
    return {**state,
            "needs_clarification": True,
            "suggestions": [s["name"] for s in suggestions]}

def render_node(state: AgentState) -> AgentState:
    """Format QueryResult → display string."""
    result = QueryResult(**state["result"])
    rendered = render(result)
    history_entry = {"query": state["query"], "result": str(rendered)}
    return {**state, "session_history": [history_entry]}
```

### Conditional Edges (Routing)
```python
def confidence_gate(state: AgentState) -> str:
    """Route based on classification confidence."""
    if state["confidence"] < 0.60:
        return "clarify"
    return "retrieve"

def after_clarify(state: AgentState) -> str:
    """After human provides clarification, re-classify."""
    if state.get("clarification_answer"):
        return "classify"      # re-run with user-provided answer
    return END                 # still waiting for human input

# Graph construction
workflow = StateGraph(AgentState)
workflow.add_node("preprocess",  preprocess_node)
workflow.add_node("classify",    classify_node)
workflow.add_node("retrieve",    retrieve_node)
workflow.add_node("clarify",     clarify_node)
workflow.add_node("render",      render_node)

workflow.set_entry_point("preprocess")
workflow.add_edge("preprocess", "classify")
workflow.add_conditional_edges("classify", confidence_gate,
                               {"retrieve": "retrieve", "clarify": "clarify"})
workflow.add_edge("retrieve",   "render")
workflow.add_edge("render",     END)
workflow.add_conditional_edges("clarify", after_clarify,
                               {"classify": "classify", END: END})
```

### MemorySaver — Persistent Session State
```python
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()      # in-memory; swap for SqliteSaver for persistence
app = workflow.compile(checkpointer=checkpointer, interrupt_before=["clarify"])

# Execute with thread-based session isolation
config = {"configurable": {"thread_id": user_session_id}}
result = app.invoke({"query": user_query, **initial_state}, config=config)

# Session persists: next invocation restores state automatically
result2 = app.invoke({"query": "and its dependents?"}, config=config)
# AgentState.current_entity is preserved from previous turn
```

### Human-in-the-Loop (interrupt)
```python
# When confidence is low, graph pauses at "clarify" node
# interrupt_before=["clarify"] means graph stops BEFORE executing clarify_node

# 1. Graph pauses, returns control to caller with suggestions
state = app.invoke({"query": "show me ehb stuff"}, config=config)
print(state["suggestions"])   # ["ehbase", "ehloop", "ehfault"]

# 2. User picks from suggestions (UI presents them)
# 3. Resume with updated state
app.invoke(
    {"query": "show me ehb stuff", "clarification_answer": "ehbase"},
    config=config
)
# Graph resumes from "clarify" → "classify" with clarification_answer
```

---

## Agentic Design Pattern Comparison

| Pattern | Description | pa_exp_agent Use Case |
|---|---|---|
| **Routing** (current) | Classify input → direct to specialist | Intent → Retriever routing |
| **Prompt chaining** | Output of step N feeds step N+1 | classify → extract → retrieve → render |
| **Parallelization** | Run multiple handlers simultaneously | Run all 3 retrievers in parallel via `RunnableParallel` |
| **Evaluator-optimizer** | LLM grades own output, iterates | confidence_gate → fallback retriever |
| **Orchestrator-workers** | Central planner delegates to specialists | Future: compound query → sub-agents per intent |
| **ReAct** | Thought → Action → Observation loop | LangGraph loop with tool-use (optional LLM) |

pa_exp_agent implements **Routing** at its core, with **Prompt chaining** as the sequential pipeline and an **Evaluator-optimizer** for the confidence gate fallback.
