using System.Text.RegularExpressions;
using System.Text;
using LibreMetaverse;

namespace OpenSimAiBridge;

/// <summary>
/// Full-precision avatar object snapshots drive a bounded, per-avatar welcome state machine.
/// No local AI inference, external API, IM, or sim-side script is required.
/// </summary>
public sealed class ProximityWelcomeOptions
{
    public bool Enabled { get; set; } = false;
    public bool FaceVisitor { get; set; } = false;
    public int RadiusMeters { get; set; } = 15;
    public int RepeatDelayMinutes { get; set; } = 30;
    public string Message { get; set; } =
        "Welcome to BloodMoon, {avatar_name}! I'm your AI assistant, here to answer questions about BloodMoon and its role-playing game. Please send me a private message (IM); I only answer questions via IM, not local chat.";
}

public sealed class ProximityWelcome
{
    private sealed class Visitor
    {
        public bool Inside;
        public DateTimeOffset? OutsideSince;
        public DateTimeOffset? LastWelcomed;
    }

    private readonly Dictionary<Guid, Visitor> visitors = new();
    private readonly object sync = new();
    private bool baselineEstablished;
    private DateTimeOffset lastPublicGreeting = DateTimeOffset.MinValue;
    private readonly ProximityWelcomeOptions settings;

    public ProximityWelcome(ProximityWelcomeOptions settings)
    {
        this.settings = settings;
    }

    public static bool Valid(ProximityWelcomeOptions settings) =>
        settings.RadiusMeters is >= 5 and <= 20 &&
        settings.RepeatDelayMinutes is >= 5 and <= 1440 &&
        !string.IsNullOrWhiteSpace(settings.Message) &&
        settings.Message.Length <= 650 && Encoding.UTF8.GetByteCount(settings.Message) <= 700 &&
        !settings.Message.Any(c => char.IsControl(c) && c is not '\n' and not '\r' and not '\t');

    public void ResetObservation()
    {
        lock (sync)
        {
            baselineEstablished = false;
            foreach (var visitor in visitors.Values)
            {
                visitor.Inside = false;
                visitor.OutsideSince = null;
            }
        }
    }

    /// <summary>Only full-resolution avatar positions from the current simulator are provided.</summary>
    public IReadOnlyList<Guid> Observe(
        DateTimeOffset now, Guid selfId, Vector3 selfPosition,
        IReadOnlyDictionary<UUID, Vector3> snapshot)
    {
        if (!settings.Enabled || !Valid(settings)) return Array.Empty<Guid>();
        lock (sync)
        {
            var seenInside = new HashSet<Guid>();
            var radiusSquared = settings.RadiusMeters * settings.RadiusMeters;
            foreach (var (id, pos) in snapshot)
            {
                var uuid = Guid.Parse(id.ToString());
                if (uuid == selfId || uuid == Guid.Empty) continue;
                // Welcome distance is horizontal. A separate vertical guard is
                // applied before turning, since rotation is visual only.
                var dx = pos.X - selfPosition.X;
                var dy = pos.Y - selfPosition.Y;
                if (dx * dx + dy * dy <= radiusSquared)
                    seenInside.Add(uuid);
            }

            if (!baselineEstablished)
            {
                baselineEstablished = true;
                foreach (var id in seenInside)
                {
                    if (!visitors.TryGetValue(id, out var visitor))
                        visitors[id] = visitor = new Visitor();
                    visitor.Inside = true;
                    visitor.OutsideSince = null;
                }
                return Array.Empty<Guid>(); // Never greet everyone on first snapshot.
            }

            var ready = new List<Guid>();
            foreach (var (id, visitor) in visitors)
            {
                if (seenInside.Contains(id))
                {
                    visitor.OutsideSince = null;
                    continue;
                }
                if (visitor.Inside)
                {
                    visitor.OutsideSince ??= now;
                    // Do not interpret one dropped packet as a real exit.
                    if (now - visitor.OutsideSince >= TimeSpan.FromSeconds(30))
                        visitor.Inside = false;
                }
            }

            foreach (var id in seenInside)
            {
                if (!visitors.TryGetValue(id, out var visitor))
                    visitors[id] = visitor = new Visitor();
                if (visitor.Inside) continue;
                // A visitor who left for fewer than 30 seconds still counts as present.
                if (visitor.OutsideSince is not null && now - visitor.OutsideSince < TimeSpan.FromSeconds(30))
                    continue;
                if (visitor.LastWelcomed is not null &&
                    now - visitor.LastWelcomed < TimeSpan.FromMinutes(settings.RepeatDelayMinutes))
                {
                    // Already welcomed recently: consider present, but stay silent.
                    visitor.Inside = true;
                    visitor.OutsideSince = null;
                    continue;
                }
                if (now - lastPublicGreeting < TimeSpan.FromSeconds(8))
                {
                    // Do not lose a new arrival during the public-chat rate limit:
                    // retry at the next simulator location snapshot.
                    continue;
                }
                visitor.Inside = true;
                visitor.OutsideSince = null;
                visitor.LastWelcomed = now;
                lastPublicGreeting = now;
                ready.Add(id);
            }

            // Avoid unbounded state growth when lots of avatars visit over time.
            foreach (var id in visitors.Where(x => !x.Value.Inside &&
                         (x.Value.LastWelcomed is null || now - x.Value.LastWelcomed >
                           TimeSpan.FromMinutes(settings.RepeatDelayMinutes)) &&
                         x.Value.OutsideSince is not null &&
                         now - x.Value.OutsideSince >= TimeSpan.FromMinutes(60))
                        .Select(x => x.Key).ToArray())
                visitors.Remove(id);
            return ready;
        }
    }

    public static string FormatMessage(string template, string? name)
    {
        // Other residents control their names. Never let one inject a new
        // chat line or formatting through the placeholder.
        var cleanName = Regex.Replace(name ?? "", @"[\p{Cc}\p{Cf}\r\n\t]+", " ").Trim();
        if (cleanName.Length > 60) cleanName = cleanName[..60].TrimEnd();
        if (cleanName.Length == 0)
            return Regex.Replace(template, @"\s*,?\s*\{avatar_name\}", "", RegexOptions.IgnoreCase)
                .Replace("  ", " ").Trim();
        return template.Replace("{avatar_name}", cleanName, StringComparison.OrdinalIgnoreCase).Trim();
    }
}
