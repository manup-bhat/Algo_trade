# Phase 6: Security Audit — OWASP Top 10 (2025) Applied to Features

Every feature you ship is a potential attack surface. This checklist applies the
OWASP Top 10 2025 to the feature being developed or modified.

> "The OWASP Top 10 is a standard awareness document for developers and web application
> security. It represents a broad consensus about the most critical security risks to
> web applications." — OWASP Foundation

---

## Minimum Mandatory Security Checks (Every Feature)

These four checks apply to every feature without exception:

- [ ] **Input validated at system boundaries** — never trust input from users, third-party services, or other systems. Validate server-side, regardless of client-side validation.
- [ ] **Authorization enforced server-side** — never rely on UI visibility to control access. The API must enforce it.
- [ ] **No secrets in code, logs, or URLs** — API keys, passwords, tokens, PII must never appear in source code, query strings, or log files.
- [ ] **Errors don't expose internals** — stack traces, SQL errors, file paths, and internal identifiers must not reach end users.

---

## A01:2025 — Broken Access Control

The most common and most impactful class of vulnerability.

### What It Means

Users can perform actions or access data they shouldn't have access to.

### Feature-Level Checks

- [ ] Every API endpoint that returns or modifies data **verifies the caller's identity and permissions** before doing anything else
- [ ] Users can only access their own resources — never another user's data via ID manipulation (e.g., `GET /orders/42` when the logged-in user owns order 99)
- [ ] Role-based access control (RBAC) enforced at the service layer, not only at the route/controller layer
- [ ] Admin-only endpoints are not just "hidden" in the UI — they require admin role server-side
- [ ] Sensitive actions (delete, modify, export) require both authentication AND authorization
- [ ] Multi-tenant features ensure complete data isolation between tenants

### Code Pattern to Avoid

```javascript
// BAD: checks if user is logged in, but not if they OWN this order
app.get('/orders/:id', authenticate, async (req, res) => {
  const order = await orderRepo.findById(req.params.id);
  return res.json(order); // Any logged-in user can read any order!
});

// GOOD: verify ownership
app.get('/orders/:id', authenticate, async (req, res) => {
  const order = await orderRepo.findById(req.params.id);
  if (!order || order.userId !== req.user.id) {
    return res.status(403).json({ error: 'Access denied' });
  }
  return res.json(order);
});
```

---

## A02:2025 — Security Misconfiguration

### What It Means

Insecure default settings, unnecessary features enabled, missing hardening.

### Feature-Level Checks

- [ ] No debug mode, verbose logging, or stack traces enabled in production
- [ ] HTTP security headers set: `Content-Security-Policy`, `X-Content-Type-Options`, `Strict-Transport-Security`, `X-Frame-Options`, `Referrer-Policy`
- [ ] No unnecessary HTTP methods exposed (if endpoint is read-only, only allow GET)
- [ ] CORS configured restrictively — not `Access-Control-Allow-Origin: *` for authenticated endpoints
- [ ] Directory listing disabled on file servers
- [ ] Error pages return generic messages, not framework error details
- [ ] New environment variables documented in `.env.example` with safe defaults

---

## A03:2025 — Software and Data Supply Chain Failures

### What It Means

Vulnerabilities introduced through third-party dependencies, build tools, or the CI/CD pipeline.

### Feature-Level Checks

- [ ] Any new dependency vetted for known CVEs before adding:
  ```bash
  npm audit                  # Node.js
  pip-audit                  # Python
  gradle dependencyCheckAnalyze  # Java
  ```
- [ ] Dependencies pinned to specific versions (not `^1.x` floating ranges in production)
- [ ] Dependency licenses reviewed (GPL vs MIT vs proprietary)
- [ ] No dependency imported only for a single trivial utility (install `left-pad` risk)
- [ ] CI/CD pipeline has no step that accepts unsigned/unverified artifacts
- [ ] Automated dependency vulnerability scanning in the pipeline (Dependabot, Snyk, etc.)

---

## A04:2025 — Cryptographic Failures

