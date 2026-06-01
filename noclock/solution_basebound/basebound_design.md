# Base and Bound Solution Design

## The Problem
The previous model (`noclock/fsm.py`) demonstrated a stale overwrite bug because the DMA Engine and the Mirror Buffer could both transmit data for Address `X` concurrently without coordination.

## The Proposed Solution: Base & Bound Handshaking
The proposed fix introduces spatial tracking:
1. **Mirror Buffer Pair**: The Mirror has two buffers. 
   - Buffer 1 catches *all* stores.
   - Buffer 2 only catches stores that fall within the active Mirror range `[a, b]`. Only Buffer 2 transmits to the network.
2. **DMA Range**: The DMA Engine reads memory sequentially based on its active range `[c, d]`.
3. **Handshaking**: The DMA and Mirror communicate their active ranges to avoid overlapping in a way that causes the bug.

## How to Abstract this for a Single Address (`X`)
Because our formal model drastically abstracts the entire memory space down to a single address (`X`), we do not need actual integers for `a, b, c, d`. 

Instead, we can model whether `X` currently falls inside those bounds using **Boolean flags**:
*   `mirror_bound_includes_X`: A boolean (True/False). If True, stores to `X` are placed in Buffer 2 and transmitted. If False, stores to `X` stay in Buffer 1 (or are dropped).
*   `dma_bound_includes_X`: A boolean (True/False). If True, the DMA engine is currently authorized to read and transmit `X`.

## Designing the Handshake Protocol
To implement this in our FSM, we need to define the exact sequence of the handshake. How do these booleans change over time?

*(This document will be updated as the handshake protocol is finalized)*
