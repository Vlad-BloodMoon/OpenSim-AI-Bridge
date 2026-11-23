using System.Collections.Concurrent;
using System.Net.Http.Headers;
using System.Net;
using System.Text;
using System.Text.Json;

namespace OpenSimAiBridge;

/// <summary>Opt-in remote IM assistant. No local language model or public-chat AI calls.</summary>
public sealed class RemoteAiSettings
{
    public bool Enabled { get; set; } = false;
    public string Provider { get; set; } = "OpenAI";
    public string Model { get; set; } = "gpt-4.1-mini";
    public string ApiKeyEnv { get; set; } = "OSAI_AI_API_KEY";
    public List<string> AuthorizedUuidList { get; set; } = new();
    public bool PublicAccess { get; set; } = false;
    public int MaxRequestsPerHour { get; set; } = 30;
    public int MinSecondsBetweenRequests { get; set; } = 15;
    public string SystemPrompt { get; set; } = "Tu es un assistant de la grille OpenSimulator BloodMoon. Réponds avec concision, dans la langue du message. N'invente ni actions ni données de la grille.";
}

public sealed class RemoteAiResponder : IDisposable
{
    private static readonly IReadOnlyDictionary<string, string> Endpoints =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["OpenAI"] = "https://api.openai.com/v1/chat/completions",
            ["Groq"] = "https://api.groq.com/openai/v1/chat/completions",
            ["OpenRouter"] = "https://openrouter.ai/api/v1/chat/completions",
        };

    private readonly HttpClient client = new() { Timeout = TimeSpan.FromSeconds(20) };
    private readonly RemoteAiSettings settings;
    private readonly string? apiKey;
    private readonly HashSet<Guid> authorized;
    private readonly ConcurrentDictionary<Guid, DateTimeOffset> lastUserRequest = new();
    private readonly object sync = new();
    private readonly SemaphoreSlim concurrency = new(1, 1);
    private DateTimeOffset hourStart = DateTimeOffset.UtcNow;
    private int usedThisHour;
    private readonly Uri? endpoint;

    public RemoteAiResponder(RemoteAiSettings settings)
    {
        this.settings = settings;
        authorized = new HashSet<Guid>(settings.AuthorizedUuidList.Where(s => Guid.TryParse(s, out _)).Select(Guid.Parse));
        apiKey = Environment.GetEnvironmentVariable(settings.ApiKeyEnv);
        if (Endpoints.TryGetValue(settings.Provider, out string? url))
            endpoint = new Uri(url);
    }

    public bool Ready => settings.Enabled && endpoint is not null &&
        !string.IsNullOrWhiteSpace(apiKey) && (authorized.Count != 0 || (settings.PublicAccess && string.Equals(settings.Provider, "Groq", StringComparison.OrdinalIgnoreCase))) &&
        settings.MaxRequestsPerHour is >= 1 and <= 120 &&
        settings.MinSecondsBetweenRequests is >= 5 and <= 3600 &&
        settings.Model.Length is >= 1 and <= 100 &&
        settings.SystemPrompt.Length <= 1200;

    public bool IsAuthorized(Guid sender) => Ready && (authorized.Contains(sender) || (settings.PublicAccess && string.Equals(settings.Provider, "Groq", StringComparison.OrdinalIgnoreCase)));

    public async Task<string?> ReplyAsync(Guid sender, string prompt, CancellationToken cancellationToken)
    {
        if (!IsAuthorized(sender) || string.IsNullOrWhiteSpace(prompt))
            return null;
        if (prompt.Length > 1000)
            return "Ton message est trop long (maximum 1000 caractères).";

        if (!await concurrency.WaitAsync(0, cancellationToken).ConfigureAwait(false))
            return "Je traite déjà une demande. Réessaie dans quelques instants.";

        try
        {
            var now = DateTimeOffset.UtcNow;
            lock (sync)
            {
                if (now - hourStart >= TimeSpan.FromHours(1))
                {
                    hourStart = now;
                    usedThisHour = 0;
                }
                if (usedThisHour >= settings.MaxRequestsPerHour)
                    return "La limite horaire de demandes IA est atteinte.";
                if (lastUserRequest.TryGetValue(sender, out var last) &&
                    now - last < TimeSpan.FromSeconds(settings.MinSecondsBetweenRequests))
                    return "Attends quelques secondes avant une nouvelle question.";
                // Count before the request, including failures, so upstream errors cannot trigger storms.
                lastUserRequest[sender] = now;
                usedThisHour++;
            }

            var payload = new
            {
                model = settings.Model,
                messages = new[]
                {
                    new { role = "system", content = settings.SystemPrompt },
                    new { role = "user", content = prompt }
                },
                max_tokens = 250,
                temperature = 0.5
            };
            using var request = new HttpRequestMessage(HttpMethod.Post, endpoint);
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiKey);
            request.Content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
            using var response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
            if (response.StatusCode == HttpStatusCode.TooManyRequests)
                return "Le fournisseur IA est temporairement limité. Réessaie plus tard.";
            if (!response.IsSuccessStatusCode)
                return "Le fournisseur IA ne répond pas correctement pour le moment.";

            using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
            using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
            var result = doc.RootElement.GetProperty("choices")[0].GetProperty("message").GetProperty("content").GetString();
            if (string.IsNullOrWhiteSpace(result))
                return "Je n'ai pas de réponse pour le moment.";
            result = result.Trim();
            return result.Length > 600 ? result[..600] + "…" : result;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { return null; }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or KeyNotFoundException or InvalidOperationException)
        {
            // No raw HTTP bodies or credentials in logs.
            return "Le service IA est temporairement indisponible.";
        }
        finally
        {
            concurrency.Release();
        }
    }

    public void Dispose()
    {
        concurrency.Dispose();
        client.Dispose();
    }
}
