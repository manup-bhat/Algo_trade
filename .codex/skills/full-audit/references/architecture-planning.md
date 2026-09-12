# Architecture & Planning — Expert-Level Application Design

> "Architecture is about the important stuff. Whatever that is." — Ralph Johnson (via Martin Fowler)
>
> "The goal of software architecture is to minimize the human resources required to build
> and maintain the required system." — Robert C. Martin (Clean Architecture)

This reference covers architecture decisions, data flow design, application type selection,
and the experienced developer's approach to planning new applications or evaluating existing
architecture. Use this for new application planning OR for auditing existing architecture.

---

## When to Use This Reference

| Scenario | What to Focus On |
|----------|-----------------|
| **Planning a new application from scratch** | Application type selection → Architecture pattern → Data flow → Tech stack → Project structure |
| **Auditing existing architecture** | Architecture anti-patterns → Layer violations → Coupling analysis → Scalability assessment |
| **Deciding monolith vs microservices** | Team size → Deployment complexity → Domain boundaries → Conway's Law |
| **Evaluating data flow** | Request lifecycle → Data transformation boundaries → State management strategy |
| **Making a technology decision** | Decision criteria → ADR (Architecture Decision Record) → Reversibility assessment |

---

## Architecture Pattern Selection — By Application Type

### Choose the Right Architecture for Your Application

| Application Type | Recommended Architecture | Data Flow | Key Concern |
|-----------------|------------------------|-----------|-------------|
| **SaaS Product (< 5 devs)** | Modular Monolith | Request → Controller → Service → Repository → DB | Ship fast, refactor later |
| **SaaS Product (5-20 devs)** | Modular Monolith → Microservices (evolve) | API Gateway → Services → Shared DB or per-service DB | Team autonomy + consistency |
| **Enterprise Internal Tool** | Monolith + Clean Architecture | UI → API → Domain → Infrastructure | Maintainability, single deploy |
| **E-Commerce Platform** | Modular with Event-Driven | Order events → Payment → Inventory → Shipping | Eventual consistency, reliability |
| **Real-Time App (Chat/Games)** | Event-Driven + WebSocket | Client ↔ WebSocket Server ↔ Message Broker ↔ Services | Low latency, connection management |
| **Data Pipeline / ETL** | Event-Driven / Batch Processing | Source → Ingest → Transform → Load → Serve | Throughput, idempotency, retry |
| **Mobile Backend (BaaS)** | API-First + Serverless | Mobile → API Gateway → Lambda/Functions → DB | Scalability, cost optimization |
| **AI/ML Application** | Microservices + Queue | API → Queue → ML Worker → Result Store → Notify | Long-running jobs, GPU scaling |
| **Static Site / Blog** | JAMstack / SSG | Build → CDN → Client (hydrate if needed) | Performance, simplicity |
| **CLI Tool / Library** | Single module / Package | Input → Parse → Execute → Output | Simplicity, zero dependencies |

---

## Architecture Patterns — Deep Reference

### 1. Modular Monolith (Default for Most Applications)

> "Start with a monolith. Decompose to microservices only when you have a proven need."
> — Martin Fowler

```
┌─────────────────────────────────────────────────┐
│                  APPLICATION                      │
├─────────────────────────────────────────────────┤
│  Module: Auth    │ Module: Orders │ Module: Users │
│  ┌─────────────┐ │ ┌────────────┐ │ ┌──────────┐ │
│  │ Controller  │ │ │ Controller │ │ │Controller│ │
│  │ Service     │ │ │ Service    │ │ │Service   │ │
│  │ Repository  │ │ │ Repository │ │ │Repository│ │
│  └─────────────┘ │ └────────────┘ │ └──────────┘ │
├─────────────────────────────────────────────────┤
│              Shared: Database, Config, Infra      │
└─────────────────────────────────────────────────┘
```

