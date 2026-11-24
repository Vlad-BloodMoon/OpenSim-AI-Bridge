using System.Text.Json;
using System.Globalization;
using LibreMetaverse;
using OpenSimAiBridge;

// CoreJ2K 2.4.x parses JPEG2000 encoder 'rate' using float.Parse without
// specifying CultureInfo. The codec supplies dot-decimal rates (e.g. 2.8125),
// which fails under fr-FR and other comma-decimal Linux locales.
// Use invariant formatting and parsing throughout this headless protocol client.
CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

// Offline regression test: run in CI without connecting to the grid or reading secrets.
if (args.Length == 1 && args[0] == "--verify-welcome")
{
    var settings = new ProximityWelcomeOptions { Enabled = true, RadiusMeters = 15, RepeatDelayMinutes = 30 };
    var welcome = new ProximityWelcome(settings);
    var time = DateTimeOffset.UtcNow;
    var selfId = Guid.NewGuid();
    var first = UUID.Random();
    var second = UUID.Random();
    var at = new Vector3(128, 128, 25);
    IReadOnlyDictionary<UUID, Vector3> snapshot(params (UUID id, Vector3 pos)[] entries) =>
        entries.ToDictionary(x => x.id, x => x.pos);

    if (welcome.Observe(time, selfId, at, snapshot((first, new Vector3(130, 128, 25)))).Count != 0 ||
        welcome.Observe(time.AddSeconds(9), selfId, at, snapshot((first, new Vector3(130, 128, 25)))).Count != 0 ||
        welcome.Observe(time.AddSeconds(10), selfId, at, snapshot((first, new Vector3(130, 128, 25)),
            (second, new Vector3(140, 128, 25)))).Count != 1 ||
        welcome.Observe(time.AddSeconds(20), selfId, at, snapshot((second, new Vector3(140, 128, 25)))).Count != 0 ||
        welcome.Observe(time.AddSeconds(25), selfId, at, snapshot((second, new Vector3(140, 128, 25)))).Count != 0 ||
        welcome.Observe(time.AddSeconds(55), selfId, at, snapshot()).Count != 0 ||
        welcome.Observe(time.AddSeconds(90), selfId, at, snapshot((second, new Vector3(140, 128, 25)))).Count != 0 ||
        welcome.Observe(time.AddMinutes(32), selfId, at, snapshot()).Count != 0 ||
        welcome.Observe(time.AddMinutes(33), selfId, at, snapshot()).Count != 0 ||
        welcome.Observe(time.AddMinutes(34), selfId, at, snapshot((second, new Vector3(140, 128, 25)))).Count != 1 ||
        ProximityWelcome.FormatMessage("Welcome, {avatar_name}!", "Alice\\nBob") != "Welcome, Alice Bob!" ||
        ProximityWelcome.FormatMessage("Welcome, {avatar_name}!", null) != "Welcome!" ||
        ProximityWelcome.Valid(new ProximityWelcomeOptions { RadiusMeters = 999 }))
    {
        Console.Error.WriteLine("Proximity welcome safety regression.");
        return 1;
    }
    Console.WriteLine("Proximity welcome checks passed.");
    return 0;
}

if (args.Length == 1 && args[0] == "--verify-invariant-rate")
{
    var rate = float.Parse("2.8125", CultureInfo.CurrentCulture);
    if (rate != 2.8125f)
    {
        Console.Error.WriteLine("Culture regression: CoreJ2K rate was misparsed.");
        return 1;
    }
    Console.WriteLine($"CoreJ2K numeric parsing ready: {rate.ToString(CultureInfo.InvariantCulture)}");
    return 0;
}

