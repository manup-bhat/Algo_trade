# User Empathy & Persona-Based Validation — Build for Real Humans

> "The API returned 200" is a developer's definition of success.
> "I got what I came for, and I knew it worked" is the user's definition. Only the second one
> ships value.

Most defects that pass tests still fail *users*: confusing flows, silent failures, dead ends,
moments of doubt. This reference makes you **simulate real people** using the feature so you
catch human-experience bugs before they do. Pair with [ux-checklist.md](./ux-checklist.md)
(the mechanical UX checks); this file covers the *empathy* and *mental-model* side.

---

## The Empathy Gap

| The developer knows... | The user does NOT know... |
|------------------------|---------------------------|
| The happy path and intended order | That there *is* an intended order |
| What each error code means | What "Error 422" means or what to do about it |
| That the spinner means "working" | Whether anything is happening at all |
| Where the button is | That a feature exists if it's hidden |
| The data model | Why their input was "invalid" |
| That it succeeded (200 OK) | Whether their action actually saved |

**Your job**: close every gap in the right column. Every place a user could think *"Did that
work?"*, *"What do I do now?"*, or *"Why won't it let me?"* is a bug.

---

## Step 1 — Cast the Personas

For each feature, walk it as **each** of these archetypes. They surface different bug classes.

| Persona | Behavior | Bugs they reveal |
|---------|----------|------------------|
| **The First-Timer** | Has never seen this; no context; reads little | Missing empty states, unclear labels, no onboarding, undiscoverable actions |
| **The Impatient** | Clicks fast, double-submits, navigates away mid-action | Double-submit/duplicate writes, no loading lock, lost progress, race conditions |
| **The Confused** | Does steps out of order, misreads, picks the wrong option | Bad validation messages, no recovery path, dead ends, irreversible mistakes |
| **The Power User** | Keyboard-only, shortcuts, bulk actions, extreme values | Missing keyboard support, no bulk handling, performance cliffs, boundary bugs |
| **The Returning User** | Comes back later with stale tabs/sessions | Expired sessions, stale data, lost draft, "this changed since you loaded it" |
| **The Mistaken** | Fat-fingers input, pastes weird data, wrong file | Validation gaps, no undo, destructive actions without confirm |
| **The Constrained** | Slow 3G, old device, small screen, data-capped | Timeouts, huge payloads, layout breakage, no offline handling |
| **The Skeptical** | Doesn't trust the system; double-checks everything | Missing confirmation, no receipt/audit, ambiguous success states |
| **The Assisted** | Uses screen reader, keyboard, magnifier, voice | Inaccessible widgets, unlabeled controls, focus traps (see ux-checklist WCAG) |
| **The Adversary** | Tries to break/abuse it (covered for completeness) | IDOR, injection, mass assignment (see security-checklist.md) |

> Minimum bar for any user-facing change: walk it as **First-Timer, Impatient, Confused,
> Constrained, and Assisted**.

---

## Step 2 — Map Journey Friction

Write the journey as a real person experiences it, and mark friction at every step.

```
GOAL the user actually has: <in their words, e.g. "see if my payment went through">

Step │ What user does │ What they EXPECT │ What they SEE │ Friction? (😟)
─────┼────────────────┼──────────────────┼──────────────┼───────────────
  1  │ lands on page  │ obvious next step│ ...          │ 😟 unclear CTA?
  2  │ clicks submit  │ "it's working"   │ ...          │ 😟 no feedback?
  3  │ waits          │ progress / done  │ ...          │ 😟 frozen UI?
  4  │ sees result    │ "it worked!"     │ ...          │ 😟 ambiguous?
─────┴────────────────┴──────────────────┴──────────────┴───────────────
```

At every step, answer the **three user questions**:
1. **"What's happening?"** — is the system's state visible? (loading, success, error)
2. **"What do I do next?"** — is the next action obvious?
3. **"Did it work?"** — is the outcome unambiguous and trustworthy?

A "no" to any of these at any step is a UX defect to fix.

---

