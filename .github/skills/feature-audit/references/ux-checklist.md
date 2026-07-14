# Phase 5: UX Validation Checklist

Code that works correctly but feels broken to users is a failed feature.
Developers who understand UX catch more issues before QA than those who only think about logic.

---

## The UX Developer Mindset

Think like a user, not like a developer:
- A developer thinks: "The API returned 200, the feature works."
- A user thinks: "I clicked the button and nothing happened. Is it broken?"

The gap between these perspectives is where most UX bugs live.

---

## Step 1: Map the Full User Journey

Before validating UX, write out the complete user journey for the feature.

```
Entry point: User arrives at [page/screen/trigger]
  ↓
Action 1: [User does X]
  → Happy path: [what the user sees]
  → Slow path: [what happens when it takes 3 seconds]
  → Error path: [what the user sees when it fails]
  ↓
Action 2: [User does Y]
  → ...
  ↓
Exit point: User has accomplished [the goal]
```

For every action, ask:
- Does the user know what happened?
- Does the user know what to do next?
- Does the user know if something went wrong?

---

## Step 2: State Coverage Checklist

These are the states where UX most frequently fails. Check every single one.

### Loading States
- [ ] Is there a visible loading indicator when data is being fetched?
- [ ] Does the UI feel frozen during loading, or are other parts still interactive?
- [ ] If loading takes > 3 seconds, is there additional feedback (progress, "still working...")?
- [ ] Does a skeleton screen or placeholder prevent layout shift?
- [ ] If loading fails, does the user see an error instead of an empty/broken state?

### Empty States
- [ ] When there is no data (0 results, first-time user), is there a meaningful message?
- [ ] Does the empty state tell the user WHY it's empty and WHAT they can do?
  - Bad: *(blank screen)*
  - Bad: "No results."
  - Good: "You haven't added any items yet. [Add your first item →]"
- [ ] Is the empty state styled and branded (not just plain text)?

### Error States
- [ ] Are errors explained in plain language (not "Error 422" or "Internal Server Error")?
- [ ] Does the error message tell the user what they can do to recover?
  - Bad: "Something went wrong."
  - Good: "We couldn't save your changes. Check your connection and try again."
- [ ] Is the error displayed near the thing that failed (inline), not only in a toast/banner?
- [ ] For validation errors, is each error shown next to the field it relates to?
- [ ] Are errors dismissible or do they persist?

### Validation / Form Errors
- [ ] Validation runs on both submit AND on field blur (not only on submit)
- [ ] Each field error is next to the field, not in a single block at the top
- [ ] Error messages explain the rule, not just that it's wrong:
  - Bad: "Invalid password"
  - Good: "Password must be at least 8 characters and include one number"
- [ ] After fixing a validation error, it clears immediately (on-change validation)
- [ ] Screen readers can read validation errors (use `aria-describedby` or `role="alert"`)

### Success / Confirmation States
- [ ] Does the user receive clear confirmation that their action completed?
- [ ] Is the success state distinguishable from the default/loading state?
- [ ] For long operations, is the user notified when it completes (email, notification, status update)?
- [ ] Is the UI consistent after success? (Data refreshed, form cleared if expected, navigation correct)

---

## Step 3: Interaction Quality

### Feedback and Responsiveness
- [ ] Every interactive element (button, link, form field) gives visual feedback on interaction (hover, focus, active states)
- [ ] Buttons are disabled and show loading state while their action is processing (prevents double-submission)
- [ ] After submitting a form, the submit button shows "Saving..." or similar
- [ ] Destructive actions (delete, remove) require confirmation before executing
- [ ] Actions are reversible where possible ("Undo" or soft delete)