// Offline safety check: remote AI requires opt-in and key; public access is restricted to Groq.
if (args.Length == 1 && args[0] == "--verify-ai-safety")
{
    using var disabled = new RemoteAiResponder(new RemoteAiSettings { Enabled = false });
    using var noUsers = new RemoteAiResponder(new RemoteAiSettings { Enabled = true });
    if (disabled.Ready || noUsers.Ready || disabled.IsAuthorized(Guid.NewGuid()))
    {
        Console.Error.WriteLine("AI must be disabled without explicit authorization.");
        return 1;
    }
    // Public access is Groq-only, requires explicit opt-in and a configured key.
    var previous = Environment.GetEnvironmentVariable("OSAI_AI_TEST_KEY");
    try
    {
        Environment.SetEnvironmentVariable("OSAI_AI_TEST_KEY", "offline-test-not-a-real-key");
        var opts = new RemoteAiSettings {
            Enabled = true, PublicAccess = true, Provider = "Groq",
            ApiKeyEnv = "OSAI_AI_TEST_KEY"
        };
        using var publicGroq = new RemoteAiResponder(opts);
        using var publicOpenAi = new RemoteAiResponder(new RemoteAiSettings {
            Enabled = true, PublicAccess = true, Provider = "OpenAI",
            ApiKeyEnv = "OSAI_AI_TEST_KEY"
        });
        using var privateGroq = new RemoteAiResponder(new RemoteAiSettings {
            Enabled = true, PublicAccess = false, Provider = "Groq",
            ApiKeyEnv = "OSAI_AI_TEST_KEY"
        });
        if (!publicGroq.IsAuthorized(Guid.NewGuid()) || publicOpenAi.IsAuthorized(Guid.NewGuid()) ||
            privateGroq.IsAuthorized(Guid.NewGuid()))
        {
            Console.Error.WriteLine("Remote AI access control regression.");
            return 1;
        }
    }
    finally
    {
        Environment.SetEnvironmentVariable("OSAI_AI_TEST_KEY", previous);
    }
    Console.WriteLine("Remote AI opt-in safety checks passed.");
    return 0;
}

