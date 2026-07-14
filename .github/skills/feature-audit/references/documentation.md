# Post-Ship: Documentation, Monitoring & Rollout

Shipping code is not the end. Features that aren't documented get misunderstood.
Features that aren't monitored go silently broken. Features without rollout control
can't be safely reverted.

---

## Documentation: What Must Be Updated

### Rule: Update Documentation in the Same PR as the Code

Documentation that lives in a separate PR often never gets merged. If your code changed, the documentation PR must be part of the same logical unit of work.

---

### README

Update the README when:
- [ ] A new feature was added that users or developers need to know about
- [ ] Installation or setup steps changed (new env vars, new dependencies, new commands)
- [ ] Configuration changed (new options, changed defaults, removed options)
- [ ] How to run, test, or deploy the application changed

**Check**: Does the README describe the current state of the application? Run through the setup steps — do they still work?

---

### API Documentation (OpenAPI / Swagger / Postman)

Update when:
- [ ] An endpoint was added → add full spec: path, method, parameters, request body, response schemas, error codes
- [ ] An endpoint's request or response schema changed → update the spec
- [ ] An endpoint was deprecated → mark with `deprecated: true` and document the replacement
- [ ] An endpoint was removed → remove from spec (with changelog entry)
- [ ] Authentication requirements changed

**Quality check for API docs**:
- Are all possible HTTP status codes documented? (200, 400, 401, 403, 404, 422, 500)
- Are all response fields documented with types and descriptions?
- Is there a request body example that matches what actually works?
- Is there a response example that matches what the API actually returns?

---

### Inline Code Documentation

Update or add when:
- [ ] A function's parameters, return value, or side effects changed
- [ ] The purpose of a class or module is no longer clear from the name alone
- [ ] A non-obvious design decision was made (explain WHY in a comment)
- [ ] A known limitation or workaround was introduced

**Remove** when:
- [ ] A comment describes behavior that no longer exists
- [ ] A `TODO` was resolved
- [ ] A comment explains what the code does when the code has been made self-explanatory

---

### CHANGELOG

