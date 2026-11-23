"""Validated multi-provider profiles for the admin controller.

The legacy Ai config is kept until the administrator explicitly saves the new
profile list. API keys are stored separately, never returned to PHP.
"""
import os
import re
import stat
import tempfile
from pathlib import Path

PROVIDERS = {
    "Groq": {"default": "openai/gpt-oss-20b", "keyenv": "OSAI_GROQ_API_KEY"},
    "OpenRouter": {"default": "openrouter/free", "keyenv": "OSAI_OPENROUTER_API_KEY"},
    "OpenAI": {"default": "gpt-4.1-mini", "keyenv": "OSAI_OPENAI_API_KEY"},
}
PROVIDER_KEYS = {"Groq": "groq", "OpenRouter": "openrouter", "OpenAI": "openai"}


class ProfileError(ValueError):
    pass


def provider_key_path(install, provider):
    if provider not in PROVIDERS:
        raise ProfileError("Unrecognized provider")
    return Path(install) / "ai-keys" / (PROVIDER_KEYS[provider] + ".txt")


def public_eligible(provider, model):
    # Zero-cost default must be fail-closed. OpenRouter :free is a candidate
    # but still requires administrator approval; provider billing needs checking.
    return provider == "Groq" or (provider == "OpenRouter" and model.endswith(":free")) or (
        provider == "OpenRouter" and model == "openrouter/free")


def normalize(values):
    if not isinstance(values, dict) or set(values) != {"enabled", "mode", "profiles", "maxRequestsPerHour", "minSecondsBetweenRequests", "systemPrompt"}:
        raise ProfileError("Invalid multi-provider settings")
    if type(values["enabled"]) is not bool or values["mode"] not in ("single", "auto"):
        raise ProfileError("Invalid activation or mode")
    profiles = values["profiles"]
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 8:
        raise ProfileError("Add 1–8 provider profiles")
    result, seen = [], set()
    for entry in profiles:
        if not isinstance(entry, dict) or set(entry) != {"id", "provider", "model", "enabled", "verified", "apiKey"}:
            raise ProfileError("Invalid provider profile")
        name, provider, model = entry["id"], entry["provider"], entry["model"]
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9-]{1,24}", name) or name in seen:
            raise ProfileError("Invalid or duplicate profile ID")
        seen.add(name)
        if provider not in PROVIDERS or not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9._:/-]{1,100}", model):
            raise ProfileError("Invalid provider or model")
        if type(entry["enabled"]) is not bool or type(entry["verified"]) is not bool:
            raise ProfileError("Invalid provider flags")
        key = entry["apiKey"]
        if not isinstance(key, str) or len(key) > 256 or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ProfileError("Invalid API key")
        if entry["verified"] and not public_eligible(provider, model):
            raise ProfileError("This provider/model is not permitted in zero-cost public routing")
        result.append({"Id": name, "Provider": provider, "Model": model,
                       "Enabled": entry["enabled"], "Verified": entry["verified"],
                       "ApiKeyEnv": PROVIDERS[provider]["keyenv"]})
    if values["enabled"] and not any(e["Enabled"] and e["Verified"] for e in result):
        raise ProfileError("Activate at least one approved provider before enabling AI")
    hourly, cooldown = values["maxRequestsPerHour"], values["minSecondsBetweenRequests"]
    if type(hourly) is not int or not 1 <= hourly <= 120 or type(cooldown) is not int or not 5 <= cooldown <= 3600:
        raise ProfileError("Invalid rate limits")
    prompt = values["systemPrompt"]
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 600 or any(ord(c) < 32 and c not in "\n\t" for c in prompt):
        raise ProfileError("Invalid system prompt")
    return {"Enabled": values["enabled"], "Mode": values["mode"], "Profiles": result,
            "MaxRequestsPerHour": hourly, "MinSecondsBetweenRequests": cooldown, "SystemPrompt": prompt.strip()}


def save_keys(install, profiles, owner_uid, owner_gid):
    root = Path(install) / "ai-keys"
    if root.is_symlink():
        raise ProfileError("Unsafe key directory")
    if not root.exists():
        root.mkdir(mode=0o700)
        os.chown(root, owner_uid, owner_gid)
    if root.stat().st_mode & 0o077:
        raise ProfileError("Key directory permissions insecure")
    for item in profiles:
        key = item["apiKey"]
        if not key:
            continue
        dest = provider_key_path(install, item["provider"])
        if dest.is_symlink():
            raise ProfileError("Unsafe key path")
        fd, temporary = tempfile.mkstemp(prefix=".key-", dir=str(root))
        try:
            os.fchmod(fd, 0o600)
            os.fchown(fd, owner_uid, owner_gid)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(key + "\n")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, dest)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def existing_profiles(ai, install):
    profiles = ai.get("Profiles")
    if not isinstance(profiles, list) or not profiles:
        provider = ai.get("Provider", "Groq")
        if provider not in PROVIDERS:
            provider = "Groq"
        profiles = [{"Id": "primary", "Provider": provider,
                     "Model": ai.get("Model", PROVIDERS[provider]["default"]),
                     "Enabled": True, "Verified": provider == "Groq",
                     "ApiKeyEnv": PROVIDERS[provider]["keyenv"]}]
    result = []
    for entry in profiles:
        provider = entry.get("Provider")
        if provider not in PROVIDERS:
            continue
        keyfile = provider_key_path(install, provider)
        legacy = Path(install) / "ai-api-key.txt"
        has_key = keyfile.is_file() and keyfile.stat().st_size > 0
        if not has_key and len(profiles) == 1 and provider == ai.get("Provider") and legacy.is_file():
            has_key = legacy.stat().st_size > 0
        result.append({"id": entry.get("Id", "primary"),
                       "provider": provider, "model": entry.get("Model", ""),
                       "enabled": bool(entry.get("Enabled", False)),
                       "verified": bool(entry.get("Verified", False)), "hasKey": has_key})
    return result
