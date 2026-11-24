# OpenSim AI Bridge v1.0.0 — First Public Release

**Release type:** public release (not pre-release). **Status:** first version available for third-party evaluation and deployment; not certified production software. Tested primarily on BloodMoon / OpenSimulator 0.9.3.1. All features and limitations below reflect the actual source code.

## English

OpenSim AI Bridge lets you run and manage OpenSimulator avatars **without a graphical viewer**, using .NET 8 and LibreMetaverse 3.3.1. AI answers rely on **external services**: no local LLM or Ollama is required.

### Features

- Headless avatar login, reconnection, private instant-message commands and remotely generated AI answers, split for Firestorm-compatible IM delivery.
- Authenticated HTTPS/PHP admin dashboard and a local Python Unix-socket controller for starting/stopping services, private per-avatar configuration, general maintenance, multiple bots and configurable model profiles.
- Remote AI providers: **Groq, Gemini and OpenRouter**; configurable profiles, attempted-request throttling and shared SQLite request limits.
- SQLite FTS5 search over indexed web documentation, PDFs and private TXT notes, with optional protected vocabulary and **optional** Azure-assisted translation of documentary search queries via a **separately operated gateway**.
- Optional visitor welcome sent to **public local chat (channel 0)** using the visitor's classic OpenSimulator avatar name and a per-bot configurable radius/cooldown.
- Optional **turn to face visitor** using LibreMetaverse `TurnToward`, without moving or following the person. AI questions are answered **in private IM**, not local chat.
- Full-precision avatar tracking, including large OpenSimulator varregions with X/Y greater than 255 metres.

### Validation and limitations

- The local greeting, original avatar-name personalization and one-time rotation were **observed working in Firestorm on BloodMoon**.
- GitHub Actions builds the Linux x64 .NET 8 framework-dependent distribution and runs Python, PHP, shell and C# offline regression checks.
- **Not validated as a universal, unattended installer** for other grids. The legacy BloodMoon-specific provisioning scripts must be reviewed and adapted before use; start with the [new standalone evaluation guide](RELEASE_INSTALL_FR_EN.md).
- Multi-provider fallback under a real 429/quota exhaustion, full multilingual IM/knowledge flows, simultaneous multi-bot scenarios and long-running availability are not all end-to-end certified.
- Web admin and privileged local controller require deliberate hardening, HTTPS, safe service permissions and an administrator-managed private secret store.
- Only classic avatar names are used in greetings, **not Display Names**. The bot does not navigate autonomously, teleport on request or provide voice features.
- Optional translation depends on an externally configured Azure gateway; **no BloodMoon private credentials, paid Azure access or keys are shipped**.

### Requirements

Linux x64; .NET **8 runtime**; an OpenSimulator avatar account and suitable grid access. The optional Web administration requires Python 3, PHP, HTTPS and systemd. Provide your own remote provider credentials and review costs and resident privacy.

**Licensing:** This repository currently has **no explicit LICENSE**. Public visibility and an attached archive do not grant an open-source reuse license. Third-party dependencies carry their own notices. The maintainer should select a license after reviewing dependency and redistribution requirements.

**For new users:** [Standalone evaluation and release installation (FR/EN)](RELEASE_INSTALL_FR_EN.md) · [README](../README.md) · [Security](../SECURITY.md) · [Detailed visitor welcome (FR)](PROXIMITY_WELCOME_FR.md).

## Français

**OpenSim AI Bridge v1.0.0** est une première **release publique officielle**, pas une préversion. Elle fournit des avatars OpenSimulator sans viewer, avec .NET 8 et LibreMetaverse, un panneau d'administration Web, des réponses IA par **IM privé** avec des API distantes, une recherche documentaire et une gestion multi-avatar.

L'accueil automatique en **chat local** permet de saluer les visiteurs par leur nom classique OpenSimulator, une seule fois par passage avec délai anti-répétition. Une option permet au bot de **se tourner vers la personne accueillie**, sans se déplacer. **Ces deux fonctions ont été testées avec succès dans Firestorm sur BloodMoon**, y compris la prise en charge des grandes régions.

**Points à connaître :** l'installation sur d'autres grilles nécessite encore des adaptations ; les scripts historiques sont liés à l'environnement BloodMoon et ne doivent pas être exécutés aveuglément. Les scénarios de panne/quotas fournisseurs, le multi-bot simultané, la stabilité longue durée et la sécurité en production demandent des validations supplémentaires. Les clés API, les mots de passe, les index privés et la configuration Azure BloodMoon ne sont jamais inclus dans l'archive.

**Aucun modèle IA local n'est requis.** Il faut cependant ses propres accès API distants, un avatar OpenSimulator, Linux x64 et le runtime .NET 8. L'administration Web est facultative et nécessite un déploiement HTTPS/PHP, un contrôleur Python et systemd.

**Licence :** aucune licence explicite n'est encore définie pour le projet. Une release publique n'implique pas, à elle seule, une licence open source.

Documentation : [installation et essai (FR/EN)](RELEASE_INSTALL_FR_EN.md) · [architecture](ARCHITECTURE.md) · [sécurité](../SECURITY.md).
