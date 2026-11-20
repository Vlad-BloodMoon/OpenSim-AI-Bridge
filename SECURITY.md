# Security policy / Politique de sécurité

**Project stage:** design and prototype. No production security guarantees exist yet.

Please do **not** publish vulnerabilities, authentication tokens, API keys, avatar passwords, database credentials, user UUID access lists or private messages in public issues.

## Security requirements

- Remote AI tools operate under explicit, least-privilege server-side authorization.
- No arbitrary SQL or shell access is provided to an AI model.
- Web console uses HTTPS, secure authentication and audited administrative operations.
- Bot credentials, OpenAI API keys, translator credentials and database secrets are stored outside Git.
- Access to paid AI is denied by default and granted by verified UUID.
- Chat transcripts and memory are minimized, protected and subject to opt-in and retention settings.
- Sensitive actions need separate, documented approvals and do not run automatically.

For a potential vulnerability, contact the maintainer privately through an appropriate GitHub private reporting channel if enabled. Do not post exploit details publicly.
