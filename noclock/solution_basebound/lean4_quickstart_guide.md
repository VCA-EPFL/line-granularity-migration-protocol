# Lean 4 Quickstart, Terminology & Tactics Guide

This guide explains the core concepts, terminology ("lingo"), keywords, and tactics used in formally verifying the line-granularity VM live migration protocol in Lean 4.

---

## 1. Fundamental Terminology ("The Lingo")

### **Proposition (`Prop`)**
A mathematical claim or assertion that can be either **True** or **False**.
* **Examples**: `2 + 2 = 4`, `s.dmaC ≤ s.dmaD`, `PipelineEquivalence s addr`.
* In Lean, `Prop` is the type of logical statements.

### **Proof & Proof Term**
A valid mathematical argument or evidence showing that a Proposition is True. In Lean, a proof is a data term whose type is the proposition it proves (Curry-Howard Isomorphism).

### **Theorem vs. Lemma**
* **Theorem**: A main, top-level mathematical result or ultimate safety goal (e.g., `protocol_safe`).
* **Lemma**: A smaller helper result or stepping stone used to prove a larger theorem (e.g., `strong_inv_init`, `strong_inv_step`).
* *Note*: In Lean 4, the keywords `theorem` and `lemma` are completely interchangeable synonyms!

### **Tactic & Tactic Mode (`by`)**
* **Tactic**: An interactive command used inside a `by` block that tells Lean's proof engine how to transform or simplify the proof goal step-by-step.
* **Tactic Mode**: Writing code inside `by ...` blocks where tactics manipulate the goal.

### **Goal & Context (Hypotheses)**
During interactive proving, Lean displays an **InfoView**:
* **Hypotheses (Context)**: Variables and known facts listed above the `⊢` symbol (e.g., `addr : Nat`, `h : addr < N`).
* **Goal**: The statement listed below the `⊢` symbol that you must prove (e.g., `⊢ AddressInvariant s addr`).

### **Inductive Invariant**
A state property $P(s)$ that guarantees safety across all reachable states of a system:
1. **Base Case**: $P(s)$ holds in the initial state (`InitState`).
2. **Inductive Step**: If $P(s)$ holds in state $s$ and a transition $s \to s'$ occurs, $P(s')$ holds in state $s'$.

### **Quiescence & Eventual Consistency**
* **Quiescence**: A state where all interconnect queues/buffers (`cpuFifo`, `b1`, `b2`, `dmaBuf`, `netFifo`) are completely empty `[]`.
* **Eventual Consistency**: The safety theorem asserting that whenever the system is quiescent, destination memory equals source memory (`memDest = memSrc`).

---

## 2. Core Lean 4 Keywords & Definitions

### `def` (Definitions: Functions vs. Propositions)
In Lean 4, `def` defines both **computational functions** and **logical propositions**.

#### A. Computation / Function (`def ... : Data`)
Returns actual data values (numbers, options, lists).
```lean
def lastB2Val (s : State) (addr : Nat) : Option Nat :=
  (s.b2.reverse.find? (fun (a, _) => a == addr)).map Prod.snd
```
* **Return type**: `: Option Nat` (data).
* **Python equivalent**: `def last_b2_val(s, addr) -> Optional[int]: ...`

#### B. Proposition / Logical Rule (`def ... : Prop`)
Returns a mathematical claim that is either True or False.
```lean
def PipelineEquivalence (s : State) (addr : Nat) : Prop :=
  let t := sourceStoreVal s addr
  match lastB2Val s addr with
  | some vb2 => vb2 = t
  | none => s.memDest addr = t
```
* **Return type**: `: Prop` (Proposition).
* **Python equivalent**: An `assert(...)` or boolean assertion.

---

### `match ... with` (Pattern Matching)
Deconstructs data structures like `Option` (`some v` vs `none`), `List` (`[]` vs `x::xs`), or tuples.

```lean
match lastB2Val s addr with
| some vb2 => vb2 = t    -- Case 1: write exists in b2; demand vb2 = t
| none     =>            -- Case 2: b2 is empty for addr; try next source
  match lastNetVal s addr with
  | some vnet => vnet = t
  | none      => s.memDest addr = t
```
* **Note**: Right-hand side of `=>` in a `: Prop` definition can be any logical claim (`=`, `≥`, `<`, `∧`, `∨`).

---

### `structure` & `inductive`
* **`structure`**: Defines a record/class with named fields (e.g. `State`).
* **`inductive`**: Defines algebraic data types or state machine transition rules (e.g. `Transition`).

---

## 3. Essential Lean 4 Tactics Cheat Sheet

Tactics are commands used inside a `by` block to simplify or transform the **Goal**.

