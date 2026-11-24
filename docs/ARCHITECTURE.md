# OpenSim AI Bridge — Architecture / Architecture réelle

**Updated / Mis à jour : 24 November 2026.** This document describes the implemented structure in `main`, and separates still-planned modules. BloodMoon is the reference environment; other installations require their own access-control and translation configuration.

## Components currently present

```text
OpenSimulator / ROBUST login
   |
   | LibreMetaverse protocol
   v
.NET 8 headless avatar(s) — IM + local chat + status heartbeat
   |
   +-- Optional visitor welcome (per-avatar config, default OFF):
   |     simulator full-resolution avatar object positions
   |     -> horizontal distance + per-UUID anti-repeat + name lookup
   |     -> optional one-time TurnToward + public channel-0 chat
   |     (no LLM/Azure request; AI questions answered by IM)
   |
   +-- Avatar and resident authorization / request gating
   |
   +-- Document retrieval:
   |     BloodMoon Azure PHP gateway (optional, translation to French)
   |        -> existing external Azure Translator subscription
   |     Local SQLite FTS5 index
   |        <- periodic public sites/PDF and local TXT import jobs
   |     Protected vocabulary (private admin-editable JSON)
   |
   +-- Remote AI response:
         shared model profiles and private keys
         shared SQLite attempted-request quota per provider
         Groq / OpenRouter / Gemini
         short per-resident conversation memory in bot process
         -> chunked Firestorm-compatible IM response

HTTPS admin browser -> PHP Web admin (authenticated session + CSRF)
                         |
                         | protected Unix socket (www-data peer)
                         v
                     local Python controller
                         |
                         +-- systemd avatar services / maintenance
                         +-- protected configuration writes
                         +-- provider validation and model settings
                         +-- knowledge indexing status and triggers
                         +-- protected vocabulary add/edit/delete
```

## Boundaries / Limites de sécurité

- The **avatar process** does not expose shell/SQL/ROBUST administration to the language model.
- The **Python controller** validates its known actions and requires the expected Unix-socket peer; never expose this socket over HTTP or TCP directly. It is a privileged service; review file ownership and permissions when deploying.
- The **Web interface** requires HTTPS and its own private credential file, outside the Web root. State changes use an authenticated form and CSRF token.
- The **Azure subscription key** belongs only in the existing protected translator configuration. The bot uses the BloodMoon gateway token; `ai-translate.php` is a distinct endpoint from the existing in-world `translate.php` and site `web-translate.php`.
- **SQLite knowledge** contains public documentation and private TXT notes ingested by the indexer. These are data, **never instructions**. The index is not a general-purpose chat-memory store.
- Provider API secrets are kept in local private files, not shipped in the repository. The provider and translation quotas are distinct.
- The operator must assess data processing/privacy before sending resident text to Azure or remote model APIs. No claim of complete consent or retention controls is made.
- Changes to shared protected terms are read during retrieval; unlike executable updates, they require **no bot restart**.

## Where settings live / Configurations

| Function | Deployment location |
| --- | --- |
| Avatar identity/login | private `appsettings.json` (per-avatar versions for multi-bot) |
| Visitor welcome and optional face rotation | `Bot.ProximityWelcome` inside each avatar's private `appsettings.json`; edited through authenticated Web admin, requires bot restart |
| Avatar password | private `bot-password.txt` loaded by launcher |
| AI profile priorities | `config/multi-ai.json` |
| Separate provider keys | `ai-keys/<provider>.txt` |
| Azure retrieval enabled | `config/translation.json` (boolean `Enabled`) |
| BloodMoon translator token | `ai-keys/bloodmoon-translator.txt` |
| Editable search terms | `config/knowledge-terms.json` (auto-created on first edit) |
| Indexed documents | `data/bloodmoon_knowledge.db` |
| Web admin credentials | `/etc/opensim-ai-bridge/web-admin.php` |
| BloodMoon Azure server credentials | `/etc/bloodmoon-translator/config.php` (reference deployment only) |

The launcher and service files may use `OSAI_INSTALL_DIR` and per-avatar config paths. Always inspect the installed service rather than assuming the example values are live.

## Implemented versus proposed / Réalisé vs prévu

**Implemented:** authenticated Web operations, headless avatar sessions, IM, provider routing, shared attempt counting, search/translation integration, editable protected vocabulary, knowledge indexing, multi-avatar service infrastructure, and optional local-chat visitor greeting with name and one-time body orientation. **The greeting and face-visitor rotation were exercised in-world on BloodMoon with Firestorm**; see [visitor welcome details](PROXIMITY_WELCOME_FR.md). Other features have different validation levels; see README and roadmap.

**Not yet delivered:** admin-editable deterministic FAQ responses, unrecognized-question moderation, independent resident language preferences, general ROBUST read/write tools, arbitrary LLM tool execution, autonomous navigation, triggered animation systems, voice or Hypergrid travel. The delivered one-time visitor-facing rotation does **not** implement autonomous movement. Earlier proposals and specifications in `docs/` may describe these as desired outcomes, not current code.

## Build and operations

GitHub Actions checks Bash syntax, Python tests, PHP syntax, .NET Release build, and offline behavioral tests before packaging the Linux x64 framework-dependent artifact. Passing automation **does not** verify a real provider-quota outage or all OpenSimulator versions.

For deployment, stop the affected avatar services via maintenance, preserve installed secrets and `config/` files, install only verified files, then validate the Web controller and a real IM conversation before wider rollout. A global maintenance lock intentionally prevents avatar services from starting; complete/resume maintenance from the Web admin after deploying, rather than bypassing the lock. Do not run `set -e` directly in an interactive PuTTY shell.
