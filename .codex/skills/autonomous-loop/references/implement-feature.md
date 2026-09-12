# Implement Feature Workflow — Autonomous Loop Reference

When the user asks to **add a feature** to an existing codebase, follow this protocol
within the autonomous loop.

---

## The Feature Implementation Loop

```
┌─────────────────────────────────────────────────────────────┐
│  1. UNDERSTAND  — What does the feature do? Where does it go?│
│  2. DESIGN      — Types, interfaces, data flow               │
│  3. IMPLEMENT   — Core logic first, integration second       │
│  4. WIRE        — Connect to existing system                 │
│  5. TEST        — Unit + integration tests                   │
│  6. VERIFY      — End-to-end feature works                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Understand the Feature (Iteration 1–2)

### Requirements Extraction

From the user's request, determine:
1. **What** — Exactly what should the feature do?
2. **Where** — Which part of the app does it affect?
3. **How** — Are there constraints on implementation approach?
4. **Scope** — What's the minimum viable implementation?

### Codebase Discovery

Before writing any new code:
1. Find where similar features are implemented (patterns to follow)
2. Identify the files that will need modification
3. Understand the data flow through the relevant area
4. Check for existing utilities/helpers that can be reused

**Search strategy:**
- Find the nearest existing feature to yours
- Read its implementation to understand the local patterns
- Note naming conventions, file organization, testing approach
- Your feature should follow the same patterns

### Impact Analysis

Determine what's affected:
- Which files need new code?
- Which files need modifications?
- Are there shared types/interfaces that need extending?
- Will existing tests need updating?
- Are there database/schema changes required?

---

## Phase 2: Design (Iteration 2–3)

### Types & Interfaces First

Before implementing logic, define the shape:

```typescript
// Example: Adding a "bookmark" feature
interface Bookmark {
  id: string;
  userId: string;
  itemId: string;
  createdAt: Date;
}

