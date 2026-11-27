using System.Diagnostics;

namespace OpenSimAiBridge;

/// <summary>
/// One monotonic deadline shared by all provider attempts for one IM.
/// A normal first answer keeps the existing 20-second timeout. In auto mode,
/// the total duration is bounded even when many profiles are configured.
/// No additional timer or background service is required.
/// </summary>
internal sealed class AiFallbackDeadline
{
    internal static readonly TimeSpan PerAttemptLimit = TimeSpan.FromSeconds(20);
    internal static readonly TimeSpan TotalAutoLimit = TimeSpan.FromSeconds(45);

    private readonly Stopwatch clock;
    private readonly TimeSpan total;

    internal AiFallbackDeadline(bool multiFallback)
    {
        total = multiFallback ? TotalAutoLimit : PerAttemptLimit;
        clock = Stopwatch.StartNew();
    }

    /// <summary>Returns zero when the total budget is exhausted.</summary>
    internal TimeSpan NextAttemptTimeout()
    {
        var remaining = total - clock.Elapsed;
        if (remaining <= TimeSpan.Zero) return TimeSpan.Zero;
        return remaining < PerAttemptLimit ? remaining : PerAttemptLimit;
    }

    internal bool Expired => clock.Elapsed >= total;

    // Pure helper for deterministic tests of a final, shortened attempt.
    internal static TimeSpan Limit(TimeSpan remaining)
    {
        if (remaining <= TimeSpan.Zero) return TimeSpan.Zero;
        return remaining < PerAttemptLimit ? remaining : PerAttemptLimit;
    }
}
