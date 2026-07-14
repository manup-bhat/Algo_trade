# NLP Intent Pipeline

General-purpose offline NLP pipeline — works for **any chatbot or RAG domain**.
No LLM, no model downloads, no internet required.

> **pa_exp_agent specific patterns** are labelled `[pa_exp_agent]` throughout.
> All other content applies to any domain: e-commerce, IT helpdesk, HR bots, customer support, code assistants, etc.

---

## Universal NLU Architecture

Any task-oriented chatbot or RAG system needs three NLP layers:

```
User utterance (raw text)
        │
        ▼ ── Layer 1: Intent Classification ──────────────────────────
        │   "What does the user want to DO?"
        │   Output: intent_type (string), confidence (0–1)
        │
        ▼ ── Layer 2: Slot / Entity Filling ─────────────────────────
        │   "What are the key OBJECTS, VALUES, and PARAMETERS?"
        │   Output: slots dict {slot_name: slot_value}
        │            entities list [{text, type, value, start, end}]
        │
        ▼ ── Layer 3: Dialogue State Tracking ───────────────────────
        │   "What CONTEXT persists from prior turns?"
        │   Output: updated state {current_entity, open_slots, history}
        │
        ▼ ── Response Routing ────────────────────────────────────────
            Intent + Slots + State → Handler → Response
```

This maps to the **NLU sub-tasks** from task-oriented dialogue research (PPTOD, SimpleTOD):
- **Intent detection** → understand request type
- **Slot filling** → extract structured parameters
- **Dialogue state tracking (DST)** → maintain context across turns
- **Policy** → select the right action/handler

---

## Layer 1: Intent Classification

### The Universal Ordered-Pattern Approach

The most production-proven no-LLM approach: an **ordered table of compiled regex patterns**, first-match wins, with pre-assigned confidence scores.

```python
# Universal intent classifier structure (any domain)
from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List

@dataclass
class IntentResult:
    intent: str
    confidence: float
    matched_pattern: str = ""
    ambiguous: bool = False

# Pattern table: (compiled_regex, intent_type, confidence)
# Order matters — specific before general
_PATTERNS: list[tuple[re.Pattern, str, float]] = [
    # ... domain-specific patterns in priority order ...
]

def classify_intent(query: str) -> IntentResult:
    q = query.lower()
    for pattern, intent, confidence in _PATTERNS:
        if pattern.search(q):
            return IntentResult(intent=intent, confidence=confidence,
                                matched_pattern=pattern.pattern)
    return IntentResult(intent="FALLBACK", confidence=0.0)
```

**Why this works for production**:
- Deterministic — same input always produces same output
- Explainable — you can print exactly which pattern matched
- Fast — compiled regex scans ~100 patterns in < 1ms
- Debuggable — add logging to `pattern.search(q)` to trace failures
- Domain-adaptable — add/remove patterns without retraining

### Designing Your Intent Taxonomy

Before writing patterns, design your intent taxonomy by answering:

| Question | Example domains |
|---|---|
| What **actions** can users request? | `search`, `book`, `cancel`, `check_status` |
| What **information** do users seek? | `get_price`, `get_policy`, `get_details` |
| What **navigation** patterns exist? | `go_back`, `start_over`, `help`, `greet` |
| What **compound** actions exist? | `book_and_confirm`, `search_then_filter` |
| What **meta** intents are needed? | `clarify`, `affirm`, `deny`, `out_of_scope` |

**Intent naming conventions**:
- Use `VERB_NOUN` format: `SEARCH_PRODUCT`, `CHECK_ORDER`, `REPORT_ISSUE`
- Or `DOMAIN_ACTION`: `IMPACT_ANALYSIS`, `REPO_INFO` [pa_exp_agent]
- Always include: `FALLBACK` (no match), `AFFIRM`, `DENY`, `GREET`, `GOODBYE`

### Intent Pattern Ordering Rules (Universal)

```
Priority 1  High-specificity, zero-ambiguity patterns      (confidence 1.0)
Priority 2  Domain-specific compound intents               (confidence 0.95)
Priority 3  Standard action intents                        (confidence 0.85–0.90)
Priority 4  Information/lookup intents                     (confidence 0.80–0.90)
Priority 5  Meta/navigation intents                        (confidence 0.75–0.85)
Priority 6  Generic catch-all patterns                     (confidence 0.60–0.75)
LAST        FALLBACK                                       (confidence 0.0)
```

