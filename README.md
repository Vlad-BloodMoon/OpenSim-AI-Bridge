# OpenSim AI Bridge

**A headless OpenSimulator avatar with remote AI, a private knowledge base, multilingual retrieval and an authenticated Web control panel.**

**FR —** Une plateforme pour connecter et administrer un ou plusieurs avatars OpenSimulator sans viewer, leur permettre de répondre aux résidents grâce à des modèles IA distants et de retrouver les informations de votre grille. **Aucun modèle IA local** n'est nécessaire.

**EN —** A platform for running and managing one or more headless OpenSimulator avatars, answering residents with remote AI models and retrieving your grid's documentation. **No local LLM inference** is required.

> **Statut / Status — 24 November 2026:** active BloodMoon pilot, with a successfully built Linux x64 artifact and automated regression tests. **Not yet a general-purpose production release.** Features marked *planned* below must not be interpreted as available. Provider quotas, privacy, deployment hardening and OpenSimulator compatibility must be evaluated on each installation.

## What it does / Fonctionnalités

| Capability | Current status |
| --- | --- |
| Headless .NET 8 avatar using LibreMetaverse, IM, local chat, login/reconnect | Implemented; basic BloodMoon login/IM tested |
| Authenticated PHP administration over HTTPS and a restricted local Unix socket | Implemented and used on BloodMoon |
| Multiple avatar configurations, systemd services, maintenance and Firestorm mode | Implemented; not all multi-avatar combinations validated in-world |
| Remote Groq, OpenRouter and Gemini models with configurable priority and fallback | Implemented; some provider probes validated live; quota-exhaustion failover still needs a live end-to-end test |
| Persistent shared SQLite quota for attempted provider requests; per-resident cooldown | Implemented; **not** a provider-side token/cost/billing limit |
| SQLite FTS5 documentation retrieval (BloodMoon Grid, Roleplay, Marketplace, OpenSim Handbook) | Implemented; includes local TXT folders with automated indexing |
| Azure translation of questions for documentary retrieval, via a separate BloodMoon PHP gateway | Implemented and tested against the existing Azure service on BloodMoon |
| Admin-editable protected terms, synonyms and knowledge categories | Implemented; shared private JSON, read again on each request |
| Optional proximity welcome in public local chat, personalized with avatar name | Implemented per bot; disabled by default, requires in-world validation |
| Curated FAQ editor, unanswered-question review queue, grid/ROBUST tools | **Planned** |
| Autonomous movement, WebRTC voice and Hypergrid travel | **Planned / research** |

The bot uses **the resident's original message** for the AI answer and adds an Azure-translated version for searching documentation. Azure translation does not guarantee that domain-specific terms are translated correctly; the editable protected vocabulary helps retrieval retain names such as *Freeland*, *HUD* or *Hypergrid*. It is not a universal translation glossary.

## Architecture / Architecture

```text
OpenSimulator login + IM/local chat
             |
      Headless .NET 8 avatar(s) (LibreMetaverse)
             |
   Authorization, throttling and short per-resident context
             |
    +--------+---------------+
    |                        |
 SQLite FTS5 knowledge   Remote AI router
    |                    Groq / OpenRouter / Gemini
    +--------+---------------+
             |
   IM reply in the resident's language

Admin browser (HTTPS)
      |
Authenticated PHP Web console
      |
Restricted Unix-socket controller (systemd, settings, index jobs)
      |
Protected files + shared bot configuration

Question -> dedicated PHP translation gateway -> existing Azure Translator
          (for knowledge retrieval, not general IM translation)
```

**BloodMoon is the reference deployment, not a plug-and-play hosted service.** The included Azure translation gateway relies on a pre-existing, private BloodMoon Translator configuration. For another grid, adapt or disable that optional integration. Never commit or publish your API tokens, avatar passwords, IM history, private indexes or SQLite data.

## Getting started / Démarrage

