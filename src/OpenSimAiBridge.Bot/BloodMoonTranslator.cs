using System.Collections.Concurrent;
using System.Net.Http.Json;
using System.Text.Json;

namespace OpenSimAiBridge;

/// <summary>
/// Calls the dedicated BloodMoon AI translation gateway, backed by the same
/// existing Azure Translator subscription. Azure detects the input language.
/// The answer-generation model still sees the resident's ORIGINAL message.
/// </summary>
public sealed class BloodMoonTranslator : IDisposable
{
    private const string Endpoint = "https://bloodmoonpack.com/translator/ai-translate.php";
    private readonly HttpClient http = new() { Timeout = TimeSpan.FromSeconds(8) };
    private readonly ConcurrentDictionary<string, (DateTimeOffset saved, string text)> cache = new();
    private readonly string? token;
    public bool Enabled { get; }

    public BloodMoonTranslator(bool enabled, string tokenEnv)
    {
        token = Environment.GetEnvironmentVariable(tokenEnv);
        Enabled = enabled && !string.IsNullOrWhiteSpace(token);
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
        if (cache.TryGetValue(question, out var existing) &&
            DateTimeOffset.UtcNow - existing.saved < TimeSpan.FromMinutes(30))
            return existing.text;
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, Endpoint)
            {
                // Only the dedicated AI gateway accepts auto. The legacy
                // translate.php for in-world HUDs stays strictly unchanged.
                Content = JsonContent.Create(new { from = "auto", to = "fr", text = question })
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
            // Fail open to the existing multilingual FTS if Azure is unavailable.
            // Never log token, resident text or Azure response body.
            return null;
        }
    }

    public void Dispose() => http.Dispose();
}