**Critical rule**: **more specific BEFORE more general**. Examples:
- `SEARCH_BY_DATE` before `SEARCH` (date-specific is more specific)
- `NTH_ORDER_LOOKUP` before `REVERSE_LOOKUP` [pa_exp_agent]
- `BOOK_RETURN_FLIGHT` before `BOOK_FLIGHT` (round-trip is more specific)

### Domain Examples — Intent Tables

**E-commerce chatbot**:

| Priority | Intent | Example Triggers | Confidence |
|---|---|---|---|
| 1 | `TRACK_ORDER` | "where is my order", "track #12345" | 1.0 |
| 2 | `RETURN_ITEM` | "return", "refund", "send back" | 0.95 |
| 3 | `SEARCH_PRODUCT` | "find", "show me", "I want", "looking for" | 0.85 |
| 4 | `CHECK_PRICE` | "how much", "price of", "cost" | 0.90 |
| 5 | `CHECK_AVAILABILITY` | "in stock", "available", "do you have" | 0.88 |
| 6 | `ADD_TO_CART` | "add to cart", "buy", "purchase" | 0.90 |
| 7 | `CHECKOUT` | "checkout", "pay", "complete order" | 0.95 |
| 8 | `GREET` | "hi", "hello", "hey", "good morning" | 0.80 |
| 9 | `FALLBACK` | *(no match)* | 0.0 |

**IT helpdesk bot**:

| Priority | Intent | Example Triggers | Confidence |
|---|---|---|---|
| 1 | `REPORT_OUTAGE` | "down", "not working", "outage", "unavailable" | 1.0 |
| 2 | `ESCALATE` | "escalate", "urgent", "critical", "manager" | 0.95 |
| 3 | `RESET_PASSWORD` | "reset password", "locked out", "forgot password" | 1.0 |
| 4 | `CHECK_TICKET_STATUS` | "status of ticket", "update on", "any news" | 0.90 |
| 5 | `REPORT_ISSUE` | "problem with", "issue", "broken", "error" | 0.85 |
| 6 | `REQUEST_ACCESS` | "need access", "permission", "grant", "authorize" | 0.88 |
| 7 | `FALLBACK` | *(no match)* | 0.0 |

**[pa_exp_agent] — Dependency analysis** (see [01-codebase-map.md](./01-codebase-map.md) for full table):

| Priority | Intent | Example Triggers |
|---|---|---|
| 1 | `PATH_QUERY` | "path from A to B", "chain from A" |
| 3 | `CYCLE_DETECT` | "circular", "cycle" |
| 6 | `IMPACT_ANALYSIS` | "what breaks if I change X" |
| 12 | `REVERSE_LOOKUP` | "who uses X", "dependents of X" |
| 15 | `SEMANTIC_SEARCH` | *(fallback)* |

---

## Layer 2: Slot / Entity Filling

### Universal Slot Definition Schema

A **slot** is a named parameter required to fulfill an intent. Every domain needs slots.

```python
@dataclass
class SlotDefinition:
    name: str               # slot identifier: "product_name", "date", "order_id"
    slot_type: str          # "entity", "date", "number", "boolean", "enum", "free_text"
    required: bool          # must be filled before action can execute
    extraction_method: str  # "regex", "dict_lookup", "fuzzy", "position", "context"
    prompt: str             # clarification question if slot is missing
    validators: list        # optional validation rules

# Example slot definitions for e-commerce:
SEARCH_PRODUCT_SLOTS = [
    SlotDefinition("product_name",  "entity",   required=True,  extraction_method="fuzzy",
                   prompt="What product are you looking for?"),
    SlotDefinition("category",      "enum",     required=False, extraction_method="dict_lookup",
                   prompt="Which category?"),
    SlotDefinition("max_price",     "number",   required=False, extraction_method="regex",
                   prompt="What's your budget?"),
    SlotDefinition("color",         "enum",     required=False, extraction_method="dict_lookup",
                   prompt="Any color preference?"),
]
```

### Entity/Slot Extraction Methods (All Offline)

#### Method 1 — Regex extraction (dates, IDs, prices, quantities)

