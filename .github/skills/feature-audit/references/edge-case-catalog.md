# Edge Case Catalog — The Encyclopedia of "What Could Break"

> "It works on my machine" means "I tested exactly one input." Production sends millions.

A centralized, scannable catalog of edge cases that apply to **any feature, any stack, any
language**. Bugs cluster at boundaries, at "nothing," at "too much," and at "two things at
once." Before shipping any change, sweep the categories relevant to your feature and prove each
one is handled — ideally with a test.

**How to use**: During REASON (choose the option that survives these) and VERIFY (prove each
handled). For deep per-bug-class detection patterns, pair with
[bug-detection.md](./bug-detection.md).

---

## The 60-Second Sweep (start here)

For ANY input or operation, ask the five killer questions:

```
1. NOTHING   → What if it's empty / null / undefined / zero / missing?
2. ONE       → What if there's exactly one (off-by-one, singular vs plural)?
3. MANY      → What if there are millions (performance, memory, pagination)?
4. WRONG     → What if it's malformed / malicious / wrong type / wrong order?
5. AT ONCE   → What if two of these happen concurrently / are retried?
```

If you can't answer all five for the data your feature touches, you haven't finished REASON.

---

## 1. Input & Boundary Values

| Edge case | Concrete inputs to test |
|-----------|------------------------|
| **Empty / absent** | `""`, `null`, `undefined`, `[]`, `{}`, missing field, whitespace-only `"   "` |
| **Boundary numbers** | `0`, `-1`, `1`, `MAX_INT`, `MIN_INT`, `MAX_INT+1` (overflow), off-by-one at limits |
| **Floating point** | `0.1 + 0.2 !== 0.3`, `NaN`, `Infinity`, `-Infinity`, `-0`, rounding/precision loss in money |
| **Sign & range** | Negative where positive assumed, values above/below allowed range, percentage > 100 |
| **Type confusion** | `"5"` vs `5`, `"true"` vs `true`, `"null"` string vs `null`, array where scalar expected |
| **Very large input** | 10MB string, 1M-row array, deeply nested JSON (stack overflow), huge file upload |
| **Exact limit** | Length exactly at min/max, quota exactly full, the Nth item where N is the page size |

**Test idea**: Parameterize a test over `[null, "", 0, -1, MAX, "wrong-type", hugeValue]`.

---

## 2. Strings, Encoding & Unicode

| Edge case | What breaks |
|-----------|-------------|
| **Unicode & emoji** | `"👨‍👩‍👧‍👦"` (multi-codepoint), combining marks, RTL text, `.length` ≠ visual length |
| **Case & locale** | Turkish `i/İ`, German `ß`, locale-sensitive sort/compare, case-insensitive collisions |
| **Whitespace** | Leading/trailing spaces, tabs, non-breaking space `\u00A0`, zero-width chars |
| **Injection metachars** | `' " ; -- < > & / \ %00 ${} {{}}` — SQL, HTML, shell, template, path |
| **Normalization** | `é` as one codepoint vs `e` + accent — equality and dedup failures |
| **Truncation** | Cutting a multi-byte char in half corrupts data; truncating at byte vs grapheme |
| **Homoglyphs** | Lookalike characters in usernames/URLs (security: spoofing) |

**Rule**: Validate and normalize at the boundary; store one canonical form (usually NFC, UTF-8).

---

## 3. Collections, Iteration & Pagination

| Edge case | What breaks |
|-----------|-------------|
| **Empty collection** | Loop body never runs; `reduce` with no initial value throws; "average of []" = NaN |
| **Single element** | Singular/plural text, "and" joins, first==last assumptions |
| **Duplicates** | Dedup logic, unique-key violations, "distinct" assumptions |
| **Order dependence** | Relying on map/dict/JSON key order, unsorted DB results without `ORDER BY` |
| **Mutation during iteration** | Removing items while looping → skipped elements or crash |
| **Pagination edges** | Last page partial, page beyond end, total changes mid-pagination, offset drift |
| **Off-by-one** | `<=` vs `<`, inclusive/exclusive ranges, slicing `[0:n]` vs `[0:n-1]` |

