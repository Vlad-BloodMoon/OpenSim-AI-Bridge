# Architecture proposal / Proposition d'architecture

**Draft — no components are implemented yet.**

```text
OpenSimulator grid (login, chat, IM, regions)
                   |
                   v
        Headless avatar (.NET 8)
          LibreMetaverse adapter
                   |
             Event dispatcher
                   |
       Core API / Orchestrator
          |       |       |
          v       v       v
       Rules   Remote AI  Translation
       engine  provider   provider
          |       |       |
          +-------+-------+
                   |
         Permissions & quotas
                   |
       Controlled grid adapter
        / optional ROBUST read
                   |
              Persistence
                   ^
                   |
       Admin Web UI (HTTPS)
```

## Modules

- **AvatarClient:** single authenticated session, IM/local chat and presence, serialized outgoing messages, reconnect/backoff, anti-loop.
- **Orchestrator:** routing according to channel, session, verified sender UUID, role, bot state and rate limit.
- **AnswerEngine:** deterministic matching, multilingual curated responses, template variables from allow-listed data, unanswered queue.
- **AiProvider:** remote API only (OpenAI first); key storage, token budget, policies, optional tool invocation with server-side authorization.
- **TranslationProvider:** configurable HTTP implementation; exact BloodMoon Translator wire protocol pending code review.
- **GridAdapter:** named, constrained operations (list regions, report selected status); read-only ROBUST first.
- **AdminApi / AdminWeb:** authenticated backend and management console; bot position, logs, answers, users, budgets, translation settings.
- **Storage:** settings, access grants, FAQ entries and revisions, opted-in memory, usage aggregates and audit events.

## Operational rules

1. Sender UUID is read from the authenticated metaverse message event; never inferred from display names or text.
2. A local answer is attempted first for public questions. A remote AI request is only allowed after a separate permission decision.
3. On AI outage or quota exhaustion, continue with curated responses; do not silently charge a different provider.
4. External text (chat, wiki, translations, remote output) is **untrusted** and cannot grant itself permissions.
5. Restrict administrative functions to an explicit tool registry; validate arguments, roles, limits and confirmation for high-risk writes.
6. Start on a test instance; integrate with production only after logs, auth, credentials and reconnect behavior are verified.

## Proposed service boundaries

The Web API is the only control plane exposed to the UI. The avatar process should not host a publicly exposed administrative endpoint. Database access stays server-side with least privileges. Use local sockets/internal interfaces when components share a host. HTTPS and strong authentication for external management.

Future modules: voice WebRTC (technical research required), Hypergrid travel, animation control, multi-bot orchestration and optional MCP gateway. Keep these **out of the first production milestone**.
