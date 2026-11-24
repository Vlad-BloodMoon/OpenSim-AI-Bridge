# OpenSim AI Bridge

**An extensible AI-avatar bridge and web administration platform for OpenSimulator.**

**FR** — Projet open source visant à connecter un véritable avatar autonome à une grille OpenSimulator, sans viewer graphique, et à proposer une interface Web de gestion, un moteur de réponses gratuites, la traduction, des services de grille contrôlés et l'IA distante pour les utilisateurs autorisés.

**EN** — Open-source project to connect a real autonomous avatar to OpenSimulator without a graphical viewer, with web administration, configurable rule-based answers, translation, controlled grid integrations, and remote AI access for authorized users.

> **Status / État (24 November 2026):** BloodMoon deployment and live provider validation are underway. The .NET multi-provider routing and shared SQLite provider-attempt limiter are implemented; full automatic failover under real quota exhaustion and long-running reliability are **not yet proven in production**. Not a production-ready general release.

## Key principles / Principes

- **OpenSimulator-first:** initially tested against OpenSimulator 0.9.3.1; compatibility must be validated.
- **Real avatar:** headless client using [LibreMetaverse](https://github.com/cinderblocks/libremetaverse), with IM, local chat and resilient login.
- **Remote AI only:** no Ollama or local language model; optional remote Groq, Gemini and OpenRouter APIs with distinct credentials, subject to provider quotas and billing settings.
- **Free answer engine:** admin-editable questions, triggers, multilingual answers, variables, fallback and unanswered-question queue without paid AI calls.
- **Translation:** configurable HTTP provider with an adapter for BloodMoon's Translator API; exact request/response contract to be confirmed from source.
- **Web console:** online status, region/position, permissions, answer editor, usage limits and audit logs.
- **ROBUST integration:** secure, allow-listed read-only operations first; do not expose raw SQL or administrative execution to language models.
- **Portable:** BloodMoon is the reference environment, not a hardcoded dependency.
- **Safety:** private credentials, explicit profile verification, approved public models, request throttling and a shared per-provider attempt cap. No guarantee that provider-side quotas or paid usage are fully measurable or prevented by the application.

## Documentation / Documentation

- [Cahier des charges (FR)](docs/CAHIER_DES_CHARGES_FR.md)
- [Requirements (EN)](docs/REQUIREMENTS_EN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Security policy](SECURITY.md)
- [Example configuration](config/appsettings.example.json)
- [Avatar password file template / Modèle de fichier mot de passe](bot-password.example.txt) — never commit the real `bot-password.txt`

## First experimental client / Premier client expérimental

- [Source .NET 8](src/OpenSimAiBridge.Bot/Program.cs)
- [Installation FR and first test](docs/INSTALLATION_V01_FR.md)
- [Verified BloodMoon V0.1 tests / Compte rendu des tests](docs/TESTS_2026-11-20_FR.md)
- [Web administration V0.2 design / Conception administration Web](docs/WEB_ADMIN_V02_FR.md)
- [Systemd and Firestorm-mode setup / Service et mode Firestorm](docs/SERVICE_SYSTEMD_V02_FR.md)
- [Web administration V0.2 install (FR) / Installation de l'administration Web](docs/WEB_INSTALL_V02_FR.md)
- [Multi-bot Web preview / Gestion de plusieurs avatars](docs/MULTI_BOT_V02_FR.md)
- [Remote AI IM pilot / IA distante pour les IM](docs/REMOTE_AI_V03_FR.md)
- [Multi-provider routing / Routage multi-fournisseurs (FR)](docs/MULTI_PROVIDER_ROUTING_FR.md)

## Current BloodMoon deployment / Déploiement actuel (24 November 2026)

**FR :** Le tableau de bord PHP, le contrôleur et le module IA distant sont utilisés sur BloodMoon. Les tests administrateur ont validé notamment Groq `openai/gpt-oss-20b` (modèle principal), Groq `openai/gpt-oss-120b` et Gemini `gemini-3.5-flash-lite` ; un test de validation ne prouve **pas** à lui seul un relais automatique en conversation IM. OpenRouter a également passé une validation, sans modèle précisé ici. Les anciens identifiants Groq `llama-3.3-70b-versatile` et `llama-3.1-8b-instant` ont renvoyé HTTP 404 dans l'administration ; ne pas les présenter comme profils fonctionnels.

**EN:** The web admin/controller and remote AI module are in use on BloodMoon. Admin-side model checks succeeded for the named Groq/Gemini models above; this is **not** evidence of a live IM failover during a provider quota outage. Actual installed configuration, enabled profiles and provider billing must be checked on the host.

### How routing works / Fonctionnement du routage

- The **global** `config/multi-ai.json` defines an ordered profile list shared by all AI-enabled avatars; API keys are separate in `ai-keys/`. Each avatar has its own AI enable switch.
- In `auto` mode, the .NET `RemoteAiResponder` tries the next *enabled, verified, publicly eligible* profile if the current profile fails, times out, produces an empty response, has a blocked local quota, or returns a non-success HTTP status. In `single` mode there is **no** automatic fallback.
- `SharedProviderQuota` stores admissions in `data/ai-provider-quotas.db`: up to **30 attempted requests per provider per UTC hour**, shared by all avatars (and constrained further by the configured application limit). **Two Groq models share this Groq bucket**, rather than receiving 30 each. Provider-imposed token, minute, daily and billing quotas are **not** directly read or guaranteed by this limit.
- A failed profile is temporarily skipped **in the current bot process**, then retried after its cooldown. The current route does **not** call `SharedProviderQuota.RecordCooldown`; therefore it does **not** persist provider-wide error cooldowns, despite the method existing in the quota class. This distinction matters when testing.
- No automatic paid-provider activation is intended. Administrator validation, key presence, enable state and eligibility checks are all necessary. A configured Gemini/OpenRouter fallback must also be enabled and the global mode set to `auto`.

**Verification still required / À tester :** actual IM reply after the primary model returns 429, fallback to the next Groq model, fallback across providers, recovery after cooldown, concurrency and full depletion behavior. Use a controlled test, keep the working Groq model and credentials intact, and do not interpret a green admin validation as an integration test.

There is no completed grid-database adapter or translation integration. See the routing document for migration notes and security limitations.

## Initial milestone / Premier jalon

A headless avatar logs in, appears in a configured region, receives an IM, replies without an AI request, exposes health/location to the Web API and reconnects after disconnection. Test off-production before enabling on the BloodMoon welcome region.

## References / Références

- [LibreMetaverse](https://github.com/cinderblocks/libremetaverse)
- [OpenSimulator](http://opensimulator.org/)
- [OpenSim Handbook](https://github.com/Vlad-BloodMoon/OpenSim_Handbook)

## Contributing / Contribuer

Feature requests, corrections and technical reviews are welcome. Please do not commit passwords, access tokens, grid credentials, database dumps or private chat logs.

**License / Licence:** to be selected after verifying third-party compatibility; until then, no explicit reuse license is granted.
