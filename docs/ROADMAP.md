# Roadmap / Feuille de route

V0.1 was built and passed first grid/IM tests on 20 November 2026; other milestones remain **planned**. See [test report](TESTS_2026-11-20_FR.md).

## V0.1 — Real avatar / Avatar réel
- [x] Verify basic login + IM compatibility with OpenSimulator 0.9.3.1 (limited test; not a full compatibility guarantee).
- [x] Implement configurable account login in .NET 8 without a viewer.
- [x] Report region and coordinates to console/IM (Web API reporting pending).
- [x] Receive/reply to **IM** with static test responses; local chat reception coded but **not tested**.
- [ ] Handle disconnection, reconnection, spam and message length.
- [x] Test on BloodMoon_TEST before use at the BloodMoon welcome area.

**Acceptance:** from Firestorm, an administrator sees the avatar and completes an IM round-trip without running any graphic viewer.

## V0.2 — Web admin & free responses (immediate priority)
- [x] Run bot under a non-root systemd service (initial start/stop tests passed on BloodMoon 2026-11-23; further hardening planned).
- [ ] Authenticated Web controls: start, stop, restart, status/position/logs.
- [x] Firestorm lock prevents manual systemd startup; stop/resume verified 2026-11-23. **Survival of full server reboot still untested**.
- [ ] Distinguish intentional shutdown from network failure; prevent session battles with Firestorm.
- [ ] Secure web login and API: initial password-authenticated PHP dashboard and restricted Unix-socket controller **coded, not yet deployed/tested**; RBAC and stronger isolation pending.
- [ ] Dashboard: systemd status and controls **coded, not yet tested**; actual avatar location and technical logs still pending.
- [ ] Persistent FAQ CRUD, categories, variants, multilingual entries and safe template variables.
- [ ] Unknown-question moderation queue, response previews and audit history.
- [ ] Verify public chat never triggers paid AI by default.

## V0.3 — Translation & remote AI
- [ ] Inspect and test BloodMoon Translator's actual JSON contract.
- [ ] Create pluggable HTTP translation adapter, language preferences and cache.
- [ ] Integrate remote OpenAI API, separate secrets and usage accounting.
- [ ] UUID allowlists, rate limits and per-user/per-model quotas.
- [ ] Test budget-stop behavior and free-answer fallback.

## V0.4 — Grid knowledge and controlled tools
- [ ] Add read-only grid/ROBUST adapter using least privilege.
- [ ] Evaluate reuse of Marketplace IM transport without tight coupling.
- [ ] Optional handbook documentation retrieval and consent-aware memory.
- [ ] Server-side authorization, validation, confirmation and audit for every tool.

## V0.5+ — Avatar life and ecosystem
- [ ] Movements, animations and controlled teleportation.
- [ ] Multi-avatar support.
- [ ] Research WebRTC voice integration.
- [ ] Research Hypergrid interaction.
- [ ] Evaluate MCP interoperability and plugin ecosystem.

## Before selecting a license
- [ ] Audit LibreMetaverse and all transitive licensing requirements.
- [ ] Choose an explicit open-source license, then add LICENSE.
