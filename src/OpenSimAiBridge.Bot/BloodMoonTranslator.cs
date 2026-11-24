using System.Collections.Concurrent;
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace OpenSimAiBridge;

/// <summary>
/// Reuses the already deployed BloodMoon translator-to-Azure gateway.
/// Azure credentials stay on the BloodMoon server; bots only use its own
/// restricted gateway token. No AI model, language pack or local translation.
/// </summary>
public sealed class BloodMoonTranslator : IDisposable
{
    private const string Endpoint = "https://bloodmoonpack.com/translator/translate.php";
    private readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(5) };
    private readonly ConcurrentDictionary<string, (DateTimeOffset saved, string text)> cache = new();
    private readonly string? token;
    public bool Enabled { get; }

    public BloodMoonTranslator(bool enabled, string tokenEnv)
    {
        token = Environment.GetEnvironmentVariable(tokenEnv);
        Enabled = enabled && !string.IsNullOrWhiteSpace(token);
    }

    // translate.php requires an explicit ISO language code: "auto" is rejected
    // by its PHP validator. Conservative lexical detection is intentionally
    // limited to the six site languages; uncertain messages skip Azure rather
    // than send an incorrect source language and corrupt retrieval.
    private static readonly (string Code, string[] Words)[] LanguageCues = {
        ("fr", new[] { "comment", "obtenir", "terrain", "gratuit", "gratuite",
            "bonjour", "puis", "dois", "pourquoi", "avec", "malédiction", "règles",
            "quelles", "quel", "une", "des", "vous", "je", "suis" }),
        ("en", new[] { "how", "can", "get", "free", "land", "plot", "where",
            "what", "does", "work", "please", "hello", "buy", "sell", "the",
            "with", "from", "are", "you" }),
        ("es", new[] { "cómo", "como", "puedo", "conseguir", "terreno", "gratis",
            "dónde", "donde", "quiero", "obtener", "maldición", "comprar",
            "vender", "los", "las", "una", "para" }),
        ("de", new[] { "wie", "bekomme", "kann", "ich", "kostenloses",
            "kostenlos", "grundstück", "grundstuck", "welche", "warum",
            "funktioniert", "fluch", "ein", "einen", "bitte", "und" }),
        ("it", new[] { "come", "ottenere", "posso", "terreno", "gratuito",
            "gratuita", "dove", "funziona", "maledizione", "acquistare",
            "vendere", "una", "per", "sono" }),
        ("pt", new[] { "como", "conseguir", "consigo", "terreno", "grátis",
            "gratis", "gratuito", "onde", "funciona", "maldição", "maldicao",
            "comprar", "vender", "uma", "para", "quero", "posso" })
    };

    public static string? DetectSourceLanguage(string text)
    {
        var words = Regex.Matches(text.ToLowerInvariant(), @"[\\p{L}]+")
            .Select(m => m.Value)
            .ToHashSet(StringComparer.Ordinal);
        if (words.Count == 0) return null;
        // One match is insufficient: proper nouns and shared cognates can
        // otherwise force a false positive.
        var scores = LanguageCues.Select(group => new {
            group.Code,
            Score = group.Words.Count(words.Contains)
        }).OrderByDescending(x => x.Score).ToArray();
        if (scores[0].Score < 2 || scores[0].Score <= scores[1].Score)
            return null;
        return scores[0].Code;
    }

    public static string? ReadTranslation(string json)
    {
        using var doc = JsonDocument.Parse(json);
        var root = doc.RootElement;
        if (!root.TryGetProperty("ok", out var ok) || ok.ValueKind != JsonValueKind.True ||
            !root.TryGetProperty("translatedText", out var translated) ||
            translated.ValueKind != JsonValueKind.String)
            return null;
        var text = translated.GetString()?.Trim();
        return text is { Length: >= 2 and <= 4000 } ? text : null;
    }

    public async Task<string?> ToFrenchForSearchAsync(string question, CancellationToken cancellation)
    {
        if (!Enabled || question.Length is < 3 or > 1000) return null;
        var sourceLanguage = DetectSourceLanguage(question);
        // French questions need no lookup translation. Unknown or mixed
        // language questions use the existing multilingual FTS path.
        if (sourceLanguage is null || sourceLanguage == "fr") return null;
        if (cache.TryGetValue(question, out var existing) &&
            DateTimeOffset.UtcNow - existing.saved < TimeSpan.FromMinutes(30))
            return existing.text;
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, Endpoint)
            {
                // Exact deployed PHP contract: explicit source code,
                // target "fr", text, plus X-BloodMoon-Token header.
                Content = JsonContent.Create(new { from = sourceLanguage, to = "fr", text = question })
            };
            request.Headers.TryAddWithoutValidation("X-BloodMoon-Token", token);
            using var response = await http.SendAsync(request,
                HttpCompletionOption.ResponseHeadersRead, cancellation);
            if (!response.IsSuccessStatusCode || response.Content.Headers.ContentLength > 16_384)
                return null;
            var payload = await response.Content.ReadAsStringAsync(cancellation);
            if (payload.Length > 16_384) return null;
            var translated = ReadTranslation(payload);
            if (translated is null) return null;
            if (cache.Count > 200) cache.Clear();
            cache[question] = (DateTimeOffset.UtcNow, translated);
            return translated;
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or
            JsonException or InvalidOperationException or IOException)
        {
            // Fail open: existing multilingual FTS expansion still works.
            // Never log gateway tokens, question text or private response bodies.
            return null;
        }
    }

    public void Dispose() => http.Dispose();
}