// Offline proof that the shared RAG retriever remains provider-independent and safe.
if (args.Length == 1 && args[0] == "--verify-knowledge")
{
    var sampleTranslation = BloodMoonTranslator.ReadTranslation(
        """{"ok":true,"from":"en","to":"fr","translatedText":"Comment obtenir un terrain gratuit ?"}""");
    if (sampleTranslation != "Comment obtenir un terrain gratuit ?" ||
        BloodMoonTranslator.ReadTranslation("""{"ok":false,"translatedText":"bad"}""") is not null)
    {
        Console.Error.WriteLine("BloodMoon Translator gateway JSON contract mismatch.");
        return 1;
    }
    var expression = KnowledgeSearch.MakeFtsExpression("Malédiction vampire ?");
    if (expression is null || !expression.Contains("\"malédiction\"", StringComparison.Ordinal) ||
        KnowledgeSearch.MakeFtsExpression("!!!") is not null)
    {
        Console.Error.WriteLine("Knowledge query tokenization failed.");
        return 1;
    }
    var englishLand = KnowledgeSearch.MakeFtsExpression("How can I get land?");
    var spanishVampire = KnowledgeSearch.MakeFtsExpression("Como convertirse en vampiro?");
    if (englishLand is null || !englishLand.Contains("\"terrain\"", StringComparison.Ordinal) ||
        spanishVampire is null || !spanishVampire.Contains("\"vampire\"", StringComparison.Ordinal))
    {
        Console.Error.WriteLine("Multilingual search expansion for French editorial notes failed.");
        return 1;
    }
    // One editorial TXT per topic: questions in all six supported languages
    // must retrieve its canonical terms without any translation API call.
    var freelandQueries = new[] {
        "Comment obtenir un terrain gratuit sur BloodMoon ?",
        "How can I get free land on BloodMoon?",
        "¿Cómo conseguir un terreno gratis en BloodMoon?",
        "Wie bekomme ich ein kostenloses Grundstück auf BloodMoon?",
        "Come ottenere un terreno gratuito su BloodMoon?",
        "Como conseguir um terreno grátis no BloodMoon?"
    };
    foreach (var question in freelandQueries)
    {
        var q = KnowledgeSearch.MakeFtsExpression(question);
        if (q is null || !q.Contains("\"freeland\"", StringComparison.Ordinal) ||
            !KnowledgeSearch.DetectDomains(question).Contains("grid"))
        {
            Console.Error.WriteLine("Multilingual Freeland retrieval failed: " + question);
            return 1;
        }
    }
    var curseQueries = new[] {
        "Comment fonctionne la malédiction des vampires ?",
        "How does the vampire curse work?",
        "¿Cómo funciona la maldición de los vampiros?",
        "Wie funktioniert der Fluch der Vampire?",
        "Come funziona la maledizione dei vampiri?",
        "Como funciona a maldição dos vampiros?"
    };
    foreach (var question in curseQueries)
    {
        var q = KnowledgeSearch.MakeFtsExpression(question);
        if (q is null || !q.Contains("\"malédiction\"", StringComparison.Ordinal) ||
            !KnowledgeSearch.DetectDomains(question).Contains("roleplay"))
        {
            Console.Error.WriteLine("Multilingual Roleplay retrieval failed: " + question);
            return 1;
        }
    }
    // Azure can translate "plot" as "intrigue" or "scénario".
    // Preserve the actual resident's protected vocabulary instead of trusting
    // the translation to classify BloodMoon services.
    var nameCases = new (string original, string french, string required, string domain)[] {
        ("How do I join the BloodMoon grid?", "Comment rejoindre la grille ?", "grid", "grid"),
        ("How to get a Freeland?", "Comment obtenir une intrigue ?", "freeland", "grid"),
        ("How does the Vampire HUD work?", "Comment marche l'interface vampire ?", "hud", "roleplay"),
        ("How do I configure Hypergrid on OpenSim?", "Comment configurer une grille ?", "hypergrid", "handbook"),
        ("How to use the Marketplace Magic Box?", "Comment utiliser la boîte magique ?", "marketplace", "marketplace")
    };
    foreach (var item in nameCases)
    {
        var retrieval = KnowledgeSearch.BuildRetrievalQuestion(item.original, item.french);
        var expr = KnowledgeSearch.MakeFtsExpression(retrieval);
        if (expr is null || !expr.Contains(((char)34) + item.required + ((char)34), StringComparison.Ordinal) ||
            !KnowledgeSearch.DetectDomains(retrieval).Contains(item.domain))
        {
            Console.Error.WriteLine("Protected vocabulary retrieval failed: " + item.original);
            return 1;
        }
    }
    if (KnowledgeSearch.BuildRetrievalQuestion("gridview", "une page") != "une page gridview")
    {
        Console.Error.WriteLine("Protected vocabulary matched a substring.");
        return 1;
    }
    // The administrator can add a protected BloodMoon term without recompiling.
    // The next IM reads it directly from the shared private configuration.
    var temporaryVocabularyRoot = Path.Combine(Path.GetTempPath(),
        "osai-vocabulary-" + Guid.NewGuid().ToString("N"));
    var priorVocabularyRoot = Environment.GetEnvironmentVariable("OSAI_INSTALL_DIR");
    Directory.CreateDirectory(Path.Combine(temporaryVocabularyRoot, "config"));
    try
    {
        Environment.SetEnvironmentVariable("OSAI_INSTALL_DIR", temporaryVocabularyRoot);
        var vocabularyFile = Path.Combine(temporaryVocabularyRoot, "config", "knowledge-terms.json");
        File.WriteAllText(vocabularyFile,
            """
            {"entries":[{"term":"Moonstone","aliases":"Pierre de lune","keywords":"soul, potion, reaper","domain":"roleplay"}]}
            """);
        var editable = KnowledgeSearch.BuildRetrievalQuestion(
            "How does Moonstone work?", "Comment fonctionne cet objet ?");
        if (!editable.Contains("soul potion reaper", StringComparison.Ordinal) ||
            !KnowledgeSearch.DetectDomains(editable).Contains("roleplay"))
        {
            Console.Error.WriteLine("Editable vocabulary was not loaded from private configuration.");
            return 1;
        }
        File.WriteAllText(vocabularyFile, """{"entries":[]}""");
        var removed = KnowledgeSearch.BuildRetrievalQuestion(
            "How does Moonstone work?", "Comment fonctionne cet objet ?");
        if (removed.Contains("soul potion reaper", StringComparison.Ordinal))
        {
            Console.Error.WriteLine("Removed vocabulary term is still active.");
            return 1;
        }
    }
    finally
    {
        Environment.SetEnvironmentVariable("OSAI_INSTALL_DIR", priorVocabularyRoot);
        Directory.Delete(temporaryVocabularyRoot, recursive: true);
    }
    var routingHits = new[] {
        new KnowledgeHit("https://bloodmoonpack.com/OpenSim_Handbook/commands-terrain-objects.php?lang=fr",
                         "OpenSimulator terrain console commands", "Technical server administration", "handbook"),
        new KnowledgeHit("knowledge://grid_bloodmoon/Terrain_Gratuit_Freelands.txt",
                         "Terrain Gratuit Freelands", "Contacter l'équipe BloodMoon", "local_grid_bloodmoon"),
        new KnowledgeHit("https://bloodmoonpack.com/grid/land/freeland.php",
                         "Freeland BloodMoon", "Prêt de terrains gratuits", "grid"),
        new KnowledgeHit("https://bloodmoonpack.com/roleplay/pages/guide.php",
                         "Grimoire", "Malédiction des vampires", "roleplay"),
        new KnowledgeHit("https://bloodmoonpack.com/Marketplace/",
                         "Marketplace", "Achats, ventes et livraisons", "marketplace")
    };
    static bool OnlyDomains(IReadOnlyList<KnowledgeHit> hits, params string[] domains) =>
        hits.Count > 0 && hits.All(hit => domains.Contains(hit.Source));
    if (!OnlyDomains(KnowledgeSearch.RouteSources(
            "comment obtenir un terrain gratuit sur BloodMoon ?", routingHits), "grid", "local_grid_bloodmoon") ||
        !OnlyDomains(KnowledgeSearch.RouteSources(
            "comment configurer le terrain avec la console OpenSimulator ?", routingHits), "handbook") ||
        !OnlyDomains(KnowledgeSearch.RouteSources(
            "How can I get free land on BloodMoon?", routingHits), "grid", "local_grid_bloodmoon") ||
        !OnlyDomains(KnowledgeSearch.RouteSources(
            "Comment fonctionne la malédiction des vampires ?", routingHits), "roleplay") ||
        !OnlyDomains(KnowledgeSearch.RouteSources(
            "Comment vendre un objet sur la Marketplace ?", routingHits), "marketplace") ||
        !OnlyDomains(KnowledgeSearch.RouteSources(
            "Comment fonctionne un script OpenSim pour la Marketplace ?", routingHits),
            "handbook", "marketplace") ||
        KnowledgeSearch.RouteSources("bonjour", routingHits).Count != routingHits.Length)
    {
        Console.Error.WriteLine("Knowledge topic routing regression.");
        return 1;
    }
    var context = KnowledgeSearch.BuildContext(new[] {
        new KnowledgeHit("https://bloodmoonpack.com/roleplay/pages/guide.php",
                         "Grimoire", "Les vampires jouent un rôle important.", "roleplay")
    });
    if (!context.Contains("https://bloodmoonpack.com/roleplay/pages/guide.php",
                          StringComparison.Ordinal) ||
        !context.Contains("NON FIABLES", StringComparison.Ordinal))
    {
        Console.Error.WriteLine("Knowledge source and safety markers missing.");
        return 1;
    }
    var search = new KnowledgeSearch(Path.Combine(Path.GetTempPath(),
                                                  $"missing-knowledge-{Guid.NewGuid():N}.db"));
    if (search.Search("Vampire").Count != 0)
    {
        Console.Error.WriteLine("Missing knowledge index must fail safely.");
        return 1;
    }
    Console.WriteLine("Shared knowledge retrieval safety checks passed.");
    return 0;
}

