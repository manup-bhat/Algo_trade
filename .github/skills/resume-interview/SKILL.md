---
name: resume-interview-mastery
description: |
  Complete, research-backed workflow for software-engineer resume writing, ATS/resume
  parsing optimization, recruiter & interviewer psychology, effective wording, AND a full
  interview study guide covering what interviewers expect, how to present projects, every
  cross-question angle, and study material for every SDLC phase (planning, design, development,
  testing, deployment). Use when: writing or rewriting a resume, making a resume ATS-friendly,
  fixing a resume that gets no callbacks, quantifying achievements, writing bullet points,
  crafting a professional summary/headline, tailoring a resume to a job description, optimizing
  keywords, understanding how recruiters scan resumes (6-second scan, F-pattern), preparing for
  a technical interview, behavioral interview, STAR/STARR stories, "tell me about your project",
  project deep-dive, anticipating interviewer cross-questions, system design discussion of your
  own project, explaining architecture/tradeoffs/testing/scaling, preparing SDLC talking points,
  building a personal project to talk about, or running mock interviews with Copilot.
  Trigger on: "write my resume", "review my resume", "resume bullet points", "make resume ATS
  friendly", "quantify achievements", "professional summary", "resume keywords", "tailor resume",
  "why no interview calls", "how recruiters read resumes", "prepare for interview", "behavioral
  interview", "STAR method", "tell me about yourself", "explain my project", "project questions",
  "cross questions on project", "what will interviewer ask", "system design my project",
  "SDLC questions", "mock interview", "interview study guide".
argument-hint: 'What you need (e.g. "rewrite my resume bullets", "make my resume ATS-safe", "prep me to explain my e-commerce project", "list cross-questions for my RAG project", "mock behavioral interview")'
---

# Resume & Interview Mastery Skill

> A resume gets you *in the door*; the interview gets you *the offer*. Most qualified engineers
> fail not because they lack skill, but because they **frame it poorly** on paper and **narrate it
> poorly** in the room. This skill fixes both.

**Two pillars:**
- **PART A — Resume Mastery**: ATS parsing, recruiter psychology, structure, wording, tailoring.
- **PART B — Interview Study Guide**: what interviewers evaluate, telling project stories, the
  full cross-question catalog, and SDLC-phase study material.

---

## ⚡ Smart Routing — Read Only What You Need

| User intent | Go to |
|---|---|
| "Write / rewrite / review my resume" | A1 → A3 → A4 → A9 |
| "Make my resume ATS-friendly / it gets no calls" | A1, A7, A10 |
| "Fix my bullet points / quantify impact" | A4 (XYZ formula + verbs) |
| "Professional summary / headline" | A5 |
| "Tailor resume to this job description" | A7 |
| "How do recruiters read resumes?" | A2 |
| "Prepare me for interviews (overview)" | B1 → B2 |
| "Help me explain my project" | B3 |
| "What cross-questions will I get on my project?" | B4 |
| "Study material by SDLC phase" | B5 |
| "Discuss my project's architecture / scaling" | B6 |
| "Behavioral / STAR / tell me about a time…" | B7 |
| "Coding interview approach" | B8 |
| "What should I ask the interviewer?" | B9 |
| "Run a mock interview" | B10 |

---

# PART A — RESUME MASTERY

## A1. ATS-Friendly Setup (make it *machine-readable* first)

Most companies parse resumes through an **Applicant Tracking System (ATS)** before any human
sees them. If the parser mangles your resume, you're rejected before page one. Hard rules:

- **Author in Microsoft Word or Google Docs; export to PDF.** Text must be selectable/highlightable
  (that is the precondition for clean parsing). Never build a resume in Photoshop, Canva, or
  graphic online builders — they produce image-like or non-standard structures the ATS misreads.
- **No headers/footers** for real content — many parsers ignore those regions. Put contact info in
  the body. Use narrow **0.5" margins** to reclaim space instead.
- **Standard fonts only**: Arial, Calibri, or Garamond. Minimum **10pt** for human readability.
  Exotic fonts can convert glyphs into unreadable characters.
- **Standard section headings** in a standard order (see A3). Do **not** put symbols/emojis in
  headings. Use a plain `|` or a tab as a divider, never decorative glyphs.
- **Single column, no tables/text-boxes for layout**, no images/icons for critical text. Two-column
  and heavily-designed templates frequently parse out-of-order.
