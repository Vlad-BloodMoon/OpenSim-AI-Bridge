using System.Text;
using System.Text.RegularExpressions;

namespace OpenSimAiBridge;

/// <summary>
/// Converts model Markdown into plain text for OpenSimulator IM and splits
/// replies at safe UTF-8 boundaries, preserving all the returned content.
/// </summary>
public static class ImReplyFormatter
{
    private const int MaxBytes = 600;
    private const int MaxParts = 16;

    public static string PlainText(string text)
    {
        if (string.IsNullOrWhiteSpace(text)) return "";
        text = text.Replace("\r\n", "\n").Replace('\r', '\n');
        // Firestorm IM doesn't render Markdown tables. Preserve each table row
        // as a readable sentence rather than transmitting table delimiters.
        var lines = new List<string>();
        foreach (var original in text.Split('\n'))
        {
            var line = original.Trim();
            if (Regex.IsMatch(line, @"^\|?\s*:?[-]{3,}:?\s*\|")) continue;
            if (line.Contains('|') && line.Count(c => c == '|') >= 2)
            {
                line = string.Join(" — ", line.Trim('|').Split('|')
                    .Select(p => p.Trim()).Where(p => p.Length > 0));
            }
            line = Regex.Replace(line, @"\[([^\]]+)\]\((https?://[^\s)]+)\)", "$1 ($2)");
            line = line.Replace("**", "").Replace("__", "").Replace("［", "[");
            line = Regex.Replace(line, @"^#{1,6}\s+", "");
            line = Regex.Replace(line, @"^[-*]\s+", "• ");
            if (line.Length > 0) lines.Add(line);
        }
        return string.Join("\n", lines).Trim();
    }

    public static IReadOnlyList<string> Split(string response)
    {
        var text = PlainText(response);
        if (text.Length == 0) return Array.Empty<string>();
        var parts = new List<string>();
        // Reserve 9 bytes for a compact "1/16" sequence marker.
        var limit = MaxBytes - 12;
        while (text.Length > 0 && parts.Count < MaxParts)
        {
            if (Encoding.UTF8.GetByteCount(text) <= limit)
            {
                parts.Add(text.Trim());
                text = "";
                break;
            }

            var length = 0;
            var bytes = 0;
            foreach (var rune in text.EnumerateRunes())
            {
                var size = rune.Utf8SequenceLength;
                if (bytes + size > limit) break;
                bytes += size;
                length += rune.Utf16SequenceLength;
            }
            if (length == 0) break;

            // Split on sentence/paragraph boundaries first, then spaces.
            var split = text.LastIndexOfAny(new[] { '\n', '.', '!', '?', ' ' }, length - 1, length);
            if (split < length / 2) split = length;
            else if (text[split] == '.' || text[split] == '!' || text[split] == '?') split++;

            var chunk = text[..split].Trim();
            if (chunk.Length == 0) { split = length; chunk = text[..split]; }
            parts.Add(chunk);
            text = text[split..].TrimStart();
        }
        if (text.Length > 0 && parts.Count == MaxParts)
            parts.Add("La réponse est trop longue pour être envoyée intégralement. Pose une question plus précise.");
        if (parts.Count <= 1) return parts;
        return parts.Select((part, index) => $"({index + 1}/{parts.Count}) {part}").ToArray();
    }
}
