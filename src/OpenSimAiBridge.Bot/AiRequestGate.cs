using System.Collections.Concurrent;
using System.Threading;

namespace OpenSimAiBridge;

/// <summary>
/// Admit a bounded number of simultaneous residents without allowing one
/// resident to occupy multiple slots at once. Never queues requests or calls
/// providers; the responder keeps existing rate and quota limits.
/// </summary>
public sealed class AiRequestGate : IDisposable
{
    public const int DefaultParallelRequests = 4;
    private readonly SemaphoreSlim slots;
    private readonly ConcurrentDictionary<Guid, byte> activeSenders = new();
    private int disposed;

    public AiRequestGate(int capacity = DefaultParallelRequests)
    {
        if (capacity is < 1 or > 16)
            throw new ArgumentOutOfRangeException(nameof(capacity));
        slots = new SemaphoreSlim(capacity, capacity);
    }

    public bool TryAcquire(Guid sender, out IDisposable? lease, out bool sameSender)
    {
        lease = null;
        sameSender = false;
        if (Volatile.Read(ref disposed) != 0) return false;
        if (!activeSenders.TryAdd(sender, 0))
        {
            sameSender = true;
            return false;
        }
        if (!slots.Wait(0))
        {
            activeSenders.TryRemove(sender, out _);
            return false;
        }
        lease = new Lease(this, sender);
        return true;
    }

    private sealed class Lease : IDisposable
    {
        private AiRequestGate? owner;
        private readonly Guid sender;

        public Lease(AiRequestGate owner, Guid sender)
        {
            this.owner = owner;
            this.sender = sender;
        }

        public void Dispose()
        {
            var gate = Interlocked.Exchange(ref owner, null);
            if (gate is null) return;
            gate.activeSenders.TryRemove(sender, out _);
            gate.slots.Release();
        }
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref disposed, 1) == 0)
            slots.Dispose();
    }
}
