using System.Text.Json;
using LibreMetaverse;

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

using var stop = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) =>
{
    e.Cancel = true;
    stop.Cancel();
};

Console.WriteLine("OpenSim AI Bridge V0.1 (experimental) — no OpenAI calls.");
Console.WriteLine($"Avatar: {options.Grid.AvatarFirstName} {options.Grid.AvatarLastName}");
Console.WriteLine($"Test region: {options.Grid.StartLocation.RegionName}");
Console.WriteLine("Ctrl+C to stop; IM 'ping', 'help' or 'where' to test.");

do
{
    var client = new GridClient();
    var disconnected = false;
    client.Network.Disconnected += (_, e) =>
    {
        disconnected = true;
        Console.WriteLine($"Connection lost: {e.Reason}");
    };

    if (options.Bot.EnableIM)
    {
        client.Self.IM += (_, e) =>
        {
            if (e.IM.FromAgentID == client.Self.AgentID || !client.Network.Connected)
                return;

            // This is a deliberately narrow, free command handler.
            // Never echo arbitrary text, or respond to group/inventory/system IMs.
            string? reply = e.IM.Message.Trim().ToLowerInvariant() switch
            {
                "ping" => "Pong ! BloodMoon AI Bridge est connecté.",
                "help" or "aide" => "Commandes de test : ping, help, where.",
                "where" or "position" => $"Région : {client.Network.CurrentSim?.Name ?? "inconnue"} ; position : {client.Self.SimPosition}",
                _ => null
            };
            if (reply is null) return;
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
        }
        else
        {
            Console.WriteLine($"Connected in {client.Network.CurrentSim?.Name} at {client.Self.SimPosition}");
            if (!string.IsNullOrWhiteSpace(location.RegionName) &&
                !string.Equals(client.Network.CurrentSim?.Name, location.RegionName, StringComparison.OrdinalIgnoreCase))
            {
                Console.Error.WriteLine("Warning: login succeeded in a different region than requested.");
            }
            while (!stop.IsCancellationRequested && client.Network.Connected && !disconnected)
                await Task.Delay(TimeSpan.FromSeconds(2), stop.Token);
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

// Avoid keeping credentials accessible longer than the process lifetime.
return 0;

public sealed class BotOptions
{
    public GridOptions Grid { get; set; } = new();
    public BotFeatures Bot { get; set; } = new();
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