---

## 4. Time, Dates & Timezones

| Edge case | What breaks |
|-----------|-------------|
| **Timezones** | Server UTC vs user local, storing local time, comparing across zones |
| **DST transitions** | "2:30 AM" that occurs twice or never; durations across the switch |
| **Boundaries** | Midnight, month/year rollover, end-of-month (Jan 31 + 1 month), week-of-year |
| **Leap year / second** | Feb 29, day-of-year math, leap-second-naive diffs |
| **Clock issues** | Clock skew between servers, non-monotonic wall clock for durations, NTP jumps |
| **Formats & parsing** | Ambiguous `01/02/03`, ISO vs locale, missing timezone, epoch `0` / negative epoch |
| **Relative time** | "in 0 minutes", future timestamps, "1 days ago" pluralization |

**Rule**: Store UTC, render in user TZ; use monotonic clocks for durations; use a date library.

---

## 5. Concurrency, Ordering & Idempotency

| Edge case | What breaks |
|-----------|-------------|
| **Race condition** | Two requests read-modify-write the same row → lost update |
| **Double submit** | User double-clicks → duplicate order/charge; missing idempotency key |
| **Check-then-act (TOCTOU)** | "If not exists, create" runs twice → unique violation or duplicate |
| **Out-of-order delivery** | Events/webhooks arrive reordered; later state overwritten by stale one |
| **Retry duplication** | At-least-once delivery + non-idempotent handler → duplicate side effects |
| **Deadlock / livelock** | Locks acquired in different orders; mutual waiting |
| **Partial failure** | Step 2 of 3 fails after step 1 committed → inconsistent state (no rollback) |
| **Cache races** | Stampede on expiry, stale-after-write, cache and DB disagree |

**Rule**: Make write operations idempotent; use transactions, optimistic locking, or
idempotency keys. See [bug-detection.md](./bug-detection.md) concurrency section.

---

## 6. Network, I/O & External Dependencies

| Edge case | What breaks |
|-----------|-------------|
| **Timeout** | Upstream hangs; no timeout set → your service hangs too |
| **Slow response** | Works but takes 30s → UX broken, connection pool exhausted |
| **Partial / dropped** | Truncated response body, connection reset mid-stream |
| **5xx / 4xx** | Upstream down, rate-limited (429), auth expired (401) mid-session |
| **Retry storms** | Naive retries amplify an outage; no backoff/jitter, no circuit breaker |
| **DNS / TLS** | Resolution failure, expired cert, clock skew breaking TLS |
| **Malformed payload** | Non-JSON where JSON expected, unexpected schema, null fields |
| **Offline / flaky** | Mobile/network drops mid-operation; optimistic UI never reconciles |

**Rule**: Every external call needs a timeout, a retry policy with backoff+jitter, and a defined
failure behavior (fail closed for security, degrade gracefully for UX).

---

## 7. State, Lifecycle & Workflow

| Edge case | What breaks |
|-----------|-------------|
| **Invalid transitions** | Cancel an already-shipped order; pay a closed invoice; double-complete |
| **Stale state** | Acting on data that changed since it was loaded (lost update, 409) |
| **Interrupted flow** | User abandons a multi-step wizard; back button mid-transaction |
| **Re-entry** | Resuming a flow that's already partially done; replaying a completed step |
| **Orphaned records** | Parent deleted, children remain; soft-delete not cascaded |
| **Uninitialized / teardown** | Use before init, use after dispose/close, double-free/double-close |

---

## 8. Authentication, Authorization & Security Edges

