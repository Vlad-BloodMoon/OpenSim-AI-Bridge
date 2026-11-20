# OpenSim AI Bridge

**An extensible AI-avatar bridge and web administration platform for OpenSimulator.**

**FR** — Projet open source visant à connecter un véritable avatar autonome à une grille OpenSimulator, sans viewer graphique, et à proposer une interface Web de gestion, un moteur de réponses gratuites, la traduction, des services de grille contrôlés et l'IA distante pour les utilisateurs autorisés.

**EN** — Open-source project to connect a real autonomous avatar to OpenSimulator without a graphical viewer, with web administration, configurable rule-based answers, translation, controlled grid integrations, and remote AI access for authorized users.

> **Status / État :** specification and architecture phase. No production-ready bot has been released yet.

## Key principles / Principes

- **OpenSimulator-first:** initially tested against OpenSimulator 0.9.3.1; compatibility must be validated.
- **Real avatar:** headless client using [LibreMetaverse](https://github.com/cinderblocks/libremetaverse), with IM, local chat and resilient login.
- **Remote AI only:** no Ollama, no local language models; remote OpenAI API where permitted, billed separately from ChatGPT subscriptions.
- **Free answer engine:** admin-editable questions, triggers, multilingual answers, variables, fallback and unanswered-question queue without paid AI calls.
- **Translation:** configurable HTTP provider with an adapter for BloodMoon's Translator API; exact request/response contract to be confirmed from source.
- **Web console:** online status, region/position, permissions, answer editor, usage limits and audit logs.
- **ROBUST integration:** secure, allow-listed read-only operations first; do not expose raw SQL or administrative execution to language models.
- **Portable:** BloodMoon is the reference environment, not a hardcoded dependency.
- **Safety:** UUID-based authorization, access tiers, privacy/consent, secrets outside the repository, rate limiting and budget enforcement.

## Documentation / Documentation

- [Cahier des charges (FR)](docs/CAHIER_DES_CHARGES_FR.md)
- [Requirements (EN)](docs/REQUIREMENTS_EN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Security policy](SECURITY.md)
- [Example configuration](config/appsettings.example.json)

## Initial milestone / Premier jalon

A headless avatar logs in, appears in a configured region, receives an IM, replies without an AI request, exposes health/location to the Web API and reconnects after disconnection. Test off-production before enabling on the BloodMoon welcome region.

## References / Références

- [LibreMetaverse](https://github.com/cinderblocks/libremetaverse)
- [OpenSimulator](http://opensimulator.org/)
- [OpenSim Handbook](https://github.com/Vlad-BloodMoon/OpenSim_Handbook)

## Contributing / Contribuer

Feature requests, corrections and technical reviews are welcome. Please do not commit passwords, access tokens, grid credentials, database dumps or private chat logs.

**License / Licence:** to be selected after verifying third-party compatibility; until then, no explicit reuse license is granted.