Maintain a changelog (following [Keep a Changelog](https://keepachangelog.com/) format) for any user-visible change:

```markdown
## [Unreleased]

### Added
- Discount system for premium customers on orders over $500 (#1234)

### Changed
- Order confirmation emails now include estimated delivery date (#1189)

### Fixed
- Cart total not updating when quantity changed from product detail page (#1205)

### Deprecated
- `GET /orders/all` endpoint is deprecated. Use `GET /orders?page=1&limit=20` instead.

### Removed
- Legacy `/api/v1/users` endpoints removed. Use `/api/v2/users`. (#1100)

### Security
- Patched CSRF vulnerability in order submission form (#1230)
```

**Rule**: Every user-visible change goes in the changelog. Internal refactors that don't change behavior do not.

---

### Architecture / Design Documents

Update when:
- [ ] A significant design decision was made during implementation (document it)
- [ ] The implementation deviated from an existing design doc (document why)
- [ ] A new component, service, or module was added to the system

---

## Observability: Logging, Metrics, and Alerts

### Structured Logging

Every significant operation in the feature should produce a structured log entry:

```javascript
// Good structured log entry
logger.info('Order discount applied', {
  orderId: order.id,
  customerId: customer.id,
  originalTotal: order.total,
  discountAmount: discount,
  discountedTotal: order.total - discount,
  requestId: req.id,
});

// What to log
// - Entry point of significant operations
// - Decision points with context (why was X chosen?)
// - Completion of significant operations with outcome
// - All errors (with full context: user, resource, action, error message)
// - Sensitive actions: auth events, data access/mutation, permission checks

// What NOT to log
// - Passwords, API keys, tokens
// - Full credit card numbers, SSNs, PHI
// - Query parameters that may contain sensitive data
// - Excessive debug logs in production (causes log noise and cost)
```

### Metrics to Add for New Features

| Metric Type | Example | When to Add |
|------------|---------|------------|
| Counter | `orders.discount.applied.count` | Every time a significant action occurs |
| Counter | `orders.discount.rejected.count` | Every time an action fails or is rejected |
| Histogram | `orders.discount.calculation.duration_ms` | Any operation that has variable latency |
| Gauge | `cart.active.count` | Current state that fluctuates over time |

**Minimum metrics for any new feature**:
- Success rate (success count vs. error count)
- Latency (P50, P95, P99 of the main operation)
- Error rate broken down by error type

### Alerting

Configure alerts so you know when the feature breaks before users report it:

| Condition | Alert Type | Response |
|-----------|-----------|----------|
| Error rate > 1% over 5 minutes | Pager alert | Immediate investigation |
| P99 latency > 2× baseline over 10 minutes | Slack alert | Investigate during business hours |
| Zero success events in 15 minutes (when traffic expected) | Pager alert | Immediate investigation |
| Auth failure rate spike | Pager alert | Potential attack — immediate investigation |

---

## Feature Flags and Rollout Control

Feature flags let you deploy code without exposing it to all users immediately. This is the primary tool for reducing deploy risk.

### When to Use a Feature Flag

- The change is large or high-risk
- You want to test in production with a subset of users
- You need the ability to instantly disable the feature without a code deploy
- The feature is dependent on external systems that may not be ready
- A/B testing a UX change with real users

### Feature Flag Best Practices

```javascript
// Feature flag check example
if (featureFlags.isEnabled('discount_system', user)) {
  const discounted = applyDiscount(order);
  return discounted;
} else {
  return order;
}
```

- [ ] Flag name is descriptive: `discount_system` not `feature_123`
- [ ] Flag is documented: what it controls, who should have it, when it will be removed
- [ ] Flag has a defined lifecycle: when will it be removed? (Flags are technical debt)
- [ ] Default value defined: what happens when the flag service is unavailable?
- [ ] Old code path (flag = false) still works after rollout — don't break it early

### Rollout Strategy

| Stage | Description |
|-------|------------|
| **Internal** | Enable for your own team / developers only |
| **Beta / Canary** | Enable for 1–5% of users; watch metrics |
| **Gradual rollout** | Increase % over days: 10% → 25% → 50% → 100% |
| **General availability** | All users; remove the flag from code |

---

## Post-Ship Monitoring Checklist

After deploying, actively monitor. Don't assume "no reports = no problems."

### First 30 Minutes After Deploy

- [ ] Error rate is not elevated vs. pre-deploy baseline
- [ ] P95/P99 latency is not elevated
- [ ] No new error types appearing in error tracker (Sentry, Rollbar, etc.)
- [ ] Feature-specific success metrics are tracking as expected
- [ ] Application logs show clean request/response cycle for the new feature

### First 24 Hours

- [ ] User-facing errors haven't spiked in any cohort or region
- [ ] Database query performance hasn't degraded (check slow query logs)
- [ ] Memory and CPU usage stable on application servers
- [ ] External service (API, queue) call patterns are normal
- [ ] Business metrics tracking expected (conversions, sign-ups, completions — depending on feature)

### Rollback Criteria

Agree on these **before** deploying, not after:

```
We will roll back if:
- Error rate exceeds X% for more than Y minutes
- Latency P99 exceeds Z ms for more than Y minutes  
- We observe [specific known bad behavior]
- [critical business metric] drops by more than X%
```

**Rollback options** (fastest to slowest):
1. Disable feature flag (instant, no deploy)
2. Revert the deploy via CD platform (1–5 minutes)
3. `git revert` and redeploy (10–30 minutes)
4. Manual hotfix (30+ minutes)

Always prefer option 1 (feature flag) — it's why we use them.

---

## Documentation and Observability Summary

| Task | Done |
|------|------|
| README updated for changed behavior | |
| API documentation updated (all endpoints, schemas, errors) | |
| Inline comments reflect new design | |
| Obsolete comments removed | |
| CHANGELOG entry added | |
| Structured logging added to new code paths | |
| No sensitive data logged | |
| Success and error metrics defined | |
| Alerts configured | |
| Feature flag implemented if high-risk | |
| Rollout plan documented | |
| Rollback criteria defined | |
| Post-deploy monitoring plan in place | |