## Step 3 — Match the User's Mental Model

Users carry expectations from the rest of the world and the rest of your app. Violating them
causes errors even when the code is "correct."

| Mental-model check | Failure example | Fix |
|--------------------|-----------------|-----|
| **Consistency** | "Save" auto-saves here but needs a button there | One pattern app-wide |
| **Real-world match** | "Archive" actually deletes | Words mean what users think |
| **Reversibility expectation** | Delete with no undo/confirm | Confirm destructive, offer undo |
| **Visibility of system status** | Background job done, UI never updates | Reflect state changes |
| **Recognition over recall** | User must remember an ID from 3 screens ago | Show it; don't make them remember |
| **Least surprise** | Enter submits *and* navigates away | Predictable behavior |

> Grounded in [Nielsen's 10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/).

---

## Step 4 — The "Did That Work?" Audit

The single most common UX bug is **invisible outcome**. For every user action, verify:

```
[ ] The action gives immediate acknowledgment (button state changes on click).
[ ] Progress is visible if it takes > 1s (spinner / skeleton / progress).
[ ] Success is explicit and distinct ("Saved ✓", row appears, toast).
[ ] Failure is explicit, in plain language, with a recovery path.
[ ] The new state persists on refresh (the user can trust it really saved).
[ ] Nothing silently no-ops (a click that does nothing visible is a bug).
```

---

## Step 5 — Error Messages a Human Can Act On

Rewrite every user-facing error to pass this test:

| Bad (developer voice) | Good (user voice) |
|-----------------------|-------------------|
| "Error 422: Unprocessable Entity" | "We couldn't save your changes — your session expired. Please sign in again." |
| "Null reference exception" | "Something went wrong on our end. We've logged it; please try again." |
| "Invalid input" | "Phone number should be 10 digits, like 555-123-4567." |
| "Request failed" | "We couldn't reach the server. Check your connection and retry." |

**Good error = What happened + Why (if useful) + What to do next.** Never leak stack traces or
internal details (also a security rule — see [security-checklist.md](./security-checklist.md)).

---

## Step 6 — Friction & Effort Budget

Count the cost of the task for the user and cut waste.

```
[ ] Clicks/taps to complete the goal — is any step removable?
[ ] Fields the user must fill — is each one truly required? Pre-fill what you know.
[ ] Decisions the user must make — reduce or provide a sensible default.
[ ] Things the user must remember — show them instead.
[ ] Waiting time — can it be optimistic, async, or backgrounded?
[ ] Re-work after errors — does an error preserve their input, or wipe it?
```

> **Rule**: Never make the user re-enter data the system already had or could have kept. Losing
> a half-filled form on error is one of the most enraging, most common UX bugs.

---

## Step 7 — Hallway Test (cheap, powerful)

Ask 2-3 people who didn't build the feature to complete the goal while you watch silently.
- Where they **hesitate** → unclear affordance.
- Where they **click the wrong thing** → bad information scent.
- Where they **say "did that work?"** → invisible outcome.
- Where they **give up** → a dead end you must remove.

Don't explain or help — their confusion *is* the bug report.

---

## User-Empathy Validation Summary

| Check | Status |
|-------|--------|
| Walked feature as First-Timer, Impatient, Confused, Constrained, Assisted | |
| Journey friction mapped; 3 user questions answered at each step | |
| Mental-model expectations met (consistency, real-world match, reversibility) | |
| Every action has visible acknowledgment + success + failure states | |
| Error messages are plain-language and actionable | |
| User never loses input on error | |
| Effort budget minimized (clicks, fields, memory, waiting) | |
| Hallway-tested with ≥2 outside people | |

---

## Sources

- [Nielsen Norman Group: 10 Usability Heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/) — visibility of status, error recovery, consistency, recognition vs recall
- [NN/g: Error Message Guidelines](https://www.nngroup.com/articles/error-message-guidelines/) — actionable error design
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/) — the Assisted persona's requirements
- [ux-checklist.md](./ux-checklist.md) — the mechanical UX/accessibility checklist this complements