```python
# Universal regex patterns for common entity types
ENTITY_PATTERNS = {
    # Temporal
    "date":      re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|today|tomorrow|yesterday|"
                             r"next\s+\w+|last\s+\w+|in\s+\d+\s+days?)\b", re.I),
    "time":      re.compile(r"\b(\d{1,2}:\d{2}(?:\s*[ap]m)?|\d{1,2}\s*[ap]m)\b", re.I),
    # Numeric
    "price":     re.compile(r"\$\s*(\d+(?:\.\d{2})?)|(\d+(?:\.\d{2})?)\s*(?:dollars?|USD)", re.I),
    "quantity":  re.compile(r"\b(\d+)\s*(?:items?|units?|pieces?|pcs?)?\b"),
    "percent":   re.compile(r"\b(\d+(?:\.\d+)?)\s*%"),
    # IDs and codes
    "order_id":  re.compile(r"\b(?:order|#|no\.?)\s*([A-Z0-9\-]{6,20})\b", re.I),
    "ticket_id": re.compile(r"\b(?:ticket|case|issue|#)\s*(\d{4,10})\b", re.I),
    # Email / URL
    "email":     re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
}

def extract_by_regex(query: str, entity_type: str) -> str | None:
    pattern = ENTITY_PATTERNS.get(entity_type)
    if pattern:
        match = pattern.search(query)
        return match.group(1) if match else None
    return None
```

#### Method 2 — Dictionary lookup with fuzzy fallback (domain entities)

The most important method for **domain-specific entities** (product names, package names, employee names, service names):

```python
# Universal 3-tier entity resolver (pure Python, no ML)
from rapidfuzz import process as rfprocess, fuzz as rffuzz

class DomainEntityResolver:
    """Resolves domain entity mentions to canonical IDs. Works for any domain."""

    def __init__(self, known_entities: dict[str, str]):
        """
        known_entities: {canonical_id: display_name}
        Example: {"ACE": "ACE", "CTRLLIB": "ctrllib"} [pa_exp_agent]
        Example: {"IPHONE_15": "iPhone 15", "MACBOOK_AIR": "MacBook Air"} [e-commerce]
        """
        self._entities = known_entities
        self._lower_map = {v.lower(): k for k, v in known_entities.items()}

    def resolve(self, query_fragment: str, context_entity: str | None = None) -> str | None:
        """Tier 1 → Tier 2 → Tier 3 → context fallback."""
        fragment = query_fragment.lower().strip()

        # Tier 1: Exact match (O(1))
        if fragment in self._lower_map:
            return self._lower_map[fragment]

        # Tier 2: Token scan — each whitespace-delimited token
        for token in re.split(r"[\s,;]+", fragment):
            if token in self._lower_map:
                return self._lower_map[token]

        # Tier 3: Fuzzy match (handles typos, abbreviations)
        match = rfprocess.extractOne(
            fragment,
            list(self._lower_map.keys()),
            scorer=rffuzz.ratio,
            score_cutoff=80,   # tune for your domain (lower = more permissive)
        )
        if match:
            return self._lower_map[match[0]]

        # Tier 4: Context fallback (use last mentioned entity from dialogue state)
        return context_entity
```

#### Method 3 — Position-based extraction (structured queries)

```python
# For queries with predictable structure: "compare X and Y", "path from A to B"
def extract_pair(query: str, known: set[str]) -> tuple[str | None, str | None]:
    """Extract two entity mentions from a comparison/path query."""
    # "compare X and Y", "X vs Y", "difference between X and Y"
    pair_pattern = re.compile(
        r"(?:compare|between|from)\s+(\S+)\s+(?:and|vs\.?|to)\s+(\S+)", re.I
    )
    m = pair_pattern.search(query)
    if m:
        a = m.group(1) if m.group(1).lower() in {n.lower() for n in known} else None
        b = m.group(2) if m.group(2).lower() in {n.lower() for n in known} else None
        return a, b
    return None, None
```

### Slot Filling State Machine

When a required slot is missing, the bot must **request clarification** before routing:

```python
@dataclass
class SlotFillingState:
    intent: str
    filled_slots: dict[str, str]          # slot_name → value
    missing_required: list[str]           # slot names still needed
    pending_slot: str | None = None       # slot currently being requested

def fill_slots(query: str, intent: str, slot_defs: list[SlotDefinition],
               state: SlotFillingState | None = None) -> SlotFillingState:
    """Extract all available slots from query, track what's still missing."""
    filled = {}

    for slot in slot_defs:
        value = None
        if slot.extraction_method == "regex":
            value = extract_by_regex(query, slot.slot_type)
        elif slot.extraction_method == "dict_lookup":
            value = lookup_enum(query, slot.name)
        elif slot.extraction_method == "fuzzy":
            value = resolver.resolve(query)
        # ... other methods

        if value:
            filled[slot.name] = value

    missing = [s.name for s in slot_defs if s.required and s.name not in filled]
    return SlotFillingState(intent=intent, filled_slots=filled, missing_required=missing)
```

