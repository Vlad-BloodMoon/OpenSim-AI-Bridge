using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace OpenSimAiBridge;

public sealed class RemoteAiProfile
{
    public string Id { get; set; } = "";
    public string Provider { get; set; } = "";
    public string Model { get; set; } = "";
    public string ApiKeyEnv { get; set; } = "";
    public bool Enabled { get; set; }
    public bool Verified { get; set; }
}

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
    public string SystemPrompt { get; set; } = "Tu es un assistant BloodMoon. Réponds dans la langue du résident, sans inventer.";
    public string Mode { get; set; } = "auto";
    public List<RemoteAiProfile> Profiles { get; set; } = new();
}

/// <summary>Remote IM assistant with public-safe provider fallback and short isolated memory.</summary>
public sealed class RemoteAiResponder : IDisposable
{
    private static readonly IReadOnlyDictionary<string, string> Endpoints =
        new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["OpenAI"] = "https://api.openai.com/v1/chat/completions",
            ["Groq"] = "https://api.groq.com/openai/v1/chat/completions",
            ["OpenRouter"] = "https://openrouter.ai/api/v1/chat/completions",
            ["Gemini"] = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        };

    private readonly HttpClient client = new() { Timeout = TimeSpan.FromSeconds(20) };
    private readonly RemoteAiSettings settings;
    private readonly string? legacyKey;
    private readonly HashSet<Guid> authorized;
    private readonly ConcurrentDictionary<Guid, DateTimeOffset> lastUserRequest = new();
    private readonly ConcurrentDictionary<Guid, (DateTimeOffset timestamp, List<(string question, string answer)> turns)> memory = new();
    private readonly ConcurrentDictionary<string, DateTimeOffset> unavailableUntil = new(StringComparer.Ordinal);
    private readonly object sync = new();
    private readonly AiRequestGate requestGate = new();
    private readonly KnowledgeSearch knowledge;
    private readonly SharedProviderQuota sharedQuota;
    private DateTimeOffset hourStart = DateTimeOffset.UtcNow;
    private int usedThisHour;

    public RemoteAiResponder(RemoteAiSettings settings)
    {
        this.settings = settings;
        knowledge = new KnowledgeSearch(KnowledgeSearch.DefaultPath());
        sharedQuota = new SharedProviderQuota(SharedProviderQuota.DefaultPath());
        authorized = new HashSet<Guid>(settings.AuthorizedUuidList.Where(s => Guid.TryParse(s, out _)).Select(Guid.Parse));
        legacyKey = Environment.GetEnvironmentVariable(settings.ApiKeyEnv);
    }

    // Legacy mode deliberately retains its original Groq-only public authorization.
    private bool Multi => settings.Profiles is { Count: > 0 };

    private static bool SafePublicModel(RemoteAiProfile p) =>
        p.Provider == "Groq" ||
        (p.Provider == "OpenRouter" &&
            (p.Model == "openrouter/free" || p.Model.EndsWith(":free", StringComparison.Ordinal))) ||
        (p.Provider == "Gemini" &&
            (p.Model is "gemini-3-flash-preview" or "gemini-3.5-flash-lite" or "gemini-3.1-flash-lite"));

    private static bool ValidProfile(RemoteAiProfile p) =>
        p.Enabled && p.Verified && SafePublicModel(p) &&
        Endpoints.ContainsKey(p.Provider) && p.Model.Length is >= 1 and <= 100 &&
        !string.IsNullOrWhiteSpace(p.ApiKeyEnv) &&
        !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable(p.ApiKeyEnv));

    private bool ValidSettings =>
        settings.MaxRequestsPerHour is >= 1 and <= 120 &&
        settings.MinSecondsBetweenRequests is >= 5 and <= 3600 &&
        settings.SystemPrompt.Length <= 1200;

    public bool Ready => settings.Enabled && ValidSettings &&
        (Multi ? settings.Mode is "single" or "auto" && settings.Profiles.Any(ValidProfile) :
            Endpoints.ContainsKey(settings.Provider) &&
            !string.IsNullOrWhiteSpace(legacyKey) &&
            (authorized.Count > 0 || (settings.PublicAccess && settings.Provider == "Groq")) &&
            settings.Model.Length is >= 1 and <= 100);

    public bool IsAuthorized(Guid sender) => Ready &&
        (Multi || authorized.Contains(sender) || (settings.PublicAccess && settings.Provider == "Groq"));

    private IReadOnlyList<RemoteAiProfile> Candidates()
    {
        if (Multi)
        {
            var candidates = settings.Profiles.Where(ValidProfile).Take(16).ToArray();
            return settings.Mode == "single" ? candidates.Take(1).ToArray() : candidates;
        }
        return new[] { new RemoteAiProfile {
            Id = "legacy", Provider = settings.Provider, Model = settings.Model,
            Enabled = true, Verified = true, ApiKeyEnv = settings.ApiKeyEnv
        } };
    }

    private List<(string question, string answer)> PreviousTurns(Guid sender, DateTimeOffset now)
    {
        lock (sync)
        {
            if (memory.TryGetValue(sender, out var state) && now - state.timestamp < TimeSpan.FromMinutes(30))
                return state.turns.TakeLast(6).ToList();
            memory.TryRemove(sender, out _);
            return new();
        }
    }

    private void Remember(Guid sender, DateTimeOffset now, string question, string answer)
    {
        lock (sync)
        {
            var turns = PreviousTurns(sender, now);
            turns.Add((question[..Math.Min(700, question.Length)], answer[..Math.Min(600, answer.Length)]));
            memory[sender] = (now, turns.TakeLast(6).ToList());
            // Limit resident state indefinitely growing with unique callers.
            if (memory.Count > 300)
                foreach (var key in memory.Keys.Take(memory.Count - 300))
                    memory.TryRemove(key, out _);
        }
    }

    private static string SwitchNotice(string question)
    {
        // A small, deterministic dictionary avoids spending a second API call
        // just to translate a provider-change notice.
        if (question.Any(c => "¿¡ñ".Contains(c))) return "🔄 Continúo con otro motor de IA.\n";
        if (question.Any(c => "äöüß".Contains(c))) return "🔄 Ich setze mit einem anderen KI-Dienst fort.\n";
        if (question.Any(c => "àâçéèêëîïôùûœ".Contains(c))) return "🔄 Je poursuis avec un autre moteur IA.\n";
        return "🔄 Continuing with another AI provider.\n";
    }

    public async Task<string?> ReplyAsync(Guid sender, string prompt, CancellationToken cancellationToken)
    {
        if (!IsAuthorized(sender) || string.IsNullOrWhiteSpace(prompt)) return null;
        if (prompt.Length > 1000) return "Ton message est trop long (maximum 1000 caractères).";
        if (!requestGate.TryAcquire(sender, out var lease, out var sameSender))
            return sameSender
                ? "Je traite déjà ta question. Attends ma réponse avant d'en envoyer une autre."
                : "Plusieurs résidents me parlent déjà. Réessaie dans quelques instants.";
        using (lease)
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
                if (lastUserRequest.TryGetValue(sender, out var previous) &&
                    now - previous < TimeSpan.FromSeconds(settings.MinSecondsBetweenRequests))
                    return "Attends quelques secondes avant une nouvelle question.";
                lastUserRequest[sender] = now;
                usedThisHour++;
            }

            var hits = knowledge.Search(prompt);
            var context = KnowledgeSearch.BuildContext(hits);
            var history = PreviousTurns(sender, now);
            var messages = new List<object> { new { role = "system", content =
                settings.SystemPrompt +
                "\\nRéponds en texte brut lisible dans les messages privés OpenSimulator/Firestorm. " +
                "N'utilise jamais de tableaux Markdown, ni de blocs de code, ni de titres Markdown. " +
                "Privilégie quelques paragraphes courts ou une liste simple. " +
                "Réponds précisément et complètement, dans la langue du résident. " +
                "Cite une URL source uniquement lorsque c'est utile. " } };
            if (Multi)
            {
                foreach (var (question, answer) in history)
                {
                    messages.Add(new { role = "user", content = question });
                    messages.Add(new { role = "assistant", content = answer });
                }
            }
            messages.Add(new { role = "user", content =
                string.IsNullOrEmpty(context) ? prompt : $"Question du résident : {prompt}\n\n{context}" });

            var switched = false;
            foreach (var profile in Candidates())
            {
                if (unavailableUntil.TryGetValue(profile.Id, out var until) && until > now)
                {
                    switched = true;
                    continue;
                }

                var key = Environment.GetEnvironmentVariable(profile.ApiKeyEnv);
                if (string.IsNullOrWhiteSpace(key) || !Endpoints.TryGetValue(profile.Provider, out var endpoint))
                    continue;

                // Multi-avatar admission is shared by provider, never by avatar.
                // A provider's local budget/cooldown does NOT stop the conversation:
                // in auto mode the next eligible provider is tried immediately.
                if (Multi && !sharedQuota.TryReserve(profile.Provider, now,
                    Math.Min(settings.MaxRequestsPerHour, SharedProviderQuota.MaxAttemptsPerProviderHour),
                    out _))
                {
                    switched = true;
                    continue;
                }

                try
                {
                    var gemini = profile.Provider == "Gemini";
                    var destination = gemini ? GeminiNative.Endpoint(profile.Model) : endpoint;
                    using var request = new HttpRequestMessage(HttpMethod.Post, destination);
                    if (gemini)
                        request.Headers.TryAddWithoutValidation("x-goog-api-key", key);
                    else
                        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", key);
                    var json = gemini ? GeminiNative.Payload(messages) :
                        JsonSerializer.Serialize(new { model = profile.Model, messages,
                                                       max_tokens = 900, temperature = 0.4 });
                    request.Content = new StringContent(json, Encoding.UTF8, "application/json");
                    using var response = await client.SendAsync(request, cancellationToken).ConfigureAwait(false);
                    if (response.StatusCode == HttpStatusCode.TooManyRequests ||
                        response.StatusCode is HttpStatusCode.ServiceUnavailable or HttpStatusCode.BadGateway or HttpStatusCode.GatewayTimeout ||
                        (int)response.StatusCode >= 500)
                    {
                        var retry = response.Headers.RetryAfter?.Delta ?? TimeSpan.FromMinutes(3);
                        var boundedRetry = retry > TimeSpan.FromHours(1) ? TimeSpan.FromHours(1) : retry;
                        unavailableUntil[profile.Id] = now + boundedRetry;
                        // A 503/429 can be specific to one model. Keep other models eligible.
                        switched = true;
                        continue;
                    }
                    if (!response.IsSuccessStatusCode)
                    {
                        // 4xx is often an invalid key or model; do not retry automatically.
                        unavailableUntil[profile.Id] = now + TimeSpan.FromMinutes(15);
                        // Invalid model/key may be profile-specific: do not block other models.
                        switched = true;
                        continue;
                    }
                    using var stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
                    using var doc = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
                    var reply = gemini ? GeminiNative.ReadText(doc.RootElement) :
                        doc.RootElement.GetProperty("choices")[0]
                            .GetProperty("message").GetProperty("content").GetString()?.Trim();
                    if (string.IsNullOrEmpty(reply))
                    {
                        switched = true;
                        continue;
                    }
                    // Preserve the complete model response; the IM transport splits it safely.
                    Remember(sender, now, prompt, reply);
                    // Never disclose provider/API keys in resident messages.
                    return (switched && Multi ? SwitchNotice(prompt) : "") + reply;
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { return null; }
                catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or JsonException or InvalidOperationException or KeyNotFoundException)
                {
                    unavailableUntil[profile.Id] = now + TimeSpan.FromMinutes(3);
                    // Transport error for this model does not disable its provider.
                    switched = true;
                }
            }
            return "Les moteurs IA configurés sont temporairement indisponibles. Réessaie plus tard.";
        }
    }

    public void Dispose()
    {
        requestGate.Dispose();
        client.Dispose();
    }
}
