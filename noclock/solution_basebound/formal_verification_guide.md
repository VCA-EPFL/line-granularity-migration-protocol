# Formal Verification Guide: VM Live Migration Protocol in Lean 4

This document serves as a handoff guide and context provider for formal verification of the asynchronous VM live migration protocol with a spatial Base-and-Bound sliding window. It summarizes the design decisions, the verification strategy, and the structure of the proof in `fsm.lean`.

---

## 1. Context & Goal

We are formally verifying an **asynchronous VM live migration protocol** that uses a **spatial Base-and-Bound sliding window** to resolve race conditions between a DMA engine (copying memory sequentially) and a Mirror engine (forwarding CPU writes). 

The goal is to prove **safety** (`Safety`): no packet in flight in the network queue (`netFifo`) contains a value older than what is already written to the destination memory (`memDest`). If this holds, the destination memory never undergoes a stale overwrite.

---

## 2. Key Lean 4 Design Decisions

### A. Pure `Nat` Representation (The Shifting Trick)
In the original Python simulation (`fsm_basebound.py`), the DMA's grant index `dma_d` is initialized to `-1` (meaning no memory has been granted yet). 

Since Lean's natural number type `Nat` cannot represent negative numbers, we shifted the semantics of `dmaD` in `fsm.lean`:
*   **Definition:** `dmaD` is defined as the **next address to request** (an exclusive upper bound) rather than the *last granted address* (an inclusive upper bound).
*   **Benefit:** Both `dmaC` (release pointer) and `dmaD` are now pure `Nat` values starting at `0`.
*   **Underflow Prevention:** The active sliding window size check in `dmaSendReq` is written as `s.dmaD - s.dmaC < DMA_BATCH`. Since `s.dmaD ≥ s.dmaC` is an invariant of the protocol, this subtraction never underflows in `Nat`.
*   This completely eliminates type coercions (like `(N : Int)`) and `Option` unwrapping, making the proof tactics much cleaner.

### B. State-based vs. Trace-based Safety
While we could model safety by looking at the stream of network packets as an infinite trace, we retain `memDest` in the state structure. It acts as a **state-based accumulator** of the FIFO network queue. Reasoning about the maximum value in `memDest` is much easier in Lean than reasoning about inductive properties of infinite lists/traces.

---

## 3. Verification Strategy: Invariant Strengthening

The safety property `Safety` is **not inductive** on its own. For example, if we only know that the current packets in `netFifo` are safe, we cannot prove that a new packet popped from a local buffer `b2` and pushed to `netFifo` (via `mirrorSend`) will be safe, because `Safety` does not constrain `b2`.

To make the proof inductive, we strengthen the property using a piecewise predicate over the entire address space:

### `AddressInvariant (s : State) (addr : Nat) : Prop`
For any address `addr` (from `0` to `N-1`), it must fall into one of three regions:

1.  **Region 1 (`addr < s.dmaC`): DMA has passed**
    *   The DMA has completed and released this address. The Mirror is active again.
    *   *Invariant:* Any in-flight packets (Mirror or DMA) and any writes in `b2` for this address must be safe (values $\ge$ `memDest`).

2.  **Region 2 (`s.dmaC ≤ addr < s.dmaD`): DMA owns the address (Range Locked)**
    *   The DMA has been granted access to this address. The Mirror's updates are locked in `b1` and cannot be moved to `b2` or sent.
    *   *Invariant:* There must be **no** writes for this address in `b2`, and **no** Mirror packets for this address in the network queue (`netFifo` packets for this address must be of type `DMA`).

3.  **Region 3 (`addr ≥ s.dmaD`): DMA has not reached**
    *   The DMA has not requested this address yet.
    *   *Invariant:* Mirror writes flow normally. There must be **no** DMA packets in flight in `netFifo` or sitting in the DMA's internal buffer `dmaBuf` for this address.

### `StrongInvariant (s : State) : Prop`
Asserts that `AddressInvariant` holds for all `addr < N`.

---

## 4. Inductive Proof Plan

The proof must be structured using the following three helper lemmas to avoid the induction trap:

```lean
-- Lemma 1: Base Case (Initial state satisfies the strong invariant)
theorem strong_inv_init : StrongInvariant InitState := by
    sorry

-- Lemma 2: Inductive Step (Every transition preserves the strong invariant)
theorem strong_inv_step : ∀ s s', StrongInvariant s → Transition s s' → StrongInvariant s' := by
    sorry

-- Lemma 3: Implication (The strong invariant implies the safety property)
theorem strong_inv_implies_safety : ∀ s, StrongInvariant s → Safety s := by
    sorry
```

Once these three lemmas are proved, the main theorem is proved by showing `StrongInvariant` holds for all reachable states via induction, then applying Lemma 3:

```lean
theorem protocol_safe : ∀ s, Reachable s → Safety s := by
    intro s hr
    have h_strong : StrongInvariant s := by
        induction hr with
        | init => exact strong_inv_init
        | step s s' hr_prev h_trans ih => exact strong_inv_step s s' ih h_trans
    exact strong_inv_implies_safety s h_strong
```

---

## 5. Instructions for the Next LLM / Developer

When you pick up this task:
1.  **Start with `strong_inv_implies_safety`:** This is the easiest lemma. Use `intro`, unfold `StrongInvariant`, and specialize the hypothesis for `addr` using the cases in `AddressInvariant`.
2.  **Prove `strong_inv_init`:** All list variables are `[]` and memories are `0` initially. The proof should resolve quickly using basic list simplifications (`simp`).
3.  **Tackle `strong_inv_step` case-by-case:** 
    *   Use `intro s s' h_inv h_trans`.
    *   Deconstruct the transition using `cases h_trans`. This will yield 9 sub-goals (one for each constructor of `Transition`).
    *   For each case, show that for any `addr < N`, the new state $s'$ preserves `AddressInvariant`.
    *   Use the tactic `by_cases` on the boundary relations (e.g. `addr < s.dmaC` and `addr < s.dmaD`) to map the address to its correct region.
    *   Useful Lean 4 tactics to try: `simp`, `aesop`, `omega` (for linear integer/natural arithmetic), and `cases` for list memberships.
