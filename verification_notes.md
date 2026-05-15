# Formal Verification and Modeling Notes

This document summarizes our discussions regarding how to transition the Python VM migration model into a formal verification context (e.g., TLA+, Promela, or Veil).

## 1. Choosing a Verification Language

When moving from a simulation to formal verification for distributed protocols, the goal is to exhaustively explore state spaces to find edge-case bugs (like race conditions).

*   **TLA+**: The industry gold standard for distributed architectures. It excels at modeling abstract state machines and non-deterministic concurrency.
*   **Promela (SPIN)**: A classic, C-like language that has first-class primitives for network `channels` (FIFOs), making it excellent for modeling message-passing queues.
*   **Veil (Lean 4)**: A cutting-edge, academic multi-modal framework embedded in Lean 4. It provides a high-level DSL (similar to Ivy) for push-button SMT verification, with the ability to drop down into Lean's interactive theorem prover for mathematically foundational guarantees.

## 2. Modeling the Network: Fixed Latency vs. The "Bag"

Our initial Python model used fixed latencies (e.g., `latency=4`). This is an anti-pattern in formal verification because it only tests one specific timeline.

*   **The "Bag" Model**: In verification, an asynchronous network is typically modeled as an unordered "Bag" (or multiset). Messages are put into the bag, and the model checker non-deterministically pulls them out to explore *every possible* interleaving and delivery order. This exhaustively proves that no combination of network delays can break the protocol.
*   **The FIFO Sequence**: If the protocol guarantees ordering, the network is modeled as a strict sequence queue.

## 3. Solving the Race Condition (Without ACKs or Bitmaps)

The core bug is the stale overwrite: the DMA reads `X`, the CPU updates `X`, the Mirror sends the update, and then the slow DMA packet overwrites it. 
To solve this without tracking local state (bitmaps) or requiring Destination feedback (ACKs), there are two architectural approaches:

### Approach A: The Time-Bound (`K`)
If we assume the network has a strict upper bound on transmission time (`K`), the Source can use time to synchronize:
1. DMA reads `X` and transmits.
2. If the CPU updates `X`, the Mirror Buffer **stalls** the transmission for `K` cycles.
3. Because `K` is the absolute maximum network delay, the Source knows the DMA chunk has landed safely. The Mirror Buffer can now send the update, guaranteeing it arrives after the DMA chunk.

**The Reality in Datacenters**: Modern lossless fabrics (RoCEv2, InfiniBand) use Priority Flow Control (PFC). If there is network congestion, the switch sends Pause frames, freezing packets in buffers. This can cause unpredictable latency spikes, violating a strict `K` bound. Therefore, `K` is only a safe assumption if the migration traffic operates on a dedicated QoS queue with guaranteed bandwidth.

### Approach B: The Single Queue (FIFO Multiplexing)
To avoid the risks of `K` entirely, the architecture can rely on hardware ordering.
If both the DMA Engine and the Mirror Buffer push their packets into the **exact same transmit queue** (e.g., a single TCP socket or a single RDMA Reliable Connection Queue Pair):
1. The DMA pushes the chunk for `X`.
2. The Mirror pushes the update for `X` immediately after.
3. **Backpressure**: If the fabric issues a PFC Pause, both packets simply pile up in the host's memory queue chronologically.
4. When the fabric unpauses, the hardware guarantees they drain in exact FIFO order.

This architectural decision elegantly eliminates the need for timers, ACKs, or bitmaps. The network itself enforces the required ordering.