// Offline regression: two separate avatars share one provider's durable budget.
if (args.Length == 1 && args[0] == "--verify-shared-quota")
{
    var dir = Path.Combine(Path.GetTempPath(), "osai-quota-test-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(dir);
    try
    {
        var file = Path.Combine(dir, "quota.db");
        var botA = new SharedProviderQuota(file);
        var botB = new SharedProviderQuota(file);
        var t = DateTimeOffset.FromUnixTimeSeconds(3600L * 100000);
        if (!botA.TryReserve("Groq", t, 2, out _) ||
            !botB.TryReserve("Groq", t, 2, out _) ||
            botA.TryReserve("Groq", t, 2, out _))
            throw new InvalidOperationException("The shared Groq quota is not enforced.");
        if (!botA.TryReserve("OpenRouter", t, 2, out _))
            throw new InvalidOperationException("A Groq exhaustion must not block OpenRouter.");
        if (!botA.TryReserve("Gemini", t, 2, out _) ||
            !botB.TryReserve("Gemini", t, 2, out _) ||
            botA.TryReserve("Gemini", t, 2, out _))
            throw new InvalidOperationException("Multiple Gemini profiles must share one provider quota.");
        botA.RecordCooldown("OpenRouter", t, TimeSpan.FromMinutes(3));
        if (botB.TryReserve("OpenRouter", t, 2, out _))
            throw new InvalidOperationException("The shared provider cooldown is not enforced.");
        if (!botA.TryReserve("Groq", t.AddHours(1), 2, out _))
            throw new InvalidOperationException("A new hourly bucket must allow fresh requests.");
        Console.WriteLine("Shared provider quota and automatic fallback preconditions passed.");
        return 0;
    }
    finally
    {
        try { Directory.Delete(dir, true); } catch (IOException) { }
    }
}

// Offline regression test: no truncation across long multilingual Firestorm IMs.
if (args.Length == 1 && args[0] == "--verify-im-chunks")
{
    var original = "La malédiction retire quatre unités de liquide vital chaque nuit. " +
        string.Concat(Enumerable.Repeat("Les vampires et les lycans doivent se protéger. ", 50)) +
        "🌙 La réponse se termine ici.";
    var chunks = ImReplyFormatter.Split(original);
    if (chunks.Count <= 1 || chunks.Any(c => System.Text.Encoding.UTF8.GetByteCount(c) > 600)
        || !chunks[^1].EndsWith("La réponse se termine ici.", StringComparison.Ordinal)
        || chunks.Any(c => c.Contains("trop longue", StringComparison.OrdinalIgnoreCase)))
    {
        Console.Error.WriteLine("IM answer should be sent completely in safe-sized chunks.");
        return 1;
    }
    var table = "| Étape | Détails |\\n|---|---|\\n| Nuit | -4 vital |";
    var plain = ImReplyFormatter.PlainText(table);
    if (plain.Contains("|---|", StringComparison.Ordinal) || !plain.Contains("Nuit — -4 vital", StringComparison.Ordinal))
    {
        Console.Error.WriteLine("Markdown tables must be readable in IM.");
        return 1;
    }
    var sentenceCase = "Les vampires perdent quatre unités chaque nuit. " +
        new string('x', 900) + ". Ils peuvent se protéger avec les objets prévus.";
    var sentenceParts = ImReplyFormatter.Split(sentenceCase);
    if (sentenceParts.Count < 2 || !sentenceParts[0].EndsWith("nuit.", StringComparison.Ordinal))
    {
        Console.Error.WriteLine("An IM must prefer a sentence boundary before splitting.");
        return 1;
    }
    Console.WriteLine("Full-length UTF-8-safe Firestorm IM delivery checks passed.");
    return 0;
}

// Offline test: multiple distinct residents can speak in parallel; one
// resident cannot occupy two slots, and the fifth distinct resident is bounded.
if (args.Length == 1 && args[0] == "--verify-ai-concurrency")
{
    using var gate = new AiRequestGate();
    var ids = Enumerable.Range(0, 5).Select(_ => Guid.NewGuid()).ToArray();
    var leases = new List<IDisposable>();
    try
    {
        for (var i = 0; i < 4; ++i)
        {
            if (!gate.TryAcquire(ids[i], out var lease, out var duplicate) ||
                duplicate || lease is null)
                throw new InvalidOperationException("Four distinct residents should be admitted.");
            leases.Add(lease);
        }
        if (gate.TryAcquire(ids[0], out _, out var alreadyActive) || !alreadyActive)
            throw new InvalidOperationException("Duplicate resident request must be rejected.");
        if (gate.TryAcquire(ids[4], out _, out var anotherDuplicate) || anotherDuplicate)
            throw new InvalidOperationException("Fifth parallel resident must be safely limited.");
        leases[0].Dispose();
        if (!gate.TryAcquire(ids[4], out var fifthLease, out var sameSender) ||
            sameSender || fifthLease is null)
            throw new InvalidOperationException("Released slot should serve another resident.");
        leases.Add(fifthLease);
        Console.WriteLine("Parallel resident AI request admission checks passed.");
        return 0;
    }
    finally
    {
        foreach (var lease in leases) lease.Dispose();
    }
}

// Static free IM commands remain available even when remote AI is off.
// Never place avatar passwords in configuration files or source code.
var configPath = args.Length > 0 ? args[0] : "appsettings.json";
if (!File.Exists(configPath))
{
    Console.Error.WriteLine($"Missing configuration: {configPath}");
    Console.Error.WriteLine("Copy config/appsettings.example.json to a private appsettings.json and edit its grid fields.");
    return 2;
}

BotOptions? options;
try
{
    options = JsonSerializer.Deserialize<BotOptions>(
        await File.ReadAllTextAsync(configPath),
        new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
}
catch (Exception ex) when (ex is JsonException or IOException)
{
    Console.Error.WriteLine($"Invalid configuration: {ex.Message}");
    return 2;
}

if (options?.Grid is null ||
    string.IsNullOrWhiteSpace(options.Grid.LoginUri) ||
    options.Grid.LoginUri.Contains("YOUR-", StringComparison.OrdinalIgnoreCase) ||
    string.IsNullOrWhiteSpace(options.Grid.AvatarFirstName) ||
    string.IsNullOrWhiteSpace(options.Grid.AvatarLastName))
{
    Console.Error.WriteLine("Configure Grid.LoginUri and the avatar's first/last names first.");
    return 2;
}

var passwordVar = options.Grid.AvatarPasswordEnv;
var password = Environment.GetEnvironmentVariable(passwordVar);
if (string.IsNullOrWhiteSpace(password))
{
    Console.Error.WriteLine($"Missing secret environment variable: {passwordVar}");
    return 2;
}

// Write the heartbeat outside the public Web root. Missing/old data is never treated as online.
var heartbeatFile = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(configPath))!, "data", "avatar-status.json");
Directory.CreateDirectory(Path.GetDirectoryName(heartbeatFile)!);
void PublishHeartbeat(GridClient? client, string state)
{
    try
    {
        var connected = client?.Network.Connected == true && state == "online";
        var pos = connected ? client!.Self.SimPosition : default;
        var payload = JsonSerializer.Serialize(new
        {
            state,
            connected,
            region = connected ? client!.Network.CurrentSim?.Name : null,
            x = connected ? (double?)pos.X : null,
            y = connected ? (double?)pos.Y : null,
            z = connected ? (double?)pos.Z : null,
            updatedUtc = DateTimeOffset.UtcNow.ToUnixTimeSeconds()
        });
        var tmp = heartbeatFile + "." + Environment.ProcessId + ".tmp";
        File.WriteAllText(tmp, payload);
        File.Move(tmp, heartbeatFile, true);
    }
    catch (IOException e) { Console.Error.WriteLine($"Heartbeat write failed: {e.GetType().Name}"); }
    catch (UnauthorizedAccessException) { Console.Error.WriteLine("Heartbeat write denied"); }
}
PublishHeartbeat(null, "starting");

