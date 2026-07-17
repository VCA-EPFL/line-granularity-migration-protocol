# Formal Verification Guide: VM Live Migration Protocol in Lean 4

This document serves as a handoff guide and context provider for the formal verification of the asynchronous VM live migration protocol with a spatial Base-and-Bound sliding window. It summarizes the design decisions, the verification strategy, and the structure of the proof in `fsm.lean`.

---

## 1. Context & Goal

We are formally verifying an **asynchronous VM live migration protocol** that uses a **spatial Base-and-Bound sliding window** to coordinate a DMA engine (copying memory sequentially) and a Mirror engine (forwarding CPU writes).

Unlike previous iterations that assumed monotonic counter writes (where values only increase), **this model supports arbitrary write values (`Nat`)**. 

The ultimate correctness goal is **Eventual Consistency** (`EventualConsistency`): once the migration has finished and all interconnect queues and internal component buffers are quiescent (empty), the destination memory must be identical to the source memory:
$$ s.memDest = s.memSrc $$

---

## 2. Key Lean 4 Design Decisions

### A. Mathematical Generality (Arbitrary $N$ and $DMA\_BATCH$)
Instead of hardcoding memory size $N = 128$ and batch size $DMA\_BATCH = 8$, the model is parameterized using **unspecified, opaque constants**:
```lean
opaque N : Nat
axiom hN : 0 < N
opaque DMA_BATCH : Nat
axiom hBatch : 0 < DMA_BATCH
```
This guarantees that the proof is valid for any positive memory size and batch size.

### B. Pure `Nat` Representation
Both `dmaC` and `dmaD` bounds are defined as natural numbers starting at `0`. `dmaD` acts as the exclusive upper bound of requested memory addresses, which avoids the need for negative initial indices (e.g. `-1` in python) or type conversions.

### C. Wrapping Arithmetic for `Fin N`
Because $N$ is arbitrary, numerals like `1` cannot be automatically assumed to be valid elements of `Fin N` (since `N = 1` is possible). Therefore, increments to `mirrorA` and `mirrorB` are written as:
```lean
mirrorA := s.mirrorA + ⟨1 % N, Nat.mod_lt 1 hN⟩
```
This mathematically represents incrementing by 1 modulo $N$ while remaining safe for any $N > 0$.

---

## 3. Verification Strategy: Invariant Strengthening

The final correctness property `EventualConsistency` is **not inductive** because it only specifies behavior when queues are empty. We strengthen it using a piecewise predicate over the address space:

### `AddressInvariant (s : State) (addr : Nat) : Prop`
For any address `addr < N`, the invariant is defined based on its sliding window region:

#### Region 1 (`addr < s.dmaC`): DMA has passed
The DMA has finished copying this address. Only Mirror packets can be in flight.
*   **Invariant:** 
    *   If no writes are in flight (in `netFifo` or `b2` for `addr`), then $\text{memDest}(addr) = \text{memSrc}(addr)$.
    *   If writes are in flight, the **most recent write** in flight must equal $\text{memSrc}(addr)$.

#### Region 2 (`s.dmaC ≤ addr < s.dmaD`): DMA owns the address (Range Locked)
The DMA is copying this address, and Mirror writes are stalled in $b1$.
*   **The Two-Pipeline Coexistence:**
    We have two parallel pipelines for `addr`: the DMA pipeline (holding the snapshot value $V_{dma}$) and the stalled Mirror pipeline `b1` (holding subsequent CPU writes).
*   **Invariant:**
    1.  No Mirror writes exist in `b2` or `netFifo` for `addr` (mutual exclusion).
    2.  If `b1` contains no writes for `addr`:
        The value in the DMA pipeline (in `dmaBuf`, `netFifo`, or already delivered to `memDest`) must equal $\text{memSrc}(addr)$.
    3.  If `b1` contains writes for `addr`:
        The **most recent write** in `b1` must equal $\text{memSrc}(addr)$. (The DMA's packet value $V_{dma}$ is older and can be arbitrary, as it is guaranteed to be delivered first and then safely overwritten by the subsequent `b1` updates).

#### Region 3 (`addr ≥ s.dmaD`): DMA has not reached
The DMA has not requested this address yet.
*   **Invariant:**
    *   Same as Region 1: only Mirror packets can be in flight, and the most recent one must equal $\text{memSrc}(addr)$.

---

## 4. Inductive Proof Structure

The proof must be structured using the following three helper lemmas:

```lean
-- Lemma 1: Base Case
theorem strong_inv_init : StrongInvariant InitState := by
    sorry

-- Lemma 2: Inductive Step (Preserved across all 9 transitions)
theorem strong_inv_step : ∀ s s', StrongInvariant s → Transition s s' → StrongInvariant s' := by
    sorry

-- Lemma 3: Implication (Strong invariant implies eventual consistency when quiescent)
theorem strong_inv_implies_safety : ∀ s, StrongInvariant s → EventualConsistency s := by
    sorry

-- Final Goal
theorem protocol_safe : ∀ s, Reachable s → EventualConsistency s := by
    intro s hr
    have h_strong : StrongInvariant s := by
        induction hr with
        | init => exact strong_inv_init
        | step s s' hr_prev h_trans ih => exact strong_inv_step s s' ih h_trans
    exact strong_inv_implies_safety s h_strong
```

---

## 5. Instructions for the Next LLM / Developer

1.  **Use `omega` Tactic:** Since $N$ and $DMA\_BATCH$ are symbolic, do not use `by decide`. Instead, use Lean's built-in Presburger arithmetic solver **`omega`** to handle all linear arithmetic inequalities involving boundaries.
2.  **Define Pipeline Selectors:** You will need to write helper functions/predicates in Lean to extract the "most recent write" for an address from lists of `(Nat × Nat)` (like `b1`, `b2`, and `netFifo`).
3.  **Tackle `strong_inv_step` case-by-case:** 
    *   Use `cases h_trans` to split the proof into the 9 transition cases.
    *   For each case, use `by_cases` on the boundary conditions (`addr < s.dmaC` and `addr < s.dmaD`) to analyze the address under its corresponding region invariant.