- **One page** for < ~10 years of experience.

## A2. Recruiter & Interviewer Psychology (what they *actually* see)

Understand the human on the other side, then design for their behavior:

- **The scan is brutally short.** On the first pass a recruiter spends only **~6–8 seconds**
  deciding keep-or-toss (eye-tracking research; commonly cited "6-second scan," later measured
  ~7.4s). They are **pattern-matching for keywords and signals**, not reading prose.
- **They scan in an F-pattern / reverse-L**: top-left → across the top → down the left edge.
  Put your strongest signal **top-left and early**. Buried achievements are invisible.
- **They read titles, companies, dates, and the first few words of each bullet.** Front-load each
  bullet with the **impact/verb**, not with "Responsible for…".
- **The hiring manager scans for the skills the job description names.** ATS and recruiters echo
  that JD. So your job is to make the match **obvious in seconds** (see A7).
- **Trust signals**: recognizable companies, quantified results, brand-name tech, a GitHub/portfolio
  link, and clean formatting. **Red flags**: walls of text, no numbers, vague buzzwords, typos,
  unexplained gaps, inconsistent tense/formatting.

**Design implication:** every line competes for a fraction of a second. Maximize *signal density*.

## A3. Structure & Section Order

Standard, recruiter-preferred order (ATS-safe headings):

1. **Name** (top of page, largest text)
2. **Contact Information** — personal phone, City/State/Zip, personal email (Gmail is fine),
   **LinkedIn**. Good-to-have: **GitHub**, portfolio/website, Stack Overflow, competitive-coding
   profiles (with rank/badges if impressive).
3. **Professional Summary** (as a 1-line headline — see A5)
4. **Skills**
5. **Work Experience**  *(students / < 3 yrs experience → put **Education** before Experience)*
6. **Education**
7. **Projects**
8. **Awards / Certifications** (optional, only if relevant)

## A4. Writing Effective Bullets — the core skill

**The XYZ formula (Google / Laszlo Bock):**
> **"Accomplished [X], as measured by [Y], by doing [Z]."**

Every strong bullet = **Action verb → what you did → quantified impact**. Lead with the result
or the strong verb, then the how.

| Weak (duty) | Strong (accomplishment) |
|---|---|
| "Responsible for the payment service." | "Cut checkout latency **40%** (p95 1.2s→0.7s) by adding a Redis cache-aside layer, lifting conversion **3%**." |
| "Worked on the search feature." | "Built an autocomplete search over **5M** products, reducing 'no-result' queries **28%**." |
| "Wrote unit tests." | "Raised coverage **55%→90%** and cut prod regressions **~60%** via a CI test gate." |

**Rules:**
- **Quantify everything** — %, time saved, latency, throughput, users, revenue, cost, scale, error
  rate. If you lack an exact number, use a **defensible estimate** and be ready to justify it.
- **Start with a strong past-tense action verb**; never "Responsible for" / "Helped with".
- **One idea per bullet**, ~1–2 lines. Cut filler ("successfully", "various", "utilized"→"used").
- **Show scope + impact + your specific contribution** (interviewers cross-examine team-vs-you).

**Action-verb bank (categorized):**
- *Built/Shipped*: Built, Designed, Developed, Implemented, Launched, Shipped, Engineered, Architected
- *Improved*: Optimized, Reduced, Increased, Accelerated, Streamlined, Refactored, Automated, Scaled
- *Led/Owned*: Led, Owned, Drove, Coordinated, Mentored, Spearheaded, Championed
- *Solved*: Debugged, Diagnosed, Resolved, Root-caused, Hardened, Migrated, Recovered
- *Analyzed*: Analyzed, Modeled, Measured, Instrumented, Forecasted, Benchmarked

**Avoid:** first person ("I"), pronouns, articles where droppable, buzzword soup
("dynamic self-starter, synergy, hard-working team player"), and unverifiable superlatives.

## A5. Professional Summary & Headline

- Replace the "Professional Summary" title with a **< 10-word headline** — like a sharpened
  LinkedIn headline — then optionally 1–2 lines (**< 50 words**).
- Start with the **role noun** ("Software Engineer", "Front End Engineer", "ML Engineer").
- Use **active voice + action words**; answer **why you fit this job**.

Examples:
- *"Full-Stack Software Engineer — 4 yrs, Ruby on Rails & PostgreSQL, e-commerce/payments domain expert."*
- *"Backend Engineer scaling distributed systems; led 3 teams, mentored 12+ engineers."*
- *"CS senior focused on AI/ML; two internships across full-stack and ML engineering."*

