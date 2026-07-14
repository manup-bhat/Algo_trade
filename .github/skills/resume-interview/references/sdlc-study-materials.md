# SDLC Study Material — every phase, concepts + interviewer probes + talking points

> Prepare so you can speak from real experience about EVERY phase of a project.

## 1. Planning & Requirements
**Concepts:** functional vs. non-functional requirements; user stories & acceptance
criteria; scoping (MoSCoW: Must/Should/Could/Won't); estimation (story points,
t-shirt sizing, planning poker); risk register; success metrics/KPIs; MVP thinking.
**Interviewer probes:** "How did you decide what to build first? How did you handle
ambiguous/changing requirements? What did you cut and why?"
**Talking points:** state the goal, the constraints, the metric of success, and one
example of a scoping decision you made under a deadline.

## 2. Design & Architecture
**Concepts:** high-level design; component & sequence diagrams; data modeling;
API design (REST/RPC, versioning, idempotency); design patterns; **SOLID / DRY /
KISS / YAGNI**; monolith vs. microservices; sync vs. async; SQL vs. NoSQL choice;
caching strategy; failure-mode analysis.
**Interviewer probes:** "Draw the architecture. Why these boundaries? Why this DB?
What are the failure modes and SPOFs?"
**Talking points:** justify each major choice with a requirement; name what you
rejected and why; identify your single points of failure and mitigations.

## 3. Development / Implementation
**Concepts:** clean code & naming; version control & branching (feature branches,
trunk-based); **pull requests & code review**; commit hygiene; pair/mob programming;
managing technical debt; dependency management; coding standards & linters;
smallest-correct-change discipline.
**Interviewer probes:** "How did you keep quality high across the team? How did you
run code reviews and resolve merge conflicts? Describe a hard implementation problem."
**Talking points:** one concrete quality practice you introduced + its measurable
effect (e.g., review checklist → −30% defects).

## 4. Testing & QA
**Concepts:** **test pyramid** (many unit → fewer integration → few e2e); TDD;
property-based testing; mocking/stubbing/fakes; meaningful coverage vs. vanity %;
**edge cases & unhappy paths**; regression tests; load/performance testing;
security testing; contract testing; flaky-test handling; test data management.
**Interviewer probes:** "How did you test this? Unit/integration split? How do you
test failure paths? Reproduce a reported bug with a failing test, then fix it?"
**Talking points:** describe your pyramid split, one nasty edge case you caught, and
your CI test gate.

## 5. Deployment & Release
**Concepts:** CI/CD pipelines; build/artifact management; environments (dev/staging/
prod); **blue-green & canary** deploys; feature flags; **zero-downtime DB migrations**
(expand-migrate-contract); rollback strategy; Infrastructure-as-Code; containers &
orchestration (Docker/Kubernetes basics); release checklists.
**Interviewer probes:** "How does code reach production? How do you roll back? How do
you ship a risky change safely?"
**Talking points:** your pipeline stages, how you deploy, and a safe-rollout example
(canary + flag + quick rollback).

## 6. Operations, Monitoring & Maintenance
**Concepts:** logging, metrics, **distributed tracing**; alerting; the four golden
signals (latency, traffic, errors, saturation); **SLI/SLO/error budgets**; on-call;
incident response; **postmortems & root-cause analysis** (5 Whys); capacity planning;
observability vs. monitoring.
**Interviewer probes:** "How do you know the system is healthy? Walk me through an
incident — detection, mitigation, root cause, prevention."
**Talking points:** what you monitor, one real incident timeline, and the durable
fix you shipped so it never recurs.

## Cross-cutting concerns (expect at any phase)
- **Security:** OWASP Top 10; least privilege; secrets management; encrypt in transit/at rest.
- **Performance:** measure before optimizing; know your bottleneck; complexity awareness.
- **Reliability:** redundancy, retries with backoff, idempotency, graceful degradation.
- **Collaboration:** design docs, RFCs, stakeholder communication, documentation.

## Build a "talk-about-able" project (deliberately touch every phase)
1. Write a 1-page design doc (requirements + architecture + tradeoffs).
2. Implement with clean commits and PRs.
3. Add unit + integration tests and a CI pipeline.
4. Containerize and deploy it somewhere (even a free tier).
5. Add basic logging/metrics + a README with the architecture diagram.
→ Now you can answer any phase question from lived experience.