**When to use**: Team < 10 devs, single deployment target, fast iteration needed.
**Key rules**:
- Each module has clear boundaries (no direct cross-module DB access)
- Modules communicate through defined interfaces (not DB joins across modules)
- Can extract to microservice later by splitting along module boundaries

### 2. Clean Architecture (Hexagonal / Ports & Adapters)

```
┌─────────────────────────────────────────────────┐
│                  INFRASTRUCTURE                    │
│  (DB, HTTP, File System, External APIs, Queue)    │
├─────────────────────────────────────────────────┤
│              INTERFACE ADAPTERS                    │
│  (Controllers, Presenters, Gateways, Repos)      │
├─────────────────────────────────────────────────┤
│               USE CASES / APPLICATION             │
│  (Business operations, orchestration)             │
├─────────────────────────────────────────────────┤
│                   ENTITIES / DOMAIN               │
│  (Business rules, pure logic, no dependencies)    │
└─────────────────────────────────────────────────┘

Dependency Rule: Dependencies point INWARD only.
Inner layers NEVER import from outer layers.
```

**When to use**: Complex domain logic, need to swap infrastructure, long-lived systems.
**Key rules**:
- Domain layer has ZERO dependencies on frameworks, databases, or HTTP
- Use cases orchestrate domain objects without knowing about infrastructure
- Infrastructure adapts to the application (not the other way around)
- Testable without any real infrastructure (mock at the port boundary)

### 3. Microservices

```
┌──────┐     ┌──────────┐     ┌─────────┐
│Client│────▶│API Gateway│────▶│Service A│──▶[DB A]
└──────┘     └──────────┘     └─────────┘
                   │           ┌─────────┐
                   ├──────────▶│Service B│──▶[DB B]
                   │           └─────────┘
                   │           ┌─────────┐
                   └──────────▶│Service C│──▶[Queue]──▶[Workers]
                               └─────────┘
```