| Tactic | What it does | Concrete Example |
| :--- | :--- | :--- |
| **`unfold P`** | Replaces definition name `P` with its full body. | `unfold StrongInvariant` expands the invariant formula. |
| **`dsimp [P]`** | Definitional Simplification. Evaluates terms like `InitState`. | `dsimp [InitState]` turns `InitState.dmaC` into `0`. |
| **`simp`** | Automatic simplifier. Cleans up lists, logic, and standard lemmas. | `simp` turns `(addr, val) ∈ []` into `False`. |
| **`rw [h]`** | Rewrite. Replaces left-hand side of equality `h : A = B` with `B`. | `rw [if_neg h]` simplifies `if False then X else Y` to `Y`. |
| **`refine ⟨a, b, c⟩`** | Proves split goals ($A \land B \land C$). | `refine ⟨proof1, ⟨proof2, proof3⟩⟩` proves 3 parts of AND. |
| **`exact term`** | Completes goal if you have the exact proof term. | `exact strong_inv_init` finishes goal using `strong_inv_init`. |
| **`intro x`** | Moves `∀ x` or `A → B` from Goal into local context hypotheses. | Goal `∀ addr, addr < N → P` creates variable `addr : Nat`. |
| **`cases h`** | Case-splits a hypothesis (e.g. `Option`, `List`, `Transition`). | `cases h_trans` splits proof into 9 transition cases. |
| **`by_cases h : C`** | Splits proof into 2 branches: $C$ is True vs $C$ is False. | `by_cases h : s.dmaC ≤ addr ∧ addr < s.dmaD` |
| **`omega`** | Solves linear arithmetic automatically ($+$, $-$, $\le$, $<$, $=$). | Proves `0 ≤ 0` or derives `False` from `0 < 0`. |

---

## 4. Understanding Tactic Differences (`rw` vs `simp` vs `dsimp` vs `unfold`)

### A. `rw [h]` vs `simp` vs `dsimp`

| Tactic | Needs a specific rule? | Does logical reasoning? | Main Use Case |
| :--- | :--- | :--- | :--- |
| **`rw [h]`** | **Yes** (you provide hypothesis `h : A = B`) | No (surgical search-and-replace) | Replace $A$ with $B$ using an explicit equality rule. |
| **`simp`** | No (searches Lean's lemma library) | **Yes** (solves obvious goals) | Automatically simplify list, boolean, and logical expressions. |
| **`dsimp [X]`**| **Yes** (you name the definition `X`) | No (evaluates code structures) | Expand/unwrap struct fields like `InitState.dmaC` to `0`. |

### B. `unfold` vs `dsimp`

* **`unfold DefName`**:
  * Targets a **named definition or function** (`unfold StrongInvariant`) and replaces the name with its definition body.
  * Does **not** attempt to evaluate nested record fields or pattern matches inside the body.
* **`dsimp [DefName]`**:
  * Performs **definitional simplification**.
  * Replaces `DefName` AND recursively evaluates record fields (e.g. `InitState.dmaC` $\to$ `0`) and function applications.

---

## 5. Example Tactic Walkthrough (`strong_inv_init`)

Here is how tactics solved the Base Case theorem line-by-line:

```lean
theorem strong_inv_init : StrongInvariant InitState := by
  -- 1. Expand the definition of StrongInvariant
  unfold StrongInvariant
  
  -- 2. Split StrongInvariant into its 3 parts: dmaC ≤ dmaD, dmaD ≤ N, and AddressInvariant
  refine ⟨by dsimp [InitState]; omega, ⟨by dsimp [InitState]; omega, ?_⟩⟩
  
  -- 3. Introduce variable 'addr' and assumption 'addr < N'
  intro addr _
  
  -- 4. Expand AddressInvariant definition
  unfold AddressInvariant
  
  -- 5. Prove that the lock condition (0 ≤ addr < 0) is false at Init
  have h_not_locked : ¬ (InitState.dmaC ≤ addr ∧ addr < InitState.dmaD) := by
    dsimp [InitState]
    omega
    
  -- 6. Rewrite the if-then-else to take the 'else' (unlocked) branch
  rw [if_neg h_not_locked]
  
  -- 7. Prove the 3 unlocked conditions: empty dmaBuf, empty b1, and PipelineEquivalence
  exact ⟨by simp [InitState], by simp [InitState], by dsimp [InitState, PipelineEquivalence, sourceStoreVal, lastCpuFifoVal, lastB2Val, lastNetVal]⟩
```

---

## 6. Overall Inductive Proof Architecture

```
                  ┌──────────────────────┐
                  │      InitState       │
                  └──────────┬───────────┘
                             │
                             ▼
                 [1. strong_inv_init (Base Case)]
                             │
                             ▼
                   StrongInvariant InitState
                             │
                             ▼
   s  ──── [Transition s s'] ────►  s'
   │                                 │
   ▼                                 ▼
StrongInvariant s  ──[3. strong_inv_step (Inductive Step)]──► StrongInvariant s'
                             │
                             ▼
                 ∀ s, Reachable s → StrongInvariant s
                             │
                             ▼
           [2. strong_inv_implies_eventual (Implication)]
                             │
                             ▼
                 ∀ s, Reachable s → EventualConsistency s
```
