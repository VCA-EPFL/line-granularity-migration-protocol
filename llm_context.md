# Live Migration Protocol Simulation (LLM Context)

## Project Overview
This repository contains a discrete-event simulation model of a live VM migration protocol. The goal is to duplicate the memory of a running source machine to a remote destination machine. 

There are two primary data paths for memory synchronization:
1. **DMA Engine**: Scans the physical memory sequentially in chunks and streams it to the destination.
2. **Mirror Buffer**: Intercepts active CPU stores to memory and pushes them into a FIFO buffer, which is transmitted over the network asynchronously.

## The Bug / Race Condition
Because the DMA stream and Mirror stream operate independently and have varying network latencies, a Time-Of-Check to Time-Of-Use (TOCTOU) race condition exists:
1. DMA reads a value from address `X`.
2. The CPU writes a new value to address `X`.
3. The Mirror Buffer intercepts this new value and transmits it quickly.
4. The DMA transmits its older, stale chunk.
5. The stale chunk from the DMA overwrites the newer value at the destination memory.

## Our Abstraction
To formally model this and make invariant checking trivial:
- **Address Space**: Reduced to just `X` and `Not X`. We only care about operations hitting `X`.
- **Memory Values**: Modeled as a monotonically increasing counter. Every store increments the value.
- **Invariant Checker**: If the destination ever receives a value for `X` that is strictly less than its current value, a stale overwrite bug has occurred.

## Current Codebase State
We have built a discrete-time (tick-based) Python simulation without external libraries.
- `main.py`: The entry point and global clock tick loop.
- `storer.py`: The CPU. Randomly writes to `X` (increments its value) every clock cycle with a 20% probability.
- `dma.py`: The DMA Engine. We abstract the full memory scan by having the DMA wait for a fixed `hit_time` (tick 20). At tick 20, it reads `X` exactly once, transmits it, and then goes `DONE` (ignoring `X` for the rest of the scan).
- `mirror.py`: FIFO queue that intercepts the `Storer`'s writes and pushes them to the network.
- `network.py`: Models network latency. Currently, the DMA channel is intentionally slower than the Mirror channel to force the race condition.
- `memory.py`: Destination memory containing the invariant assertion.

Currently, running `main.py` **will fail** with an `AssertionError` because the race condition is unmitigated. The parameters are exaggerated (slow DMA, high store rate) to guarantee the bug surfaces reliably for testing.

## Next Steps
The human developer is currently exploring ways to fix this bug by introducing "polite handshaking" between the DMA and the Mirror Buffer (e.g., locks, generation counters, ping-pong buffers, or stalling).
If you are an LLM reading this to continue the work, your task will likely involve reviewing the human's changes to the state machines in `dma.py` and `mirror.py` or formalizing the fixed protocol in TLA+.
