---
name: react-nextjs-typescript-ux
description: >
  Comprehensive production-grade skill for React 19, Next.js 15+, TypeScript strict-mode,
  and UI/UX excellence. Use when: writing, reviewing, auditing, or debugging any React
  component, Next.js page/layout/action, TypeScript module, custom Hook, form, state
  management, data fetching, Suspense/Error Boundary, Server Component, TanStack Query
  integration, async pattern, or UI/UX implementation. Also trigger for: design systems,
  dark mode, accessibility (WCAG), animations, responsive layouts, data tables, charts,
  color tokens, typography, component architecture, performance optimization, security
  (OWASP A01-A10), ESLint/tsconfig config, test strategy, or any DevSecOps dashboard
  UI work. Covers React 19 new APIs (useActionState, useOptimistic, useFormStatus, use,
  ref-as-prop, Context-as-provider), Next.js 15 PPR/Partial Prerendering, use cache
  directive, React Compiler, and full OWASP frontend security. Best practices for 2025-2026.
argument-hint: 'Component, page, hook, or feature to implement/review (e.g. "AlertsPage", "auth form", "data table", "dashboard layout")'
---

# React · Next.js · TypeScript · UI/UX Pro Skill

A unified, production-grade reference for React 19, Next.js 15+, TypeScript strict-mode,
and professional UI/UX patterns. Synthesized from official React/Next.js docs (2025–2026),
UI/UX Pro Max design system, OWASP frontend security guidelines, and hands-on audit of
the DevSecOps Dashboard codebase.

---

## ⚡ How to Use This Skill (read only what you need)

This is a **large reference (28 sections)**. Do **not** read it top-to-bottom — that wastes context
and can overflow the chat. Match the task to the **one or two** sections below, jump there, and
answer from that section only.

| Task | Jump to § |
|---|---|
| Type errors, generics, `any`, strict mode | §2 |
| Hook bug, `useEffect` loop, stale closure, deps | §3, §4 |
| `useMemo` / `useCallback` — is it needed? | §5 |
| Build/split a component, prop design | §6 |
| React 19 API (`useActionState`, `use`, `useOptimistic`) | §7 |
| Loading/streaming, Suspense, error boundary | §8, §23 |
| Server Components / Next.js 15 / PPR / `use cache` | §9, §10 |
| Data fetching / caching / TanStack Query | §11 |
| Async race conditions, cancellation | §12 |
| State shape, immutability | §13 |
| Design system / tokens / dark mode / color | §14, §16, §17 |
| Accessibility (WCAG / ARIA) | §15 |
| Animation / motion | §18 |
| Forms & validation UX | §19 |
| Tables / lists / virtualization | §20 |
| Charts / data visualization | §21 |
| Navigation patterns | §22 |
| Security (OWASP A01–A10) | §24 |
| Performance | §25 |
| Lint / tsconfig, tests, final review | §26, §27, §28 |

