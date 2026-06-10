# Base and Bound Solution Design

## The Problem
The previous model (`noclock/fsm.py`) demonstrated a stale overwrite bug because the DMA Engine and the Mirror Buffer could both transmit data for Address `X` concurrently without coordination.

## The Proposed Solution: Base & Bound Handshaking
The proposed fix is to use a sliding lock to coordinate the DMA and Mirror. The solution essentially gives the dma engine ownership of a contiguous block of memory lines. While the dma engine owns a range [c, d], the mirror is not allowed to write to any memory within that range. The mirror keeps track of the bounds of the memory it has access to, which we call [a, b].

Key points of the design:
1. **Mirror Buffer Pair**: The Mirror has two buffers. 
   - Buffer 1 catches *all* stores.
   - Buffer 2 only catches stores that fall within the active Mirror range `[a, b]`. Only Buffer 2 transmits to the network.
2. **DMA Range**: The DMA Engine reads memory sequentially based on its active range `[c, d]`. The goal is to have `[a, b]` and `[c, d]` be complements in the address range.
3. **Handshaking**: The DMA and Mirror communicate their active ranges to avoid overlapping in a way that causes the bug. As the DMA progresses, it requests ownership of d+1 and releases ownership of c (so it tries to increment c and d). If the mirror is holding the line it wants to increment, it tells the dma engine to wait. Once the mirror is done with the line it's holding, it releases it and the dma engine can claim it. Then, the DMA increments c and d, and the mirror claims the old c and yields the old d.


## The Handshake Protocol: Complementary Sliding Windows
Memory is an array of size `N` (e.g., 128). The ranges operate as a ring buffer.
The Mirror's safe range `[a, b]` is always the exact mathematical complement of the DMA's active range `[c, d]`. They never overlap.

The handshake occurs at the edges of the window as the DMA slides forward by 1 line:

1. **DMA Requests `d+1`**: 
   - The DMA asks the Mirror to yield address `d+1`.
   - The Mirror stops putting new CPU writes for `d+1` into Buffer 2.
   - The Mirror waits for Buffer 2 to drain any existing writes for `d+1`. Once empty, it grants permission.
   - `d` increments. DMA now safely owns `d+1` and can read it without racing.

2. **DMA Releases `c`**:
   - Once the DMA finishes transmitting the line at `c`, it releases it.
   - `c` increments. The Mirror regains control of the old `c`.
   - The Mirror immediately sweeps Buffer 1, pulling any stranded writes for `c` (which happened while the DMA held the lock) and dumps them into Buffer 2 for transmission over the network.

This lock-step edge handoff guarantees that the DMA and Mirror never transmit the same address concurrently, completely eliminating the stale overwrite bug!

## Evolution: Realistic Chip Asynchrony
To make the FSM model more realistic and closer to physical hardware implementation, we introduced asynchronous interconnect delays:
1. **CPU Store Buffer**: CPU writes are no longer atomically applied to memory and the Mirror. They queue in a `cpu_store_buffer` before the Memory Controller commits them.
2. **Decoupled Handshake**: The handshaking between the DMA and Mirror uses asynchronous FIFO queues (`dma_to_mirror_req`, `mirror_to_dma_grant`, `dma_to_mirror_release`). The DMA does not atomically expand `[c, d]`. Instead, it sends a request message, the Mirror updates its bounds and sends a grant message, and the DMA receives the grant before finally updating its own bounds and reading memory.

## A Hidden Danger: The In-Flight Grant Bug
Decoupling the handshake mathematically introduced a new race condition into our "perfect" lock, exposing a flaw in how **Buffer 1** operates. 

If Buffer 1 acts as an *append-only log* of values (storing exactly what the CPU wrote), the following fatal sequence is possible:
1. The DMA requests address `Y`.
2. The Mirror yields `Y` (updating its bounds so new writes go to Buffer 1) and sends the **Grant Message**.
3. While the Grant Message is *in flight*, the CPU furiously writes to `Y` three times. The memory is updated to value `3`. Buffer 1 logs `(Y, 1)`, `(Y, 2)`, and `(Y, 3)`.
4. The DMA receives the Grant Message, reads memory (getting the newest value `3`), and transmits it.
5. The DMA releases `Y`. The Mirror sweeps Buffer 1 and transmits the logged values `1`, `2`, `3`.
6. The destination receives the DMA's newest value `3`, followed by the Mirror's delayed log values `1` and `2`, causing a stale overwrite!

**The Proposed Fix (Dirty Bitmaps)**
To solve this, Buffer 1 cannot be an append-only log of values. In hardware, it should be implemented as a **Dirty Bitmap** (or a dictionary that only keeps the latest value). When the CPU writes to a locked address, the Mirror simply flags the address as "dirty." When the DMA releases the lock, the Mirror sweeps the bitmap, sees the dirty flag, and *re-reads* the latest value directly from memory for transmission, discarding any intermediate stale states.