## A6. Section-by-Section Content

- **Skills**: `[[Category]] : skill | skill | skill`. Group by **Languages / Frameworks / Databases /
  Cloud & Tools**. List real, defensible skills (you *will* be quizzed). Spell out abbreviations at
  least once (Amazon Web Services (AWS)) for ATS keyword matching.
- **Work Experience**: reverse-chronological.
  `Company, Location | Title | MM/YYYY – MM/YYYY`, then XYZ bullets (top accomplishments only).
- **Education**: `Degree, Grad Year | University, Location`. Include **GPA only if ≥ 3.5/4.0**.
  Add honors, leadership, notable coursework (early-career only).
- **Projects**: ≥ 2, each **linked** (GitHub/live). One line of impact + tech + your role. Prefer
  projects that demonstrate JD-relevant skills and that you can defend in depth (see PART B).
- **Awards/Certifications**: `Year | Quantified distinction | Event` (e.g. "2024 | 1st of 50 teams | HackX").

## A7. Keyword Optimization & Tailoring (the callback lever)

- **Mine the job description** for must-have and nice-to-have skills. Mirror its exact wording in
  **Skills**, and **echo the same keywords naturally** in Experience/Projects.
- **Frequency + placement matter**: some ATS weight a skill by how often/early it appears, and may
  infer years-of-experience from where a keyword sits relative to a job's dates.
- **Spell out abbreviations** and include both forms (GCP / Google Cloud Platform).
- **Generalize to a role** if applying broadly: collect 3–5 JDs → run them through a word/phrase
  frequency tool → incorporate the recurring skills you genuinely have.
- **Never keyword-stuff** dishonestly — a human reads it next, and interviewers verify every claim.

## A8. "Less Is More" — prioritize ruthlessly

- **One page.** A few *great* achievements beat many *average* ones.
- Cut anything not aligned to the target role. Consistency of tense, punctuation, and date format
  signals attention to detail (which the job requires).
- Don't spray applications across many roles at one company — recruiters see all your applications
  and read it as a lack of focus.

## A9. Resume Review Checklist

- [ ] Parses cleanly (see A10 plain-text test) and is **1 page**, 0.5" margins, standard font ≥10pt.
- [ ] Top-left holds your strongest signal; headline present.
- [ ] Every experience/project bullet: **verb + what + quantified impact** (XYZ).
- [ ] No "Responsible for", no first person, no buzzword filler, **zero typos**.
- [ ] Skills mirror the JD; abbreviations spelled out; keywords echoed in Experience.
- [ ] Projects are linked and defensible in a deep-dive.
- [ ] Consistent tense/dates/formatting; dates in `MM/YYYY`.
- [ ] GPA only if ≥3.5; contact info in the **body**, not header/footer.

## A10. Resume Parsing — how ATS reads it + how to test

**How parsing works (mental model):** the ATS extracts raw text → segments it by recognizing
**standard headings** → maps fields (name, contact, employer, title, dates, skills) → scores
against the JD. Non-standard layout, tables, columns, headers/footers, and images break these steps.

**Tests before you apply:**
1. **Plain-text test** — copy the whole resume, paste into Notepad/plain text. If order scrambles,
   characters break, or bullets vanish, the ATS will choke too. Fix until the plain text reads well.
2. **Scanner tools** — run it through an ATS-style scanner / targeted-resume checker to see the
   keyword match and readability score against a specific JD.
3. **Recognizable-headings check** — ensure headings are literally "Work Experience", "Skills",
   "Education", "Projects" (no cute renames).

**Application-form caution:** if a company's portal asks you to re-type Experience/Education, fill it
carefully — often only *that* structured data is screened, and your PDF may never be read.

---

# PART B — INTERVIEW STUDY GUIDE

## B1. What Interviewers Actually Evaluate

Interviewers are collecting **signal**, not trivia. Across rounds they score:

- **Technical competence** — correctness, data-structure/algorithm choice, complexity awareness,
  clean code, testing instinct.
- **Problem-solving process** — how you clarify, decompose, weigh alternatives, and handle the
  unknown (they care *how you think*, not just the final answer).
- **Communication** — can you explain reasoning clearly, take a hint, and collaborate?
- **Ownership & depth** — for projects: did *you* build it, do you understand *why* each decision
  was made, and can you defend tradeoffs?