### What It Means

Sensitive data not protected in transit or at rest. Weak or broken cryptography.

### Feature-Level Checks

- [ ] All traffic to/from this feature uses TLS 1.2+ (never HTTP in production)
- [ ] Passwords hashed with bcrypt, scrypt, or Argon2 — never MD5, SHA1, or unsalted SHA256
- [ ] Sensitive data (PII, financial data, health data) encrypted at rest
- [ ] Encryption keys stored in a secrets manager (Vault, AWS Secrets Manager, Azure Key Vault) — not in config files or environment variables directly
- [ ] Session tokens and API keys have sufficient entropy (≥ 128 bits)
- [ ] Sensitive data not returned in API responses unless explicitly required (e.g., don't return `passwordHash` in user profile response)
- [ ] Sensitive data redacted from logs:
  ```javascript
  // BAD: logs the full user object including password hash and token
  logger.info('User logged in', { user });
  
  // GOOD: log only what's needed, never sensitive fields
  logger.info('User logged in', { userId: user.id, email: user.email });
  ```

---

## A05:2025 — Injection

### What It Means

Attacker-controlled data is interpreted as commands or queries (SQL injection, XSS, command injection, LDAP injection, etc.)

### SQL Injection Prevention

```javascript
// BAD: string concatenation into SQL
const query = `SELECT * FROM users WHERE email = '${req.body.email}'`;
// Attacker sends: admin@example.com' OR '1'='1

// GOOD: parameterized query
const user = await db.query('SELECT * FROM users WHERE email = $1', [req.body.email]);
```

**Rule**: Never construct SQL, LDAP, OS commands, or XML by concatenating user input. Always use parameterized queries or prepared statements.

### XSS (Cross-Site Scripting) Prevention

- [ ] All user-provided content rendered in HTML is escaped (`<`, `>`, `&`, `"`, `'`)
- [ ] Never use `innerHTML`, `dangerouslySetInnerHTML`, or `document.write()` with user content
- [ ] `Content-Security-Policy` header configured to restrict inline scripts
- [ ] Sanitize rich text input with a whitelist-based HTML sanitizer (DOMPurify)

### Command Injection Prevention

```javascript
// BAD: user input in shell command
exec(`convert ${req.body.filename} output.png`);

// GOOD: use library APIs instead of shell, validate filename strictly
const safeName = path.basename(req.body.filename).replace(/[^a-zA-Z0-9._-]/g, '');
await sharp(safeName).toFile('output.png');
```

### Path Traversal Prevention

```javascript
// BAD: user can request ../../etc/passwd
const filePath = path.join('./uploads', req.params.filename);

// GOOD: resolve and verify the path stays within the allowed directory
const uploadDir = path.resolve('./uploads');
const filePath = path.resolve(uploadDir, req.params.filename);
if (!filePath.startsWith(uploadDir)) {
  return res.status(400).json({ error: 'Invalid filename' });
}
```

---

## A06:2025 — Insecure Design

### What It Means

Security issues baked into the design before a line of code is written. No amount of implementation can fix a design that wasn't secure.

### Feature-Level Checks

- [ ] **Threat model performed**: What's the worst a malicious user could do with this feature? How is it prevented?
- [ ] Rate limiting in place for sensitive actions (login, password reset, OTP verification)
- [ ] Brute-force protection on authentication endpoints (lockout, CAPTCHA, exponential backoff)
- [ ] "Forgot password" flow does not reveal whether an email exists in the system
- [ ] Bulk data operations (export, delete all) have safeguards (pagination limits, confirmation, audit log)
- [ ] Business logic enforced server-side — never trust the client to enforce constraints

---

## A07:2025 — Authentication Failures

### What It Means

Broken authentication allows attackers to compromise credentials, session tokens, or bypass authentication.

### Feature-Level Checks

- [ ] Session tokens have appropriate expiry (short-lived, e.g., 1 hour with refresh)
- [ ] Sessions invalidated on logout (server-side session destruction, not just client cookie deletion)
- [ ] "Remember me" tokens are long, random, stored hashed, and rotated on use
- [ ] Failed login attempts are rate-limited and logged (with alert on excessive failures)
- [ ] Password reset tokens are single-use, expire quickly (15–60 minutes), and sent to verified email only
- [ ] Multi-factor authentication available for sensitive features
- [ ] No plaintext credentials in HTTP requests (use POST body, never URL params)
- [ ] Account lockout after N failed attempts (with unlock mechanism that doesn't itself become an attack vector)

---

## A08:2025 — Software and Data Integrity Failures

### What It Means

Code and infrastructure that makes assumptions about software updates, data, and CI/CD pipelines without verifying integrity.

### Feature-Level Checks

- [ ] Deserialization of objects from untrusted sources includes type validation (no `unserialize()` on user input in PHP; no `pickle.loads()` on untrusted data in Python)
- [ ] Webhooks from external services are verified via signature (HMAC signature verification)
- [ ] CI/CD pipelines do not accept input from untrusted sources without sanitization
- [ ] Auto-update mechanisms verify signatures of downloaded artifacts

---

## A09:2025 — Security Logging and Monitoring Failures

### What It Means

Without logs and alerts, attacks go undetected. Breach detection time averages months without proper logging.

### Feature-Level Checks

- [ ] Authentication events logged: login (success and failure), logout, token refresh, session expiry
- [ ] Authorization failures logged: access denied events (with user ID, resource, action attempted)
- [ ] Sensitive data operations logged: create, read (for sensitive data), update, delete (CRUD audit trail)
- [ ] Logs include sufficient context: timestamp, user ID, action, resource, IP address
- [ ] Logs do **not** include: passwords, tokens, full credit card numbers, SSNs, or other sensitive values
- [ ] Alerts configured for: N failed logins in M minutes, access denied spikes, abnormal data export volumes
- [ ] Logs are written to a system the application cannot modify (tamper-evident)

---

## A10:2025 — Mishandling of Exceptional Conditions

### What It Means

Unhandled exceptions reveal internal details, crash systems, or leave systems in insecure states.

### Feature-Level Checks

- [ ] All code paths that can throw exceptions are wrapped in error handlers
- [ ] Unhandled promise rejections / uncaught exceptions are caught at the top level and logged
- [ ] Application **fails closed** (denies access when in doubt), not **fails open** (grants access on error)
- [ ] User-facing error messages are generic — never expose internal identifiers, file paths, or stack traces
- [ ] Error responses use appropriate HTTP status codes (401 for unauthorized, 403 for forbidden, 404 for not found — not 200 with error in body, not always 500)
- [ ] Database constraint violations result in 400/409 responses, not 500s with SQL error details
- [ ] Error handling logic itself is covered by tests

```javascript
// BAD: fails open — grants access if authorization check throws
try {
  if (await authService.canAccess(user, resource)) {
    return resource;
  }
} catch (e) {
  return resource; // ERROR: exception means we let them in!
}

// GOOD: fails closed
try {
  if (!await authService.canAccess(user, resource)) {
    return res.status(403).json({ error: 'Access denied' });
  }
  return resource;
} catch (e) {
  logger.error('Authorization check failed', { userId: user.id, error: e.message });
  return res.status(403).json({ error: 'Access denied' }); // deny on failure
}
```

---

## Security Audit Summary Checklist

| Risk | Checked |
|------|---------|
| A01: Authorization enforced server-side on all routes/actions | |
| A02: No debug mode in prod; security headers set | |
| A03: New dependencies scanned for CVEs | |
| A04: Sensitive data encrypted; bcrypt for passwords | |
| A05: All inputs parameterized; no raw SQL or HTML injection | |
| A06: Rate limiting on sensitive actions; threat-modeled | |
| A07: Sessions expire; logout invalidates server-side | |
| A08: Webhook signatures verified; no unsafe deserialization | |
| A09: Audit log for sensitive actions; no secrets in logs | |
| A10: All exceptions caught; fails closed; no internals exposed | |