### Common Slot Types by Domain

| Domain | Key Slots | Extraction Method |
|---|---|---|
| E-commerce | `product_name`, `category`, `price_range`, `color`, `size` | fuzzy + dict + regex |
| IT helpdesk | `service_name`, `ticket_id`, `severity`, `affected_user` | dict + regex + enum |
| HR chatbot | `employee_name`, `leave_type`, `start_date`, `end_date` | fuzzy + regex + enum |
| Travel | `destination`, `departure_date`, `return_date`, `passengers` | dict + regex + number |
| Dependency RAG [pa_exp_agent] | `package_name`, `repo_name`, `risk_filter`, `depth` | fuzzy + enum + number |

---

## Layer 3: Dialogue State Tracking

### What Is Dialogue State?

Dialogue state = everything the bot knows from prior turns that is still relevant:

```python
@dataclass
class DialogueState:
    # Entity context
    current_entity: str | None = None      # most recently mentioned entity
    entity_history: list[str] = field(default_factory=list)

    # Slot accumulation (slots build up across turns)
    slots: dict[str, str] = field(default_factory=dict)

    # Intent history
    intent_history: list[str] = field(default_factory=list)
    last_intent: str | None = None

    # Turn tracking
    turn_count: int = 0
    session_id: str = ""

    # Pending actions
    pending_slot_request: str | None = None    # slot being requested
    awaiting_confirmation: bool = False        # bot asked "did you mean X?"
```

### Context-Aware Entity Resolution

When the user says "what about its dependencies?", "it" refers to the last mentioned entity:

```python
def resolve_with_context(query: str, resolver: DomainEntityResolver,
                          state: DialogueState) -> str | None:
    """Try to resolve entity from query; fall back to state.current_entity."""
    # Pronouns and context references
    CONTEXTUAL_REFS = re.compile(
        r"\b(it|its|this|that|the same|same one|that one)\b", re.I
    )

    # Try direct extraction first
    entity = resolver.resolve(query)
    if entity:
        return entity

    # If query contains a contextual reference AND we have prior context
    if CONTEXTUAL_REFS.search(query) and state.current_entity:
        return state.current_entity

    # Implicit context: "what about its dependents?" → use current_entity
    if not entity and state.current_entity:
        # Only fall back if query contains intent keywords
        # (prevents arbitrary fallback on unrelated queries)
        return state.current_entity

    return None

def update_state(state: DialogueState, intent: str, entity: str | None,
                  slots: dict) -> DialogueState:
    """Update dialogue state after each turn."""
    new_state = DialogueState(
        current_entity=entity or state.current_entity,  # persist if not updated
        entity_history=state.entity_history + ([entity] if entity else []),
        slots={**state.slots, **slots},   # accumulate slots
        intent_history=state.intent_history + [intent],
        last_intent=intent,
        turn_count=state.turn_count + 1,
        session_id=state.session_id,
    )
    return new_state
```

### Multi-Turn Example

```
Turn 1: "what does ehbase depend on?"
  Intent:  FORWARD_LOOKUP, entity: "ehbase", confidence: 0.95
  State:   current_entity="ehbase", intent_history=["FORWARD_LOOKUP"]
  Answer:  "ehbase depends on: ctrllib, alm, base64"

Turn 2: "who uses it?"    ← contextual reference
  Intent:  REVERSE_LOOKUP, entity: None (resolved to "ehbase" from state)
  State:   current_entity="ehbase", intent_history=[..., "REVERSE_LOOKUP"]
  Answer:  "ehbase is used by: controller, acecee, ..."

Turn 3: "and what are the 2nd order dependents?"   ← still implicitly about ehbase
  Intent:  NTH_ORDER_LOOKUP, entity: "ehbase" (from state), depth: 2
  State:   current_entity="ehbase"
  Answer:  "2nd order dependents of ehbase: ..."
```

---

## [pa_exp_agent] Intent Pattern Table (All 15 Types)

**Source**: `src/retrieval/intent_classifier.py::_PATTERNS` — ordered, first-match wins.