using var stop = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    stop.Cancel();
};

// Every avatar uses the same root-owned provider configuration and secrets.
// The per-avatar Ai.Enabled flag alone controls access for that avatar.
var sharedProviderConfig = Path.Combine(
    Environment.GetEnvironmentVariable("OSAI_INSTALL_DIR") ?? AppContext.BaseDirectory,
    "config", "multi-ai.json");
if (File.Exists(sharedProviderConfig))
{
    try
    {
        var globalAi = JsonSerializer.Deserialize<RemoteAiSettings>(
            await File.ReadAllTextAsync(sharedProviderConfig),
            new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        if (globalAi?.Profiles is { Count: > 0 })
        {
            globalAi.Enabled = options.Ai.Enabled && globalAi.Enabled;
            options.Ai = globalAi;
        }
    }
    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
    {
        Console.Error.WriteLine("Shared provider configuration could not be loaded; remote AI disabled.");
        options.Ai.Enabled = false; // Fail closed: never fall back to a paid legacy provider.
    }
}

// Translation is configured separately from provider profiles so the Web
// "save AI models" action cannot silently reset the gateway setting.
var translationSettings = Path.Combine(
    Environment.GetEnvironmentVariable("OSAI_INSTALL_DIR") ?? AppContext.BaseDirectory,
    "config", "translation.json");
if (File.Exists(translationSettings))
{
    try
    {
        using var translationDoc = JsonDocument.Parse(await File.ReadAllTextAsync(translationSettings));
        var root = translationDoc.RootElement;
        options.Ai.UseBloodMoonTranslation =
            root.TryGetProperty("Enabled", out var flag) && flag.ValueKind == JsonValueKind.True;
    }
    catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
    {
        options.Ai.UseBloodMoonTranslation = false;
        Console.Error.WriteLine("Translator configuration unreadable; translation fallback disabled.");
    }
}

var welcomeSettings = options.Bot.ProximityWelcome ?? new ProximityWelcomeOptions();
if (welcomeSettings.Enabled && !ProximityWelcome.Valid(welcomeSettings))
{
    Console.Error.WriteLine("Invalid per-avatar proximity welcome settings; welcome disabled.");
    welcomeSettings.Enabled = false;
}
var proximityWelcome = new ProximityWelcome(welcomeSettings);
using var ai = new RemoteAiResponder(options.Ai);
Console.WriteLine($"OpenSim AI Bridge — remote AI: {(ai.Ready ? "enabled for configured IM access" : "disabled")}.");
Console.WriteLine($"Avatar: {options.Grid.AvatarFirstName} {options.Grid.AvatarLastName}");
Console.WriteLine($"Test region: {options.Grid.StartLocation.RegionName}");
Console.WriteLine("Ctrl+C to stop; IM 'ping', 'help' or 'where' to test.");

do
{
    var client = new GridClient();
    PublishHeartbeat(null, "connecting");
    var disconnected = false;
    client.Network.Disconnected += (_, e) =>
    {
        disconnected = true;
        PublishHeartbeat(null, "disconnected");
        Console.WriteLine($"Connection lost: {e.Reason}");
    };

    if (welcomeSettings.Enabled)
    {
        proximityWelcome.ResetObservation();
        var pendingNames = new System.Collections.Concurrent.ConcurrentDictionary<Guid, TaskCompletionSource<string>>();
        client.Avatars.UUIDNameReply += (_, e) =>
        {
            foreach (var (id, name) in e.Names)
            {
                if (pendingNames.TryGetValue(Guid.Parse(id.ToString()), out var pending))
                    pending.TrySetResult(name);
            }
        };
        client.Grid.CoarseLocationUpdate += (_, e) =>
        {
            if (!client.Network.Connected || stop.IsCancellationRequested ||
                !ReferenceEquals(e.Simulator, client.Network.CurrentSim))
                return;
            var matches = proximityWelcome.Observe(
                DateTimeOffset.UtcNow, Guid.Parse(client.Self.AgentID.ToString()),
                client.Self.SimPosition, e.Positions);
            foreach (var id in matches)
            {
                var lookup = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously);
                pendingNames[id] = lookup;
                _ = Task.Run(async () =>
                {
                    try
                    {
                        client.Avatars.RequestAvatarName(UUID.Parse(id.ToString()));
                        string? visitorName = null;
                        try { visitorName = await lookup.Task.WaitAsync(TimeSpan.FromSeconds(3), stop.Token); }
                        catch (TimeoutException) { } // Name optional; never expose UUID publicly.
                        if (client.Network.Connected && !stop.IsCancellationRequested)
                        {
                            var text = ProximityWelcome.FormatMessage(welcomeSettings.Message, visitorName);
                            if (!string.IsNullOrWhiteSpace(text))
                            {
                                client.Self.Chat(text, 0, ChatType.Normal, splitLargeMessages: false);
                                Console.WriteLine("Sent one proximity welcome in local chat.");
                            }
                        }
                    }
                    catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
                    catch (Exception ex)
                    {
                        Console.Error.WriteLine($"Proximity welcome failed: {ex.GetType().Name}");
                    }
                    finally { pendingNames.TryRemove(id, out var ignoredPending); }
                }, stop.Token);
            }
        };
    }

    if (options.Bot.EnableIM)
    {
        client.Self.IM += (_, e) =>
        {
            if (e.IM.FromAgentID == client.Self.AgentID || !client.Network.Connected)
                return;

            // Only direct person-to-person IMs, never group notices or inventory offers.
            if (e.IM.Dialog != InstantMessageDialog.MessageFromAgent)
                return;
            var message = e.IM.Message?.Trim() ?? "";
            if (message.Length == 0) return;
            string? reply = message.ToLowerInvariant() switch
            {
                "ping" => "Pong ! BloodMoon AI Bridge est connecté.",
                "help" or "aide" => "Commandes de test : ping, help, where.",
                "where" or "position" => $"Région : {client.Network.CurrentSim?.Name ?? "inconnue"} ; position : {client.Self.SimPosition}",
                _ => null
            };
            if (reply is null)
            {
                // Remote calls are opt-in, restricted to explicit UUIDs, and never
                // block the LibreMetaverse IM event thread.
                if (!ai.IsAuthorized(Guid.Parse(e.IM.FromAgentID.ToString())))
                    return;
                var recipient = e.IM.FromAgentID;
                _ = Task.Run(async () =>
                {
                    try
                    {
                        var result = await ai.ReplyAsync(Guid.Parse(recipient.ToString()), message, stop.Token);
                        if (result is not null && client.Network.Connected && !stop.IsCancellationRequested)
                        {
                            // Each Firestorm IM is short enough not to be truncated.
                            // Send the complete answer in order; don't flood the viewer.
                            foreach (var part in ImReplyFormatter.Split(result))
                            {
                                if (!client.Network.Connected || stop.IsCancellationRequested) break;
                                client.Self.InstantMessage(recipient, part);
                                await Task.Delay(250, stop.Token);
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.Error.WriteLine($"Remote AI IM handler failed: {ex.GetType().Name}");
                    }
                }, stop.Token);
                return;
            }
            try
            {
                client.Self.InstantMessage(e.IM.FromAgentID, reply);
                Console.WriteLine($"Replied to IM from {e.IM.FromAgentID}.");
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"IM reply failed: {ex.GetType().Name}");
            }
        };
    }

    if (options.Bot.EnableLocalChat)
    {
        client.Self.ChatFromSimulator += (_, e) =>
        {
            // Observe only; do not reply publicly in V0.1.
            if (e.SourceID != client.Self.AgentID && !string.IsNullOrWhiteSpace(e.Message))
                Console.WriteLine($"Local chat received from {e.SourceID}.");
        };
    }

    try
    {
        var login = client.Network.DefaultLoginParams(
            options.Grid.AvatarFirstName,
            options.Grid.AvatarLastName,
            password,
            "OpenSim AI Bridge",
            "0.1.0");

        login.URI = options.Grid.LoginUri;
        var location = options.Grid.StartLocation;
        // "last" is resolved by the OpenSimulator login service from the
        // avatar's last location; no local location cache is necessary.
        if (string.Equals(location.Mode, "Last", StringComparison.OrdinalIgnoreCase))
        {
            login.Start = "last";
        }
        else if (!string.IsNullOrWhiteSpace(location.RegionName))
        {
            login.Start = NetworkManager.StartLocation(
                location.RegionName,
                location.Position.X,
                location.Position.Y,
                location.Position.Z);
        }
        else
        {
            login.Start = "home";
        }

        using var loginTimeout = CancellationTokenSource.CreateLinkedTokenSource(stop.Token);
        loginTimeout.CancelAfter(TimeSpan.FromSeconds(45));
        Console.WriteLine("Connecting...");
        var ok = await client.Network.LoginAsync(login, loginTimeout.Token);
        if (!ok)
        {
            Console.Error.WriteLine($"Login failed: {client.Network.LoginMessage}");
            PublishHeartbeat(null, "login_failed");
        }
        else
        {
            Console.WriteLine($"Connected in {client.Network.CurrentSim?.Name} at {client.Self.SimPosition}");
            PublishHeartbeat(client, "online");
            if (!string.Equals(location.Mode, "Last", StringComparison.OrdinalIgnoreCase) &&
                !string.IsNullOrWhiteSpace(location.RegionName) &&
                !string.Equals(client.Network.CurrentSim?.Name, location.RegionName, StringComparison.OrdinalIgnoreCase))
            {
                Console.Error.WriteLine("Warning: login succeeded in a different region than requested.");
            }
            while (!stop.IsCancellationRequested && client.Network.Connected && !disconnected)
            {
                PublishHeartbeat(client, "online");
                await Task.Delay(TimeSpan.FromSeconds(2), stop.Token);
            }
        }
    }
    catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
    catch (OperationCanceledException)
    {
        Console.Error.WriteLine("Login timed out.");
    }
    catch (Exception ex)
    {
        Console.Error.WriteLine($"Session failed: {ex.GetType().Name}: {ex.Message}");
    }
    finally
    {
        PublishHeartbeat(null, "offline");
        if (client.Network.Connected)
        {
            try { await client.Network.LogoutAsync(); }
            catch { /* Best effort shutdown. */ }
        }
    }

    if (stop.IsCancellationRequested || !options.Bot.ReconnectEnabled) break;
    Console.WriteLine("Retrying in 10 seconds...");
    try { await Task.Delay(TimeSpan.FromSeconds(10), stop.Token); }
    catch (OperationCanceledException) { break; }
} while (true);

PublishHeartbeat(null, "stopped");
// Avoid keeping credentials accessible longer than the process lifetime.
return 0;

public sealed class BotOptions
{
    public GridOptions Grid { get; set; } = new();
    public BotFeatures Bot { get; set; } = new();
    public RemoteAiSettings Ai { get; set; } = new();
}

public sealed class GridOptions
{
    public string LoginUri { get; set; } = "";
    public string AvatarFirstName { get; set; } = "";
    public string AvatarLastName { get; set; } = "";
    public string AvatarPasswordEnv { get; set; } = "OSAI_AVATAR_PASSWORD";
    public StartOptions StartLocation { get; set; } = new();
}
public sealed class StartOptions
{
    // "Region" preserves all existing configurations without an explicit Mode.
    public string Mode { get; set; } = "Region";
    public string RegionName { get; set; } = "";
    public StartPosition Position { get; set; } = new();
}
public sealed class StartPosition
{
    public int X { get; set; } = 128;
    public int Y { get; set; } = 128;
    public int Z { get; set; } = 25;
}
public sealed class BotFeatures
{
    public bool EnableLocalChat { get; set; } = true;
    public bool EnableIM { get; set; } = true;
    public bool ReconnectEnabled { get; set; } = true;
    public ProximityWelcomeOptions ProximityWelcome { get; set; } = new();
}
