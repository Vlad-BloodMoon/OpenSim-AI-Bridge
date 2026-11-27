using System.Net;
using System.Text;
using System.Text.Json;

namespace OpenSimAiBridge;

/// <summary>
/// Full responder regression using an in-memory HTTP transport and private
/// temporary SQLite files. No HTTP requests can escape the test process.
/// </summary>
internal static class AiFallbackIntegrationChecks
{
    private sealed class FakeHttp : HttpMessageHandler
    {
        private readonly Queue<Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>>> replies = new();
        internal readonly List<string> CalledProviders = new();

        internal void Add(HttpStatusCode status, string body = "")
        {
            replies.Enqueue((_, _) => Task.FromResult(new HttpResponseMessage(status) {
                Content = new StringContent(body, Encoding.UTF8, "application/json")
            }));
        }

        internal void Timeout()
        {
            replies.Enqueue((_, _) => throw new TaskCanceledException("simulated timeout"));
        }

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            var host = request.RequestUri?.Host ?? "";
            var provider = host switch {
                "api.groq.com" => "Groq",
                "openrouter.ai" => "OpenRouter",
                "generativelanguage.googleapis.com" => "Gemini",
                _ => throw new InvalidOperationException("Unexpected outbound request; the mock forbids it.")
            };
            CalledProviders.Add(provider);
            if (replies.Count == 0)
                throw new InvalidOperationException("Unexpected provider request: " + provider);
            return await replies.Dequeue()(request, cancellationToken).ConfigureAwait(false);
        }
    }

    private static RemoteAiSettings Settings(bool automatic = true)
    {
        return new RemoteAiSettings {
            Enabled = true,
            PublicAccess = true,
            MaxRequestsPerHour = 30,
            MinSecondsBetweenRequests = 5,
            Mode = automatic ? "auto" : "single",
            Profiles = new List<RemoteAiProfile> {
                new() { Id = "test-groq", Provider = "Groq", Model = "openai/gpt-oss-20b",
                        Enabled = true, Verified = true, ApiKeyEnv = "OSAI_FAKE_FALLBACK_KEY" },
                new() { Id = "test-router", Provider = "OpenRouter", Model = "test-model:free",
                        Enabled = true, Verified = true, ApiKeyEnv = "OSAI_FAKE_FALLBACK_KEY" },
                new() { Id = "test-gemini", Provider = "Gemini", Model = "gemini-3.5-flash-lite",
                        Enabled = true, Verified = true, ApiKeyEnv = "OSAI_FAKE_FALLBACK_KEY" }
            }
        };
    }

    private static readonly string OpenAiAnswer =
        """{"choices":[{"message":{"content":"Test answer from approved model."}}]}""";
    private static readonly string GeminiAnswer =
        """{"candidates":[{"content":{"parts":[{"text":"Gemini backup answered."}]}}]}""";

    private static List<JsonElement> Events(string path)
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        return doc.RootElement.EnumerateArray().Select(x => x.Clone()).ToList();
    }

    private static void Assert(bool ok, string message)
    {
        if (!ok) throw new InvalidOperationException("Fake provider test: " + message);
    }

    internal static async Task RunAsync()
    {
        var old = Environment.GetEnvironmentVariable("OSAI_FAKE_FALLBACK_KEY");
        var dir = Path.Combine(Path.GetTempPath(), "osai-fallback-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        Environment.SetEnvironmentVariable("OSAI_FAKE_FALLBACK_KEY", "not-a-real-key-for-offline-tests");
        try
        {
            // 429 → 503 → Gemini success, with correct order and per-avatar
            // event sequence. Same message used by the normal production code.
            var fake = new FakeHttp();
            fake.Add(HttpStatusCode.TooManyRequests, "rate limit exceeded");
            fake.Add(HttpStatusCode.ServiceUnavailable);
            fake.Add(HttpStatusCode.OK, GeminiAnswer);
            var log = Path.Combine(dir, "primary.json");
            var db = Path.Combine(dir, "shared.db");
            using (var bot = new RemoteAiResponder(Settings(), log, fake, db))
            {
                var answer = await bot.ReplyAsync(Guid.NewGuid(), "Where is the welcome region?", CancellationToken.None);
                Assert(answer?.Contains("Gemini backup answered.") == true, "third provider must answer");
                Assert(answer!.Contains("Continuing with another AI provider."), "fallback notice expected");
            }
            Assert(fake.CalledProviders.SequenceEqual(new[] {"Groq","OpenRouter","Gemini"}), "exact 429/503/success order");
            var events = Events(log);
            Assert(events.Count == 3, "exactly three audited attempts");
            Assert(events[0].GetProperty("reason").GetString() == "rate_limit", "429 classification");
            Assert(events[1].GetProperty("reason").GetString() == "provider_unavailable", "503 classification");
            Assert(events[2].GetProperty("outcome").GetString() == "success" &&
                   events[2].GetProperty("switched").GetBoolean(), "third success must register fallback");
            Assert(events.All(x => !x.TryGetProperty("prompt", out _) &&
                                   !x.TryGetProperty("apiKey", out _)), "no resident message or key in audit");
            Assert(!File.ReadAllText(log).Contains("not-a-real-key-for-offline-tests"),
                   "mock credential must not leak to activity log");

            // A second avatar shares the SQLite cooldown but is allowed to
            // call the next provider immediately without touching Groq.
            var otherFake = new FakeHttp();
            otherFake.Add(HttpStatusCode.OK, OpenAiAnswer);
            using (var other = new RemoteAiResponder(Settings(), Path.Combine(dir, "secondary.json"), otherFake, db))
            {
                var answer = await other.ReplyAsync(Guid.NewGuid(), "Hello", CancellationToken.None);
                Assert(answer?.Contains("Test answer from approved model.") == true, "second bot must answer");
            }
            Assert(otherFake.CalledProviders.SequenceEqual(new[] {"OpenRouter"}),
                   "second avatar must skip shared Groq cooldown but retain next provider");

            // An HTTP 200 with empty text is not a valid answer: next model.
            var emptyFake = new FakeHttp();
            emptyFake.Add(HttpStatusCode.OK, """{"choices":[{"message":{"content":""}}]}""");
            emptyFake.Add(HttpStatusCode.OK, OpenAiAnswer);
            using (var empty = new RemoteAiResponder(Settings(), Path.Combine(dir, "empty.json"), emptyFake,
                                                       Path.Combine(dir, "empty.db")))
            {
                var answer = await empty.ReplyAsync(Guid.NewGuid(), "Hello", CancellationToken.None);
                Assert(answer?.Contains("Test answer from approved model.") == true, "empty answer fallback");
            }
            Assert(emptyFake.CalledProviders.SequenceEqual(new[] {"Groq","OpenRouter"}), "empty reply order");
            Assert(Events(Path.Combine(dir, "empty.json"))[0].GetProperty("outcome").GetString() == "empty_reply",
                   "empty reply must appear in audit");

            // Transport cancellation affects only one attempt, not the next.
            var timeoutFake = new FakeHttp();
            timeoutFake.Timeout();
            timeoutFake.Add(HttpStatusCode.OK, OpenAiAnswer);
            using (var timeout = new RemoteAiResponder(Settings(), Path.Combine(dir, "timeout.json"), timeoutFake,
                                                         Path.Combine(dir, "timeout.db")))
            {
                var answer = await timeout.ReplyAsync(Guid.NewGuid(), "Hello", CancellationToken.None);
                Assert(answer?.Contains("Test answer from approved model.") == true, "timeout fallback");
            }
            Assert(timeoutFake.CalledProviders.SequenceEqual(new[] {"Groq","OpenRouter"}), "timeout order");
            Assert(Events(Path.Combine(dir, "timeout.json"))[0].GetProperty("reason").GetString() == "timeout",
                   "timeout reason must be reflected in admin audit");

            // In single mode, failures never try the second provider.
            var singleFake = new FakeHttp();
            singleFake.Add(HttpStatusCode.TooManyRequests);
            using (var single = new RemoteAiResponder(Settings(false), Path.Combine(dir, "single.json"), singleFake,
                                                        Path.Combine(dir, "single.db")))
            {
                var answer = await single.ReplyAsync(Guid.NewGuid(), "Hello", CancellationToken.None);
                Assert(answer?.Contains("temporairement indisponibles") == true,
                       "single-mode refusal must be understandable");
            }
            Assert(singleFake.CalledProviders.SequenceEqual(new[] {"Groq"}),
                   "single mode must never switch providers");

            // Disabled profiles and missing credentials must never reach an API.
            var disabledSettings = Settings();
            disabledSettings.Profiles.ForEach(x => x.Enabled = false);
            var disabledFake = new FakeHttp();
            using (var disabled = new RemoteAiResponder(disabledSettings, null, disabledFake,
                                                          Path.Combine(dir, "disabled.db")))
            {
                Assert(!disabled.Ready, "disabled profiles must not be ready");
                Assert(await disabled.ReplyAsync(Guid.NewGuid(), "Hello", CancellationToken.None) is null,
                       "disabled profiles must not call an API");
            }
            Assert(disabledFake.CalledProviders.Count == 0, "no unauthorized API calls");
            Console.WriteLine("Full fake-provider IM fallback verified: 429 -> 503 -> Gemini, " +
                              "shared SQLite cooldown, empty reply, timeout, single mode, disabled profiles.");
        }
        finally
        {
            Environment.SetEnvironmentVariable("OSAI_FAKE_FALLBACK_KEY", old);
            try { Directory.Delete(dir, true); } catch (IOException) { }
        }
    }
}