1. Read the [installation instructions (FR)](docs/INSTALLATION_V01_FR.md) and [architecture](docs/ARCHITECTURE.md). Use a **test avatar and test region** first.
2. Configure `Grid.LoginUri`, avatar identity and starting location in a **private** `appsettings.json`, using [the example](config/appsettings.example.json). Store the avatar password outside Git and supply it using the documented launcher.
3. Build the .NET 8 project or retrieve the **successful Linux x64 artifact** from [GitHub Actions](https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge/actions). The artifacts are framework-dependent and require the .NET 8 runtime.
4. For Web management and multiple avatars, read [Web setup](docs/WEB_INSTALL_V02_FR.md) and [multi-avatar operations](docs/MULTI_BOT_V02_FR.md). Keep the controller on a local Unix socket, not a public network port.
5. To use documentation, read [Knowledge / RAG](docs/BLOODMOON_KNOWLEDGE_RAG_FR.md). For remote AI, read [AI IM pilot](docs/REMOTE_AI_V03_FR.md) and [multi-provider routing](docs/MULTI_PROVIDER_ROUTING_FR.md).
6. **Back up** binary, configuration, Web page and controller, then use maintenance before updating a running grid. Never paste `set -e` directly into an interactive SSH shell: run installation scripts in a separate Bash process.

**Quick offline check / Vérification hors grille** (after compiling or extracting the artifact):

```bash
dotnet OpenSimAiBridge.Bot.dll --verify-ai-safety
dotnet OpenSimAiBridge.Bot.dll --verify-knowledge
dotnet OpenSimAiBridge.Bot.dll --verify-shared-quota
```

The tests do not require Firestorm or a live grid. A successful run does **not** replace in-world IM and failover verification.

## Project structure / Organisation

| Path | Purpose |
| --- | --- |
| `src/OpenSimAiBridge.Bot/` | Avatar, AI routing, translation client and FTS5 retrieval |
| `controller/` | Restricted local administration, bot registry, providers, protected vocabulary |
| `web/OpenSim_AI/` | PHP Web administration, authentication and forms |
| `knowledge/` | Documentation indexer |
| `deploy/php/ai-translate.php` | Optional dedicated translation gateway; keeps existing HUD/site endpoints untouched |
| `deploy/systemd/` | Service templates |
| `scripts/` | Launcher and operational installation helpers |
| `tests/` | Python regression tests |
| `docs/` | Technical setup, specifications, progress and limitations |

## Operational notes / Points importants

- No Ollama, no local LLM, no unconditional use of paid APIs.
- Model validation in the Web UI **does not prove** conversation-level fallback during a real 429 or exhausted quota.
- The shared SQLite limit counts attempts; it cannot guarantee a provider's external token limits, billing status or pricing.
- Knowledge pages, PDFs and resident messages are **untrusted input**. The assistant is not granted unrestricted shell, SQL or ROBUST access.
- Authentication, secret permissions, HTTPS, usage rules and resident privacy remain the **operator's responsibility**. Sending text to remote AI/translation providers may involve personal data.
- In-world voice, a visual viewer, a free-answer rule editor and ROBUST administration are **not delivered features** in this repository.

## Documentation / Documentation

- [Overview of the implemented architecture](docs/ARCHITECTURE.md)
- [Project status and roadmap](docs/ROADMAP.md)
- [Installation (FR)](docs/INSTALLATION_V01_FR.md)
- [Web installation / administration (FR)](docs/WEB_INSTALL_V02_FR.md)
- [Multi-avatar operations (FR)](docs/MULTI_BOT_V02_FR.md)
- [Remote AI and provider routing (FR)](docs/MULTI_PROVIDER_ROUTING_FR.md)
- [Knowledge, Azure and editable vocabulary (FR)](docs/BLOODMOON_KNOWLEDGE_RAG_FR.md)
- [Proximity welcome in local chat / Accueil des visiteurs (FR)](docs/PROXIMITY_WELCOME_FR.md)
- [Initial requirements (FR)](docs/CAHIER_DES_CHARGES_FR.md) and [initial requirements (EN)](docs/REQUIREMENTS_EN.md) — **historical specifications**, not current feature checklists
- [Security](SECURITY.md)
- [Repository audit and cleanup record (FR)](docs/AUDIT_2026-11-24_FR.md)

## Contributing / Contribution

Bug reports, documentation fixes and tested patches are welcome. Include the OpenSimulator version, relevant **redacted** logs, reproduction steps and expected behavior. Do not paste secrets, resident private messages or identifying data in public issues.

**License / Licence:** no explicit open-source license has been selected yet. The source is visible, but **open-source reuse rights are not granted by a license at this time**. Before publishing a licensed release, verify third-party dependencies and add the corresponding `LICENSE` file.

Maintainer / Dépôt : [Vlad-BloodMoon](https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge).