| Priority | Intent Type | Example Triggers | Confidence |
|---|---|---|---|
| 1 | `PATH_QUERY` | "path from A to B", "chain from A", "shortest path" | 1.0 |
| 2 | `TOPO_SORT` | "build order for X", "deployment order", "topological" | 0.9–1.0 |
| 3 | `CYCLE_DETECT` | "circular", "cycle", "cycles" | 1.0 |
| 4 | `REPO_IMPACT` | "if I change repo X", "repo X breaks" | 1.0 |
| 5 | `REPO_INFO` | "packages in repo X", "list repos", "what repos" | 0.85–0.95 |
| 6 | `IMPACT_ANALYSIS` | "what breaks", "impact of", "if I change X", "cascade" | 0.85–0.95 |
| 7 | `TRANSITIVE_FWD` | "transitive dependencies", "full dependency tree", "recursive deps" | 0.90–1.0 |
| 8 | `TRANSITIVE_REV` | "transitive dependents", "all indirect dependents" | 0.90–1.0 |
| 9 | `FORWARD_LOOKUP` | "what does X depend on", "dependencies of X" | 0.85–1.0 |
| 10 | `NTH_ORDER_LOOKUP` | "2nd order dependents", "3rd level deps", "N hops" | 0.95–0.97 |
| 11 | `REVERSE_LOOKUP_FILTERED` | "critical dependents of X", "high risk dependents" | 0.95–0.97 |
| 12 | `REVERSE_LOOKUP` | "who uses X", "dependents of X", "used by" | 0.85–1.0 |
| 13 | `COMPARE_PACKAGES` | "compare X and Y", "X vs Y" | 0.85–0.90 |
| 14 | `AGGREGATE` | "riskiest packages", "critical packages", "isolated" | 0.90–1.0 |
| 15 | `SEMANTIC_SEARCH` | *(fallback — no regex match)* | 0.0 |

**Critical ordering rules**:
1. `NTH_ORDER_LOOKUP` BEFORE `REVERSE_LOOKUP` — "2nd order dependents" must not match generic reverse
2. `REVERSE_LOOKUP_FILTERED` BEFORE `AGGREGATE` — "high risk dependents" ≠ aggregate
3. `TRANSITIVE_FWD/REV` BEFORE `FORWARD/REVERSE_LOOKUP` — "full tree" ≠ direct deps
4. `REPO_IMPACT` BEFORE `IMPACT_ANALYSIS` — repo-scoped is more specific

**[pa_exp_agent] Entity extraction** — 3 tiers:
- **Tier 1**: Exact token match against `known_packages` set (O(1) dict lookup)
- **Tier 2**: `rapidfuzz` fuzzy match with score_cutoff=80
- **Tier 3**: Path-component extraction for `\blockext\system\blockext.cpp` style queries via `_resolve_package_from_path()` in `hybrid_retriever.py`

Special: hybrid packages use `node_id = f"{raw_name}::{pkg_manager}"` — strip `::*` suffix before lookup.

---

## Semantic / Fallback Search — Universal TF-IDF Pattern

When intent classification returns `FALLBACK` (confidence = 0), use semantic search to retrieve the most relevant items. This works for **any domain** with a document corpus.

### Universal Document Chunking for TF-IDF

The key insight: craft `_make_chunk()` to inject **domain synonyms** — this is what makes TF-IDF work for concept queries.

```python
# Universal pattern — adapt for your domain
def make_chunk(item: dict) -> str:
    """
    Build a keyword-rich text representation for TF-IDF indexing.
    The richer this text, the better concept queries work.
    """
    parts = [item["id"], item["name"], item.get("category", ""), item.get("tags", "")]

    # Domain-specific synonym injection:
    if item.get("is_critical"):                  # e-commerce: featured/bestseller
        parts += ["popular", "bestseller", "top rated", "recommended"]
    if item.get("is_free"):                      # pricing
        parts += ["free", "no cost", "complimentary"]
    if "error" in item["name"].lower():          # IT: error-related
        parts += ["bug", "fault", "exception", "crash", "failure"]
    if item.get("department") == "hr":           # HR bot
        parts += ["employee", "staff", "people", "workforce", "human resources"]

    # Always include: description, metadata, computed attributes
    return " ".join(filter(None, parts + [item.get("description", "")]))
```

### [pa_exp_agent] `_make_chunk()` Implementation

Source: `src/ingest/embedder.py::_make_chunk()`

