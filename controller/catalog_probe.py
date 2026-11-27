"""Manual compatibility probes for curated external OpenAI-compatible APIs.

This module NEVER grants bot routing or stores credentials. Only explicitly
reviewed HTTPS destinations may receive an admin-supplied API key. A catalog
claim of OpenAI compatibility is NOT permission to send secrets to its URL.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

# Audited HTTPS endpoints. Expand this registry only after reviewing a provider.
# No arbitrary URL, hostname, path, redirect or proxy is accepted from a user.
ENDPOINTS = {
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
    "cohere": "https://api.cohere.ai/compatibility/v1/chat/completions",
}
MAX_RESPONSE = 32768


class ProbeError(ValueError):
    pass


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProbeError("Le fournisseur a redirigé la requête : test arrêté.")


def available(provider):
    return provider in ENDPOINTS


def validate_selection(provider, model, snapshot):
    if not isinstance(provider, str) or provider not in ENDPOINTS:
        raise ProbeError("Ce fournisseur n'est pas encore autorisé pour un test générique.")
    if not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9._:/-]{1,100}", model):
        raise ProbeError("Identifiant de modèle invalide.")
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("models"), list):
        raise ProbeError("Catalogue indisponible.")
    if not any(isinstance(row, dict) and row.get("provider") == provider and
               row.get("model") == model for row in snapshot["models"][:3000]):
        raise ProbeError("Ce modèle n'est pas présent dans le catalogue importé.")
    return ENDPOINTS[provider]


def probe(provider, model, key, snapshot, opener=None):
    """One explicit API test; never persists or returns key/prompt/response."""
    endpoint = validate_selection(provider, model, snapshot)
    if (not isinstance(key, str) or not 1 <= len(key) <= 256 or
        any(ord(c) < 33 or ord(c) > 126 for c in key)):
        raise ProbeError("Renseigne une clé API valide pour ce fournisseur.")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "Reply with the word BONJOUR."}],
        "max_tokens": 40,
        "temperature": 0
    }, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        endpoint, data=body, method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "Accept": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    if opener is None:
        opener = urllib.request.build_opener(_RejectRedirect(), urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=12) as response:
            if response.status != 200:
                raise ProbeError("Réponse HTTP inattendue.")
            if int(response.headers.get("Content-Length", "0")) > MAX_RESPONSE:
                raise ProbeError("Réponse API trop volumineuse.")
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise ProbeError("Réponse API trop volumineuse.")
    except urllib.error.HTTPError as exc:
        messages = {
            400: "Requête ou modèle refusé.",
            401: "Clé API refusée.",
            403: "Accès interdit pour cette clé ou depuis ce serveur.",
            404: "Modèle introuvable chez le fournisseur.",
            429: "Quota atteint.",
            500: "Erreur du fournisseur.",
            503: "Service temporairement indisponible.",
        }
        raise ProbeError("HTTP " + str(exc.code) + " — " +
                         messages.get(exc.code, "Échec du test.")) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProbeError("Connexion impossible ou délai dépassé.") from None
    try:
        result = json.loads(raw)
        text = result["choices"][0]["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Empty text")
    except (KeyError, IndexError, TypeError, ValueError):
        raise ProbeError("API joignable mais réponse incompatible avec chat/completions.") from None
    return {"success": True, "provider": provider, "model": model,
            "responseFormat": "OpenAI chat/completions",
            "routingEnabled": False, "credentialsStored": False}
