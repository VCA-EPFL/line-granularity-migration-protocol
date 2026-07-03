abbrev N := 128
abbrev DMA_BATCH := 8

inductive NetReq where
| Mirror
| DMA

structure State where
    memSrc : Nat → Nat
    memDest : Nat → Nat
    cpuFifo : List Nat
    dmaFifo : List Nat
    grantFifo : List Nat
    releaseFifo : List Nat
    dmaWait : Bool
    b1 : List (Nat × Nat)
    b2 : List (Nat × Nat)
    mirrorA : Fin N
    mirrorB : Fin N
    netFifo : List (NetReq × Nat × Nat)
    dmaC : Nat
    dmaD : Nat
    dmaBuf : List (Nat × Nat)

def State.isInRange (s : State) (addr : Nat) :=
    if s.mirrorA ≤ s.mirrorB then
        s.mirrorA.val ≤ addr && addr ≤ s.mirrorB.val
    else
        addr ≤ s.mirrorB.val || s.mirrorA.val ≤ addr

inductive Transition : State → State → Prop where
| cpuExecuteStore : ∀ s s' addr,
    s' = {s with cpuFifo := s.cpuFifo ++ [addr]} → Transition s s'

| commitStore : ∀ s s' addr tl b1' b2' val,
    s.cpuFifo = addr :: tl
    → val = s.memSrc addr + 1
    → (if s.isInRange addr then
        b2' = s.b2 ++ [(addr, val)] ∧ b1' = s.b1
      else
        b1' = s.b1 ++ [(addr, val)] ∧ b2' = s.b2)
    → s' = {s with
        cpuFifo := tl,
        b1 := b1',
        b2 := b2',
        memSrc := fun x => if x == addr then val else s.memSrc x
      }
    → Transition s s'

| mirrorSend : ∀ s addr val tl,
    s.b2 = (addr, val) :: tl
    → Transition s {s with b2 := tl, netFifo := s.netFifo ++ [(NetReq.Mirror, addr, val)]}

| dmaSendReq : ∀ s d',
    ¬ s.dmaWait
    → s.dmaD < (N : Int) - 1
    → (s.dmaD - s.dmaC + 1) < (DMA_BATCH : Int)
    → d' = s.dmaD + 1
    → Transition s {s with dmaWait := true, dmaFifo := s.dmaFifo ++ [d']}

| mirrorProcReq : ∀ s targetD tl,
    s.dmaFifo = targetD :: tl
    → List.all s.b2 (fun (a, _) => targetD ≠ a)
    → Transition s {s with dmaFifo := tl, mirrorA := s.mirrorA + 1, grantFifo := s.grantFifo ++ [targetD]}

| receiveGrant : ∀ s targetD tl val,
    s.grantFifo = targetD :: tl
    → val = s.memSrc targetD
    → Transition s {s with dmaD := targetD, dmaBuf := s.dmaBuf ++ [(targetD, val)], dmaWait := false}

| sendAndRelease : ∀ s addr val tl,
    s.dmaBuf = (addr, val) :: tl
    → addr = s.dmaC
    → Transition s {s with
        dmaBuf := tl,
        netFifo := s.netFifo ++ [(NetReq.DMA, addr, val)],
        dmaC := s.dmaC + 1,
        releaseFifo := s.releaseFifo ++ [s.dmaC]
      }

| procRelease : ∀ s c tl l1 l2,
    s.releaseFifo = c :: tl
    → (l1, l2) = List.partition (fun (a, _) => a == c) s.b1
    → Transition s {s with
        b1 := l2,
        b2 := s.b2 ++ l1,
        mirrorB := s.mirrorB + 1,
        releaseFifo := tl
      }

| networkDeliver : ∀ s ty addr val tl,
    s.netFifo = (ty, addr, val) :: tl
    → Transition s {s with memDest := fun x => if x == addr then val else s.memDest x}

-- ==========================================
-- Formal Verification Setup
-- ==========================================

-- 1. Initial State definition
def InitState : State where
    memSrc      := fun _ => 0
    memDest     := fun _ => 0
    cpuFifo     := []
    dmaFifo     := []
    grantFifo   := []
    releaseFifo := []
    dmaWait     := false
    b1          := []
    b2          := []
    mirrorA     := ⟨0, by decide⟩
    mirrorB     := ⟨N - 1, by decide⟩
    netFifo     := []
    dmaC        := 0
    dmaD        := -1
    dmaBuf      := []

-- 2. Inductive definition of all reachable states from InitState
inductive Reachable : State → Prop where
| init : Reachable InitState
| step : ∀ s s', Reachable s → Transition s s' → Reachable s'

-- 3. Safety Invariant: No packet in flight contains a value older than what is already at the destination memory
def Safety (s : State) : Prop :=
    ∀ ty addr val, (ty, addr, val) ∈ s.netFifo → val ≥ s.memDest addr

-- 4. The Goal Theorem for Formal Proof
theorem protocol_safe : ∀ s, Reachable s → Safety s := by
    sorry