```python
def _make_chunk(pkg: Package) -> str:
    role_keywords = [pkg.name.lower(), pkg.component.lower()]
    if pkg.is_foundation:
        role_keywords += ["foundation", "base", "core", "leaf", "no dependencies"]
    if pkg.rev_dep_count > 200:
        role_keywords += ["critical", "widely used", "shared", "common"]
    # ... more synonym rules for error handling, database, library packages
    return (
        f"{pkg.name} {pkg.component} {pkg.repo_name} {pkg.package_manager} "
        f"{pkg.risk_category.value} "
        f"dependencies {pkg.fwd_dep_count} dependents {pkg.rev_dep_count} "
        + " ".join(role_keywords)
    )
```

### TF-IDF Vectorizer Settings (Production)

```python
TfidfVectorizer(
    analyzer="word",
    ngram_range=(1, 2),     # bigrams capture "error handling", "out of stock"
    min_df=1,               # small corpus: keep all terms
    sublinear_tf=True,      # log(1+tf) prevents common words dominating
    strip_accents="unicode",
    lowercase=True,
)
```

### At Query Time

```python
q_vec = vectorizer.transform([query])          # sparse (1, vocab_size)
scores = cosine_similarity(q_vec, matrix)      # (1, n_docs)
top_indices = scores.argsort()[0][-k:][::-1]   # top-k descending
```

---

## TF-IDF vs BM25 — Universal Comparison

| Criterion | TF-IDF (built-in sklearn) | BM25 (`rank_bm25` pip) |
|---|---|---|
| Setup | Zero new deps | `pip install rank_bm25` |
| Offline | ✓ | ✓ |
| Term saturation | No | Yes — plateau after k1 threshold |
| Document length norm | Implicit | Explicit (b parameter) |
| Best for | Concept / category queries | Exact keyword, product name, ID queries |
| Corpus size | Any | Any |
| Build time | < 2s for 1000 docs | < 1s |

**Rule of thumb**:
- `SEMANTIC_SEARCH` fallback → TF-IDF (concept matching)
- Exact product/entity name search → BM25
- Best results → RRF fusion of both (see [06-architecture-options.md](./06-architecture-options.md))

---

## NLP Improvement Tiers (Universal, All Offline)

### Tier 1 — Regex Expansion (zero new deps)

**Improve intent coverage** — add patterns for synonyms, paraphrases, slang:
```python
# Any domain: add new regex at the correct priority position
(re.compile(r"\b(?:busted|borked|crapped out)\b", re.I), "REPORT_ISSUE", 0.88),    # IT slang
(re.compile(r"\b(?:find me|got any|do you carry)\b", re.I), "SEARCH_PRODUCT", 0.85), # e-commerce

# [pa_exp_agent] expand IMPACT_ANALYSIS:
(re.compile(r"\bcrash\b|\bbreak down\b", re.I), "IMPACT_ANALYSIS", 0.85),
```

**Improve entity recall** — inject domain synonyms into `make_chunk()`:
```python
# Any domain: add synonyms for better TF-IDF concept matching
if "error" in item["name"].lower():
    parts += ["exception", "crash", "failure", "bug", "defect"]
```

**Effort**: 30 min. **Risk**: low. **Gain**: +5–15% recall on edge-case queries.

---

### Tier 2 — Latent Semantic Indexing (sklearn only, no new deps)

Add `TruncatedSVD` after TF-IDF — maps to latent concept space so synonyms cluster:

```python
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import make_pipeline

# Works for ANY domain corpus (products, packages, tickets, employees)
lsi_pipeline = make_pipeline(
    TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True),
    TruncatedSVD(n_components=50, random_state=42)  # 50 latent topics
)
lsi_matrix = lsi_pipeline.fit_transform(docs)   # dense (n_docs, 50)

# Query: project into latent space
q_lsi = lsi_pipeline.transform([query])         # (1, 50)
scores = cosine_similarity(q_lsi, lsi_matrix)   # (1, n_docs)
```

**Benefit**: "crash" and "failure" cluster together — concept queries work without explicit synonym injection.
**New deps**: none. **Effort**: 2 hours.

---

### Tier 3 — BM25 (`rank_bm25`, one small dep)

```bash
pip install rank_bm25    # pure Python, Apache 2.0, ~30 KB
```