- **Behavioral fit / seniority** — conflict handling, leadership, learning from failure, values
  alignment. Behavioral weight is **rising** as AI writes more code.

**Golden rule:** *Never claim on your resume what you can't defend for 10 minutes of drill-down.*

## B2. Interview Formats & Pipeline

Typical stages (early → late): **Quiz** → **Online coding assessment** → (sometimes) **Take-home**
→ **Phone screen** (collaborative editor; often can't run code) → **Onsite** (multiple rounds:
coding + system design + behavioral). Know each format so nothing surprises you:

- **Coding**: 1–2 algorithm problems in a shared editor. Practice writing runnable, correct code
  without an execution crutch.
- **System design** (mid/senior): open-ended design of a real system — *you* lead the conversation.
- **Behavioral**: your history + "tell me about a time…" + values.

## B3. Telling Project Stories — the Framework

This is the skill the user asked for most: **how to narrate a project so an interviewer "gets it"
and trusts you built it.** Prepare each project on **two tracks**:

### Track 1 — The 60–90s pitch (STAR / STAR-R)
- **Situation** — context + why it mattered (1 sentence).
- **Task** — the problem/goal and constraints (scope, deadline, scale).
- **Action** — *what YOU did*, the options you weighed, and **why you chose** your approach. This is
  the heart — interviewers hire for repeatable **behaviors/decisions**, not the project itself.
- **Result** — quantified outcome (latency, users, revenue, adoption).
- **(R) Reflection** — what you learned / would do differently (adds a strong seniority signal).

### Track 2 — The deep-dive map (be ready to zoom into any layer)
Prepare a mental diagram: **problem → users → requirements → architecture → data model → key
components → hardest bug → tradeoffs → testing → deployment → results → what's next.** Interviewers
pick a thread and pull. Know the numbers (QPS, data size, latency, team size, your % of the code).

### Narration tips
- Start **top-down** (one-line "what and why"), then drill on request — don't data-dump.
- Say **"I" for your work, "we" for the team**, and be honest about boundaries.
- Volunteer **tradeoffs and alternatives** ("I chose X over Y because…") — it signals maturity.
- Keep a **whiteboard-ready diagram** in your head; offer to sketch it.

## B4. Project Cross-Question Catalog — *every angle an interviewer probes*

Prepare answers to **all** of these for each headline project. This is the "every angle / cross
questions" the user asked for:

**Motivation & requirements**
- Why did this project exist? Who were the users? What problem did it solve?
- What were the functional and **non-functional requirements** (scale, latency, availability)?
- How did you gather/validate requirements? What was explicitly out of scope?

**Your role & the team**
- What exactly did *you* build vs. the team? Which parts are you the expert on?
- How big was the team? How were tasks divided? How did you estimate effort?

**Architecture & design**
- Walk me through the architecture end-to-end. Why this structure?
- Why this **tech stack / language / framework / database**? What did you reject and why?
- Show the **data model / schema**. Why normalized vs. denormalized? Indexing choices?
- Monolith vs. services — why? Where are the boundaries and why there?
- How do components communicate (REST/RPC/queue) and why?

**Tradeoffs & alternatives (the maturity test)**
- What were the main tradeoffs? What would you do differently now?
- If you had 10× the time / a bigger team / more budget, what changes?
- What's the weakest part of the design? What technical debt did you accept and why?

**Scale, performance, reliability**
- What was the load (QPS, data volume, concurrent users)? Where's the bottleneck?
- How would you scale it 10×/100×? (caching, load balancing, horizontal scaling, sharding,
  async/queues, CDN, read replicas — see B6).
- What's the p95/p99 latency? How did you measure and improve it?
- What happens when component X fails? Single points of failure? Failover/replication?
- How do you ensure consistency vs. availability (CAP tradeoffs)?

**Data & correctness**
- Concurrency/race conditions — how handled (locks, transactions, idempotency)?
- How do you guarantee data integrity? Migrations without downtime?

**Security**
- AuthN/AuthZ approach? How do you prevent the OWASP Top 10 (injection, XSS, SSRF, broken access
  control)? Secrets management? Input validation at boundaries? Encryption in transit/at rest?

**Testing & quality (see B5-Testing)**
- How did you test it? Unit vs. integration vs. e2e coverage? What's *not* tested and why?
- How did you catch regressions? How would you reproduce a reported bug?