interface BookmarkService {
  add(userId: string, itemId: string): Promise<Bookmark>;
  remove(userId: string, itemId: string): Promise<void>;
  list(userId: string): Promise<Bookmark[]>;
  isBookmarked(userId: string, itemId: string): Promise<boolean>;
}
```

### Data Flow Design

Map how data flows through the feature:
```
User Action → Route/Handler → Service → Data Layer → Response
```

For each layer, know:
- What input does it receive?
- What output does it produce?
- What errors can it throw?

### File Plan

List the files to create/modify:
```
CREATE: src/services/bookmark.ts      (business logic)
CREATE: src/routes/bookmarks.ts       (API routes)
CREATE: tests/bookmark.test.ts        (tests)
MODIFY: src/types/index.ts            (add Bookmark type)
MODIFY: src/routes/index.ts           (register new routes)
```

---

## Phase 3: Implement Core Logic (Iterations 3–6)

### Layer-by-Layer Implementation

Implement in this order (inner to outer):

#### Layer 1: Data/Model
- Create or modify database models/schemas
- Add migration if needed
- Verify: model creates/reads correctly

#### Layer 2: Business Logic / Service
- Implement core operations (CRUD, validation, transformation)
- Keep business logic pure — no HTTP, no CLI, no UI concerns
- Verify: unit tests pass for service functions

#### Layer 3: Integration / Controller
- Create routes, handlers, commands, or components
- Wire service to I/O layer
- Add input validation at the boundary
- Verify: integration test passes

#### Layer 4: Cross-Cutting Concerns
- Add authorization checks (can this user do this?)
- Add logging for important operations
- Add rate limiting if applicable
- Verify: auth test passes, unauthorized requests rejected

### Implementation Rules

**Follow existing patterns exactly:**
- Same file structure as sibling features
- Same naming convention (camelCase, snake_case, etc.)
- Same error handling pattern
- Same test structure

**Don't over-engineer:**
- Implement what's needed NOW
- Don't add "just in case" abstractions
- Don't build for hypothetical future requirements
- YAGNI — You Aren't Gonna Need It

**Don't under-engineer:**
- Handle errors that can actually happen
- Validate input at system boundaries
- Use proper types (not `any`, not `object`)
- Return meaningful error messages

---

## Phase 4: Wire Into System (Iterations 5–8)

### Registration

Connect the feature to the application:
- Register new routes with the router
- Add new commands to CLI parser
- Add new components to the page/layout
- Export new modules from barrel files

### Navigation / Discoverability

If the feature has a UI:
- Add navigation link or button
- Add to relevant menus
- Ensure it's reachable from the expected entry points

### Configuration

If the feature needs config:
- Add environment variables with sensible defaults
- Document the configuration options
- Add to .env.example

---

## Phase 5: Testing (Iterations 6–10)

### Test Strategy

Write tests at multiple levels:

#### Unit Tests (always)
- Test business logic in isolation
- Test edge cases (empty, null, max, concurrent)
- Test error paths (invalid input, missing data)
- Mock external dependencies

#### Integration Tests (for I/O features)
- Test the full request/response cycle
- Test with realistic data
- Test authentication and authorization
- Test error responses have correct status codes

#### End-to-End Test (for critical flows)
- Test the complete user journey
- Test from entry point to final output
- Verify side effects (database writes, notifications)

### Test Patterns

```
describe('Feature: Bookmarks', () => {
  describe('add bookmark', () => {
    it('creates a bookmark for authenticated user', ...);
    it('rejects duplicate bookmarks', ...);
    it('rejects unauthenticated requests', ...);
    it('returns 404 for non-existent items', ...);
  });

  describe('list bookmarks', () => {
    it('returns only the user own bookmarks', ...);
    it('returns empty array for new users', ...);
    it('paginates large result sets', ...);
  });
});
```

---

## Phase 6: Final Verification (Iterations 8–12)

### Integration Verification

1. Start the application fresh
2. Exercise the new feature end-to-end
3. Verify it works with existing features (no conflicts)
4. Check that existing functionality is unaffected

### Complete Verification Checklist

- [ ] Feature works as described by user
- [ ] All new tests pass
- [ ] All existing tests still pass
- [ ] No type errors
- [ ] No lint warnings
- [ ] Feature is accessible from expected entry points
- [ ] Error cases return meaningful messages
- [ ] Feature follows existing codebase patterns
- [ ] No unnecessary files or dead code added

---

## Common Feature Patterns

### CRUD Feature
```
1. Define model/type
2. Create data access layer (repository/service)
3. Add create endpoint + validation
4. Add read endpoint (single + list with pagination)
5. Add update endpoint + partial validation
6. Add delete endpoint + cascade handling
7. Tests for each operation
8. Wire into router/menu
```

### Authentication Feature
```
1. Define user model + credentials
2. Implement password hashing
3. Create login endpoint (returns token/session)
4. Create registration endpoint
5. Create auth middleware (validates token)
6. Protect existing routes with middleware
7. Tests for auth flows
8. Test unauthorized access is denied
```

### Notification/Event Feature
```
1. Define event types
2. Create event emitter/bus
3. Implement handlers for each event
4. Wire triggers into existing operations
5. Add delivery mechanism (email, push, in-app)
6. Tests for event propagation
7. Tests for delivery
```

### Search/Filter Feature
```
1. Define searchable fields and filter criteria
2. Implement query builder
3. Add search endpoint with validation
4. Handle pagination and sorting
5. Optimize with indexes (if database)
6. Tests for various filter combinations
7. Test empty results and edge cases
```

---

## When the Feature is Large

If the feature requires more than 15 iterations:

1. **Split into sub-features** — implement the core first, enhancements later
2. **Vertical slices** — implement one complete thin slice first, then broaden
3. **Start with happy path** — get the main flow working, then add error handling
4. **Defer optimization** — make it work, then make it fast
