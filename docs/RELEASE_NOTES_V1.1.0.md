# OpenSim AI Bridge v1.1.0 — Baseline before the intelligent AI router roadmap

**Release date:** 27 November 2026. **Type:** stable-tagged public snapshot of the current code, before the planned V1/V2/V3 intelligent-routing work. The original `v1.0.0` release remains unchanged. **A GitHub Actions build is not a universal production certification.**

## English

### What's new since v1.0.0

- **Per-avatar provider activity audit:** records which remote AI provider and model actually answered, plus failed/skipped attempts, HTTP codes and whether a fallback occurred. The private activity log is bounded and the authenticated admin panel shows recent attempts. No message text, API key or resident UUID is intentionally recorded in this activity trail. See [AI provider activity guide (FR)](AI_PROVIDER_ACTIVITY_FR.md).
- **Shared document-library PDF indexing:** recursive incremental import of PDFs from a configurable local directory such as BloodMoon's `/var/www/BloodMoon/files/`. SHA-256 incremental updates, deleted-file handling and per-page source references, with an independent example systemd timer. Existing documents and categories are retained. See [PDF knowledge guide (FR)](FILES_PDFS_KNOWLEDGE_FR.md).
- **More offline tests and deployment notes** for the provider audit, PDF indexing and related controls.
- **Documented multi-version roadmap:** [V1 reliable fallback](https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge/issues/2), [V2 remote model catalog](https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge/issues/3) and [V3 optional intelligent selection](https://github.com/Vlad-BloodMoon/OpenSim-AI-Bridge/issues/4). **These roadmap changes are not yet implemented in v1.1.0.**

### Scope and operational status

- Continues to run headless OpenSimulator avatars via LibreMetaverse / .NET 8, private IM AI answers through **remote** Groq, Gemini and OpenRouter APIs, local FTS5 knowledge retrieval, optional translation and authenticated Web administration.
- The **normal successful Groq IM response and provider model audit** were exercised on BloodMoon. **An actual multi-provider fallback after a live 429 / quota exhaustion is not yet end-to-end validated.** Shared SQLite attempted-request quotas exist, but a received provider 429 currently sets a **per-process/per-profile cooldown**; sharing provider-error cooldowns across bots is planned for V1.
- Recursive PDF indexing was deployed and checked on BloodMoon; it depends on `pdftotext` and access to the document files. It is not enabled automatically on other installations.
- No local LLM inference is bundled, no provider keys or passwords are included, and **no new AI router or catalog service** is installed by this release.
- Linux x64 / framework-dependent .NET 8 distribution. The optional admin/control stack needs independently configured PHP, Python, systemd, HTTPS and security permissions.

### Upgrade, limitations and safety

- **Back up the installed bot DLLs, controller, PHP, configuration, private keys, avatar profiles and SQLite databases** before updating. This ZIP is an archive for controlled deployment, **not** an auto-updater.
- Do **not** overwrite `appsettings.json`, `config/multi-ai.json`, private credential files, knowledge databases or production state with example files.
- Test on a non-production avatar before restarting public bots. Verify IM delivery, permissions, model selection, knowledge search, welcome messages and admin services. Preserve the known-good binaries and restore them if regression occurs.
- Free providers may change quotas or require billing; rate-limits are **not** an availability guarantee.
- Public repository visibility does not establish a license for OpenSim AI Bridge: **this repository has no explicit project LICENSE as of this release**. Third-party code and licenses remain governed by their respective terms.
- Read the [standalone installation/evaluation guide](RELEASE_INSTALL_FR_EN.md), [security guidance](../SECURITY.md) and [full roadmap (FR)](AI_ROUTER_CATALOG_ROADMAP_FR.md).

## Français

### Nouveautés depuis v1.0.0

- **Historique réel des API par avatar** : fournisseur et modèle ayant répondu, essais rejetés, codes HTTP et indication d'un éventuel basculement. Consultation dans **Modules IA** sans stocker le texte des IM ou les clés dans ce journal. [Guide](AI_PROVIDER_ACTIVITY_FR.md).
- **Indexation incrémentale et récursive des PDF** de la bibliothèque documentaire (avec extraction des pages, empreintes SHA-256, prise en compte des ajouts/modifications/suppressions et timer systemd séparé). [Guide](FILES_PDFS_KNOWLEDGE_FR.md).
- **Tests et documentation supplémentaires**, notamment pour vérifier le suivi des API et la bibliothèque PDF.
- **Plan d'évolution V1/V2/V3** ajouté au dépôt : [feuille de route](AI_ROUTER_CATALOG_ROADMAP_FR.md). **Le routeur intelligent et le catalogue ne font pas encore partie du logiciel publié.**

### État de validation et précautions

- Le bot répond actuellement par **IM privé** avec des API distantes ; une réponse réelle de Groq et son suivi ont été observés sur BloodMoon. Un **basculement réel** après saturation d'un fournisseur doit encore être testé.
- Les budgets SQLite sont partagés entre avatars, mais les périodes de refroidissement déclenchées par un 429 ne le sont **pas encore**. Leur partage est prévu en V1.
- La bibliothèque PDF a été testée sur BloodMoon ; elle nécessite `pdftotext` et un réglage local explicite.
- **Avant toute installation : sauvegarder** binaires, contrôleur, fichiers PHP, configurations, clés et bases SQLite ; tester sur un avatar non public ; conserver un retour arrière.
- Ne jamais mettre de secrets dans GitHub. Les nouvelles fonctions V1/V2/V3 ne doivent pas casser l'existant, les connaissances, la traduction ou les réponses IM.
- Cette distribution est un **instantané public de référence**, pas une certification universelle. Aucune IA locale ni passerelle supplémentaire n'est installée.

**Liens :** [Guide d'installation](RELEASE_INSTALL_FR_EN.md) · [Roadmap V1–V3](AI_ROUTER_CATALOG_ROADMAP_FR.md) · [Suivi des API](AI_PROVIDER_ACTIVITY_FR.md) · [Bibliothèque PDF](FILES_PDFS_KNOWLEDGE_FR.md).
