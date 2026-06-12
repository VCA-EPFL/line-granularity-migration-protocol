# Formal Specification of the Base-and-Bound Protocol

This document provides a rigorous mathematical specification of the asynchronous Live VM Migration protocol modeled in `fsm_basebound.py`. This formulation is designed to be easily transcribed into a formal verification language such as TLA+, Event-B, or Lean 4.

---

## 1. Sets and Domains

Let $N = 128$ be the total number of memory addresses, and $BATCH = 8$ be the maximum capacity of the DMA window.

*   $A = \{0, 1, \dots, N-1\}$ represents the Memory Address Space.
*   $V = \mathbb{N}$ represents the set of possible Memory Values (monotonically increasing counters).
*   $Q[T]$ denotes the domain of FIFO sequences (queues) containing elements of type $T$.
*   $SrcType = \{DMA, MIRROR\}$ represents the source of a network packet.

**Queue Operations:** 
For any queue $q \in Q[T]$:
*   $q \ne \emptyset$ means the queue is not empty.
*   $head(q)$ returns the first element of the queue.
*   $tail(q)$ returns the queue with the first element removed.
*   $q \oplus e$ returns a new queue with element $e$ appended to the end.

---

## 2. State Space ($\Sigma$)

A global state $s \in \Sigma$ is defined by the following state variables:

### Memory State
*   $mem_{src} : A \rightarrow V$ (Source memory mapping)
*   $mem_{dst} : A \rightarrow V$ (Destination memory mapping)

### Internal Component Buffers
*   $buf_{cpu} : Q[A]$ (Stores addresses written by CPU)
*   $mir_{b1} : Q[A \times V]$ (Mirror Buffer 1: Stranded writes)
*   $mir_{b2} : Q[A \times V]$ (Mirror Buffer 2: Ready for transmission)
*   $dma_{buf} : Q[A \times V]$ (DMA Internal Buffer: Read chunks)
*   $net : Q[SrcType \times A \times V]$ (Network Hardware FIFO)

### Bounds & Handshake Variables
*   $a \in A, b \in A$ (Mirror's physical bounds representing its safe range)
*   $c \in A, d \in A \cup \{-1\}$ (DMA's active locked window)
*   $wait_{dma} \in \{True, False\}$ (Prevents DMA from emitting multiple concurrent requests)
*   $q_{req} : Q[A]$ (Interconnect: DMA requesting $d+1$)
*   $q_{grant} : Q[A]$ (Interconnect: Mirror granting $d+1$)
*   $q_{rel} : Q[A]$ (Interconnect: DMA releasing $old\_c$)

---

## 3. Helper Functions

**Mirror Range Check:**
Determines if an address $x$ is currently within the Mirror's wrapped safe range $[a, b]$.
$$ InMir(x, a, b) \triangleq (a \le b \land a \le x \le b) \lor (a > b \land (x \ge a \lor x \le b)) $$

**Buffer Sweep Operation:**
Extracts all tuples $(x, v)$ from $mir_{b1}$ where $x = c$, and appends them to $mir_{b2}$. 
(For brevity in the transitions, we denote the resulting state of the two buffers after this operation as $sweep(mir_{b1}, mir_{b2}, c)$).

---

## 4. Transitions ($\rightarrow$)

The system evolves through transitions $s \xrightarrow{T_i} s'$. 
Below, $v'$ denotes the value of variable $v$ in the next state $s'$. **Any variable not explicitly primed is assumed to remain unchanged ($v' = v$).**

### $T_1$: CpuExecutesStore
*   **Guard**: $True$
*   **Effect**: $\exists x \in A$, $buf_{cpu}' = buf_{cpu} \oplus x$

### $T_2$: MemCtrlCommits
*   **Guard**: $buf_{cpu} \ne \emptyset$
*   **Effect**: 
    Let $x = head(buf_{cpu})$
    Let $val = mem_{src}(x) + 1$
    $buf_{cpu}' = tail(buf_{cpu})$
    $mem_{src}' = mem_{src}[x \mapsto val]$
    **If** $InMir(x, a, b)$ **then**:
       $mir_{b2}' = mir_{b2} \oplus (x, val)$
    **Else**:
       $mir_{b1}' = mir_{b1} \oplus (x, val)$

### $T_3$: MirrorSends
*   **Guard**: $mir_{b2} \ne \emptyset$
*   **Effect**: 
    Let $(x, v) = head(mir_{b2})$
    $mir_{b2}' = tail(mir_{b2})$
    $net' = net \oplus (MIRROR, x, v)$

### $T_4$: DmaSendsRequest
*   **Guard**: $\neg wait_{dma} \land (d < N - 1) \land ((d - c + 1) < BATCH)$
*   **Effect**:
    $q_{req}' = q_{req} \oplus (d + 1)$
    $wait_{dma}' = True$

### $T_5$: MirrorProcessesRequest
*   **Guard**: $q_{req} \ne \emptyset \land \neg (\exists v \in V : (head(q_{req}), v) \in mir_{b2})$
    *(The Mirror refuses to fire if Buffer 2 contains pending writes for the requested address).*
*   **Effect**:
    Let $x = head(q_{req})$
    $q_{req}' = tail(q_{req})$
    $a' = (a + 1) \pmod N$
    $q_{grant}' = q_{grant} \oplus x$

### $T_6$: DmaReceivesGrant
*   **Guard**: $q_{grant} \ne \emptyset$
*   **Effect**:
    Let $x = head(q_{grant})$
    $q_{grant}' = tail(q_{grant})$
    $d' = x$
    $dma_{buf}' = dma_{buf} \oplus (x, mem_{src}(x))$
    $wait_{dma}' = False$

### $T_7$: DmaSendsAndReleases
*   **Guard**: $dma_{buf} \ne \emptyset \land \text{addr}(head(dma_{buf})) = c$
*   **Effect**:
    Let $(x, v) = head(dma_{buf})$
    $dma_{buf}' = tail(dma_{buf})$
    $net' = net \oplus (DMA, x, v)$
    $q_{rel}' = q_{rel} \oplus c$
    $c' = c + 1$

### $T_8$: MirrorProcessesRelease
*   **Guard**: $q_{rel} \ne \emptyset$
*   **Effect**:
    Let $x = head(q_{rel})$
    $q_{rel}' = tail(q_{rel})$
    $b' = (b + 1) \pmod N$
    $mir_{b1}', mir_{b2}' = sweep(mir_{b1}, mir_{b2}, x)$

### $T_9$: NetworkDelivers (Invariant Monitor)
*   **Guard**: $net \ne \emptyset$
*   **Effect**:
    Let $(src, x, v) = head(net)$
    **Assert**: $v \ge mem_{dst}(x)$ *(The Stale Overwrite safety property)*
    $net' = tail(net)$
    $mem_{dst}' = mem_{dst}[x \mapsto v]$
