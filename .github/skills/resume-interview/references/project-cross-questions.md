# Project Cross-Question Catalog — with how-to-answer guidance

> Goal: for EACH headline project, pre-write a crisp answer to every question below.
> Wherever an answer is weak, that's exactly where the interviewer will push.

## How to answer any cross-question (pattern)
**Claim → Reason → Tradeoff → Evidence.**
"I chose **X** *(claim)* because **[requirement]** *(reason)*; I gave up **Y**
*(tradeoff)*; it worked — **[metric]** *(evidence)*."
Answer **top-down first** (one sentence), then offer to go deeper. Say **"I"** for
your work, **"we"** for the team. Volunteering a tradeoff scores higher than a
"perfect" answer with none.

## 1. Motivation & requirements
- Why did this project exist? Who were the users? What problem did it solve?
- Functional vs. **non-functional** requirements (scale, latency, availability, cost)?
- How did you gather/validate requirements? What was explicitly **out of scope**?
- What were the success metrics/KPIs?
> Model skeleton: "Users were X; pain was Y; we targeted [metric]; non-functionals were
> [N req/s, p95 < Xms, 99.9%]; out of scope was Z to hit the deadline."

## 2. Your role & the team
- What did **you** build vs. the team? Which parts are you the expert on?
- Team size? Task split? How did you estimate effort? Timeline?
> Be honest about boundaries — over-claiming collapses under follow-ups.

## 3. Architecture & design
- Walk through the architecture end-to-end. Why this structure?
- Why this **stack/language/framework/database**? What did you reject and why?
- Show the **data model/schema**. Normalized vs. denormalized? Indexes? Why?
- Monolith vs. services — why? Where are the boundaries and why there?
- How do components communicate (REST/RPC/queue) and why?
> Keep a mental diagram; offer to sketch: client → LB → API → cache → DB → workers/queue.

## 4. Tradeoffs & alternatives (the maturity test)
- Main tradeoffs? What would you do differently now?
- With 10× time / bigger team / more budget — what changes?
- Weakest part of the design? What tech debt did you accept and why?
> Always have at least **one** honest "I'd change this" answer ready.

## 5. Scale, performance, reliability
- Load (QPS, data volume, concurrent users)? Where's the bottleneck?
- Scale it 10×/100×: caching, load balancing, horizontal scaling, **sharding**,
  read replicas, async/queues, CDN — which and why?
- p95/p99 latency? How measured and improved?
- If component X fails, what happens? Single points of failure? Failover/replication?
- Consistency vs. availability (**CAP**) — what did you choose and why?

## 6. Data & correctness
- Concurrency/race conditions — locks, transactions, **idempotency**?
- Data integrity guarantees? **Zero-downtime migrations**?

## 7. Security (be ready for OWASP-style probing)
- AuthN/AuthZ approach (sessions/JWT/OAuth2)?
- Preventing injection (parameterized queries), XSS (output encoding), SSRF, broken
  access control? Secrets management? Input validation at boundaries?
- Encryption in transit (TLS) and at rest?

## 8. Testing & quality
- How did you test it? Unit vs. integration vs. e2e split? Coverage?
- What's **not** tested and why? How did you catch regressions?
- How would you write a **failing test to reproduce a bug**, then fix it?

## 9. Delivery & operations
- CI/CD pipeline? Deploy strategy (blue-green/canary)? Rollback? Feature flags?
- Monitoring: logs, metrics, alerts, tracing? How do you know it's healthy?
- Biggest production incident — what happened, response, **root cause + prevention**?

## 10. Reflection
- Hardest bug you fixed and how? Proudest of? What did you learn? What's next?

## Rapid-fire drill (say each in one sentence)
Why this DB? · Why this language? · Biggest bottleneck? · What breaks at 10×? ·
Weakest design decision? · Hardest bug? · How tested? · How deployed/rolled back? ·
Where are the secrets? · What would you redo?