### Navigation and Flow
- [ ] The user can navigate back without losing progress (browser back button doesn't break the form)
- [ ] After a successful action, the user lands in the right place (not on a blank page)
- [ ] The URL updates to reflect the current state (deep-linkable where appropriate)
- [ ] Breadcrumbs or navigation indicators show where the user is in a multi-step flow

---

## Step 4: Accessibility (WCAG 2.2 Baseline)

Accessibility is not optional. It is a legal requirement in many jurisdictions and is the right thing to do.

### Keyboard Navigation
- [ ] All interactive elements can be reached via `Tab` key
- [ ] Tab order is logical (matches visual order and workflow order)
- [ ] Actions that require a mouse also work with `Enter` or `Space` on keyboard
- [ ] Keyboard focus never gets trapped (modal dialogs are an exception — they trap focus intentionally and release on close)
- [ ] Focus is managed after dynamic changes (modals, drawers, notifications — focus moves to the new content)
- [ ] There is a "Skip to main content" link for keyboard users to bypass navigation

### Focus Indicators
- [ ] Focus ring is visible on all interactive elements
- [ ] Focus ring is not suppressed with `outline: none` without a custom alternative
- [ ] Focus indicator has at least 3:1 contrast with the surrounding background

### Screen Reader Compatibility
- [ ] All images have meaningful `alt` text (or `alt=""` if decorative)
- [ ] Form inputs have associated `<label>` elements (not just placeholder text)
- [ ] Icon-only buttons have `aria-label` or visually-hidden text
- [ ] Status messages and toast notifications use `role="alert"` or `aria-live`
- [ ] Dynamic content updates (loading complete, errors appeared) are announced
- [ ] Tables have `<th>` elements with `scope` attributes
- [ ] Modals and dialogs trap focus and have `role="dialog"` with `aria-modal="true"` and a labeled heading

### Color and Contrast
- [ ] Text contrast ratio ≥ 4.5:1 against its background (use WebAIM Contrast Checker)
- [ ] Large text (18px+ or 14px bold) contrast ratio ≥ 3:1
- [ ] UI component contrast (buttons, input borders) ≥ 3:1 against adjacent colors
- [ ] No information is conveyed by color alone (icons, patterns, or text labels must supplement color)
- [ ] The feature is usable when viewed in high-contrast mode (Windows/macOS accessibility settings)

### Semantic HTML
- [ ] Headings (`h1–h6`) form a logical document outline
- [ ] Navigation landmarks use `<nav>`, `<main>`, `<aside>`, `<header>`, `<footer>`
- [ ] Lists use `<ul>`, `<ol>`, `<dl>` (not just styled `<div>` elements)
- [ ] No `<div>` or `<span>` used for interactive elements — use `<button>`, `<a>`, `<input>` etc.
- [ ] Custom widgets that mimic native controls implement the correct ARIA roles and keyboard patterns (see [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/))

---

## Step 5: Responsive and Mobile Behavior

- [ ] Feature works correctly on mobile screen sizes (360px–414px width minimum)
- [ ] Touch targets are at least 44×44px (WCAG 2.2 requirement)
- [ ] No content is cut off or horizontally scrolls unexpectedly on small screens
- [ ] Hover states have touch equivalents (tap to reveal, not hover-dependent)
- [ ] Inputs of type `email`, `tel`, `number`, `date` trigger the correct mobile keyboard
- [ ] Pinch-to-zoom is not disabled (`user-scalable=no` must not be used)

---

## Step 6: Performance Perception

A technically fast feature can feel slow, and vice versa.

| Threshold | User Perception | What to Do |
|-----------|----------------|------------|
| < 100ms | Instant | No indicator needed |
| 100ms – 1s | Slight delay | Show that action was received (button state) |
| 1s – 3s | Noticeable wait | Show a loading spinner |
| 3s – 10s | Frustrating | Show progress + estimated time |
| > 10s | Broken feeling | Async operation + notify when done |

- [ ] Optimistic updates used where safe (show result immediately, rollback on failure)
- [ ] Page doesn't jump or reflow when data loads (skeleton screens or reserved space)
- [ ] Images have explicit `width` and `height` attributes to prevent layout shift
- [ ] Long lists use virtualization if > 100 items

---

## Step 7: Exploratory Testing

Structured testing proves the feature works. Exploratory testing finds what you didn't think to test.

**Mindset**: You are trying to break the feature. Think adversarially.

**Exploration patterns**:
1. **The impatient user**: Click rapidly, double-submit, navigate away mid-action
2. **The confused user**: Try the wrong workflow, use the feature in an unintended order
3. **The power user**: Use keyboard shortcuts throughout, try every form field with extreme values
4. **The mobile user**: Use on a real phone (not browser emulation) — touch, zoom, rotate
5. **The slow connection user**: Throttle to 3G in devtools, test all async operations
6. **The edge data user**: Empty strings, very long strings, special characters, Unicode, past dates, future dates
7. **The multi-tab user**: Open the same page in two tabs and perform actions in both

**Hallway testing**: Ask 2–3 people who didn't build the feature to use it while you watch silently.
The places they hesitate, click the wrong thing, or express confusion are UX bugs.

---

## UX Validation Quick Summary

| Check | Status |
|-------|--------|
| Happy path works end-to-end | |
| Loading state visible and meaningful | |
| Empty state is informative (not blank) | |
| Error state is clear and actionable | |
| Validation errors are field-level | |
| Success is confirmed to the user | |
| Keyboard navigable (Tab through everything) | |
| Focus indicators visible | |
| Screen reader labels on all interactive elements | |
| Color contrast passes WCAG 2.2 | |
| Mobile touch targets ≥ 44×44px | |
| Exploratory testing completed | |
| Animation is smooth and purposeful | |
| Card layouts fit content properly | |
| UI style matches application type | |

---

## Step 8: Modern UI Styles — Choose What Fits Your Application

### UI Style Guide by Application Type

Different applications need different UI approaches. Choose the style that matches your context:

| Application Type | Recommended UI Style | Key Characteristics |
|-----------------|---------------------|-------------------|
| **SaaS Dashboard** | Clean/Minimal + Data-dense | Sidebar nav, card grids, charts, muted colors, lots of whitespace between data |
| **E-commerce** | Visual/Product-focused | Large images, clear CTAs, trust signals, quick-scan pricing, filter panels |
| **Social/Community** | Feed-based + Engaging | Card feeds, infinite scroll, reactions, avatars, real-time updates |
| **Enterprise/Internal** | Functional/Dense | Tables, forms, navigation trees, status badges, compact spacing |
| **Landing Page/Marketing** | Bold/Expressive | Hero sections, large typography, scroll animations, gradient backgrounds |
| **Mobile App** | Touch-first/Native feel | Bottom nav, gesture-driven, full-width cards, large touch targets |
| **Developer Tool** | Monospace/Technical | Code blocks, terminal aesthetic, dark mode default, minimal chrome |
| **Healthcare/Finance** | Conservative/Trustworthy | Neutral colors, clear hierarchy, high contrast, no decorative elements |
| **Creative/Portfolio** | Artistic/Experimental | Asymmetric layouts, custom typography, bold colors, immersive media |
| **AI/Chat Interface** | Conversational/Minimal | Message bubbles, typing indicators, suggested actions, streaming text |

### Modern Design Trends (2025–2026)

| Trend | What It Is | When to Use | When NOT to Use |
|-------|-----------|-------------|-----------------|
| **Bento Grid** | Asymmetric card grid (like Apple's feature pages) | Feature showcases, dashboards, portfolios | Dense data tables, forms |
| **Glassmorphism** | Frosted glass effect with backdrop blur | Hero overlays, modals, floating panels | Body text areas, enterprise apps |
| **Neubrutalism** | Raw borders, high contrast, handdrawn feel | Creative sites, portfolios, indie products | Enterprise, healthcare, finance |
| **Soft UI / Neumorphism** | Subtle shadows mimicking physical buttons | Settings panels, toggles | Dense UIs, accessibility-critical |
| **Dark Mode First** | Dark backgrounds with light text | Developer tools, media apps, gaming | Document-heavy apps (optional is better) |
| **Gradient Mesh** | Complex multi-color gradients | Backgrounds, hero sections, branding | Text areas, data displays |
| **Micro-animations** | Small purposeful motion (hover, click, transition) | EVERYWHERE (but subtle) | Never overdo — performance matters |
| **3D Elements** | Three.js/WebGL integrated elements | Hero sections, product showcases, gaming | Content-heavy apps, mobile-first |
| **Variable Fonts** | Single font with weight/width axis adjustments | Headings, responsive typography | Icon text, small UI labels |
| **Spatial Design** | Depth through layering, shadows, z-axis | Cards, modals, navigation, dropdowns | Flat information architecture |

---

## Step 9: Card Design — Fitting Content Properly

Cards are the building block of modern UI. Getting them right is critical.

### Card Layout Rules

| Rule | Why | Implementation |
|------|-----|---------------|
| **Consistent height in rows** | Prevents jarring gaps | Use CSS Grid with `grid-auto-rows: 1fr` or `align-items: stretch` |
| **Content hierarchy** | Users scan top-to-bottom | Image/visual → Title → Description → Action (always this order) |
| **Appropriate padding** | Breathing room without waste | 16-24px padding, 12-16px gap between cards |
| **Truncation strategy** | Long text doesn't break layout | `line-clamp` for descriptions, `text-overflow: ellipsis` for titles |
| **Responsive columns** | Works on all screens | `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr))` |
| **Image aspect ratio** | Prevents layout shift | Fixed aspect ratio container (`aspect-ratio: 16/9` or `4/3`) |
| **Hover feedback** | Indicates interactivity | Subtle shadow lift + scale(1.02) transition |
| **Clear action area** | Users know what to click | Full-card clickable OR explicit button — never ambiguous |

### Card Fitting Solutions

```css
/* Problem: Cards with different content heights look broken */
/* Solution: CSS Grid with equal height rows */
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
  align-items: stretch; /* Equal height cards */
}

.card {
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
  background: var(--surface);
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  transition: box-shadow 0.2s, transform 0.2s;
}

.card:hover {
  box-shadow: 0 8px 25px rgba(0,0,0,0.12);
  transform: translateY(-2px);
}

.card-body {
  flex: 1; /* Pushes footer to bottom regardless of content height */
  padding: 1.25rem;
}

.card-footer {
  padding: 1rem 1.25rem;
  border-top: 1px solid var(--border);
  margin-top: auto; /* Always at the bottom */
}

/* Problem: Images break card layout */
/* Solution: Fixed aspect ratio container */
.card-image {
  aspect-ratio: 16 / 9;
  object-fit: cover;
  width: 100%;
}

/* Problem: Long titles/descriptions overflow */
/* Solution: Multi-line clamp */
.card-title {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-description {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: var(--text-secondary);
}
```

### Card Types for Different Content

| Card Type | Best For | Structure |
|-----------|----------|-----------|
| **Basic Card** | List items, feeds, products | Image + Title + Description + Action |
| **Stat Card** | Dashboards, analytics | Big number + Label + Trend indicator |
| **Profile Card** | Users, contacts, team | Avatar + Name + Role + Actions |
| **Action Card** | CTA, feature promotion | Icon/Illustration + Title + Button |
| **Media Card** | Gallery, portfolio, video | Full-bleed image + Overlay title |
| **Comparison Card** | Pricing, plans, features | Header + Feature list + CTA (equal height!) |
| **Timeline Card** | Activity feed, changelog | Date + Content + Status indicator |
| **Notification Card** | Alerts, messages, updates | Icon + Message + Time + Dismiss |

---

## Step 10: Animations & Micro-Interactions — Professional Motion Design

### Animation Principles (from Disney's 12 Principles adapted for UI)

| Principle | UI Application | Example |
|-----------|---------------|---------|
| **Easing** | Never use linear motion | `ease-out` for entrances, `ease-in` for exits |
| **Anticipation** | Prepare user for change | Button press slightly shrinks before action |
| **Follow-through** | Natural momentum | List items settle slightly past position then bounce back |
| **Staging** | Direct attention | Darken background when modal appears |
| **Timing** | Match importance to duration | Small UI: 150-200ms. Page transitions: 300-400ms |
| **Exaggeration** | Make feedback visible | Error shake slightly more than needed to be noticed |

### Timing Guidelines

| Animation Type | Duration | Easing |
|---------------|----------|--------|
| Hover effects | 100-150ms | ease-out |
| Button feedback | 100-200ms | ease-in-out |
| Dropdown/menu open | 200-250ms | ease-out |
| Modal entrance | 200-300ms | ease-out (with slight scale) |
| Page transitions | 300-400ms | ease-in-out |
| Loading skeletons | 1.5-2s loop | ease-in-out pulse |
| Notification slide-in | 250-350ms | ease-out (spring-like) |
| Notification auto-dismiss | 5000ms wait + 200ms fade |

### CSS Animation Patterns

```css
/* Smooth hover lift (cards, buttons) */
.interactive {
  transition: transform 0.2s ease-out, box-shadow 0.2s ease-out;
}
.interactive:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.15);
}

/* Entrance animation (elements appearing) */
@keyframes fadeInUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-in { animation: fadeInUp 0.3s ease-out forwards; }

/* Staggered list items */
.list-item { animation: fadeInUp 0.3s ease-out forwards; }
.list-item:nth-child(1) { animation-delay: 0ms; }
.list-item:nth-child(2) { animation-delay: 50ms; }
.list-item:nth-child(3) { animation-delay: 100ms; }

/* Loading skeleton pulse */
@keyframes shimmer {
  0% { background-position: -200px 0; }
  100% { background-position: calc(200px + 100%) 0; }
}
.skeleton {
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200px 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}

/* Smooth page/section transitions */
.page-enter { opacity: 0; transform: translateX(20px); }
.page-enter-active {
  opacity: 1; transform: translateX(0);
  transition: opacity 0.3s, transform 0.3s ease-out;
}

/* Button press feedback */
.button:active { transform: scale(0.96); }

/* Error shake */
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20%, 60% { transform: translateX(-5px); }
  40%, 80% { transform: translateX(5px); }
}
.error-shake { animation: shake 0.4s ease-in-out; }

/* Respect user preferences */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### When NOT to Animate

- ❌ Don't animate every element (overwhelms users)
- ❌ Don't use animation > 500ms for UI actions (feels slow)
- ❌ Don't animate if it delays task completion
- ❌ Don't forget `prefers-reduced-motion` (accessibility requirement!)
- ❌ Don't animate layout shifts (causes jank — use CSS transforms only)
- ❌ Don't autoplay videos or looping animations without user control

---

## Step 11: Laws of UX — Design Psychology Applied

These laws (from lawsofux.com) should guide EVERY UI decision:

| Law | Rule | Practical Application |
|-----|------|----------------------|
| **Fitts's Law** | Larger, closer targets are easier to hit | Make primary actions big; don't put important buttons in corners |
| **Hick's Law** | More choices = more decision time | Limit options to 5-7; use progressive disclosure for complexity |
| **Jakob's Law** | Users expect your site to work like others | Follow platform conventions; don't reinvent standard patterns |
| **Miller's Law** | Working memory holds ~7 items | Chunk information into groups; don't show 20 options at once |
| **Doherty Threshold** | Keep response < 400ms for flow state | Optimistic updates, instant feedback, perceived performance |
| **Law of Proximity** | Close elements are perceived as grouped | Use spacing to create visual groups; more space = separate groups |
| **Law of Similarity** | Similar-looking elements = same function | Consistent button styles; different styles for different actions |
| **Von Restorff Effect** | Different items stand out | Make CTAs visually distinct from surrounding content |
| **Peak-End Rule** | Experiences judged by peak and end | Make success moment delightful; make errors gentle |
| **Aesthetic-Usability** | Beautiful UI perceived as more usable | Invest in visual polish — it directly affects usability perception |
| **Tesler's Law** | Complexity can't be eliminated, only moved | Put complexity in the system, not in the user's head |
| **Postel's Law** | Be liberal in accepting input | Accept dates in multiple formats; don't reject "  extra spaces  " |

---

## Step 12: UI Component Best Practices by Type

### Navigation Patterns

| Pattern | Best For | Don'ts |
|---------|----------|--------|
| **Top nav bar** | Marketing sites, simple apps (≤ 7 items) | Don't use if > 7 nav items |
| **Side nav (drawer)** | Dashboards, admin panels, complex apps | Don't auto-collapse on desktop |
| **Bottom tab bar** | Mobile apps (≤ 5 tabs) | Don't use > 5 items; don't use on web desktop |
| **Breadcrumbs** | Deep hierarchies, e-commerce categories | Don't use for flat navigation |
| **Mega menu** | Large sites with many categories | Don't use without clear grouping |
| **Command palette** | Developer tools, power user apps | Don't make it the ONLY way to navigate |

### Form Design Best Practices

| Rule | Why |
|------|-----|
| One column layout | Multi-column forms decrease completion rate |
| Labels above fields | Faster scanning than left-aligned labels |
| Group related fields | Reduces cognitive load (chunk) |
| Show field requirements clearly | `*` for required OR "(optional)" labels — don't mix |
| Inline validation on blur | Immediate feedback without interrupting typing |
| Disabled submit until valid | Prevents errors; shows progress |
| Autofill support | Respect browser autofill names (`name="email"`, `autocomplete="email"`) |
| Smart defaults | Pre-fill what you can (country from locale, today's date) |

### Table/Data Display Best Practices

| Rule | Implementation |
|------|---------------|
| Sticky headers | Header stays visible during scroll |
| Row hover highlight | Helps track across wide tables |
| Zebra striping OR borders | Helps distinguish rows (not both) |
| Sortable columns | Click header to sort; show sort indicator |
| Responsive strategy | Horizontal scroll on mobile OR card layout transformation |
| Pagination or virtual scroll | Never load 1000+ rows at once |
| Empty state | "No data found. [Try different filters →]" |
| Action column last | Edit/Delete buttons on the right (RTL: left) |

---

## Step 13: Color & Typography Best Practices

### Color System

| Token | Purpose | Example Value |
|-------|---------|--------------|
| `--primary` | Main brand/action color | Interactive buttons, links, active states |
| `--primary-hover` | Darker primary for hover | 10-15% darker than primary |
| `--surface` | Card/panel backgrounds | White (light) / Dark gray (dark mode) |
| `--background` | Page background | Slightly off-white / Pure dark |
| `--text-primary` | Main text color | Near-black / Near-white |
| `--text-secondary` | Supporting text | Medium gray (pass contrast!) |
| `--border` | Dividers, card borders | Very light gray / Subtle dark |
| `--success` | Positive feedback | Green tones |
| `--warning` | Caution states | Amber/Orange tones |
| `--error` | Error/destructive | Red tones |
| `--info` | Informational | Blue tones |

### Typography Scale

| Level | Size | Weight | Use |
|-------|------|--------|-----|
| Display | 36-48px | Bold/Black | Hero headings, landing pages |
| H1 | 28-32px | Bold | Page titles |
| H2 | 22-24px | Semibold | Section headers |
| H3 | 18-20px | Semibold | Card titles, sub-sections |
| Body | 15-16px | Regular | Paragraphs, descriptions |
| Small/Caption | 12-14px | Regular/Medium | Metadata, labels, timestamps |

### Spacing Scale (4px base)

```
4px — tight (between related inline elements)
8px — compact (between form field and label)
12px — cozy (between list items)
16px — standard (card padding, section gaps)
24px — comfortable (between cards, between sections)
32px — spacious (major section separation)
48-64px — generous (page-level section separation)
```

---

## Step 14: Dark Mode Implementation

| Rule | Why |
|------|-----|
| Don't just invert colors | Dark backgrounds need reduced contrast text (not pure white) |
| Use `color-scheme: dark` meta | Lets browser handle native controls |
| Reduce image brightness slightly | Bright images are jarring in dark mode |
| Elevate with lighter surfaces (not shadows) | Shadows are invisible on dark backgrounds |
| Test ALL states in dark mode | Forms, errors, disabled states often break |
| Respect `prefers-color-scheme` | Auto-detect user preference |
| Provide manual toggle | Let users override system preference |

### Dark Mode Color Adjustments

```css
:root {
  --background: #ffffff;
  --surface: #f8f9fa;
  --text-primary: #1a1a2e;
  --text-secondary: #6c757d;
}

@media (prefers-color-scheme: dark) {
  :root {
    --background: #0f0f1a;
    --surface: #1a1a2e;
    --text-primary: #e8e8f0;
    --text-secondary: #9ca3af;
  }
}
```

---

## Copilot Routing — UX Queries

When a user asks about UX, use this routing to find the right section:

| User Asks About... | Go To Section |
|--------------------|---------------|
| "Card layout broken" / "cards different heights" | Step 9: Card Design |
| "What animation to use" / "hover effects" | Step 10: Animations |
| "What UI style for my app" / "modern look" | Step 8: Modern UI Styles |
| "Form design" / "form UX" | Step 12: Forms |
| "Colors" / "color system" / "dark mode" | Steps 13-14 |
| "Accessibility" / "a11y" / "keyboard" | Step 4: Accessibility |
| "Loading states" / "skeleton" | Step 2: State Coverage |
| "Navigation pattern" / "sidebar vs top nav" | Step 12: Navigation |
| "Table design" / "data display" | Step 12: Tables |
| "Responsive" / "mobile" | Step 5: Responsive |
| "User testing" / "usability" | Step 7: Exploratory Testing |
| "UX laws" / "design psychology" | Step 11: Laws of UX |

---

## Sources & Further Reading

- [Laws of UX](https://lawsofux.com/) — Psychology-based UX principles (Yablonski, 2026)
- [NNGroup: Top 10 Application Design Mistakes](https://www.nngroup.com/articles/top-10-application-design-mistakes/) — Common UX pitfalls
- [Material Design 3](https://m3.material.io/) — Google's design system (components, tokens, guidelines)
- [Apple Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/) — iOS/macOS design standards
- [WCAG 2.2](https://www.w3.org/WAI/WCAG22/quickref/) — Accessibility requirements
- [Refactoring UI](https://www.refactoringui.com/) — Practical design tips for developers
- [SmashingMagazine: UI Animation](https://www.smashingmagazine.com/category/animation/) — Motion design best practices
- [Web.dev: Performance](https://web.dev/performance/) — Core Web Vitals and perceived performance
