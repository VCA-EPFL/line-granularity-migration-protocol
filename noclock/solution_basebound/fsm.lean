opaque N : Nat
axiom hN : 0 < N
opaque DMA_BATCH : Nat
axiom hBatch : 0 < DMA_BATCH

inductive NetReq where
| Mirror
| DMA

structure State where
    memSrc : Nat → Nat
    memDest : Nat → Nat
    cpuFifo : List (Nat × Nat)
    dmaDRequestBuffer : List Nat
    grantFifo : List Nat
    releaseFifo : List Nat
    dmaWait : Bool
    b1 : List (Nat × Nat)
    b2 : List (Nat × Nat)
    mirrorA : Fin N
    mirrorB : Fin N
    netFifo : List (NetReq × Nat × Nat)
    dmaC : Nat -- Release pointer (address of next chunk to release from DMA to Mirror)
    dmaD : Nat -- Next address to request (exclusive bound; starts at 0, replacing Python's inclusive -1)
    dmaBuf : List (Nat × Nat)

def State.isInRange (s : State) (addr : Nat) :=
    if s.mirrorA ≤ s.mirrorB then
        s.mirrorA.val ≤ addr && addr ≤ s.mirrorB.val
    else
        addr ≤ s.mirrorB.val || s.mirrorA.val ≤ addr

inductive Transition : State → State → Prop where
| cpuExecuteStore : ∀ s addr val,
    Transition s {s with cpuFifo := s.cpuFifo ++ [(addr, val)]}

| commitStore : ∀ s s' addr val tl b1' b2',
    s.cpuFifo = (addr, val) :: tl
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
    → s.dmaD < N
    → (s.dmaD - s.dmaC) < DMA_BATCH
    → d' = s.dmaD
    → Transition s {s with dmaWait := true, dmaDRequestBuffer := s.dmaDRequestBuffer ++ [d']}

| mirrorProcReq : ∀ s targetD tl,
    s.dmaDRequestBuffer = targetD :: tl
    → List.all s.b2 (fun (b2addr, _) => targetD ≠ b2addr)
    → Transition s {s with dmaDRequestBuffer := tl, mirrorA := s.mirrorA + ⟨1 % N, Nat.mod_lt 1 hN⟩, grantFifo := s.grantFifo ++ [targetD]}

| receiveGrant : ∀ s targetD tl val,
    s.grantFifo = targetD :: tl
    → val = s.memSrc targetD
    → Transition s {s with dmaD := targetD + 1, dmaBuf := s.dmaBuf ++ [(targetD, val)], dmaWait := false}

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
        mirrorB := s.mirrorB + ⟨1 % N, Nat.mod_lt 1 hN⟩,
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
    dmaDRequestBuffer     := []
    grantFifo   := []
    releaseFifo := []
    dmaWait     := false
    b1          := []
    b2          := []
    mirrorA     := ⟨0, hN⟩
    mirrorB     := ⟨N - 1, Nat.sub_lt hN Nat.zero_lt_one⟩
    netFifo     := []
    dmaC        := 0
    dmaD        := 0
    dmaBuf      := []

-- 2. Inductive definition of all reachable states from InitState
inductive Reachable : State → Prop where
| init : Reachable InitState
| step : ∀ s s', Reachable s → Transition s s' → Reachable s'

-- ==========================================
-- Pipeline Helpers for Address Invariant
-- ==========================================

def sourceStoreVal (s : State) (addr : Nat) : Nat :=
  s.memSrc addr

def lastB1Val (s : State) (addr : Nat) : Option Nat :=
  (s.b1.reverse.find? (fun (a, _) => a == addr)).map Prod.snd

def lastB2Val (s : State) (addr : Nat) : Option Nat :=
  (s.b2.reverse.find? (fun (a, _) => a == addr)).map Prod.snd

def lastNetVal (s : State) (addr : Nat) : Option Nat :=
  (s.netFifo.reverse.find? (fun (_, a, _) => a == addr)).map (fun (_, _, v) => v)

def PipelineEquivalence (s : State) (addr : Nat) : Prop :=
  let t := sourceStoreVal s addr
  match lastB2Val s addr with
  | some vb2 => vb2 = t
  | none =>
    match lastNetVal s addr with
    | some vnet => vnet = t
    | none => s.memDest addr = t

def LockedPipelineEquivalence (s : State) (addr : Nat) : Prop :=
  let t := sourceStoreVal s addr
  match lastB1Val s addr with
  | some vb1 => vb1 = t
  | none =>
    match lastNetVal s addr with
    | some vnet => vnet = t
    | none => s.memDest addr = t

-- 3. Piecewise Strong Invariant for Inductive Proof
def AddressInvariant (s : State) (addr : Nat) : Prop :=
    if s.dmaC ≤ addr ∧ addr < s.dmaD then
        -- Region 1: DMA owns this address (Range locked)
        (∀ val, (addr, val) ∉ s.b2) ∧
        LockedPipelineEquivalence s addr
    else
        -- Region 2: Outside DMA lock (DMA has not reached yet OR DMA has passed)
        (∀ val, (addr, val) ∉ s.dmaBuf) ∧
        (∀ val, (addr, val) ∉ s.b1) ∧
        PipelineEquivalence s addr

def StrongInvariant (s : State) : Prop :=
    s.dmaC ≤ s.dmaD ∧ s.dmaD ≤ N ∧
    ∀ addr, addr < N → AddressInvariant s addr

-- ==========================================
-- Formal Verification Proofs
-- ==========================================

-- 1. Base Case: Initial state satisfies StrongInvariant
theorem strong_inv_init : StrongInvariant InitState := by
  unfold StrongInvariant
  refine ⟨by dsimp [InitState]; omega, ⟨by dsimp [InitState]; omega, ?_⟩⟩
  intro addr _
  unfold AddressInvariant
  have h_not_locked : ¬ (InitState.dmaC ≤ addr ∧ addr < InitState.dmaD) := by
    dsimp [InitState]
    omega
  rw [if_neg h_not_locked]
  exact ⟨by simp [InitState], by simp [InitState], by dsimp [InitState, PipelineEquivalence, sourceStoreVal, lastB2Val, lastNetVal]⟩


theorem strong_inv_step: ∀ s s', StrongInvariant s → Transition s s' → StrongInvariant s' := by
  intro s s' hs h_trans
  cases h_trans
  case cpuExecuteStore addr val =>
    exact hs
  case commitStore => sorry
  case mirrorSend addr val tl h_b2 =>
    refine ⟨?_, ?_, ?_⟩
    ·   simp
        exact hs.1
    ·   simp
        exact hs.2.1
    ·   intro addr' h_addr_bound
        unfold AddressInvariant
        simp
        by_cases h_cond: s.dmaC ≤ addr ∧ addr < s.dmaD
        ·   sorry
        ·   sorry

  case dmaSendReq h_g1 h_g2 h_g3 h_eq =>
    exact hs
  case mirrorProcReq targetD tl h_split h_eq=>
    exact hs
  case receiveGrant => sorry
  case sendAndRelease => sorry
  case procRelease => sorry
  case networkDeliver => sorry

def EventualConsistency (s : State) : Prop :=
    (s.cpuFifo = [] ∧ s.b1 = [] ∧ s.b2 = [] ∧ s.dmaBuf = [] ∧ s.netFifo = [] ∧ s.dmaDRequestBuffer = [] ∧ s.grantFifo = [] ∧ s.releaseFifo = [])
    → s.memDest = s.memSrc

-- 5. The Goal Theorem for Formal Proof
theorem protocol_safe : ∀ s, Reachable s → EventualConsistency s := by
    sorry
