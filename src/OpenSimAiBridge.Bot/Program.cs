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

// Prototype V0.1: static IM commands only, no paid AI, no ROBUST connection.
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

using var ai = new RemoteAiResponder(options.Ai);
Console.WriteLine($"OpenSim AI Bridge — remote AI: {(ai.Ready ? "enabled for authorized IMs" : "disabled")}.");
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
                            client.Self.InstantMessage(recipient, result);
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
        if (!string.IsNullOrWhiteSpace(location.RegionName))
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
            if (!string.IsNullOrWhiteSpace(location.RegionName) &&
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
}
