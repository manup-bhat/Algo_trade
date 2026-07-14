# Migration Checklist — Pre/Post Migration Validation Gate

## Pre-Migration Checklist (Before Starting)

### Discovery & Planning
- [ ] Listed all Django apps and their interdependencies
- [ ] Counted total URL patterns / API endpoints
- [ ] Identified Django-specific features in use (Admin, Channels, Celery, Forms)
- [ ] Mapped signal connections (who listens to what)
- [ ] Documented current authentication mechanism (session, token, OAuth)
- [ ] Identified external service integrations (email, payment, storage)
- [ ] Checked Django version and any deprecated features in use
- [ ] Established baseline performance metrics (latency, throughput)
- [ ] Set up monitoring/alerting for both old and new systems
- [ ] Created rollback plan document

### Infrastructure
- [ ] FastAPI project structure created alongside Django
- [ ] Database connection configured (same DB as Django)
- [ ] CI/CD pipeline updated to build and test both apps
- [ ] Feature flag system ready (if using gradual rollout)
- [ ] Reverse proxy or WSGIMiddleware mount configured
- [ ] Health check endpoint responding on FastAPI

---

## Per-Endpoint Migration Checklist

For EACH endpoint being migrated, verify:

### Functional Equivalence
- [ ] Same URL path (or documented redirect from old to new)
- [ ] Same HTTP methods supported
- [ ] Same request body schema accepted
- [ ] Same response body schema returned
- [ ] Same HTTP status codes for success and error cases
- [ ] Same pagination format and behavior
- [ ] Same filtering/search parameters work
- [ ] Same sorting behavior

### Authentication & Authorization
- [ ] Same auth requirement (public vs authenticated)
- [ ] Same permission/role checks enforced
- [ ] Token/session from Django still works (during transition)
- [ ] Proper 401 for unauthenticated requests
- [ ] Proper 403 for unauthorized requests
- [ ] Object-level permissions migrated (e.g., owner-only edit)

### Data Integrity
- [ ] Same database table being read/written
- [ ] Same validation rules enforced
- [ ] Same unique constraints respected
- [ ] Same cascade behavior on delete
- [ ] Related objects loaded correctly (no N+1)
- [ ] Timestamps handled correctly (timezone-aware)

### Error Handling
- [ ] 404 returned for non-existent resources
- [ ] 422/400 returned for invalid input (with useful error messages)
- [ ] 500 errors logged properly
- [ ] Error response format matches expected schema

### Testing
- [ ] Contract test passes against BOTH Django and FastAPI
- [ ] Unit tests for service layer logic
- [ ] Edge cases tested (empty lists, null fields, max lengths)
- [ ] Load test completed (performance not degraded)

---

## Authentication Migration Checklist

- [ ] User model SQLModel matches Django's `auth_user` table exactly
- [ ] Password verification works with existing Django PBKDF2 hashes
- [ ] New passwords are hashed with Argon2 (not PBKDF2)
- [ ] Legacy hashes transparently upgraded on successful login
- [ ] JWT token creation and verification works
- [ ] Token expiration enforced
- [ ] Refresh token flow works
- [ ] `get_current_user` dependency correctly extracts user from token
- [ ] Timing attack prevention (constant-time comparison, dummy hash)
- [ ] CORS configured for frontend domains
- [ ] Swagger UI `/docs` shows Authorize button

---

## Middleware Migration Checklist

- [ ] Security headers present (X-Content-Type-Options, X-Frame-Options, HSTS)
- [ ] CORS configuration matches Django's django-cors-headers settings
- [ ] Request logging captures method, path, status, duration
- [ ] Request size limiting in place
- [ ] Trusted host validation configured
- [ ] Custom exception handlers registered
- [ ] Middleware execution order is correct

---

## Background Tasks Migration Checklist

- [ ] All Django signals identified and replaced with explicit calls
- [ ] Simple async tasks use `BackgroundTasks`
- [ ] Complex/distributed tasks use Arq or remain on Celery
- [ ] Periodic tasks scheduled (Arq cron or APScheduler)
- [ ] Task failure handling and retry logic in place
- [ ] Management commands converted to CLI scripts or lifespan events

---

## Post-Migration Checklist (After Django Removal)

### Cleanup
- [ ] Django removed from `requirements.txt` / `pyproject.toml`
- [ ] Django app directories deleted
- [ ] `WSGIMiddleware` mount removed
- [ ] Django-specific settings files removed
- [ ] Django migration files archived or deleted
- [ ] Alembic now manages ALL tables
- [ ] No remaining `import django` in codebase
- [ ] CI/CD only builds FastAPI app

### Verification
- [ ] Full test suite passes (100% of migrated tests)
- [ ] No 5xx errors in production for 48+ hours
- [ ] Performance metrics meet or exceed Django baseline
- [ ] All API clients/frontends confirmed working
- [ ] Monitoring alerts configured and tested
- [ ] Documentation updated (API docs, README, runbooks)
- [ ] Team trained on FastAPI patterns

### Performance Validation
- [ ] P50 latency equal or better than Django
- [ ] P99 latency equal or better than Django
- [ ] Throughput (req/sec) equal or better
- [ ] Memory usage acceptable
- [ ] Database query count per endpoint verified (no N+1)
- [ ] Connection pool sized correctly

---

## Risk Assessment Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Password hash incompatibility | Low (pwdlib handles it) | Critical | Test with production hash samples |
| Silent data format change | Medium | High | Contract tests on every endpoint |
| Missing permission check | Medium | Critical | Audit every `Depends()` chain |
| N+1 queries in SQLModel | High | Medium | Profile all list endpoints |
| Lost background task | Medium | High | Verify all signal→service migrations |
| CORS misconfiguration | Low | Medium | Test from actual frontend origin |
| JWT token not accepted | Low | Critical | Test token flow end-to-end |
| Timezone handling difference | Medium | Medium | Verify all datetime fields are tz-aware |

---

## Go/No-Go Criteria

### Ready to switch traffic ✅
- All contract tests pass
- Error rate < 0.1% in staging
- P99 latency within 20% of Django baseline
- Security scan passes (no new vulnerabilities)
- Rollback tested and documented

### NOT ready ❌
- Any contract test failing
- Missing permission checks discovered
- Performance regression > 20%
- Untested edge cases in critical flows
- No rollback plan

---

## Quick Commands Reference

```bash
# Run FastAPI in development
fastapi dev fastapi_app/main.py

# Run Alembic migrations
alembic upgrade head
alembic revision --autogenerate -m "description"

# Run tests
pytest tests/ -v --tb=short

# Run contract tests against both
pytest tests/contract/ --base-url=http://localhost:8000  # Django
pytest tests/contract/ --base-url=http://localhost:8001  # FastAPI

# Check for blocking calls in async routes
grep -rn "requests\.\|time\.sleep\|psycopg2" fastapi_app/src/

# Verify no Django imports remain (post-migration)
grep -rn "from django\|import django" fastapi_app/
```
