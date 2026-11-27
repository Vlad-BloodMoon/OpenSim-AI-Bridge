using System.Net;
using System.Net.Http.Headers;

namespace OpenSimAiBridge;

/// <summary>
/// Classifies remote API failures without persisting response bodies or credentials.
/// All fallback decisions use the same bounded policy in manual/auto routing.
/// </summary>
internal static class ProviderFailurePolicy
{
    internal readonly record struct Decision(string Category, TimeSpan Cooldown, bool ShareWithOtherAvatars);

    internal static bool RequiresFallback(HttpStatusCode status) =>
        status == HttpStatusCode.TooManyRequests ||
        status == HttpStatusCode.RequestTimeout ||
        (int)status >= 500;

    internal static Decision Classify(HttpResponseMessage response, DateTimeOffset observedAt,
                                      string? limitedErrorBody = null)
    {
        var status = response.StatusCode;
        if (status == HttpStatusCode.TooManyRequests)
        {
            // Body is inspected only in-memory for a bounded classification hint.
            // No body is written to logs or exposed in the admin API.
            var daily = !string.IsNullOrEmpty(limitedErrorBody) &&
                        (limitedErrorBody.Contains("per day", StringComparison.OrdinalIgnoreCase) ||
                         limitedErrorBody.Contains("daily quota", StringComparison.OrdinalIgnoreCase) ||
                         limitedErrorBody.Contains("requests per day", StringComparison.OrdinalIgnoreCase) ||
                         limitedErrorBody.Contains("RPD", StringComparison.OrdinalIgnoreCase));
            var fallback = daily ? TimeSpan.FromMinutes(30) : TimeSpan.FromMinutes(3);
            return new(daily ? "daily_quota" : "rate_limit",
                       RetryDelay(response.Headers.RetryAfter, observedAt, fallback), true);
        }
        if (status == HttpStatusCode.RequestTimeout || (int)status >= 500)
            return new(status == HttpStatusCode.RequestTimeout ? "timeout" : "provider_unavailable",
                       RetryDelay(response.Headers.RetryAfter, observedAt, TimeSpan.FromMinutes(3)), true);
        if (status is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden)
            return new("auth_failed", TimeSpan.FromMinutes(15), false);
        if (status == HttpStatusCode.NotFound)
            return new("model_unavailable", TimeSpan.FromMinutes(15), false);
        return new("http_error", TimeSpan.FromMinutes(15), false);
    }

    internal static TimeSpan RetryDelay(RetryConditionHeaderValue? retryAfter, DateTimeOffset now,
                                        TimeSpan fallback)
    {
        // Retry-After is either delay-seconds OR an HTTP-date; a date is not
        // an absolute duration. Invalid/past values must not create a busy loop.
        var desired = retryAfter?.Delta ??
                      (retryAfter?.Date is { } date ? date - now : fallback);
        if (desired <= TimeSpan.Zero) desired = fallback;
        return desired > TimeSpan.FromHours(24) ? TimeSpan.FromHours(24) : desired;
    }
}
