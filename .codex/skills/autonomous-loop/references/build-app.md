# Build App Workflow — Autonomous Loop Reference

When the user asks to **build an application from scratch**, follow this extended protocol
within the autonomous loop. Each numbered step is one or more loop iterations.

---

## Phase 1: Foundation (Iterations 1–5)

### Step 1: Determine Stack & Architecture

Before writing any code:
- Ask yourself: What tech stack does the user want? (or infer from context)
- What kind of app? (API, web app, CLI, library, full-stack)
- What's the minimum viable architecture?

**Decision matrix:**
| App Type | Default Stack (if not specified) |
|----------|-------------------------------|
| REST API | Node.js + Express/Fastify OR Python + FastAPI |
| Web App | Next.js + TypeScript OR React + Vite |
| CLI Tool | Node.js + Commander OR Python + Click |
| Full-Stack | Next.js (frontend + API routes) |
| Library/Package | TypeScript + tsup OR Python + setuptools |

### Step 2: Scaffold Project Structure

Create the project skeleton in one iteration:
```
project-root/
├── src/              # Source code
├── tests/            # Test files
├── package.json      # OR pyproject.toml, Cargo.toml, etc.
├── tsconfig.json     # If TypeScript
├── .gitignore
└── README.md         # Brief description only
```

**Rules:**
- Use the standard layout for the detected ecosystem
- Include only files needed NOW — don't pre-create empty files
- Set up the build tool configuration correctly from the start

### Step 3: Install Dependencies

Run the package manager to install:
- Core framework (express, fastapi, next, etc.)
- TypeScript + types (if applicable)
- Test framework (jest, vitest, pytest)
- Linting (eslint, ruff — only if the ecosystem expects it)

**Verify:** `npm install` / `pip install -e .` exits with code 0.

### Step 4: Create Entry Point

Write the minimal running application:
- A server that starts and responds to at least one request
- OR a CLI that parses args and prints help
- OR a library that exports at least one function

**Verify:** The app starts without errors. Server responds to health check.

### Step 5: Verify Foundation

Run the full verification suite:
- App starts ✅
- Linter passes ✅
- Type checker passes ✅ (if TypeScript)
- One smoke test passes ✅

---

## Phase 2: Core Implementation (Iterations 6–20)

### Feature-by-Feature Loop

For each feature the user requested, execute this sub-loop:

```
FOR each feature in user's requirements:
  1. Create types/interfaces for this feature
  2. Implement core business logic (pure functions first)
  3. Create the integration layer (routes, handlers, UI components)
  4. Write tests for this feature
  5. VERIFY: tests pass, no type errors, no lint errors
  6. VERIFY: feature works when tested manually (curl, browser, CLI)
NEXT feature
```

**Priority rules:**
- Implement data models first (types, schemas, database models)
- Then implement business logic (validation, transformation, computation)
- Then implement I/O layer (API routes, CLI commands, UI components)
- Then implement cross-cutting concerns (auth, logging, error handling)

### Data Layer First

If the app has data persistence:
1. Define schemas/models
2. Set up database connection (or in-memory store for MVPs)
3. Create CRUD operations
4. Write tests for data layer
5. VERIFY before building on top

### API / Route Layer

For each endpoint or command:
1. Define the route/command with input validation
2. Connect to business logic
3. Handle errors gracefully (proper status codes / exit codes)
4. Write integration test
5. VERIFY: endpoint responds correctly to valid and invalid input

### UI Layer (if applicable)

For each page or component:
1. Create the component with proper TypeScript types
2. Connect to data source (API, state, props)
3. Handle loading, error, and empty states
4. Style appropriately (use existing design system or Tailwind)
5. VERIFY: renders without errors, handles all states

---

## Phase 3: Integration & Polish (Iterations 21–30)

### Step 1: End-to-End Verification

Test the complete user flow:
- Start the application fresh
- Walk through the primary use case from beginning to end
- Verify all pieces connect correctly

### Step 2: Error Handling

Add proper error handling at system boundaries:
- Network failures (timeouts, connection refused)
- Invalid input (validation errors returned to user)
- Missing resources (404s, not-found states)
- Unexpected errors (catch-all with proper logging)

### Step 3: Configuration

Ensure the app is configurable:
- Environment variables for secrets and config
- Sensible defaults for development
- No hardcoded values for things that might change

### Step 4: Final Verification

Run the complete verification suite:
- All tests pass ✅
- Build succeeds ✅
- App starts and responds correctly ✅
- No lint or type errors ✅
- Primary user flow works end-to-end ✅

---

## Common Build Patterns

### REST API Sequence
```
1. Setup (scaffold, deps, config)
2. Database/models
3. Core routes (CRUD)
4. Validation middleware
5. Auth (if needed)
6. Error handling
7. Tests
8. Final verification
```

### Full-Stack App Sequence
```
1. Setup monorepo or unified framework
2. Shared types/schemas
3. Backend API
4. Frontend pages/components
5. Connect frontend ↔ backend
6. Auth flow
7. Tests (unit + integration)
8. Final verification
```

### CLI Tool Sequence
```
1. Setup (scaffold, deps)
2. Argument parsing + help text
3. Core command implementation
4. File I/O and output formatting
5. Error handling and exit codes
6. Tests
7. Final verification
```

---

## Quality Checklist (Before Declaring Done)

- [ ] App starts without errors
- [ ] All user-requested features are implemented
- [ ] Tests exist and pass
- [ ] No TypeScript/type errors
- [ ] No linter errors
- [ ] Error cases return proper messages (not stack traces)
- [ ] Configuration uses environment variables (not hardcoded)
- [ ] Code follows consistent naming and structure
- [ ] No placeholder code (`TODO`, `...`, `pass`, `NotImplementedError`)
- [ ] README explains how to run the app