| Edge case | What breaks |
|-----------|-------------|
| **Expired/invalid token** | Mid-session expiry, clock skew, revoked token still accepted |
| **Privilege boundaries** | Horizontal (other user's ID in URL — IDOR), vertical (user hits admin route) |
| **Missing authz** | Endpoint checks authn but not authz; relies on hidden UI button |
| **Injection** | SQL/NoSQL/command/LDAP/template injection via every input |
| **Mass assignment** | Client sets `isAdmin:true` via extra JSON field |
| **Enumeration** | Login/reset reveals whether an account exists; sequential IDs |
| **Replay / CSRF** | Reused request, missing CSRF token, state-changing GET |

> Full coverage: [security-checklist.md](./security-checklist.md) (OWASP 2025).

---

## 9. Resources, Scale & Performance

| Edge case | What breaks |
|-----------|-------------|
| **Memory** | Loading a huge dataset into memory; unbounded cache/queue growth |
| **N+1 queries** | One query per row in a loop → DB meltdown at scale |
| **Leaks** | Unclosed connections/files/streams/listeners accumulate |
| **Pool exhaustion** | All DB/HTTP connections checked out and not returned |
| **Unbounded work** | No pagination, no max page size, no rate limit, no payload cap |
| **Thundering herd** | Cache expiry or restart → all clients hit the DB at once |
| **Cold start / warmup** | First request slow; serverless cold start; JIT not warm |

---

## 10. Platform, Environment & Config

| Edge case | What breaks |
|-----------|-------------|
| **Missing/bad config** | Absent env var, wrong type, empty string vs unset, default in prod |
| **Cross-platform** | Path separators `/` vs `\`, line endings, case-sensitive FS, locale |
| **Browser/device** | Old browsers, Safari quirks, small screens, slow CPUs, reduced motion |
| **Permissions** | No write access, read-only FS, sandbox restrictions |
| **Version skew** | Client and server on different versions during deploy; schema migration in flight |
| **Feature flags** | Flag on for some users; flag flips mid-session; flag combinations |

---

## 11. Data Integrity & Money

| Edge case | What breaks |
|-----------|-------------|
| **Money math** | Float for currency (use minor units / decimal), rounding, currency mismatch |
| **Precision loss** | Large IDs as JS numbers (> 2^53), silent truncation |
| **Encoding round-trip** | Serialize→store→deserialize loses type/precision/timezone |
| **Null vs zero vs missing** | "0 items" vs "unknown" vs "not provided" conflated |
| **Duplicate/partial writes** | Same event processed twice; write succeeds, ack lost |
| **Referential integrity** | FK pointing to deleted row; dangling reference |

---

## Edge-Case Test Recipe

Turn the sweep into tests so coverage is permanent:

```
For each input the feature accepts:
  1. Nominal value            (happy path)
  2. Empty/null/zero          (Category 1)
  3. Boundary (min, max, ±1)  (Category 1)
  4. Wrong type / malformed   (Category 1, 8)
  5. Huge / many              (Category 1, 9)
  6. Unicode / metachars      (Category 2, 8)

For each operation the feature performs:
  7. Concurrent invocation    (Category 5)
  8. Retried invocation       (Category 5)
  9. Dependency fails/timeouts(Category 6)
 10. Interrupted mid-way      (Category 7)
```

> **Bug-fix rule**: every bug you fix corresponds to an edge case that was missed. Add that
> exact case as a permanent regression test (see [fix-verification.md](./fix-verification.md)).

---

## Quick Coverage Scorecard

| Category | Swept? | Tests added? |
|----------|--------|--------------|
| 1. Input & boundary | | |
| 2. Strings & unicode | | |
| 3. Collections & pagination | | |
| 4. Time & timezone | | |
| 5. Concurrency & idempotency | | |
| 6. Network & external deps | | |
| 7. State & lifecycle | | |
| 8. Auth & security | | |
| 9. Resources & scale | | |
| 10. Platform & config | | |
| 11. Data integrity & money | | |

---

## Sources

- [OWASP Top 10:2025](https://owasp.org/Top10/2025/) — injection, access control, security edges
- [Falsehoods programmers believe (names, time, addresses)](https://github.com/kdeldycke/awesome-falsehood) — exhaustive edge-case lore
- [Martin Fowler: Patterns of Distributed Systems](https://martinfowler.com/articles/patterns-of-distributed-systems/) — idempotency, ordering, partial failure
- [Google Testing Blog: Boundary testing](https://testing.googleblog.com/) — boundary and equivalence partitioning
