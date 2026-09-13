# ADR 0007: Secrets Provider Interface

## Status
Accepted

## Context
Currently, the platform retrieves API keys, database URLs, and other sensitive credentials via Pydantic settings loading from a local `.env` file or direct `os.environ` reads. As the platform prepares for a Staging environment (Phase 1/2) and eventual multi-broker capability, a hard-coded `.env` dependency restricts the ability to fetch dynamic credentials from cloud secret managers (like AWS Secrets Manager, HashiCorp Vault, or Google Secret Manager). 

## Decision
We will define a formal `SecretsProvider` protocol.
- The interface will expose simple credential retrieval methods.
- The initial and default implementation for Phase 0 will be `EnvFileSecretsProvider`, simply wrapping current `.env` loading behavior.
- We will establish the strict configuration precedence order: `Environment Variables → .env (via Provider) → StrategyManifest DB row → Runtime Feature-Flag override`.
- We will not implement a cloud vault provider immediately. The goal is only to establish the seam so a future upgrade is a drop-in replacement.

## Consequences
- **Positive:** Prepares the architecture for enterprise-grade secret management without requiring an immediate rewrite.
- **Positive:** Keeps unit testing straightforward by allowing an `InMemorySecretsProvider`.
- **Negative:** Introduces an extra layer of abstraction for fetching basic environment variables.
