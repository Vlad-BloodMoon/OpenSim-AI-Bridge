"""V2 read-only remote API discovery catalog (no bot/runtime integration).

All input is untrusted third-party metadata. This module never makes network
requests, stores credentials, approves a model, or modifies existing profiles.
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit
import re

SCHEMA_VERSION = 2
MAX_PROVIDERS = 250
MAX_MODELS = 3000
MAX_FIELD = 300
# Explicit aliases for the three remote providers implemented by our V1 router.
# Catalog entries from OTHER aggregators (including models named "Gemini")
# must never be treated as Gemini's direct API.
CATALOG_ADAPTERS = {
    "groq": "Groq",
    "groq-cloud": "Groq",
    "openrouter": "OpenRouter",
    "gemini": "Gemini",
    "google-ai-studio": "Gemini",
}


def adapter_for_slug(slug):
    """Return a supported V1 remote adapter, never infer from model names."""
    return CATALOG_ADAPTERS.get(slug) if isinstance(slug, str) else None


def catalog_provider_search_text(slug, display_name):
    """Accept either catalog names (Google AI Studio) or V1 names (Gemini)."""
    adapter = adapter_for_slug(slug)
    return " ".join(value for value in (slug, display_name, adapter) if isinstance(value, str))



class CatalogError(ValueError):
    """Invalid external catalog."""


def _clean(value, limit=MAX_FIELD):
    if not isinstance(value, str):
        return ""
    # The UI escapes output too; strip controls at the ingestion boundary.
    return "".join(c for c in value if c.isprintable())[:limit].strip()


def _https_url(value):
    if not isinstance(value, str) or len(value) > 500:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return ""
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            return ""
        return value if parsed.port is None or parsed.port == 443 else ""
    except ValueError:
        return ""


def normalize_catalog(payload):
    """Normalize schema-v2 records into inert metadata; never an API profile."""
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise CatalogError("Unsupported catalog schema")
    providers = payload.get("providers")
    if not isinstance(providers, list) or len(providers) > MAX_PROVIDERS:
        raise CatalogError("Invalid provider list")
    source = _https_url(payload.get("source"))
    if not source or source != "https://free-llm.com":
        raise CatalogError("Unexpected catalog provenance")
    generated = _clean(payload.get("generated_at"), 64)
    try:
        timestamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("Naive timestamp")
    except ValueError as exc:
        raise CatalogError("Missing or invalid catalog generation time") from exc

    result, seen = [], set()
    for provider in providers:
        if not isinstance(provider, dict):
            raise CatalogError("Invalid provider record")
        kind = _clean(provider.get("type"), 32).lower()
        # Local or self-hosted runtimes are deliberately excluded.
        if kind not in {"api", "proxy"}:
            continue
        slug = _clean(provider.get("slug"), 80)
        label = _clean(provider.get("name"), 120)
        url = _https_url(provider.get("url"))
        base_url = _https_url(provider.get("base_url"))
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", slug) or not label or not url or not base_url:
            continue
        models = provider.get("models")
        if not isinstance(models, list):
            continue
        for model in models:
            if not isinstance(model, dict) or _clean(model.get("kind"), 32).lower() != "chat":
                continue
            model_id = _clean(model.get("id"), 100)
            model_name = _clean(model.get("name"), 150)
            if not model_id or not model_name or not re.fullmatch(r"[A-Za-z0-9._:/+-]{1,100}", model_id):
                continue
            unique = (slug, model_id)
            if unique in seen:
                continue
            seen.add(unique)
            if len(result) >= MAX_MODELS:
                raise CatalogError("Catalog exceeds model limit")
            context = model.get("context_tokens")
            context_tokens = context if type(context) is int and 0 < context <= 10_000_000 else None
            free_tier = _clean(provider.get("free_tier"), 40)
            result.append({
                "provider": slug,
                "providerName": label,
                "model": model_id,
                "modelName": model_name,
                "vision": model.get("vision") is True,
                "contextTokens": context_tokens,
                "freeTierClaim": free_tier or "unknown",
                "costVerified": False,
                "rateLimitClaim": _clean(provider.get("rate_limit")),
                "dailyLimitClaim": _clean(provider.get("daily_limit")),
                "sourceUrl": url,
                "apiBaseUrl": base_url,
                "routerCompatible": adapter_for_slug(slug) is not None,
                "approved": False,
                "enabled": False,
            })
    return {
        "source": source,
        "generatedAtUtc": timestamp.isoformat(),
        "schemaVersion": SCHEMA_VERSION,
        "models": result,
    }