**Delivery & operations**
- CI/CD pipeline? How do you deploy? Rollback strategy? Feature flags?
- How is it monitored (logs, metrics, alerts, tracing)? How do you know it's healthy?
- Biggest production incident — what happened and how did you respond (root cause + prevention)?

**Reflection**
- Hardest bug you fixed and how? What did you learn? What are you proudest of? What's next?

> **Prep method:** for each project, write a one-line answer to every bullet above. If any answer is
> weak, that's exactly where the interviewer will push — patch it *before* the interview.

## B5. Study Material by SDLC Phase (planning → dev → test → deploy)

The user asked for "every phase and planning development and testing and every detail." For each
phase, know the **concepts, your decisions, and the questions asked**:

### 1) Planning & Requirements
- **Study**: functional vs. non-functional requirements; user stories; acceptance criteria; scoping
  (MoSCoW); estimation (story points, t-shirt sizing); risk identification; success metrics/KPIs.
- **Interviewer asks**: "How did you decide what to build first? How did you handle ambiguous or
  changing requirements? What did you deprioritize and why?"

### 2) Design & Architecture
- **Study**: high-level design, component diagrams, data modeling, API design (REST/RPC), design
  patterns, SOLID/DRY/KISS/YAGNI, monolith vs. microservices, sync vs. async, chosen datastore
  (SQL vs. NoSQL) with justification.
- **Interviewer asks**: "Draw the architecture. Why these boundaries? Why this DB? What are the
  failure modes?" (See B6 for the toolbox.)

### 3) Development / Implementation
- **Study**: clean code, version control/branching (feature branches, PRs, code review), commit
  hygiene, pair/mob programming, handling technical debt, dependency management, coding standards,
  the smallest-correct-change discipline.
- **Interviewer asks**: "How did you keep code quality high across the team? How did you handle code
  reviews and merge conflicts? A hard implementation problem you solved?"

### 4) Testing & QA
- **Study**: the **test pyramid** (unit → integration → e2e), TDD, property-based testing, mocking/
  stubbing, coverage vs. meaningful tests, edge cases, regression tests, load/performance testing,
  security testing, test data management, flaky-test handling.
- **Interviewer asks**: "How did you test this? What's your unit/integration split? How do you test
  the unhappy paths? How would you write a failing test to reproduce a reported bug, then fix it?"

### 5) Deployment & Release
- **Study**: CI/CD pipelines, build/artifact management, environments (dev/staging/prod),
  blue-green & canary deploys, feature flags, database migrations with zero downtime, rollback,
  Infrastructure-as-Code, containers/orchestration basics.
- **Interviewer asks**: "How does code get to production? How do you roll back? How do you ship a
  risky change safely?"

### 6) Operations, Monitoring & Maintenance
- **Study**: logging, metrics, distributed tracing, alerting, SLIs/SLOs/error budgets, on-call,
  incident response, postmortems/root-cause analysis, capacity planning, observability.
- **Interviewer asks**: "How do you know the system is healthy? Walk me through an incident. What
  was the root cause and how did you prevent recurrence?"

> **Tip for building a "talk-about-able" project:** deliberately touch *every* phase — write tests,
> add CI, deploy it, add basic monitoring, and keep a short design doc. Then you can answer any
> phase question from real experience.

## B6. System-Design Toolbox for Discussing Your Project

Know these well enough to justify choices (and to answer "how would you scale it?"):

- **Approach a design in 4 steps**: (1) clarify **use cases, constraints, assumptions** (users, QPS,
  read:write ratio, data size); (2) **high-level design** (main components + connections); (3)
  **deep-dive core components** (schema, APIs, algorithms); (4) **scale it** (find bottlenecks,
  apply patterns). *Everything is a tradeoff.*
- **Building blocks**: DNS, CDN, load balancer (L4/L7), reverse proxy, app/service layer,
  **database** (RDBMS vs. NoSQL; replication, federation, **sharding**, denormalization, indexing),
  **cache** (cache-aside, write-through, write-behind; Redis/Memcached; invalidation), **async**
  (message/task queues, back-pressure), **communication** (HTTP, TCP vs. UDP, REST vs. RPC).
- **Core tradeoffs**: performance vs. scalability, latency vs. throughput, **CAP** (consistency vs.
  availability under partition), strong vs. eventual consistency, **availability in 9s**.