**Use a different skill when it fits better** (don't reinvent here):
- Broad **design decisions** for *any* stack (style, palette, typography, morphisms, chart-type or
  chart-library choice) → use the **UI/UX Pro Max** skill (`search.py` + its `references/`), which is
  token-disciplined and framework-agnostic.
- Full-feature **plan → build → audit → root-cause-fix** lifecycle, edge cases, user-empathy →
  use the **feature-audit** skill.

---

## Table of Contents

1. [Quick Scenario → Starting Point](#1-quick-scenario--starting-point)
2. [TypeScript Strict-Mode Foundations](#2-typescript-strict-mode-foundations)
3. [React Hooks Rules & Patterns](#3-react-hooks-rules--patterns)
4. [useEffect Patterns & Anti-Patterns](#4-useeffect-patterns--anti-patterns)
5. [useMemo / useCallback — When & When Not](#5-usememo--usecallback--when--when-not)
6. [Component Architecture & Design](#6-component-architecture--design)
7. [React 19 — New APIs Reference](#7-react-19--new-apis-reference)
8. [Suspense & Error Boundaries](#8-suspense--error-boundaries)
9. [Server Components (RSC) & Next.js 15](#9-server-components-rsc--nextjs-15)
10. [Next.js 15 — PPR, use cache, Streaming](#10-nextjs-15--ppr-use-cache-streaming)
11. [TanStack Query v5](#11-tanstack-query-v5)
12. [Async & Concurrency Patterns](#12-async--concurrency-patterns)
13. [State Shape & Immutability](#13-state-shape--immutability)
14. [UI/UX Design System — DevSecOps Dashboard](#14-uiux-design-system--devsecops-dashboard)
15. [Accessibility (WCAG 2.2 / ARIA)](#15-accessibility-wcag-22--aria)
16. [Dark Mode & Color Tokens](#16-dark-mode--color-tokens)
17. [Typography & Spacing](#17-typography--spacing)
18. [Animation & Interaction Patterns](#18-animation--interaction-patterns)
19. [Forms & Validation UX](#19-forms--validation-ux)
20. [Data Tables & Lists](#20-data-tables--lists)
21. [Charts & Data Visualization](#21-charts--data-visualization)
22. [Navigation Patterns](#22-navigation-patterns)
23. [Loading States & Skeletons](#23-loading-states--skeletons)
24. [Frontend Security (OWASP A01–A10)](#24-frontend-security-owasp-a01a10)
25. [Performance Optimization](#25-performance-optimization)
26. [ESLint & tsconfig](#26-eslint--tsconfig)
27. [Testing Strategy](#27-testing-strategy)
28. [Master Review Checklist](#28-master-review-checklist)

---

## 1. Quick Scenario → Starting Point

| Scenario | Trigger Examples | Start |
|----------|-----------------|-------|
| New page / feature | "Build a dashboard page", "Add incidents list" | §6, §14, §15 |
| New component | "Create a modal", "Add stat card" | §6, §14, §18 |
| Review UI code | "Review AlertsPage for UX issues" | §15, §16, §28 |
| Fix React bug | "stale data", "effect runs too often" | §3, §4, §11 |
| Auth / security | "Is JWT stored safely?", "XSS risk?" | §24 |
| Form / validation | "Add inline validation", "Submit feedback" | §7, §19 |
| Chart / data viz | "Add CPU trend chart", "Anomaly timeline" | §21 |
| Performance | "Page re-renders too often", "Large list slow" | §5, §25 |
| Next.js SSR | "Server Component vs Client?", "Caching?" | §9, §10 |
| Data fetching | "TanStack Query setup", "Optimistic UI" | §11, §7 |
| TypeScript errors | "any usage", "type not narrowed" | §2 |
| Dark mode | "Add theme toggle", "CSS variables" | §16 |

---

## 2. TypeScript Strict-Mode Foundations

### 2.1 Never use `any` — use `unknown` + type guards

```ts
// ❌ any removes all safety — compiler cannot help you
function process(data: any) { return data.value; }

// ✅ unknown forces narrowing before use
function process(data: unknown): string {
  if (
    typeof data === 'object' &&
    data !== null &&
    'value' in data &&
    typeof (data as Record<string, unknown>).value === 'string'
  ) {
    return (data as { value: string }).value;
  }
  throw new Error('Invalid data shape');
}
```

### 2.2 Discriminated unions — eliminate ambiguous state

```ts
// ❌ three booleans that can contradict each other
interface ApiState { loading?: boolean; data?: User; error?: Error; }

// ✅ one state field — exhaustive and self-documenting
type ApiState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error };

// TypeScript narrows correctly in every branch
function render(state: ApiState<User>) {
  switch (state.status) {
    case 'loading': return <Spinner />;
    case 'success': return <View user={state.data} />;  // data: User ✓
    case 'error':   return <ErrorCard msg={state.error.message} />;
    case 'idle':    return null;
  }
}
```

### 2.3 `as const` for configuration objects

```ts
// ❌ method inferred as string — breaks fetch type overloads
const cfg = { method: 'GET', url: '/api/users' };

// ✅ method inferred as literal 'GET' — no cast needed
const cfg = { method: 'GET', url: '/api/users' } as const;
fetch(cfg.url, { method: cfg.method });
```

### 2.4 Essential utility types (cheat sheet)

```ts
type PartialUser  = Partial<User>;             // all optional
type RequiredUser = Required<User>;            // all required
type ReadUser     = Readonly<User>;            // immutable
type UserKeys     = keyof User;               // 'id' | 'name' | ...
type NameOnly     = Pick<User, 'name'>;       // subset
type NoId         = Omit<User, 'id'>;         // exclusion
type UserMap      = Record<string, User>;     // index signature
type NonNullUser  = NonNullable<User | null>; // strips null/undefined

// Template literal — type-safe CSS variables
type CSSVar = `--${string}`;

// Auto-generate getters
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};
```

### 2.5 Narrowing patterns

```ts
// typeof
function len(v: string | string[]) {
  return Array.isArray(v) ? v.length : v.length;
}

// instanceof
function handle(e: unknown) {
  if (e instanceof Error) console.error(e.message);
}

// 'in' operator (discriminated union)
function speak(a: Dog | Cat) {
  if ('bark' in a) a.bark(); else a.meow();
}

// Assertion function (throws on null/undefined)
function assertDefined<T>(v: T | null | undefined): asserts v is T {
  if (v == null) throw new Error('Expected value, got null/undefined');
}
```

### 2.6 Generics — constrain, don't over-abstract

```ts
// ✅ keyof constraint gives accurate return type
function pick<T, K extends keyof T>(obj: T, keys: K[]): Pick<T, K> {
  return keys.reduce((acc, k) => ({ ...acc, [k]: obj[k] }), {} as Pick<T, K>);
}

// ✅ infer for utility types
type Awaited<T> = T extends Promise<infer R> ? R : T;
type UnpackArray<T> = T extends (infer U)[] ? U : T;
```

---

## 3. React Hooks Rules & Patterns

### Rule 1 — Always call Hooks unconditionally at the top level

```tsx
// ❌ conditional Hook call — React breaks
function Bad({ show }: { show: boolean }) {
  if (show) {
    const [n, setN] = useState(0);  // Error!
  }
}

// ✅ declare at top level; guard with early return
function Good({ show }: { show: boolean }) {
  const [n, setN] = useState(0);
  if (!show) return null;
  return <button onClick={() => setN(n + 1)}>{n}</button>;
}
```

### Rule 2 — Custom Hooks must start with `use`

```tsx
// ❌ linter and React cannot identify this as a Hook
function windowSize() { ... }

// ✅
function useWindowSize() {
  const [size, setSize] = useState({ w: 0, h: 0 });
  useEffect(() => {
    const update = () => setSize({ w: innerWidth, h: innerHeight });
    addEventListener('resize', update);
    update();
    return () => removeEventListener('resize', update);
  }, []);
  return size;
}
```

### 3.1 React 19 — `ref` as a prop (replaces `forwardRef`)

```tsx
// ✅ React 19: ref is a plain prop — no forwardRef needed
function MyInput({ placeholder, ref }: { placeholder: string; ref?: React.Ref<HTMLInputElement> }) {
  return <input placeholder={placeholder} ref={ref} />;
}

// ✅ React 19: <Context> as provider (deprecates <Context.Provider>)
const ThemeContext = createContext('dark');
function App({ children }: { children: React.ReactNode }) {
  return (
    <ThemeContext value="dark">   {/* New syntax */}
      {children}
    </ThemeContext>
  );
}
```

### 3.2 Ref cleanup functions (React 19)

```tsx
// ✅ React 19: ref callbacks can return cleanup
<input
  ref={(ref) => {
    // setup
    return () => {
      // cleanup when unmounted — do NOT use implicit return
    };
  }}
/>
```

---

## 4. useEffect Patterns & Anti-Patterns

### 4.1 Complete dependency arrays — never lie to React

```tsx
// ❌ stale closure — effect reads userId but won't re-run when it changes
useEffect(() => {
  fetchUser(userId).then(setUser);
}, []);  // missing userId!

// ✅ every reactive value in the array
useEffect(() => {
  let cancelled = false;
  fetchUser(userId).then(d => { if (!cancelled) setUser(d); });
  return () => { cancelled = true; };
}, [userId]);
```

### 4.2 Always clean up subscriptions and timers

```tsx
useEffect(() => {
  const id = setInterval(() => setTick(t => t + 1), 1_000);
  return () => clearInterval(id);
}, []);

useEffect(() => {
  const ctrl = new AbortController();
  fetch('/api/data', { signal: ctrl.signal }).then(/* ... */);
  return () => ctrl.abort();
}, [url]);
```

### 4.3 Derived state — compute inline, don't use useEffect

```tsx
// ❌ extra render cycle + sync risk
const [filtered, setFiltered] = useState<Item[]>([]);
useEffect(() => setFiltered(items.filter(i => i.active)), [items]);

// ✅ computed at render time — zero extra state
const filtered = useMemo(() => items.filter(i => i.active), [items]);
```

### 4.4 Side effects belong in handlers, not effects

```tsx
// ❌ analytics tied to state change via effect — fragile
useEffect(() => {
  if (query) analytics.track('search', { query });
}, [query]);

// ✅ side effect at the event site — predictable
const handleSearch = (q: string) => {
  setQuery(q);
  analytics.track('search', { query: q });
};
```

### 4.5 `useEffectEvent` for non-reactive callbacks (React 19)

```tsx
import { experimental_useEffectEvent as useEffectEvent } from 'react';

function Chat({ roomId, onJoin }: { roomId: string; onJoin: (id: string) => void }) {
  // onJoin is always fresh but NOT a dep — no stale closure, no infinite loop
  const onJoinStable = useEffectEvent(onJoin);

  useEffect(() => {
    const conn = connect(roomId);
    conn.on('connected', () => onJoinStable(roomId));
    return () => conn.disconnect();
  }, [roomId]);  // onJoin intentionally absent
}
```

---

## 5. useMemo / useCallback — When & When Not

### 5.1 Only memoize what's genuinely expensive or ref-sensitive

```tsx
// ❌ memoizing a constant — zero benefit, added noise
const cfg = useMemo(() => ({ timeout: 5_000 }), []);

// ✅ constant belongs outside the component
const DEFAULT_CFG = { timeout: 5_000 };
```

### 5.2 `useCallback` only when the ref must be stable

```tsx
// ❌ useCallback on a non-memo child — recreates anyway, wasted
const handle = useCallback(() => console.log('click'), []);
return <PlainDiv onClick={handle} />;

// ✅ stable ref needed for React.memo child or dep of another hook
const MemoChild = React.memo(({ onClick }: { onClick: () => void }) => (
  <button onClick={onClick}>Click</button>
));

function Parent() {
  const handleClick = useCallback(() => { /* expensive or ref-sensitive */ }, []);
  return <MemoChild onClick={handleClick} />;
}
```

### 5.3 Dependency instability anti-pattern

```tsx
// ❌ filters is a new object every render → useCallback is useless
function Bad({ filters }: { filters: Record<string, string> }) {
  const fetch = useCallback(() => fetchItems(filters), [filters]);
}

// ✅ stabilize the input first
function Good({ filters }: { filters: Record<string, string> }) {
  const stableFilters = useMemo(() => filters, [JSON.stringify(filters)]);
  const fetch = useCallback(() => fetchItems(stableFilters), [stableFilters]);
}
```

### 5.4 `useDeferredValue` for expensive renders (React 19 — initialValue)

```tsx
function Search({ deferredValue }: { deferredValue: string }) {
  // React 19: initialValue param means no empty flash on first render
  const value = useDeferredValue(deferredValue, '');
  return <Results query={value} />;
}
```

---

## 6. Component Architecture & Design

### 6.1 Never define components inside other components

```tsx
// ❌ Child is a NEW function every render → remounts, loses state
function Parent() {
  function Child() { return <div>child</div>; }
  return <Child />;
}

// ✅ module scope
function Child() { return <div>child</div>; }
function Parent() { return <Child />; }
```

### 6.2 Stabilize props passed to memoized children

```tsx
// ❌ new object + new function every render → React.memo is useless
<MemoChild style={{ color: 'red' }} onClick={() => {}} />

// ✅
const STYLE = { color: 'red' } as const;
function Parent() {
  const handleClick = useCallback(() => {}, []);
  return <MemoChild style={STYLE} onClick={handleClick} />;
}
```

### 6.3 Single-responsibility: extract logic to custom Hooks

```tsx
// ❌ God component — fetches, formats, validates, renders 300 lines
function UserDashboard({ id }: { id: string }) { /* ... */ }

// ✅ business logic in Hook; component stays declarative
function useUserProfile(id: string) {
  const query = useSuspenseQuery(userQueryOptions(id));
  const update = useMutation({ mutationFn: updateUser });
  return { user: query.data, update: update.mutate, isPending: update.isPending };
}

function UserProfile({ id }: { id: string }) {
  const { user, update, isPending } = useUserProfile(id);
  return <ProfileForm user={user} onSave={update} saving={isPending} />;
}
```

### 6.4 Composition over configuration

```tsx
// ❌ prop-drilling configuration into a mega-component
<DataTable sortable filterable paginated exportable onSort={...} onFilter={...} ... />

// ✅ composable slots
<DataTable>
  <DataTable.Toolbar>
    <DataTable.Search />
    <DataTable.Export />
  </DataTable.Toolbar>
  <DataTable.Body />
  <DataTable.Pagination />
</DataTable>
```

### 6.5 Component size limits

- **≤ 200 lines** per component file (JSX + logic)
- **≤ 50 lines** per render function body
- Extract sub-components when a region has its own meaningful state or lifecycle
- Long lists → virtual scrolling (`@tanstack/react-virtual`)

---

## 7. React 19 — New APIs Reference

### 7.1 `useActionState` — replaces multi-useState form patterns

```tsx
import { useActionState } from 'react';

// ✅ state + action + isPending in a single hook
type State = { success: boolean; error: string | null };
const INIT: State = { success: false, error: null };

function ContactForm() {
  const [state, action, isPending] = useActionState(
    async (_prev: State, fd: FormData): Promise<State> => {
      try {
        await submitContact(fd);
        return { success: true, error: null };
      } catch (e) {
        return { success: false, error: (e as Error).message };
      }
    },
    INIT
  );

  return (
    <form action={action}>
      <input name="email" type="email" required />
      <button disabled={isPending}>
        {isPending ? 'Sending…' : 'Send'}
      </button>
      {state.error && <p role="alert" className="text-red-400">{state.error}</p>}
      {state.success && <p role="status" className="text-green-400">Sent!</p>}
    </form>
  );
}
```

### 7.2 `useFormStatus` — inside `<form>` child only

```tsx
import { useFormStatus } from 'react-dom';

// ❌ called in same component as <form> — always returns defaults
function BadForm() {
  const { pending } = useFormStatus();  // always false!
  return <form action={action}><button disabled={pending}>Submit</button></form>;
}

// ✅ extracted child
function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      aria-label={pending ? 'Submitting form' : 'Submit form'}
      className="btn-primary"
    >
      {pending ? 'Saving…' : 'Save'}
    </button>
  );
}
```

### 7.3 `useOptimistic` — instant feedback with auto-rollback

```tsx
import { useOptimistic } from 'react';

function LikeButton({ postId, initialLikes }: { postId: string; initialLikes: number }) {
  const [likes, addOptimistic] = useOptimistic(
    initialLikes,
    (current: number, delta: number) => current + delta
  );

  async function handleLike() {
    addOptimistic(1);           // instant UI update
    await likePost(postId);     // server sync — auto-reverts on error
  }

  return (
    <button
      onClick={handleLike}
      aria-label={`Like post. Current likes: ${likes}`}
    >
      ♥ {likes}
    </button>
  );
}
```

> **CRITICAL:** Do NOT use `useOptimistic` for irreversible operations (payments,
> destructive deletes without undo, financial transactions).

### 7.4 `use()` — read Promises and Context in render

```tsx
import { use, Suspense } from 'react';

// ✅ read a promise (triggers Suspense boundary above)
function Comments({ promise }: { promise: Promise<Comment[]> }) {
  const comments = use(promise);  // suspends until resolved
  return <ul>{comments.map(c => <li key={c.id}>{c.text}</li>)}</ul>;
}

// ✅ read Context conditionally (unlike useContext)
function Heading({ children }: { children: React.ReactNode }) {
  if (!children) return null;
  const theme = use(ThemeContext);  // works after early return
  return <h1 style={{ color: theme.color }}>{children}</h1>;
}
```

> **CRITICAL:** Do NOT create promises inside render and pass them to `use()`.
> Promises must come from outside (Server Component props, stable refs, or
> Suspense-compatible libraries). React will warn: "A component was suspended by
> an uncached promise."

### 7.5 Server Actions (Next.js 15)

```ts
// app/actions/posts.ts — server-only
'use server';
import { revalidatePath } from 'next/cache';
import { db } from '@/lib/db';
import { z } from 'zod';

const CreatePostSchema = z.object({
  title: z.string().min(1).max(200),
  body: z.string().min(1).max(10_000),
});

export async function createPost(
  _prev: { success: boolean; error?: string } | null,
  fd: FormData
) {
  // ✅ always validate server-side — never trust FormData directly
  const parsed = CreatePostSchema.safeParse({
    title: fd.get('title'),
    body: fd.get('body'),
  });
  if (!parsed.success) {
    return { success: false, error: parsed.error.issues[0].message };
  }
  await db.posts.create({ data: parsed.data });
  revalidatePath('/posts');
  return { success: true };
}
```

---

## 8. Suspense & Error Boundaries

### 8.1 Always pair Suspense with ErrorBoundary

```tsx
// ❌ uncaught errors crash the entire tree
<Suspense fallback={<Spinner />}>
  <AsyncComponent />
</Suspense>

// ✅ every Suspense boundary has an ErrorBoundary wrapper
<ErrorBoundary fallback={<ErrorCard message="Failed to load" />}>
  <Suspense fallback={<Skeleton />}>
    <AsyncComponent />
  </Suspense>
</ErrorBoundary>
```

### 8.2 Granular boundaries for independent loading

```tsx
// ❌ one slow component blocks everything
<Suspense fallback={<FullPageSpinner />}>
  <Header />     {/* fast */}
  <Content />    {/* slow — blocks Header */}
  <Sidebar />    {/* medium */}
</Suspense>

// ✅ independent boundaries — stream independently
export default function DashboardLayout() {
  return (
    <>
      <Header />  {/* synchronous — no boundary needed */}
      <div className="grid grid-cols-[1fr_280px] gap-4">
        <ErrorBoundary fallback={<ContentError />}>
          <Suspense fallback={<ContentSkeleton />}>
            <MainContent />
          </Suspense>
        </ErrorBoundary>

        <ErrorBoundary fallback={<SidebarError />}>
          <Suspense fallback={<SidebarSkeleton />}>
            <Sidebar />
          </Suspense>
        </ErrorBoundary>
      </div>
    </>
  );
}
```

### 8.3 Skeletons beat spinners

```tsx
// ❌ generic spinner — no content shape hint, causes layout shift
<Suspense fallback={<div className="animate-spin" />}>

// ✅ skeleton matches the content layout — prevents layout shift
<Suspense fallback={<StatCardSkeleton count={4} />}>
  <StatCards />
</Suspense>
```

### 8.4 React 19 error reporting hooks

```tsx
// createRoot supports granular error handlers in React 19
const root = createRoot(container, {
  onCaughtError(error, errorInfo) {
    // error caught by ErrorBoundary — report to monitoring
    Sentry.captureException(error, { extra: errorInfo });
  },
  onUncaughtError(error, errorInfo) {
    // error not caught — critical alert
    Sentry.captureException(error);
  },
  onRecoverableError(error) {
    // React auto-recovered (e.g. hydration mismatch)
    console.warn('Recovered error:', error);
  },
});
```

---

## 9. Server Components (RSC) & Next.js 15

### 9.1 RSC capability table

| Allowed in RSC | NOT allowed in RSC |
|---|---|
| `async/await` at top level | `useState`, `useReducer`, `useEffect` |
| Direct DB / filesystem access | Event handlers (`onClick`, `onChange`) |
| Server-only imports | `'use client'` siblings in same file |
| Pass serializable props to Client | Browser APIs (`window`, `document`) |
| `use cache` directive | `useContext` (use `use()` instead) |

### 9.2 Push `'use client'` to leaf nodes

```tsx
// ❌ marking the layout as client makes the ENTIRE subtree a client bundle
'use client';
export default function Layout({ children }) { ... }

// ✅ only the interactive leaf is a Client Component
// components/ThemeToggle.tsx
'use client';
export function ThemeToggle() {
  const { toggle, isDark } = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
      className="cursor-pointer p-2 rounded-md hover:bg-[var(--bg-inset)] transition-colors"
    >
      {/* SVG icon — never emoji */}
      {isDark ? <SunIcon size={18} /> : <MoonIcon size={18} />}
    </button>
  );
}

// app/layout.tsx — RSC (no directive needed)
import { ThemeToggle } from '@/components/ThemeToggle';
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html>
      <body>
        <nav><ThemeToggle /></nav>
        <main>{children}</main>
      </body>
    </html>
  );
}
```

### 9.3 Next.js 15 — `params` and `searchParams` are Promises

```tsx
// ❌ Next.js 14 pattern — breaks in Next.js 15
export default function Page({ params }: { params: { id: string } }) {
  const id = params.id;  // TypeError in Next.js 15
}

// ✅ Next.js 15 — must await
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  const { id } = await params;
  const { tab = 'overview' } = await searchParams;
  const data = await fetchItem(id);
  return <ItemView item={data} defaultTab={tab} />;
}
```

---

## 10. Next.js 15 — PPR, `use cache`, Streaming

### 10.1 `use cache` directive — data-level and UI-level

```tsx
// Data-level caching — cache a fetch function
import { cacheLife, cacheTag } from 'next/cache';

export async function getUsers() {
  'use cache';
  cacheLife('hours');         // revalidate every hour
  cacheTag('users');          // on-demand invalidation key
  return db.query('SELECT * FROM users');
}

// UI-level caching — cache a whole component's output
async function BlogPosts() {
  'use cache';
  cacheLife('hours');
  cacheTag('posts');
  const res = await fetch('https://api.example.com/posts');
  const posts = await res.json();
  return <PostList posts={posts} />;
}
```

### 10.2 Partial Prerendering (PPR) pattern

```tsx
// Static shell + streaming dynamic content on the same page
export default function DashboardPage() {
  return (
    <>
      {/* Static — prerendered at build time */}
      <PageHeader title="Dashboard" />

      {/* Cached dynamic — included in static shell */}
      <MetricsSummary />

      {/* Runtime dynamic — streams at request time */}
      <Suspense fallback={<AlertsSkeleton />}>
        <LiveAlerts />          {/* user-specific, no cache */}
      </Suspense>
    </>
  );
}

// LiveAlerts reads cookies → cannot be cached
async function LiveAlerts() {
  const userId = (await cookies()).get('userId')?.value;
  const alerts = await fetchUserAlerts(userId);
  return <AlertsList alerts={alerts} />;
}
```

### 10.3 Pass runtime values to cached functions (not runtime APIs directly)

```tsx
// ❌ accessing cookies inside a cached function — runtime error
async function CachedProfile() {
  'use cache';
  const theme = (await cookies()).get('theme')?.value;  // Error!
}

// ✅ extract at request time, pass as prop (becomes part of cache key)
async function ProfileContent() {
  const sessionId = (await cookies()).get('session')?.value;
  return <CachedProfile sessionId={sessionId} />;
}

async function CachedProfile({ sessionId }: { sessionId?: string }) {
  'use cache';
  const data = await fetchUserData(sessionId);
  return <div>{data}</div>;
}
```

### 10.4 Caching cheat sheet

```tsx
// Time-based (use cache)
cacheLife('seconds')   // 60s
cacheLife('minutes')   // 5 min
cacheLife('hours')     // 1 hr
cacheLife('days')      // 1 day
cacheLife('weeks')     // 7 days
cacheLife('max')       // 1 year

// On-demand invalidation
cacheTag('posts');
// later...
import { revalidateTag } from 'next/cache';
revalidateTag('posts');

// No caching (dynamic at every request)
const data = await fetch('/api/live', { cache: 'no-store' });
```

---

## 11. TanStack Query v5

### 11.1 QueryClient setup

```tsx
// lib/queryClient.ts
import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1_000 * 60 * 5,   // 5 min fresh
      gcTime:    1_000 * 60 * 30,  // 30 min GC (was cacheTime in v4)
      retry: 3,
      refetchOnWindowFocus: false,
    },
  },
});
```

### 11.2 `queryOptions` — single source of truth for keys + fetcher

```tsx
// lib/queries/alerts.ts
export const alertsQueryOptions = (machineId: string) =>
  queryOptions({
    queryKey: ['alerts', machineId],
    queryFn:  () => fetchAlerts(machineId),
    staleTime: 1_000 * 30,  // 30s fresh for alerts
  });

// Usage in component
const { data } = useQuery(alertsQueryOptions(machineId));

// Usage in prefetch (loader or RSC)
await queryClient.prefetchQuery(alertsQueryOptions(machineId));

// Fully typed cache access
const cached = queryClient.getQueryData(alertsQueryOptions(machineId).queryKey);
```

### 11.3 queryKey must include every variable that affects the result

```tsx
// ❌ filters change but key is static → shows stale data
useQuery({
  queryKey: ['items'],
  queryFn:  () => fetchItems(filters),  // filters ignored by cache
});

// ✅ filters are part of the cache identity
useQuery({
  queryKey: ['items', filters],
  queryFn:  () => fetchItems(filters),
});
```

### 11.4 `useSuspenseQuery` — guaranteed data, no undefined

```tsx
// ✅ data is T — never undefined inside this component
function AlertList({ machineId }: { machineId: string }) {
  const { data: alerts } = useSuspenseQuery(alertsQueryOptions(machineId));
  return <ul>{alerts.map(a => <AlertRow key={a.id} alert={a} />)}</ul>;
}

// MUST be wrapped in ErrorBoundary + Suspense at usage site
function AlertSection({ machineId?: string }) {
  if (!machineId) return <EmptyState title="No machine selected" />;
  return (
    <ErrorBoundary fallback={<AlertsError />}>
      <Suspense fallback={<AlertsSkeleton />}>
        <AlertList machineId={machineId} />
      </Suspense>
    </ErrorBoundary>
  );
}
```

### 11.5 Mutations — always invalidate on success

```tsx
const mutation = useMutation({
  mutationFn: (data: CreateAlertInput) => createAlert(data),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['alerts'] });
    toast.success('Alert rule created');
  },
  onError: (err) => {
    toast.error(`Failed: ${err.message}`);
  },
});
```

### 11.6 Optimistic mutation with `variables`

```tsx
function AlertRuleList() {
  const { data: rules } = useQuery(alertRulesQueryOptions);
  const { mutate, isPending, variables } = useMutation({
    mutationFn: createAlertRule,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alert-rules'] }),
  });

  return (
    <ul>
      {rules?.map(r => <RuleRow key={r.id} rule={r} />)}
      {isPending && (
        <RuleRow rule={variables} isOptimistic className="opacity-50 pointer-events-none" />
      )}
    </ul>
  );
}
```

---

## 12. Async & Concurrency Patterns

### 12.1 Always check `response.ok`

```ts
async function fetchAlerts(machineId: string): Promise<Alert[]> {
  const res = await fetch(`/api/alerts?machine=${machineId}`);
  if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`);
  return res.json() as Promise<Alert[]>;
}
```

### 12.2 `Promise.all` vs `Promise.allSettled`

```ts
// Promise.all — use when ALL must succeed
const [user, alerts] = await Promise.all([fetchUser(id), fetchAlerts(id)]);

// Promise.allSettled — use when partial success is acceptable
const results = await Promise.allSettled(machineIds.map(fetchMetrics));
const metrics  = results.filter(r => r.status === 'fulfilled').map(r => r.value);
const failures = results.filter(r => r.status === 'rejected').length;
```

### 12.3 Race conditions — AbortController

```tsx
useEffect(() => {
  const ctrl = new AbortController();
  async function load() {
    try {
      const data = await fetchSearch(query, ctrl.signal);
      setResults(data);
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError(e as Error);
    }
  }
  void load();
  return () => ctrl.abort();
}, [query]);
```

### 12.4 No `forEach` with async — use `for...of` or `Promise.all`

```ts
// ❌ forEach ignores returned Promises → unhandled rejections
items.forEach(async item => await save(item));

// ✅ sequential
for (const item of items) await save(item);

// ✅ parallel
await Promise.all(items.map(save));
```

### 12.5 No floating promises

```ts
// ❌ ESLint: no-floating-promises
doAsync();

// ✅ await, void, or handle
await doAsync();
void doAsync();
doAsync().catch(console.error);
```

---

## 13. State Shape & Immutability

### 13.1 Never mutate props or arguments

```ts
// ❌ mutates caller's array
function sort(items: User[]) {
  return items.sort((a, b) => a.name.localeCompare(b.name));
}

// ✅ copy first
function sort(items: readonly User[]): User[] {
  return [...items].sort((a, b) => a.name.localeCompare(b.name));
}
```

### 13.2 `useReducer` for complex state transitions

```tsx
type State = { alerts: Alert[]; selected: string | null; filter: string };
type Action =
  | { type: 'SET_ALERTS'; alerts: Alert[] }
  | { type: 'SELECT'; id: string }
  | { type: 'FILTER'; query: string };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'SET_ALERTS': return { ...state, alerts: action.alerts };
    case 'SELECT':     return { ...state, selected: action.id };
    case 'FILTER':     return { ...state, filter: action.query };
  }
}
```

### 13.3 Prefer derived state over stored state

```tsx
// ❌ redundant stored total
const [items, setItems] = useState<Item[]>([]);
const [total, setTotal] = useState(0);

// ✅ derive — single source of truth
const [items, setItems] = useState<Item[]>([]);
const total = items.reduce((sum, i) => sum + i.price, 0);
```

---

## 14. UI/UX Design System — DevSecOps Dashboard

### 14.1 Design System Tokens (from UI/UX Pro Max audit)

```css
/* Design: Dark Mode (OLED) — Recommended for DevSecOps dashboards */
:root[data-theme="dark"] {
  /* Background hierarchy */
  --bg-page:       #020617;    /* OLED black — deepest */
  --bg-surface:    #0F172A;    /* cards, panels */
  --bg-elevated:   #1E293B;    /* dropdowns, modals */
  --bg-inset:      #1A1E2F;    /* inputs, code blocks */
  --bg-hover:      rgba(255, 255, 255, 0.05);

  /* Text hierarchy */
  --text-primary:   #F8FAFC;   /* main content */
  --text-secondary: #94A3B8;   /* labels, metadata */
  --text-muted:     #64748B;   /* placeholders, dims */
  --text-dim:       #475569;   /* disabled */

  /* Semantic colors */
  --color-success:  #22C55E;   /* healthy, online */
  --color-warning:  #F59E0B;   /* degraded, warn */
  --color-critical: #EF4444;   /* critical, error */
  --color-info:     #3B82F6;   /* informational */

  /* Interactive */
  --accent:         #22C55E;   /* primary CTA */
  --accent-hover:   #16A34A;
  --accent-dim:     rgba(34, 197, 94, 0.12);

  /* Structural */
  --border:         #334155;
  --border-focus:   #6366F1;   /* focus ring */
  --shadow-sm:      0 1px 3px rgba(0,0,0,0.4);
  --shadow-md:      0 4px 12px rgba(0,0,0,0.5);

  /* Status glow effects (OLED optimized — use sparingly) */
  --glow-success:   0 0 12px rgba(34, 197, 94, 0.3);
  --glow-critical:  0 0 12px rgba(239, 68, 68, 0.3);
}

:root[data-theme="light"] {
  --bg-page:       #F8FAFC;
  --bg-surface:    #FFFFFF;
  --bg-elevated:   #F1F5F9;
  --bg-inset:      #E2E8F0;
  --text-primary:  #0F172A;
  --text-secondary:#475569;
  --text-muted:    #94A3B8;
  --border:        #E2E8F0;
}
```

### 14.2 Typography (Fira Code + Fira Sans — recommended for dashboards)

```css
/* Google Fonts import */
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

:root {
  --font-heading: 'Fira Code', 'JetBrains Mono', monospace;
  --font-body:    'Fira Sans', 'Inter', system-ui, sans-serif;
  --font-mono:    'Fira Code', monospace;

  /* Scale */
  --text-xs:   11px;
  --text-sm:   12px;
  --text-base: 14px;   /* dashboard default — dense data */
  --text-md:   15px;
  --text-lg:   18px;
  --text-xl:   22px;
  --text-2xl:  28px;

  /* Line height */
  --leading-tight:  1.3;
  --leading-normal: 1.5;
  --leading-relaxed:1.7;
}
```

### 14.3 Spacing system (4px base grid)

```css
:root {
  --space-1:  4px;
  --space-2:  8px;
  --space-3:  12px;
  --space-4:  16px;
  --space-6:  24px;
  --space-8:  32px;
  --space-12: 48px;
  --space-16: 64px;
}
```

### 14.4 Border radius

```css
:root {
  --radius-sm:  6px;   /* badges, chips */
  --radius-md:  8px;   /* cards, inputs */
  --radius-lg:  12px;  /* modals, panels */
  --radius-xl:  16px;  /* overlays */
  --radius-full: 9999px; /* pills, avatars */
}
```

---

## 15. Accessibility (WCAG 2.2 / ARIA)

### 15.1 Contrast ratios — non-negotiable

| Text Type | Minimum Contrast | Target |
|-----------|-----------------|--------|
| Normal text (< 18pt) | 4.5:1 | 7:1 (WCAG AAA) |
| Large text (≥ 18pt) | 3:1 | 4.5:1 |
| UI components/borders | 3:1 | - |
| Decorative | None | - |

Dashboard dark theme: `#F8FAFC` on `#0F172A` = **15.6:1** ✓

### 15.2 Interactive elements — touch targets

```tsx
// ❌ 24×24px — too small for touch
<button style={{ width: 24, height: 24 }}>×</button>

// ✅ minimum 44×44px touch target (can use padding to expand hit area)
<button
  style={{ minWidth: 44, minHeight: 44 }}
  className="flex items-center justify-center p-2.5"
  aria-label="Close dialog"
>
  <XIcon size={20} aria-hidden="true" />
</button>
```

### 15.3 ARIA patterns for dashboard components

```tsx
// Status badges
<span
  role="status"
  aria-label={`Machine status: ${status}`}
  className={cn('badge', statusClass)}
>
  {status}
</span>

// Alert notifications
<div role="alert" aria-live="assertive">
  {criticalAlert && <p>{criticalAlert.message}</p>}
</div>

// Live data regions
<div role="region" aria-label="CPU metrics" aria-live="polite">
  <span>{cpuPercent}%</span>
</div>

// Data tables
<table role="table" aria-label="Runner metrics">
  <caption className="sr-only">GitHub runners with status and metrics</caption>
  <thead>
    <tr>
      <th scope="col" aria-sort={sortField === 'name' ? sortDir : 'none'}>
        Name
      </th>
    </tr>
  </thead>
</table>

// Toggle buttons
<button
  role="switch"
  aria-checked={isEnabled}
  aria-label="Enable alert rule"
  onClick={toggleRule}
>
  {isEnabled ? 'On' : 'Off'}
</button>
```

### 15.4 Keyboard navigation

```tsx
// ✅ Skip link — critical for keyboard users
<a
  href="#main-content"
  className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:bg-[var(--bg-elevated)] focus:rounded-md focus:text-[var(--text-primary)]"
>
  Skip to main content
</a>

// ✅ Focus ring — never suppress outline globally
// In Tailwind:
className="focus-visible:ring-2 focus-visible:ring-[var(--border-focus)] focus-visible:ring-offset-1 focus-visible:outline-none"

// ❌ Never do this:
// * { outline: none; }
// button:focus { outline: none; }
```

### 15.5 Icons — never emoji, always SVG with aria-hidden

```tsx
// ❌ emoji as icon — screen readers read them, no style control
<button>🔔 Alerts</button>

// ✅ SVG icon with aria-hidden + text label
import { Bell } from 'lucide-react';
<button className="flex items-center gap-2">
  <Bell size={16} aria-hidden="true" />
  <span>Alerts</span>
</button>

// ✅ icon-only button requires aria-label
<button aria-label="View alerts">
  <Bell size={16} aria-hidden="true" />
</button>
```

---

## 16. Dark Mode & Color Tokens

### 16.1 Theme toggle implementation

```tsx
// ThemeContext.tsx — data-theme attribute on <html>
import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
type Theme = "dark" | "light";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const stored = localStorage.getItem("theme");
      if (stored === "light" || stored === "dark") return stored;
      // Respect OS preference on first load
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    } catch { return "dark"; }
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try { localStorage.setItem("theme", theme); } catch { /* ignore */ }
  }, [theme]);

  const toggle = () => setTheme(t => t === "dark" ? "light" : "dark");
  return <ThemeContext.Provider value={{ theme, isDark: theme === "dark", toggle }}>{children}</ThemeContext.Provider>;
}
```

### 16.2 CSS-variable usage rules

```tsx
// ✅ always use CSS variables — never hardcoded colors in components
<div style={{ background: 'var(--bg-surface)', borderColor: 'var(--border)' }}>

// ✅ Tailwind via arbitrary values
<div className="bg-[var(--bg-surface)] border-[var(--border)]">

// ❌ hardcoded dark-mode colors — breaks light theme
<div className="bg-slate-900 text-white">
```

### 16.3 Status color system

```tsx
// Use semantic variables, not raw colors
const STATUS_COLORS = {
  online:  { color: 'var(--color-success)', bg: 'var(--accent-dim)' },
  offline: { color: 'var(--color-critical)', bg: 'rgba(239,68,68,.12)' },
  warning: { color: 'var(--color-warning)', bg: 'rgba(245,158,11,.12)' },
  idle:    { color: 'var(--text-muted)', bg: 'var(--bg-inset)' },
} as const;

// Never use color as the ONLY indicator (color-blindness)
<span
  className="flex items-center gap-1.5"
  style={{ color: STATUS_COLORS[status].color }}
>
  <span className="w-2 h-2 rounded-full" style={{ background: 'currentColor' }} />
  {/* Symbol + text alongside color */}
  {status === 'online' ? 'Online' : status === 'offline' ? 'Offline' : status}
</span>
```

---

## 17. Typography & Spacing

### 17.1 Dashboard typography scale

```tsx
// Page title
<h1 className="text-[22px] font-semibold tracking-tight text-[var(--text-primary)]">
  Runner Metrics
</h1>

// Section header
<h2 className="text-[15px] font-semibold text-[var(--text-primary)]">
  Active Runners
</h2>

// Table header
<th className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]">
  Status
</th>

// Body text
<p className="text-[13px] leading-relaxed text-[var(--text-secondary)]">
  Description text here
</p>

// Monospace metric values
<span className="font-mono text-[14px] text-[var(--text-primary)]">
  {cpuPercent.toFixed(1)}%
</span>
```

### 17.2 Spacing consistency

```tsx
// Card padding
<div className="p-4">        {/* 16px — standard card */}
<div className="p-3">        {/* 12px — compact card */}
<div className="p-5 md:p-6"> {/* 20/24px — spacious */}

// Table cells
<td className="px-3 py-2.5"> {/* 12px horizontal, 10px vertical */}

// Button padding
<button className="px-4 py-2">   {/* standard */}
<button className="px-3 py-1.5"> {/* compact */}
<button className="px-5 py-2.5"> {/* prominent CTA */}

// Gaps between elements
<div className="flex gap-2">  {/* 8px — tight group */}
<div className="flex gap-3">  {/* 12px — normal group */}
<div className="flex gap-4">  {/* 16px — generous group */}
```

---

## 18. Animation & Interaction Patterns

### 18.1 Animation principles

| Rule | Value |
|------|-------|
| Duration | 150–300ms (UI); 300–500ms (page transitions) |
| Easing | `ease-out` for enter; `ease-in` for exit |
| Motion conveys meaning | Use for state changes, not decoration |
| Respect `prefers-reduced-motion` | Always |
| Loading indicators | `animate-pulse` for skeleton; `animate-spin` for spinners only |
| Continuous decorative animation | ❌ Never |

### 18.2 Transition patterns

```css
/* Standard interactive transition */
.btn {
  transition: background-color 150ms ease, box-shadow 150ms ease, transform 100ms ease;
}

/* Prefers-reduced-motion: disable all motion */
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

```tsx
// ✅ Tailwind transition with reduced-motion support
<button className="
  bg-[var(--accent)] hover:bg-[var(--accent-hover)]
  transition-colors duration-150 ease-out
  motion-reduce:transition-none
  cursor-pointer
">
  Click
</button>
```

### 18.3 Hover & focus states (mandatory on all interactive elements)

```tsx
// ✅ every clickable element needs: cursor-pointer + hover state + focus ring
<button className="
  cursor-pointer
  px-4 py-2 rounded-md
  bg-[var(--bg-elevated)]
  hover:bg-[var(--bg-hover)] hover:border-[var(--border-focus)]
  border border-[var(--border)]
  transition-colors duration-150
  focus-visible:ring-2 focus-visible:ring-[var(--border-focus)] focus-visible:outline-none
  active:scale-[0.98]
">
  Action
</button>
```

### 18.4 Skeleton animation

```tsx
function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-md motion-reduce:animate-none",
        className
      )}
      style={{ background: 'var(--bg-inset)' }}
      aria-hidden="true"
    />
  );
}

// Skeleton card matching StatCard layout
function StatCardSkeleton() {
  return (
    <div className="p-4 rounded-lg border border-[var(--border)]" style={{ background: 'var(--bg-surface)' }}>
      <Skeleton className="h-4 w-24 mb-3" />
      <Skeleton className="h-8 w-16 mb-2" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}
```

---

## 19. Forms & Validation UX

### 19.1 Form UX rules

| Rule | Reason |
|------|--------|
| Validate on blur (not on submit only) | Immediate feedback reduces errors |
| Error message near the field (not top/bottom) | User sees it immediately |
| Use `role="alert"` for errors | Screen readers announce instantly |
| Show success state after submit | Confirms action was taken |
| Disable submit during pending | Prevents double-submit |
| Never clear form on validation failure | Frustrating to retype |
| Label every input (visible or sr-only) | WCAG requirement |

### 19.2 Accessible form pattern

```tsx
function AlertRuleForm({ onSave }: { onSave: (rule: AlertRule) => void }) {
  const [errors, setErrors] = useState<Record<string, string>>({});

  function validate(name: string, value: string) {
    if (name === 'threshold' && (Number(value) < 0 || Number(value) > 100)) {
      setErrors(e => ({ ...e, threshold: 'Must be between 0 and 100' }));
    } else {
      setErrors(e => { const { [name]: _, ...rest } = e; return rest; });
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className="flex flex-col gap-1">
        <label htmlFor="threshold" className="text-[12px] font-medium text-[var(--text-secondary)]">
          Threshold (%)
        </label>
        <input
          id="threshold"
          name="threshold"
          type="number"
          min={0}
          max={100}
          aria-invalid={!!errors.threshold}
          aria-describedby={errors.threshold ? 'threshold-error' : undefined}
          onBlur={e => validate('threshold', e.target.value)}
          className={cn(
            "input-base",
            errors.threshold && "border-[var(--color-critical)] focus-visible:ring-[var(--color-critical)]"
          )}
        />
        {errors.threshold && (
          <p
            id="threshold-error"
            role="alert"
            className="text-[11px] text-[var(--color-critical)]"
          >
            {errors.threshold}
          </p>
        )}
      </div>
      <SubmitButton />
    </form>
  );
}
```

---

## 20. Data Tables & Lists

### 20.1 Table best practices

```tsx
function MetricsTable({ rows }: { rows: MetricRow[] }) {
  return (
    // ✅ horizontal scroll wrapper prevents mobile overflow
    <div className="overflow-x-auto">
      <table
        className="w-full text-[13px]"
        role="table"
        aria-label="Machine metrics"
      >
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th
              scope="col"
              className="px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-[var(--text-muted)]"
            >
              Machine
            </th>
            {/* sortable column */}
            <th
              scope="col"
              aria-sort={sortField === 'cpu' ? (sortDir as 'ascending' | 'descending') : 'none'}
              onClick={() => toggleSort('cpu')}
              className="px-3 py-2.5 text-left cursor-pointer select-none hover:text-[var(--text-primary)] transition-colors"
            >
              CPU %
              <SortIcon field="cpu" currentField={sortField} direction={sortDir} />
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr
              key={row.id}
              className="border-b border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors cursor-pointer"
              onClick={() => onRowClick(row.id)}
              onKeyDown={e => e.key === 'Enter' && onRowClick(row.id)}
              tabIndex={0}
              role="row"
              aria-label={`Machine ${row.name}`}
            >
              <td className="px-3 py-2.5">{row.name}</td>
              <td className="px-3 py-2.5 font-mono">{row.cpu}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### 20.2 Virtual scrolling for large lists

```tsx
import { useVirtualizer } from '@tanstack/react-virtual';

function VirtualRunnerList({ runners }: { runners: Runner[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: runners.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 48,
    overscan: 5,
  });

  return (
    <div ref={parentRef} className="overflow-auto h-[500px]">
      <div style={{ height: virtualizer.getTotalSize() }} className="relative">
        {virtualizer.getVirtualItems().map(item => (
          <div
            key={item.key}
            style={{ position: 'absolute', top: item.start, width: '100%' }}
          >
            <RunnerRow runner={runners[item.index]} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

### 20.3 Bulk actions pattern (UX Pro Max)

```tsx
// ✅ checkbox column + action bar for bulk operations
function TableWithBulkActions({ rows }: { rows: Row[] }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());

  return (
    <>
      {selected.size > 0 && (
        <div
          role="region"
          aria-label="Bulk actions"
          className="flex items-center gap-3 px-4 py-2 rounded-md border border-[var(--border-focus)] bg-[var(--accent-dim)] mb-2"
        >
          <span className="text-[13px] text-[var(--text-secondary)]">
            {selected.size} selected
          </span>
          <button onClick={handleBulkDelete} className="btn-destructive">Delete</button>
          <button onClick={() => setSelected(new Set())} className="btn-ghost">Clear</button>
        </div>
      )}
      <table>
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                checked={selected.size === rows.length}
                onChange={e => setSelected(e.target.checked ? new Set(rows.map(r => r.id)) : new Set())}
                aria-label="Select all rows"
              />
            </th>
            {/* ... */}
          </tr>
        </thead>
      </table>
    </>
  );
}
```

---

## 21. Charts & Data Visualization

### 21.1 Chart type decision table (from UI/UX Pro Max)

| Data Type | Best Chart | Library | Notes |
|-----------|-----------|---------|-------|
| CPU/RAM trend over time | **Line Chart** | Recharts, ApexCharts | Line style (not color only) per series |
| Real-time streaming metrics | **Streaming Area** | ApexCharts, Canvas-based | Pause/resume control required |
| Anomaly detection | **Line + highlights** | D3.js, Plotly, ApexCharts | Shape marker per anomaly (not color only) |
| Category comparison | **Bar Chart** | Recharts | Horizontal for long labels |
| Distribution | **Histogram** | Chart.js | |
| Part-of-whole | **Pie/Donut** | Recharts | Max 6 segments |
| Correlation | **Scatter** | D3.js | |
| KPI single value | **Stat Card** | Custom | Large text + trend indicator |

### 21.2 Chart accessibility requirements

```tsx
// ✅ every chart needs:
// 1. aria-label on container
// 2. title + description elements
// 3. differentiate series by LINE STYLE not color only
// 4. pause/resume on real-time charts
// 5. toggleable data table fallback

function CPUChart({ data }: { data: MetricPoint[] }) {
  const [paused, setPaused] = useState(false);

  return (
    <div role="img" aria-label="CPU usage over time">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[13px] font-semibold text-[var(--text-secondary)]">CPU Usage</h3>
        {/* Pause/resume for real-time charts */}
        <button
          onClick={() => setPaused(p => !p)}
          aria-pressed={paused}
          aria-label={paused ? 'Resume live updates' : 'Pause live updates'}
          className="btn-ghost text-[11px]"
        >
          {paused ? 'Resume' : 'Pause'}
        </button>
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="time" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
          <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} domain={[0, 100]} />
          <Tooltip
            contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
            labelStyle={{ color: 'var(--text-secondary)' }}
          />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#3B82F6"
            strokeWidth={2}
            fill="rgba(59,130,246,.12)"
            strokeDasharray={undefined}  /* solid for primary */
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```

### 21.3 Real-time chart limits

- **Canvas/WebGL required** for > 1000 data points
- Buffer last 60–300s of data; downsample older data
- Show current value as large text KPI alongside chart
- Update at ≤ 1Hz for SVG; use Canvas for higher rates
- `prefers-reduced-motion` → freeze animation, show latest value only

---

## 22. Navigation Patterns

### 22.1 Sidebar navigation (dashboard pattern)

```tsx
function Sidebar({ currentPage, onNavigate }: SidebarProps) {
  return (
    <nav
      role="navigation"
      aria-label="Main navigation"
      className="flex flex-col w-[220px] h-screen border-r border-[var(--border)] bg-[var(--bg-surface)]"
    >
      {/* Logo */}
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <span className="text-[15px] font-semibold text-[var(--text-primary)]">Dashboard</span>
      </div>

      {/* Nav items */}
      <ul className="flex-1 py-2 overflow-y-auto" role="list">
        {NAV_ITEMS.map(item => (
          <li key={item.page}>
            <button
              role="menuitem"
              aria-current={currentPage === item.page ? 'page' : undefined}
              onClick={() => onNavigate(item.page)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-2.5 text-[13px] transition-colors",
                "cursor-pointer hover:bg-[var(--bg-hover)]",
                "focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--border-focus)] focus-visible:outline-none",
                currentPage === item.page
                  ? "bg-[var(--accent-dim)] text-[var(--accent)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              )}
            >
              <item.Icon size={16} aria-hidden="true" />
              {item.label}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
```

### 22.2 Hash-based routing (SPA without React Router)

```tsx
// Pattern used in DevSecOps Dashboard — lightweight hash routing
const VALID_PAGES = new Set<Page>(["landing", "metrics", "alerts"]);

function pageFromHash(): Page {
  const h = window.location.hash.replace(/^#\/?/, "");
  return VALID_PAGES.has(h as Page) ? (h as Page) : "landing";
}

function pushPage(p: Page) {
  const hash = `#/${p}`;
  if (window.location.hash !== hash) window.history.pushState(null, "", hash);
}

// Listen for browser back/forward
useEffect(() => {
  const handler = () => setPage(pageFromHash());
  window.addEventListener('popstate', handler);
  return () => window.removeEventListener('popstate', handler);
}, []);
```

---

## 23. Loading States & Skeletons

### 23.1 Loading decision matrix

| Duration | Pattern |
|----------|---------|
| < 100ms | Nothing (instant) |
| 100–300ms | Subtle opacity fade |
| 300ms–1s | Skeleton loader |
| > 1s | Skeleton + progress indicator |
| Indefinite | Skeleton + cancel option |

### 23.2 Skeleton component library pattern

```tsx
// Base skeleton with reduced-motion support
function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-md motion-reduce:animate-none", className)}
      style={{ background: 'var(--bg-inset)' }}
      aria-hidden="true"
    />
  );
}

// Composed skeleton for specific content shapes
function RunnerTableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div>
      {/* Table header */}
      <div className="flex gap-3 px-3 py-2 border-b border-[var(--border)]">
        <Skeleton className="h-3 w-32" />
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-24" />
      </div>
      {/* Table rows */}
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex gap-3 px-3 py-3 border-b border-[var(--border)]">
          <Skeleton className={`h-4 w-[${40 + (i % 3) * 20}%]`} />
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
    </div>
  );
}
```

### 23.3 Empty states

```tsx
function EmptyState({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon: React.ElementType;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div
      className="flex flex-col items-center justify-center py-16 gap-3"
      role="status"
      aria-label={title}
    >
      <div
        className="w-14 h-14 rounded-2xl flex items-center justify-center border border-[var(--border)]"
        style={{ background: 'var(--bg-inset)' }}
      >
        <Icon size={24} className="text-[var(--text-dim)]" aria-hidden="true" />
      </div>
      <div className="text-center">
        <p className="text-[13px] font-semibold text-[var(--text-secondary)]">{title}</p>
        <p className="text-[11px] text-[var(--text-muted)] mt-0.5">{body}</p>
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
```

---

## 24. Frontend Security (OWASP A01–A10)

### A01 — Broken Access Control

```tsx
// ❌ client-side RBAC only — bypassed by editing JS
function AdminPanel() {
  const role = localStorage.getItem('role');  // client-controlled!
  if (role !== 'admin') return null;
  return <DangerousAdminActions />;
}

// ✅ RBAC from trusted server session, gated server-side
// Client hides UI, server enforces
function AdminPanel() {
  const { user } = useAuth();  // user from server-signed JWT
  if (user?.role !== 'admin') return null;
  return <AdminActions />;     // server also validates before action
}
```

### A02 — Cryptographic Failures

```tsx
// ❌ storing tokens in localStorage (XSS steals them)
localStorage.setItem('token', jwt);

// ✅ HttpOnly cookie (set by server) — not accessible via JS
// Client just calls API; cookie is sent automatically
// Never store sensitive tokens in localStorage, sessionStorage, or window vars
```

### A03 — Injection (XSS)

```tsx
// ❌ dangerouslySetInnerHTML with user content — XSS
<div dangerouslySetInnerHTML={{ __html: userContent }} />

// ✅ render as text — React escapes automatically
<div>{userContent}</div>

// ✅ when HTML rendering is necessary, sanitize first
import DOMPurify from 'dompurify';
<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(htmlContent) }} />

// ❌ building URLs from user input without validation
const url = `javascript:${userInput}`;     // XSS via javascript: scheme

// ✅ validate href origin
function SafeLink({ href, children }: { href: string; children: React.ReactNode }) {
  const safe = href.startsWith('https://') || href.startsWith('/');
  if (!safe) return <span>{children}</span>;
  return <a href={href} rel="noopener noreferrer">{children}</a>;
}
```

### A05 — Security Misconfiguration

```tsx
// ✅ rel="noopener noreferrer" on all external links
<a href={externalUrl} target="_blank" rel="noopener noreferrer">
  External Link
</a>

// ✅ Content Security Policy headers (set server-side in nginx/FastAPI)
// script-src 'self'; style-src 'self' fonts.googleapis.com; img-src 'self' data:
```

### A07 — Identification & Auth Failures

```tsx
// ✅ handle 401 globally — redirect to login without exposing session
useEffect(() => {
  const handler = () => {
    setUser(null);
    setLoading(false);
    // Don't expose which endpoint triggered the 401
  };
  window.addEventListener("auth:expired", handler);
  return () => window.removeEventListener("auth:expired", handler);
}, []);

// api.ts — emit event on 401 rather than throwing to each caller
if (res.status === 401) {
  window.dispatchEvent(new Event("auth:expired"));
  throw new Error("Session expired");
}
```

### A10 — SSRF (via user-controlled URLs)

```tsx
// ❌ fetching user-supplied URLs client-side (also an issue server-side)
const preview = await fetch(userSuppliedUrl);

// ✅ proxy via backend that validates URL against allowlist
const preview = await fetch(`/api/preview?url=${encodeURIComponent(userSuppliedUrl)}`);
// Backend validates URL scheme, host, and port before proxying
```

---

## 25. Performance Optimization

### 25.1 Bundle size

```tsx
// ❌ import entire library for one utility
import _ from 'lodash';
const sorted = _.sortBy(items, 'name');

// ✅ named import — tree-shakeable
import { sortBy } from 'lodash-es';

// ✅ replace with native where possible
const sorted = [...items].sort((a, b) => a.name.localeCompare(b.name));

// ✅ code splitting for heavy components
const AnalyticsPage = lazy(() => import('./components/AnalyticsPage'));
```

### 25.2 Image optimization

```tsx
// ✅ Next.js Image component (auto WebP/AVIF, lazy loading, LCP optimization)
import Image from 'next/image';
<Image src="/logo.png" width={48} height={48} alt="Company logo" priority />

// ✅ native lazy loading for non-critical images
<img src="/screenshot.png" loading="lazy" decoding="async" alt="Dashboard screenshot" />

// ❌ auto-play video — massive data and energy waste
<video autoPlay loop />

// ✅ click-to-play
<video controls preload="none" playsInline />
```

### 25.3 React performance

```tsx
// ✅ React 18+ automatic batching — trust it
setAlerts(a);
setLoading(false);  // batched automatically — no flushSync needed

// ✅ use React DevTools Profiler before optimizing
// Profile → identify → optimize → verify improvement

// ✅ virtualize lists over 50–100 items
import { useVirtualizer } from '@tanstack/react-virtual';

// ✅ React Compiler (Next.js 15 — auto-memoization)
// next.config.ts
const nextConfig = {
  experimental: {
    reactCompiler: true,  // auto-memoizes eligible components and hooks
  },
};
```

### 25.4 Core Web Vitals targets

| Metric | Good | Target |
|--------|------|--------|
| LCP (Largest Contentful Paint) | < 2.5s | < 1.5s |
| INP (Interaction to Next Paint) | < 200ms | < 100ms |
| CLS (Cumulative Layout Shift) | < 0.1 | < 0.05 |

```tsx
// CLS prevention — always specify dimensions for media
<img width={200} height={100} src="..." alt="..." />
<div style={{ aspectRatio: '16/9' }}><img ... /></div>

// LCP optimization — preload critical images
import { preload } from 'react-dom';
preload('/hero.webp', { as: 'image' });
```

---

## 26. ESLint & tsconfig

### 26.1 Recommended `tsconfig.json`

```jsonc
{
  "compilerOptions": {
    // Strictness (all required)
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "exactOptionalPropertyTypes": true,
    "useUnknownInCatchVariables": true,

    // Module
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,

    // Output
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "jsx": "preserve",
    "noEmit": true,

    // Quality
    "forceConsistentCasingInFileNames": true,
    "skipLibCheck": true
  },
  "include": ["src"],
  "exclude": ["node_modules", "dist"]
}
```

### 26.2 Recommended ESLint flat config

```ts
// eslint.config.ts
import tseslint from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';

export default [
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { parser: tsParser, parserOptions: { project: true } },
    plugins: {
      '@typescript-eslint': tseslint,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // Type safety
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-member-access': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
      '@typescript-eslint/await-thenable': 'error',

      // Style
      '@typescript-eslint/consistent-type-imports': 'error',
      '@typescript-eslint/prefer-nullish-coalescing': 'warn',
      '@typescript-eslint/prefer-optional-chain': 'warn',

      // React
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'react-refresh/only-export-components': 'warn',

      // Security
      'no-eval': 'error',
      'no-implied-eval': 'error',
    },
  },
];
```

---

## 27. Testing Strategy

### 27.1 Test pyramid for React apps

| Layer | Tool | Focus | Coverage |
|-------|------|-------|----------|
| Unit | Vitest + Testing Library | Hooks, utilities, reducers | 70%+ |
| Integration | Vitest + Testing Library | Component behavior, forms | 20%+ |
| E2E | Playwright | Critical user flows | 5 flows |
| Visual | Playwright screenshot | UI regressions | Key pages |

### 27.2 Component test pattern

```tsx
// AlertsPage.test.tsx
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { AlertsPage } from '../components/AlertsPage';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';

test('shows skeleton while loading alerts', () => {
  // Delay response to catch loading state
  server.use(http.get('/api/alerts', async () => {
    await new Promise(r => setTimeout(r, 100));
    return HttpResponse.json([]);
  }));

  render(<AlertsPage />, { wrapper: QueryWrapper });
  expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
});

test('displays error state when API fails', async () => {
  server.use(http.get('/api/alerts', () => HttpResponse.error()));

  render(<AlertsPage />, { wrapper: QueryWrapper });
  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent(/failed to load/i);
  });
});

test('navigates to alert detail on row click', async () => {
  server.use(http.get('/api/alerts', () => HttpResponse.json([mockAlert])));

  render(<AlertsPage />, { wrapper: QueryWrapper });
  await screen.findByText(mockAlert.name);

  fireEvent.click(screen.getByRole('row', { name: mockAlert.name }));
  expect(mockOnNavigate).toHaveBeenCalledWith(mockAlert.id);
});
```

### 27.3 Custom Hook testing

```tsx
// useAlertRules.test.ts
import { renderHook, act } from '@testing-library/react';
import { useAlertRules } from '../hooks/useAlertRules';

test('toggles alert rule enabled state optimistically', async () => {
  const { result } = renderHook(() => useAlertRules(), { wrapper: QueryWrapper });

  await waitFor(() => expect(result.current.rules).toHaveLength(2));

  act(() => result.current.toggle(rules[0].id));

  // Optimistic — instant
  expect(result.current.rules[0].enabled).toBe(false);

  // After server confirm — still false
  await waitFor(() => expect(result.current.isTogglingId).toBeNull());
  expect(result.current.rules[0].enabled).toBe(false);
});
```

---

## 28. Master Review Checklist

Use before shipping any React/Next.js/TypeScript UI change.

### TypeScript

- [ ] No `any` — use `unknown` + type guard, or proper interface
- [ ] Discriminated unions for multi-state objects
- [ ] Generics have `extends` constraints
- [ ] `as const` for fixed option objects
- [ ] No `@ts-ignore` (use `@ts-expect-error` with comment)
- [ ] `strict: true` + `noUncheckedIndexedAccess: true` in tsconfig
- [ ] Array index access checked for `undefined` before use

### React Hooks

- [ ] All Hooks called unconditionally at top level
- [ ] Custom Hooks start with `use`
- [ ] `useEffect` deps complete — no suppressed lint warnings
- [ ] Every subscription/timer effect returns cleanup
- [ ] Derived state computed inline — not stored in useState
- [ ] Side effects from events live in handlers, not effects
- [ ] `useMemo`/`useCallback` only for genuinely expensive/ref-sensitive code

### Component Design

- [ ] No child component definitions inside render functions
- [ ] Props to `React.memo` children use stable references
- [ ] Components ≤ 200 lines; logic in custom Hooks
- [ ] Lists > 100 items use virtualization

### React 19

- [ ] `useActionState` replaces multi-useState form patterns
- [ ] `useFormStatus` called inside `<form>` child, not in the form itself
- [ ] `useOptimistic` not used for irreversible operations
- [ ] `use()` receives Promise from outside render (not created in render)
- [ ] Server Actions marked `'use server'`, validated server-side

### Suspense & Error Boundaries

- [ ] Every `<Suspense>` is wrapped in `<ErrorBoundary>`
- [ ] Boundaries are granular — independent content has independent boundaries
- [ ] Fallbacks are skeletons matching content shape, not generic spinners
- [ ] `useSuspenseQuery` guarded by component composition (not `enabled`)

### UI/UX — Accessibility

- [ ] No emoji as icons — SVG (Lucide, Heroicons)
- [ ] All interactive elements have `cursor-pointer`
- [ ] Hover + focus states with transitions (150–300ms)
- [ ] Text contrast ≥ 4.5:1 (normal), ≥ 3:1 (large)
- [ ] Focus rings visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected in animations
- [ ] Touch targets ≥ 44×44px
- [ ] Semantic HTML (`<button>`, `<nav>`, `<main>`, `<table>`)
- [ ] ARIA labels on icon-only buttons
- [ ] `role="alert"` on error messages
- [ ] `aria-live` on dynamic content regions

### UI/UX — Responsive

- [ ] No horizontal scroll at 375px, 768px, 1024px, 1440px
- [ ] Tables wrapped in `overflow-x-auto`
- [ ] Mobile-first breakpoints

### UI/UX — Visual

- [ ] CSS variables used for all colors (never hardcoded)
- [ ] Consistent spacing (4px grid)
- [ ] Loading states for all async operations > 300ms
- [ ] Empty states for empty collections
- [ ] Error states for failed fetches
- [ ] Dark mode tested

### Security

- [ ] No `localStorage` for auth tokens (HttpOnly cookies only)
- [ ] No `dangerouslySetInnerHTML` with unsanitized content
- [ ] External links have `rel="noopener noreferrer"`
- [ ] User content rendered as text, not HTML
- [ ] Client-side RBAC only hides UI — server enforces access
- [ ] No hardcoded secrets in frontend code

### Performance

- [ ] Heavy components code-split with `lazy()`
- [ ] Images have `width`/`height` (prevents CLS)
- [ ] Long lists virtualized
- [ ] No import of entire libraries for one utility

### TanStack Query

- [ ] `queryKey` includes every variable affecting the result
- [ ] `staleTime` set explicitly (not default 0)
- [ ] Mutations call `invalidateQueries` on success
- [ ] `useSuspenseQuery` wrapped in `<ErrorBoundary>` + `<Suspense>`

### Async

- [ ] `fetch` calls check `response.ok`
- [ ] Concurrent independent requests use `Promise.all`
- [ ] Race conditions in `useEffect` handled with `AbortController`
- [ ] No `forEach` with async callbacks
- [ ] No floating Promises

---

## Quick Reference — Design System Tokens

```css
/* Copy this into your global styles */
:root[data-theme="dark"] {
  --bg-page: #020617; --bg-surface: #0F172A; --bg-elevated: #1E293B;
  --bg-inset: #1A1E2F; --bg-hover: rgba(255,255,255,0.05);
  --text-primary: #F8FAFC; --text-secondary: #94A3B8;
  --text-muted: #64748B; --text-dim: #475569;
  --color-success: #22C55E; --color-warning: #F59E0B;
  --color-critical: #EF4444; --color-info: #3B82F6;
  --accent: #22C55E; --accent-hover: #16A34A;
  --accent-dim: rgba(34,197,94,.12);
  --border: #334155; --border-focus: #6366F1;
}
:root[data-theme="light"] {
  --bg-page: #F8FAFC; --bg-surface: #FFFFFF; --bg-elevated: #F1F5F9;
  --bg-inset: #E2E8F0; --text-primary: #0F172A; --text-secondary: #475569;
  --text-muted: #94A3B8; --border: #E2E8F0;
  --color-success: #16A34A; --color-warning: #D97706;
  --color-critical: #DC2626; --color-info: #2563EB;
  --accent: #16A34A; --accent-hover: #15803D;
  --accent-dim: rgba(22,163,74,.12); --border-focus: #6366F1;
}
```

---

*Maintained for React 19 · Next.js 15 · TypeScript 5.x · TanStack Query v5 · WCAG 2.2 · OWASP 2025.*  
*Design system: UI/UX Pro Max — Dark Mode (OLED) for DevSecOps Dashboard.*  
*Last reviewed: June 2026.*
