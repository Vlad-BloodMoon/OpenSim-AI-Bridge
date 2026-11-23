using Microsoft.Data.Sqlite;

namespace OpenSimAiBridge;

/// <summary>
/// Shared, persistent admission control across ALL avatars using one credentials pool.
/// A reservation is consumed BEFORE contacting a remote provider, including failed calls.
/// Each provider has a separate hourly budget and cooldown. No background tasks.
/// </summary>
public sealed class SharedProviderQuota
{
    public const int MaxAttemptsPerProviderHour = 30;
    private readonly string databasePath;
    private readonly object localLock = new();

    public SharedProviderQuota(string databasePath) => this.databasePath = databasePath;

    public static string DefaultPath()
    {
        var install = Environment.GetEnvironmentVariable("OSAI_INSTALL_DIR");
        if (string.IsNullOrWhiteSpace(install))
            install = AppContext.BaseDirectory;
        return Path.Combine(install, "data", "ai-provider-quotas.db");
    }

    public bool TryReserve(string provider, DateTimeOffset now, int maxPerHour, out string reason)
    {
        reason = "unavailable";
        if (provider is not ("Groq" or "OpenRouter" or "Gemini" or "OpenAI") || maxPerHour is < 1 or > 120)
            return false;
        // Avoid creating an SQLite file in an unexpected directory.
        if (!Directory.Exists(Path.GetDirectoryName(databasePath)))
            return false;
        try
        {
            lock (localLock)
            {
                using var conn = Connect();
                using var tx = conn.BeginTransaction(System.Data.IsolationLevel.Serializable);
                var epoch = now.ToUnixTimeSeconds();
                var hour = epoch / 3600;
                using (var create = conn.CreateCommand())
                {
                    create.Transaction = tx;
                    create.CommandText = """
                        CREATE TABLE IF NOT EXISTS provider_budget (
                            provider TEXT PRIMARY KEY,
                            hour_bucket INTEGER NOT NULL,
                            attempts INTEGER NOT NULL,
                            cooldown_until INTEGER NOT NULL DEFAULT 0
                        );
                        """;
                    create.ExecuteNonQuery();
                }
                long lastHour = -1;
                long attempts = 0;
                long cooldown = 0;
                using (var read = conn.CreateCommand())
                {
                    read.Transaction = tx;
                    read.CommandText = "SELECT hour_bucket,attempts,cooldown_until FROM provider_budget WHERE provider=$p";
                    read.Parameters.AddWithValue("$p", provider);
                    using var reader = read.ExecuteReader();
                    if (reader.Read())
                    {
                        lastHour = reader.GetInt64(0);
                        attempts = reader.GetInt64(1);
                        cooldown = reader.GetInt64(2);
                    }
                }
                if (cooldown > epoch)
                {
                    reason = "cooldown";
                    tx.Commit();
                    return false;
                }
                if (lastHour != hour) attempts = 0;
                if (attempts >= maxPerHour)
                {
                    reason = "hourly-limit";
                    tx.Commit();
                    return false;
                }
                using var write = conn.CreateCommand();
                write.Transaction = tx;
                write.CommandText = """
                    INSERT INTO provider_budget(provider,hour_bucket,attempts,cooldown_until)
                    VALUES($p,$h,$n,$c)
                    ON CONFLICT(provider) DO UPDATE SET
                        hour_bucket=excluded.hour_bucket,
                        attempts=excluded.attempts,
                        cooldown_until=excluded.cooldown_until
                    """;
                write.Parameters.AddWithValue("$p", provider);
                write.Parameters.AddWithValue("$h", hour);
                write.Parameters.AddWithValue("$n", attempts + 1);
                write.Parameters.AddWithValue("$c", cooldown > epoch ? cooldown : 0);
                write.ExecuteNonQuery();
                tx.Commit();
                reason = "reserved";
                return true;
            }
        }
        catch (Exception ex) when (ex is SqliteException or IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            // Fail closed on unavailable shared quota store: never exceed a provider cap.
            return false;
        }
    }

    public void RecordCooldown(string provider, DateTimeOffset now, TimeSpan duration)
    {
        if (provider is not ("Groq" or "OpenRouter" or "OpenAI")) return;
        var seconds = Math.Clamp((long)Math.Ceiling(duration.TotalSeconds), 60, 3600);
        try
        {
            lock (localLock)
            {
                using var conn = Connect();
                // A failed request should already have initialized the row via TryReserve.
                using var update = conn.CreateCommand();
                update.CommandText = """
                    UPDATE provider_budget
                    SET cooldown_until=MAX(cooldown_until,$until)
                    WHERE provider=$provider
                    """;
                update.Parameters.AddWithValue("$provider", provider);
                update.Parameters.AddWithValue("$until", now.ToUnixTimeSeconds() + seconds);
                update.ExecuteNonQuery();
            }
        }
        catch (Exception ex) when (ex is SqliteException or IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            // Future calls fail closed on inaccessible store.
        }
    }

    private SqliteConnection Connect()
    {
        var conn = new SqliteConnection(new SqliteConnectionStringBuilder {
            DataSource = databasePath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Pooling = false,
            DefaultTimeout = 5,
        }.ToString());
        conn.Open();
        return conn;
    }
}
