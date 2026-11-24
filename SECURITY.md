# Security policy / Politique de sécurité

**Status / État:** active pilot; **not security-certified or generally production-ready**. This public repository contains a .NET bot, a PHP administrator and a privileged local Python controller. Treat deployment and remote-model usage as security-sensitive.

## Reporting vulnerabilities / Signaler une vulnérabilité

If GitHub private vulnerability reporting is enabled for this repository, use it. Otherwise contact the repository maintainer through a **private** channel before disclosing details. Never post working credentials, avatar passwords, resident messages, personally identifying data, secret URLs, database backups or exploit instructions in public issues.

## Implemented boundaries / Mesures présentes

- HTTPS-only admin panel, authenticated PHP session, session timeout, CSRF on writes, restrictive response headers and a local Unix-socket controller authenticated by operating-system peer credentials.
- A fixed command allowlist and argument validation in the controller. The LLM cannot directly issue systemd/shell/SQL commands or arbitrary administrative requests.
- Avatar password and provider API keys are stored in private files loaded outside Git. The Azure subscription key is not placed in the bot or public Web directory.
- Remote providers are selected only from configured profiles. The app has a local attempted-request limit and sender cooldown; these are **not a guarantee** against external provider quota/billing events.
- Private TXT source folders and local SQLite state must remain outside publicly served document paths or be filesystem-inaccessible to the Web user; `.htaccess` alone is not sufficient.
- AI and retrieved documents are untrusted; prompt-injection defenses, privacy policy and provider logging require continued review.

## Deployment rules / Consignes

1. Keep the Web admin credentials, provider tokens, avatar login, `config/` secrets and databases out of Git and backup archives shared publicly.
2. Use dedicated least-privilege service identities. Review the actual `systemd` unit files, filesystem permissions and Web/PHP ownership.
3. Expose **only** the authenticated HTTPS admin page to trusted administrators. Do not expose the controller socket publicly.
4. Confirm Azure translator access-control configuration before deploying the optional `deploy/php/ai-translate.php`; the endpoint uses a protected token and sends resident questions to a remote third party.
5. Back up old binaries/scripts before updating, enter maintenance mode, test a controlled rollout and restore the old files if necessary.
6. Document how residents are informed that their IM text may be processed by external AI and translation services; avoid storing unnecessary raw conversation content.
7. Review externally hosted API price, usage and billing controls directly with the provider. A locally accepted free model may later change eligibility.

## Scope limitations / Limites

There is no independent security audit, no complete RBAC policy, no general tool-execution interface with per-action approvals, and no proof of total token/cost enforcement. The presence of a `LICENSE` file is also pending a third-party license review. Contributions to security hardening are welcome.
