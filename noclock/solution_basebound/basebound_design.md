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
