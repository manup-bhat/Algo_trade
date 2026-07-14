# Resume Playbook — examples, transformations, templates

## The one universal bullet formula (use for every line)
**XYZ:** "Accomplished **[X]**, as measured by **[Y]**, by doing **[Z]**."
→ *Impact* + *metric* + *how*. Lead with the strong verb or the result.

## Before → After transformations
| Before (weak) | After (strong, XYZ) |
|---|---|
| Responsible for backend APIs. | Designed **12 REST endpoints** serving **2M req/day** at **p95 <120ms**, by adding Redis caching and query indexing. |
| Worked on improving performance. | Cut page load **2.4s → 0.9s (-63%)** by code-splitting and lazy-loading, raising Lighthouse score **58 → 94**. |
| Helped migrate the database. | Migrated **300GB** Postgres→Aurora with **zero downtime** via dual-write + backfill, cutting DB cost **35%**. |
| Did testing for the app. | Added **180 unit/integration tests** (coverage **52% → 89%**), reducing prod regressions **~60%**. |
| Part of a team that built a chatbot. | Built the intent-classification module of an internal support bot handling **8k tickets/mo**, deflecting **41%**. |
| Used Docker and CI. | Containerized 6 services and built a GitHub Actions pipeline cutting deploy time **45min → 7min**. |

## Full action-verb bank
- **Built/Delivered:** Built, Designed, Developed, Engineered, Architected, Implemented, Launched, Shipped, Delivered, Created, Prototyped
- **Improved:** Optimized, Reduced, Increased, Accelerated, Streamlined, Refactored, Automated, Scaled, Simplified, Consolidated
- **Owned/Led:** Led, Owned, Drove, Spearheaded, Coordinated, Mentored, Championed, Directed, Facilitated
- **Fixed/Hardened:** Debugged, Diagnosed, Root-caused, Resolved, Hardened, Stabilized, Recovered, Migrated, Patched
- **Analyzed:** Analyzed, Measured, Instrumented, Benchmarked, Modeled, Forecasted, Profiled, Evaluated

**Ban list:** Responsible for, Helped, Worked on, Assisted, Various, Utilized (→ used), Successfully, Team player, Hard-working, Go-getter, Synergy.

## ATS-safe one-page template (single column)

```
JANE DOE
San Jose, CA 95112 | (555) 123-4567 | jane.doe@gmail.com
linkedin.com/in/janedoe | github.com/janedoe | janedoe.dev

Backend Software Engineer — 4 yrs, distributed systems in Go & Python

SKILLS
Languages : Python | Go | TypeScript | SQL
Frameworks: FastAPI | React | Node.js
Data      : PostgreSQL | Redis | Kafka
Cloud/Ops : AWS (EC2, S3, Lambda) | Docker | Kubernetes | GitHub Actions

WORK EXPERIENCE
Acme Corp, San Jose, CA | Software Engineer II | 06/2022 – Present
- Cut checkout p95 latency 40% (1.2s→0.7s) by adding a Redis cache-aside layer,
  lifting conversion 3% (~$1.1M/yr).
- Designed an event-driven order pipeline on Kafka processing 5M events/day with
  99.98% delivery, replacing a brittle cron system.
- Mentored 3 junior engineers; introduced a PR review checklist that cut defect
  escape rate ~30%.

Beta Inc, Remote | Software Engineer | 07/2020 – 05/2022
- Built 20+ REST endpoints (FastAPI) serving 2M req/day at p95 <120ms.
- Raised test coverage 52%→89% and added a CI gate, reducing prod regressions ~60%.

EDUCATION
B.S. Computer Science, 2020 | San Jose State University, CA | GPA 3.7/4.0

PROJECTS
Dependency Risk Analyzer — github.com/janedoe/deprisk
- Static analyzer scoring 4k+ C++ packages by change-risk; Streamlit UI; used by
  2 internal teams for release planning.
```

## Tailoring workflow (per application)
1. Paste the JD; extract must-have + nice-to-have skills/keywords.
2. Ensure each appears in **Skills**, echoed naturally in **Experience/Projects**.
3. Spell out abbreviations once (AWS / Amazon Web Services).
4. Reorder bullets so the JD's top skill shows in your **first** experience block.
5. Run the plain-text test + an ATS scanner; fix parse/order issues.

## Final self-audit (must all be true)
- 1 page · single column · standard headings · font ≥10pt · 0.5" margins.
- Every bullet: verb + what + **number**. Zero "Responsible for". Zero typos.
- Contact info in body (not header/footer). GPA only if ≥3.5. Projects linked.
- Every claim is defensible for a 10-minute drill-down.