**When to use**: Team > 15 devs, independent deployment needed, different scaling requirements per service.
**Prerequisites** (don't start with microservices unless you have ALL of these):
- [ ] CI/CD pipeline per service
- [ ] Container orchestration (Kubernetes, ECS)
- [ ] Service discovery and load balancing
- [ ] Distributed tracing and centralized logging
- [ ] Team ownership model (one team per service)

**Red flags — you're NOT ready for microservices**:
- Team < 5 people
- No CI/CD automation
- Can't answer "what are your bounded contexts?"
- No observability infrastructure
- Doing it because "Netflix does it"

### 4. Event-Driven Architecture

```
┌─────────┐     ┌────────────┐     ┌──────────┐
│Producer │────▶│Message Broker│────▶│Consumer A│
│(Service)│     │(Kafka/RabbitMQ)   │(Service) │
└─────────┘     └────────────┘     └──────────┘
                       │            ┌──────────┐
                       └───────────▶│Consumer B│
                                    │(Service) │
                                    └──────────┘
```

**When to use**: Decoupled services, eventual consistency acceptable, complex workflows, audit trails needed.
**Key patterns**:
- **Event Sourcing**: Store events, not state. Reconstruct state by replaying events.
- **CQRS**: Separate read models from write models. Optimize each independently.
- **Saga Pattern**: Manage distributed transactions through event choreography.
- **Outbox Pattern**: Publish events reliably alongside DB writes.

### 5. Serverless / FaaS

**When to use**: Unpredictable traffic, cost-sensitive, event-triggered workloads, rapid prototyping.
**When NOT to use**: Long-running processes (> 15 min), consistent high traffic, cold-start sensitive.

---

## Data Flow Design — By Layer

### The Request Lifecycle (Web Application)

```
Client Request
    │
    ▼
┌─────────────────┐
│  EDGE / CDN     │  Static assets, caching, DDoS protection
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  LOAD BALANCER  │  Distribute traffic, health checks, SSL termination
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  API GATEWAY    │  Auth, rate limiting, request validation, routing
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  CONTROLLER     │  Parse request, call use case, format response
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  SERVICE LAYER  │  Business logic, orchestration, authorization
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  REPOSITORY     │  Data access, query building, caching
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│  DATABASE       │  Persistence, indexing, transactions
└─────────────────┘
```

### Data Transformation Boundaries

Data should be validated and transformed at SPECIFIC boundaries:

| Boundary | Responsibility | Example |
|----------|---------------|---------|
| **Client → API** | Schema validation, sanitization | Zod/Pydantic validates request body |
| **Controller → Service** | Convert DTO to domain object | `CreateUserRequest` → `User` entity |
| **Service → Repository** | Convert domain to persistence model | `User` entity → DB row/document |
| **Repository → Service** | Convert persistence model to domain | DB row → `User` entity |
| **Service → Controller** | Convert domain to response DTO | `User` entity → `UserResponse` |
| **External API → Service** | Validate external data, adapt to internal model | Third-party response → internal format |

### State Management Strategy by App Type

| App Type | State Strategy | Where State Lives |
|----------|---------------|-------------------|
| **Server-rendered (SSR)** | Server state + minimal client | Session/DB on server, cookies for auth |
| **SPA (React/Vue/Angular)** | Client state + server sync | React Query/TanStack, Zustand, Redux |
| **Mobile app** | Local-first + sync | SQLite/Realm locally, sync to API |
| **Real-time app** | Shared state via WebSocket | Server is source of truth, clients subscribe |
| **Static site** | No client state (or minimal) | All state at build time |

---

## Technology Stack Decision Framework

### How to Choose a Tech Stack

| Factor | Weight | Questions to Ask |
|--------|--------|-----------------|
| **Team expertise** | Highest | What does the team already know? Learning curve vs deadline? |
| **Ecosystem maturity** | High | Libraries available? Community active? Stack Overflow answers? |
| **Hiring pool** | High | Can we hire developers for this stack? |
| **Performance requirements** | Medium | Do we need sub-ms latency? High throughput? Low memory? |
| **Deployment target** | Medium | Cloud? Edge? Embedded? Serverless? Container? |
| **Maintenance horizon** | Medium | Will this exist in 5 years? 10 years? Is it EOL? |
| **Compliance requirements** | Variable | Regulated industry? Need specific certifications? |

### Stack Recommendations by Application Type

| Application | Backend | Frontend | Database | Infra |
|-------------|---------|----------|----------|-------|
| **SaaS MVP** | Node.js/FastAPI | Next.js/React | PostgreSQL | Vercel/Railway |
| **Enterprise** | Java Spring/C# .NET | React/Angular | PostgreSQL/Oracle | Kubernetes |
| **Real-time** | Go/Elixir/Node.js | React + WebSocket | Redis + PostgreSQL | Kubernetes |
| **Data-heavy** | Python/Scala | React/Dash | PostgreSQL + ClickHouse | Kubernetes + Spark |
| **Mobile backend** | Node.js/Go | React Native/Flutter | PostgreSQL + Redis | AWS/GCP Serverless |
| **AI/ML** | Python (FastAPI) | React/Streamlit | PostgreSQL + Vector DB | GPU Cloud + Queue |

---

## Project Structure Patterns

### Standard Web Application Structure (Any Language)

```
project/
├── src/                    # Source code
│   ├── modules/            # Feature modules (vertical slices)
│   │   ├── auth/           # Auth feature: controller, service, repository, tests
│   │   ├── users/          # Users feature
│   │   └── orders/         # Orders feature
│   ├── shared/             # Shared utilities, base classes, types
│   │   ├── middleware/     # Cross-cutting middleware
│   │   ├── utils/          # Pure utility functions
│   │   └── types/          # Shared type definitions
│   ├── infrastructure/     # External service adapters
│   │   ├── database/       # DB connection, migrations
│   │   ├── cache/          # Redis/cache adapter
│   │   └── queue/          # Message queue adapter
│   └── config/             # App configuration, env parsing
├── tests/                  # Test files (mirror src structure)
├── docs/                   # Documentation
├── scripts/                # Build, deploy, dev scripts
├── .github/                # CI/CD workflows
└── docker/                 # Container configuration
```

### Module Internal Structure (Feature Slice)

```
modules/orders/
├── orders.controller.ts    # HTTP layer: routes, request parsing, response formatting
├── orders.service.ts       # Business logic: validation, orchestration, rules
├── orders.repository.ts    # Data access: queries, persistence
├── orders.types.ts         # Types/interfaces for this module
├── orders.events.ts        # Events this module emits/consumes
├── orders.test.ts          # Unit tests
└── orders.integration.ts   # Integration tests
```

---

## Architecture Decision Records (ADR)

Every significant architecture decision should be documented:

```markdown
# ADR-001: Use PostgreSQL as Primary Database

## Status: Accepted
## Date: 2026-01-15

## Context
We need a primary database for the application. Requirements:
- ACID transactions for financial data
- JSON support for flexible schemas
- Full-text search capability
- Strong ecosystem and community

## Decision
Use PostgreSQL 16+ as the primary database.

## Consequences
### Positive
- ACID compliance for critical data
- jsonb for semi-structured data without separate NoSQL
- pg_trgm and full-text search built-in
- Excellent tooling (pgAdmin, Prisma, SQLAlchemy)

### Negative
- Horizontal scaling more complex than NoSQL
- Need connection pooling for serverless deployments

### Risks
- May need read replicas at > 10k concurrent users
- Mitigation: Design for read-replica compatibility from day 1

## Alternatives Considered
- MongoDB: Good for flexible schemas but weaker ACID
- MySQL: Less feature-rich, weaker JSON support
- DynamoDB: Vendor lock-in, complex access patterns
```

---

## Architecture Anti-Patterns to Detect

When auditing existing architecture, look for these:

| Anti-Pattern | Signal | Impact | Fix |
|-------------|--------|--------|-----|
| **Big Ball of Mud** | No clear module boundaries, everything imports everything | Impossible to change safely | Define module boundaries, enforce with lint rules |
| **Distributed Monolith** | Microservices that must be deployed together | Worst of both worlds | Merge back to monolith or properly decouple |
| **Golden Hammer** | Using same tech for everything | Square pegs in round holes | Evaluate fit per problem |
| **Leaky Abstractions** | Upper layers know about lower-layer details | Tight coupling | Enforce dependency direction |
| **God Service** | One service does everything | Single point of failure, impossible to scale | Decompose by bounded context |
| **Shared Database** | Multiple services read/write same tables | Coupling through data | Each service owns its data |
| **Circular Dependencies** | A depends on B depends on A | Can't deploy independently | Extract shared logic or merge |
| **Premature Decomposition** | Split into microservices before understanding domain | Wrong boundaries, excessive coordination | Start monolith, split when boundaries are clear |
| **Resume-Driven Development** | Tech chosen because it's exciting, not because it fits | Over-complexity, team can't maintain | Choose boring technology |

---

## Scalability Assessment

### When to Scale What

| Signal | What's Overloaded | Scaling Strategy |
|--------|------------------|-----------------|
| High CPU usage | Compute | Horizontal scaling (more instances) |
| High memory usage | Memory | Vertical scaling or optimize data structures |
| Slow DB queries | Database reads | Read replicas, caching, query optimization |
| DB write contention | Database writes | Sharding, queue writes, event sourcing |
| Slow external API calls | Network I/O | Async processing, circuit breakers, caching |
| Long response times | End-to-end | CDN, edge caching, connection pooling |
| Queue backing up | Background processing | More workers, partition processing |

### Performance Budgets

| Metric | Target | Unacceptable |
|--------|--------|-------------|
| Page load (LCP) | < 2.5s | > 4s |
| API response (p50) | < 200ms | > 1s |
| API response (p99) | < 1s | > 5s |
| Time to Interactive | < 3.8s | > 7.3s |
| First Contentful Paint | < 1.8s | > 3s |

---

## Development Lifecycle — End-to-End

### The Complete Application Development Process

```
1. PLAN        ──→ Requirements, architecture, scope, estimation
2. DESIGN      ──→ Data model, API contracts, UI wireframes
3. IMPLEMENT   ──→ Build in vertical slices, smallest deployable increments
4. TEST        ──→ Unit → Integration → E2E (test pyramid)
5. REVIEW      ──→ Code review, security review, architecture review
6. DEPLOY      ──→ CI/CD, feature flags, staged rollout
7. MONITOR     ──→ Metrics, alerting, error tracking, user feedback
8. ITERATE     ──→ Feedback loop, continuous improvement
```

### Decision Points in the Lifecycle

| Decision Point | What to Decide | Key Criteria |
|---------------|---------------|-------------|
| **Before writing code** | Architecture pattern, tech stack, project structure | Team size, requirements, timeline |
| **Before each feature** | Implementation approach, scope, acceptance criteria | Complexity, risk, dependencies |
| **Before each commit** | Is this a complete, reviewable unit of work? | Atomicity, test coverage |
| **Before each deploy** | Is this safe to release? Rollback plan? | Test pass rate, feature flag |
| **After each deploy** | Is it working in production? | Metrics, error rate, user feedback |

---

## Conway's Law and Team Structure

> "Any organization that designs a system will produce a design whose structure is a
> copy of the organization's communication structure." — Melvin Conway

| Team Structure | Resulting Architecture | Best For |
|---------------|----------------------|----------|
| Single cross-functional team | Monolith / Modular monolith | Startups, small products |
| Multiple teams, shared codebase | Modular monolith with clear boundaries | Medium companies |
| Multiple teams, independent repos | Microservices | Large organizations |
| Platform team + product teams | Platform + microservices | Enterprise |

**Inverse Conway Maneuver**: Structure your teams to match the architecture you WANT, not the other way around.

---

## Architecture Audit Checklist

When auditing an existing system's architecture:

- [ ] Can you explain the architecture in one diagram? (If not → too complex or no clear pattern)
- [ ] Does dependency direction flow inward? (Infrastructure → Application → Domain)
- [ ] Can each module be tested in isolation? (If not → too coupled)
- [ ] Can you deploy a single change without deploying everything? (If not → monolith risks)
- [ ] Are boundaries aligned with business domains? (If not → wrong decomposition)
- [ ] Is the tech stack appropriate for the problem? (If not → golden hammer)
- [ ] Can a new developer understand the structure in < 1 day? (If not → too complex)
- [ ] Are architecture decisions documented? (ADRs?)
- [ ] Is there a clear data ownership model? (Who owns what data?)
- [ ] Are cross-cutting concerns handled consistently? (Auth, logging, errors)
- [ ] Can the system handle 10× current load? (Scalability headroom)
- [ ] Is there a clear path to scale when needed? (Not "we'll figure it out later")

---

## Sources

- [Martin Fowler: Software Architecture Guide](https://martinfowler.com/architecture/)
- [Martin Fowler: Microservices](https://martinfowler.com/microservices/)
- [Martin Fowler: Patterns of Enterprise Application Architecture](https://martinfowler.com/eaaCatalog/)
- [Robert C. Martin: Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [12factor.net](https://12factor.net/) — Cloud-native application methodology
- [C4 Model](https://c4model.com/) — Visualizing software architecture
- [ADR (Architecture Decision Records)](https://adr.github.io/)
- [Conway's Law](https://www.melconway.com/Home/Conways_Law.html)
- [Patterns of Distributed Systems](https://martinfowler.com/articles/patterns-of-distributed-systems/)
- [Choose Boring Technology](https://boringtechnology.club/)
