# Live Migration FSM Model (LLM Context)

## Overview
This directory (`noclock`) contains an evolution of the VM migration protocol model. We have moved away from a discrete-time simulation (with ticks and fixed latencies) to an **Asynchronous State Transition System (Finite State Machine)**. 

This FSM approach is specifically designed to mirror how formal verification tools (like TLA+, Promela, or Lean/Veil) evaluate systems: by exhaustively exploring non-deterministic state transitions rather than running a single chronological timeline.

## The Global State (`GlobalState`)
The entire universe is frozen in a single snapshot containing:
1. `source_mem` & `dest_mem`: Monotonically increasing counters representing the memory at Address `X`.
2. `mirror_buffer`: A FIFO queue (`[]`) intercepting host CPU writes.
3. `network_bag`: An unordered set (`[]`) of all packets currently in flight across the fabric.
4. `dma_state`: The DMA engine's state machine (`WAITING`, `TRANSMITTING`, `DONE`).
5. `dma_internal_buffer`: A single register (`None` or `int`) holding the chunk the DMA just read.

## The Transitions (`Transitions`)
Time is replaced by non-deterministic Actions. Each Action has:
*   **Guard**: A condition checking if the action is valid in the current state.
*   **Effect**: A function that mutates the `GlobalState`.

The defined actions are:
*   `storer_writes`: CPU increments memory and pushes to `mirror_buffer`.
*   `mirror_sends`: Moves an item from `mirror_buffer` to `network_bag`.
*   `dma_reads`: DMA reads from `source_mem` to its internal buffer.
*   `dma_sends`: DMA moves its internal buffer to the `network_bag`.
*   `network_delivers`: Randomly pops a packet from the `network_bag` and applies it to `dest_mem`.

## The Execution Engine
`fsm.py` runs a random walk (a simplistic model checker). At every step, it evaluates all Guards, finds all currently valid Actions, and randomly executes exactly one. 

## A Note on Network Ordering (The UDP Bug)
When this random walk was first executed, it discovered a new bug immediately: **Out-of-order Mirror delivery**. Because the `network_bag` is completely unordered, the random walker delivered Mirror Update #4 before Mirror Update #2, causing the invariant to fail.
*   *Architectural Takeaway*: If the system assumes the Mirror stream operates over a reliable, ordered connection (like TCP), the `network_bag` must be modified to enforce FIFO ordering *within* the Mirror stream, while still allowing the DMA stream to interleave non-deterministically.

## Next Steps for the LLM
1. **Refine the FSM**: You may be asked to implement handshaking logic (locks, bounded timers, or sequence numbers) into the `GlobalState` and `Transitions` to solve the stale overwrite bug.
2. **Port to Lean 4 / Veil**: The Python `GlobalState` and `Transitions` map 1-to-1 to Lean `struct` definitions and Inductive relations. You may be asked to translate this exact FSM into a Lean 4 formal proof environment.
