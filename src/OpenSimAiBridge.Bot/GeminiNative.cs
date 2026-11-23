using System.Text.Json;

namespace OpenSimAiBridge;

/// <summary>Google Gemini native generateContent request/response adapter.</summary>
public static class GeminiNative
{
    public static string Endpoint(string model) =>
        "https://generativelanguage.googleapis.com/v1beta/models/" +
        Uri.EscapeDataString(model) + ":generateContent";

    public static string Payload(IReadOnlyList<object> messages)
    {
        var contents = new List<object>();
        string? system = null;
        foreach (var message in messages)
        {
            var item = JsonSerializer.SerializeToElement(message);
            var role = item.GetProperty("role").GetString();
            var text = item.GetProperty("content").GetString() ?? "";
            if (role == "system")
            {
                system = text;
                continue;
            }
            contents.Add(new {
                role = role == "assistant" ? "model" : "user",
                parts = new[] { new { text } }
            });
        }
        return JsonSerializer.Serialize(new {
            contents,
            systemInstruction = new { parts = new[] { new { text = system ?? "" } } },
            generationConfig = new { maxOutputTokens = 2048, temperature = 0.4 }
        });
    }

    public static string? ReadText(JsonElement root)
    {
        if (!root.TryGetProperty("candidates", out var candidates) ||
            candidates.ValueKind != JsonValueKind.Array || candidates.GetArrayLength() == 0)
            return null;
        var candidate = candidates[0];
        if (!candidate.TryGetProperty("content", out var content) ||
            !content.TryGetProperty("parts", out var parts) ||
            parts.ValueKind != JsonValueKind.Array)
            return null;
        var texts = new List<string>();
        foreach (var part in parts.EnumerateArray())
        {
            if (part.TryGetProperty("text", out var text) && text.ValueKind == JsonValueKind.String)
                texts.Add(text.GetString() ?? "");
        }
        return string.Join("\n", texts).Trim();
    }
}
