# OpenSim AI Bridge — Requirements (EN)

> **Historical requirements, 20 November 2026.** This is the original scope, **not** the current implementation status. Some features are now implemented, while others remain planned. See the [README](../README.md) and [roadmap](ROADMAP.md) for the audited current state.

**Status:** initial proposal, 20 November 2026; not implemented yet.  
**Reference environment:** BloodMoon / OpenSimulator 0.9.3.1; reusable across grids.

## Vision

Build an open-source, modular, headless OpenSimulator avatar service with web administration, a no-cost curated response engine, configurable translation, and optional **remote** AI for explicitly authorized residents and administrators.

## Firm decisions

- .NET 8 + LibreMetaverse as the first candidate for a real avatar session; verify in a test grid.
- **No local language models, Ollama or on-premises LLM inference.**
- Remote OpenAI API only for allowed UUIDs; ChatGPT subscription does not cover API usage.
- Public visitors use curated, editable answers without paid AI calls.
- Web console must configure responses, permission rules, bots, translation providers and usage quotas.
- Translation provider abstraction; BloodMoon Translator HTTP integration after inspecting its actual contract.
- Read-only ROBUST integration by default; no arbitrary SQL, shell or destructive operations exposed to the model.
- Grid-neutral code and configuration, no private credentials committed.

## Functional requirements

1. Login/logout, online health, current region and position, local chat, IM, throttling, reconnect.
2. Web-managed FAQ entries with alternative phrasings, multilingual variants, categories, enabled/disabled state and deterministic matching.
3. Unanswered-question review queue, safe placeholders, import/export and change history.
4. Authorization by verified avatar UUID and separately authenticated web operator roles.
5. Remote AI provider interface with budgets, rate limits, auditable tool calls, safe degradation to free answers.
6. Translation provider adapter, caching and user language preferences; optional explicit resident-to-resident translation.
7. Grid lookup through allow-listed tools and least-privilege integration; no raw database credentials visible to AI.
8. Optional future mobility, animations, WebRTC voice, Hypergrid, multi-bot and MCP integration.

## Architecture

`Avatar Client (.NET / LibreMetaverse)` ↔ `Core API / Orchestrator` ↔ `Web Console`, `Answer Engine`, `Remote AI Provider`, `Translation Provider`, `Grid Adapter`, `Storage`.

Use async message queues with bounds, independent permission checks on every operation, secure secret storage and graceful failure handling.

## Release milestones

- **0.1:** avatar visible, local chat/IM, static responses, reconnect, location/health.
- **0.2:** secure admin UI and persistent free answer engine.
- **0.3:** translation and remote AI access policies, budgets and quotas.
- **0.4:** safe ROBUST/grid lookups and opted-in knowledge/memory.
- **0.5+:** movement, automation, multi-avatar, voice and Hypergrid.

## Security and privacy

Least privilege, HTTPS, credentials outside Git, server-side UUID verification, user isolation, consent-aware message retention, deletion controls, request throttling, bounded context and human confirmation for high-risk operations. The language model may never construct unrestricted SQL or administrative shell commands.

The French specification is the detailed project reference: [Cahier des charges FR](CAHIER_DES_CHARGES_FR.md).