```python
from rank_bm25 import BM25Okapi

# Build (once, during ingest/indexing) — works for any domain
tokenized_docs = [make_chunk(item).lower().split() for item in corpus]
bm25 = BM25Okapi(tokenized_docs)

# Query (at runtime)
scores = bm25.get_scores(query.lower().split())
top_idx = scores.argsort()[-k:][::-1]
results = [corpus[i] for i in top_idx]
```

**Benefit**: Better precision for exact entity name searches (product IDs, package names, ticket numbers). Term saturation prevents "the" and "is" from dominating.
**Effort**: 3 hours.

---

### Tier 4 — RRF Hybrid Fusion (no extra deps beyond Tier 3)

$$\text{RRF}(d) = \sum_{r \in R} \frac{1}{k + \text{rank}_r(d)}, \quad k = 60$$

```python
def rrf_fuse(*ranked_lists: list[str], k: int = 60) -> list[str]:
    """Fuse N ranked result lists into one via Reciprocal Rank Fusion. Any domain."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.get, reverse=True)

# Fuse TF-IDF + BM25 + exact DB/dict results
fused = rrf_fuse(tfidf_results, bm25_results, exact_results)
```

**Benefit**: 10–20% precision improvement. Works for any domain.
**Effort**: 4 hours (after Tier 3).

---

## Negation Detection (Universal)

Negation changes query semantics in any domain: "products WITHOUT dairy", "tickets NOT assigned to me".

```python
NEGATION_PATTERNS = [
    re.compile(r"\bnot\b|\bno\b|\bnever\b|\bwithout\b", re.I),
    re.compile(r"\bexclude\b|\bexcept\b|\bapart from\b|\bother than\b", re.I),
    re.compile(r"\bdon'?t\b|\bdoesn'?t\b|\bwon'?t\b|\bcan'?t\b", re.I),
]

def detect_negation(query: str) -> bool:
    return any(p.search(query) for p in NEGATION_PATTERNS)
```

**Retriever behavior when `negated=True`**: return the **complement** of the normal result set.

Examples:
- E-commerce: "products not on sale" → `SEARCH_PRODUCT`, `negated=True`, exclude `is_sale=True`
- IT: "tickets not resolved" → `CHECK_TICKET_STATUS`, `negated=True`, filter `status != resolved`
- [pa_exp_agent]: "what does X NOT depend on" → `FORWARD_LOOKUP`, `negated=True`, complement of deps

---

## NLU Testing Patterns (Universal)

### Table-driven intent tests

```python
# Works for ANY domain — just change the test cases
@pytest.mark.parametrize("query,expected_intent,expected_entity,min_conf", [
    # E-commerce
    ("where is my order 12345",         "TRACK_ORDER",    "12345",   0.90),
    ("I want to return the blue shirt",  "RETURN_ITEM",    None,      0.85),
    # IT helpdesk
    ("JIRA is down",                    "REPORT_OUTAGE",  "JIRA",    0.95),
    ("reset my password",               "RESET_PASSWORD", None,      1.00),
    # [pa_exp_agent] dependency
    ("what breaks if I change ehbase",  "IMPACT_ANALYSIS","ehbase",  0.85),
    ("who uses ace",                    "REVERSE_LOOKUP", "ace",     0.90),
])
def test_intent(query, expected_intent, expected_entity, min_conf):
    result = classify_intent(query)
    assert result.intent == expected_intent
    assert result.confidence >= min_conf
```

---

## Anti-Patterns (Universal NLP)

| Anti-Pattern | Symptom | Fix |
|---|---|---|
| Pattern ordering conflict | Specific intent falls through to generic FALLBACK | Put specific before general in `_PATTERNS` |
| Missing synonym coverage | "busted" → FALLBACK instead of REPORT_ISSUE | Expand patterns with slang / paraphrases |
| No negation detection | "no dairy" treated same as "dairy" | Add `negated` flag; invert retriever results |
| Entity after stopword strip | "the product iPhone" → entity "product" not "iPhone" | Don't strip domain nouns; use allowlist approach |
| Fuzzy threshold too low | "iron" matches too many entities | Raise `score_cutoff` or require word-boundary |
| No slot validation | Price "abc" accepted as number | Add validators to `SlotDefinition` |
| Context not preserved | "what about its price?" → FALLBACK (no entity) | Check `state.current_entity` before returning "not found" |
| Missing meta-intents | "yes", "no" → FALLBACK | Always include `AFFIRM`, `DENY`, `GREET`, `GOODBYE` |
