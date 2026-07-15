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
    dmaFifo : List Nat
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
| cpuExecuteStore : ∀ s s' addr val,
    s' = {s with cpuFifo := s.cpuFifo ++ [(addr, val)]} → Transition s s'

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
    → Transition s {s with dmaWait := true, dmaFifo := s.dmaFifo ++ [d']}

| mirrorProcReq : ∀ s targetD tl,
    s.dmaFifo = targetD :: tl
    → List.all s.b2 (fun (a, _) => targetD ≠ a)
    → Transition s {s with dmaFifo := tl, mirrorA := s.mirrorA + ⟨1 % N, Nat.mod_lt 1 hN⟩, grantFifo := s.grantFifo ++ [targetD]}

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
    dmaFifo     := []
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

-- 3. Piecewise Strong Invariant for Inductive Proof (Placeholder for rewrite)
def AddressInvariant (s : State) (addr : Nat) : Prop :=
    if addr < s.dmaC then
        -- REGION 1: DMA has passed this address
        (∀ val, (NetReq.Mirror, addr, val) ∈ s.netFifo → val ≥ s.memDest addr) ∧
        (∀ val, (NetReq.DMA, addr, val) ∈ s.netFifo → val ≥ s.memDest addr) ∧
        (∀ val, (addr, val) ∈ s.b2 → val ≥ s.memDest addr)
    else if addr < s.dmaD then
        -- REGION 2: DMA owns this address (Range locked)
        (∀ val, (addr, val) ∉ s.b2) ∧
        (∀ ty val, (ty, addr, val) ∈ s.netFifo → ty = NetReq.DMA)
    else
        -- REGION 3: DMA has not reached this address yet
        (∀ val, (NetReq.Mirror, addr, val) ∈ s.netFifo → val ≥ s.memDest addr) ∧
        (∀ val, (addr, val) ∈ s.b2 → val ≥ s.memDest addr) ∧
        (∀ val, (addr, val) ∉ s.dmaBuf) ∧
        (∀ ty val, (ty, addr, val) ∈ s.netFifo → ty = NetReq.Mirror)

def StrongInvariant (s : State) : Prop :=
    ∀ addr, addr < N → AddressInvariant s addr

-- 4. Eventual Consistency Invariant: When the system is quiescent, destination memory equals source memory
def EventualConsistency (s : State) : Prop :=
    (s.cpuFifo = [] ∧ s.b1 = [] ∧ s.b2 = [] ∧ s.dmaBuf = [] ∧ s.netFifo = [] ∧ s.dmaFifo = [] ∧ s.grantFifo = [] ∧ s.releaseFifo = [])
    → s.memDest = s.memSrc

-- 5. The Goal Theorem for Formal Proof
theorem protocol_safe : ∀ s, Reachable s → EventualConsistency s := by
    sorry