- **Reliability**: failover (active-passive/active-active), replication (master-slave/master-master),
  redundancy, avoiding single points of failure.
- **Security basics**: encrypt in transit & at rest; **parameterized queries** (no SQL injection);
  sanitize all input (XSS); least privilege.

## B7. Behavioral Interview Mastery

Companies won't hire a "brilliant jerk." Behavioral rounds assess collaboration, leadership,
conflict handling, and **seniority**.

- **Use STAR(R)** (see B3). Emphasize **Actions** — the repeatable behaviors they're buying.
- **Build a story bank**: pick **3–5 high-impact, high-complexity, high-your-involvement** projects.
  One rich project usually covers many themes (conflict, ambiguity, leadership, failure). For each,
  write STAR bullets (not a memorized script).
- **Prepare the "Big Three"** everyone gets:
  1. **"Tell me about yourself"** — a crisp 60–90s self-intro (present → relevant past → why here).
  2. **"Your most impactful/favorite project"** — intersection of impact × scope × your ownership.
  3. **"A time you had a conflict"** — the most common soft-skill question.
- **Cover the signal areas**: conflict, dealing with ambiguity, failure/mistake + learning, leading/
  mentoring, data-driven decisions, going beyond scope, disagreement with a manager/peer.
- **Map to company values** — research the target company's principles and have a matching story
  for each.
- **Practice out loud** (with Copilot — see B10). Write bullets, verbalize; don't memorize prose.

## B8. Coding Interview Approach (process = signal)

1. **Clarify** inputs, outputs, constraints, edge cases before coding.
2. **Work an example by hand**; state a brute-force, then optimize (discuss time/space complexity).
3. **Think out loud** — communicate the plan; take hints gracefully.
4. **Write clean, correct code**; handle edge cases; you often can't run it, so **dry-run** it.
5. **Test**: walk through normal + edge cases; state complexity; mention improvements.
- Practice **patterns**, don't memorize answers. Pick **one language** you're fluent in
  (Python/Java/C++/JS are common) — don't learn a new one for interviews.

## B9. Questions to Ask the Interviewer (you're being scored here too)

- "What does success look like in this role in the first 6–12 months?"
- "How does the team handle code review, testing, and deployment?"
- "What's the biggest technical challenge the team faces right now?"
- "How are technical decisions made and disagreements resolved?"
- "What does on-call / incident response look like?"
Avoid asking only about perks; ask about **engineering culture and impact**.

## B10. Mock-Practice Loop with Copilot

Use this skill to run realistic drills:
- **"Mock behavioral"**: Copilot asks a behavioral question, you answer, it critiques STAR structure,
  specificity, and metrics, then asks **follow-ups** and pushes on weak spots.
- **"Project grill"**: give your project; Copilot fires the **B4 cross-question catalog** one at a
  time, escalating depth, flagging any answer that's vague or unverifiable.
- **"Resume pass"**: paste your resume; Copilot runs the **A9 checklist**, rewrites weak bullets with
  the **XYZ formula**, and lists JD keywords you're missing.
- **"SDLC drill"**: Copilot quizzes you phase-by-phase (B5) on a chosen project.

---

## Quick Reference Card

- **Resume**: ATS-safe (Word→PDF, 1 col, standard headings, 0.5" margins, ≥10pt) · 1 page ·
  top-left = strongest signal · every bullet = **verb + what + quantified impact (XYZ)** ·
  mirror the JD keywords · zero typos · defensible claims only.
- **Interview**: interviewers buy **how you think + repeatable behaviors** · narrate projects
  **top-down then deep** (STAR-R + deep-dive map) · pre-answer the **B4 cross-question catalog** ·
  know **every SDLC phase** · lead system-design in **4 steps**, everything a tradeoff · build a
  **3–5 story bank** for behavioral · practice **out loud**.

## Sources (research-backed)
- Tech Interview Handbook — *FAANG-ready resume guide* (ATS, structure, keywords, tools).
- Tech Interview Handbook — *Software Engineer interview guide* (formats, coding, system design,
  behavioral, negotiation).
- Tech Interview Handbook — *Behavioral interviews* (STAR/STAR-R, story bank, Big Three).
- Google/Laszlo Bock — the **XYZ résumé formula**.
- Eye-tracking résumé research — the **~6–8s recruiter scan** and **F-pattern**.
- *The System Design Primer* (donnemartin) — design approach, scaling patterns, CAP, caching, DBs.