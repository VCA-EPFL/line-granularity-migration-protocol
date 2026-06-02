import random

N = 128
DMA_BATCH = 8

class GlobalState:
    """The snapshot of the base-and-bound generalized protocol."""
    def __init__(self):
        self.source_mem = [0] * N
        self.dest_mem = [0] * N
        
        # Mirror Buffers
        self.mirror_b1 = [] # Buffer 1: Catches stranded stores
        self.mirror_b2 = [] # Buffer 2: Eligible for network transmission
        
        # Mirror's explicit view of its safe range [a, b]
        # Initially, the Mirror safely owns all of memory (0 to 127)
        self.mirror_a = 0
        self.mirror_b = N - 1
        
        # Network (Modeled as a FIFO Queue)
        self.network_queue = [] # list of ("MIRROR"/"DMA", addr, val)
        
        # DMA Window (Initially empty, expands to DMA_BATCH)
        self.dma_c = 0
        self.dma_d = -1  
        self.dma_internal_buffer = [] # list of (addr, val)

    def is_in_mirror_range(self, addr):
        # The mirror ONLY uses its own a and b registers to filter writes!
        if self.mirror_a <= self.mirror_b:
            return self.mirror_a <= addr <= self.mirror_b
        else:
            # The range wraps around the end of the memory array
            return addr >= self.mirror_a or addr <= self.mirror_b

    def __repr__(self):
        return f"DMA[{self.dma_c}..{self.dma_d}] | Mirror[{self.mirror_a}..{self.mirror_b}] | NetQueue:{len(self.network_queue)} | B1:{len(self.mirror_b1)} B2:{len(self.mirror_b2)}"

class Transitions:
    @staticmethod
    def storer_writes(state: GlobalState):
        # Guard: Storer can theoretically always write.
        def effect():
            addr = random.randint(0, N - 1)
            state.source_mem[addr] += 1
            val = state.source_mem[addr]
            
            # The Mirror uses its own physical [a, b] bounds to route the write
            if state.is_in_mirror_range(addr):
                # Safe to transmit
                state.mirror_b2.append((addr, val))
            else:
                # Outside Mirror's range (DMA holds the lock). Strand it in Buffer 1.
                state.mirror_b1.append((addr, val))
                
            return f"Storer wrote {val} to addr {addr}"
        return effect

    @staticmethod
    def mirror_sends(state: GlobalState):
        # Guard: Mirror buffer must have items waiting
        if len(state.mirror_b2) > 0:
            def effect():
                addr, val = state.mirror_b2.pop(0)
                state.network_queue.append(("MIRROR", addr, val))
                return f"Mirror sent {val} for addr {addr}"
            return effect
        return None

    @staticmethod
    def dma_requests_d(state: GlobalState):
        # Guard: DMA wants to expand its window, up to DMA_BATCH size
        if state.dma_d < N - 1 and (state.dma_d - state.dma_c + 1) < DMA_BATCH:
            target_d = state.dma_d + 1
            
            # THE HANDSHAKE: DMA politely asks Mirror for target_d.
            # Mirror checks if it has pending transmissions for target_d in B2.
            has_pending = any(a == target_d for (a, v) in state.mirror_b2)
            
            if not has_pending:
                def effect():
                    # 1. Mirror yields target_d by shrinking the front of its range [a]
                    state.mirror_a = (state.mirror_a + 1) % N
                    
                    # 2. DMA takes ownership
                    state.dma_d += 1
                    
                    # 3. DMA reads the newly acquired address
                    val = state.source_mem[state.dma_d]
                    state.dma_internal_buffer.append((state.dma_d, val))
                    
                    return f"Handshake: Mirror yielded {target_d} (a={state.mirror_a}). DMA expanded lock to {state.dma_d}"
                return effect
        return None

    @staticmethod
    def dma_sends_c(state: GlobalState):
        # Guard: DMA has data to send
        if len(state.dma_internal_buffer) > 0:
            addr, val = state.dma_internal_buffer[0]
            if addr == state.dma_c:
                def effect():
                    # 1. Transmit
                    state.dma_internal_buffer.pop(0)
                    state.network_queue.append(("DMA", addr, val))
                    
                    # 2. Release old_c, increment c
                    old_c = state.dma_c
                    state.dma_c += 1
                    
                    # 3. Mirror claims old_c by expanding the back of its range [b]
                    state.mirror_b = (state.mirror_b + 1) % N
                    
                    # 4. Mirror Sweep: Find stranded writes for old_c in B1, move to B2
                    swept = []
                    remaining = []
                    for (a, v) in state.mirror_b1:
                        if a == old_c:
                            swept.append((a, v))
                        else:
                            remaining.append((a, v))
                    
                    state.mirror_b1 = remaining
                    state.mirror_b2.extend(swept)
                    
                    return f"Handshake: DMA released {old_c}. Mirror claimed it (b={state.mirror_b}) and swept {len(swept)} writes."
                return effect
        return None

    @staticmethod
    def network_delivers(state: GlobalState):
        if len(state.network_queue) > 0:
            def effect():
                # FIFO Delivery: Because DMA and Mirror share the same hardware queue!
                packet_type, addr, val = state.network_queue.pop(0)
                
                # Invariant Check
                if val < state.dest_mem[addr]:
                    raise AssertionError(f"BUG DETECTED! Stale overwrite via {packet_type} at addr {addr}. Current: {state.dest_mem[addr]}, Incoming: {val}")
                
                state.dest_mem[addr] = val
                return f"Network delivered {val} for addr {addr} via {packet_type}"
            return effect
        return None

def run_basebound_fsm(steps=5000):
    # Fixed seed for reproducibility
    random.seed(42)
    state = GlobalState()
    
    all_transitions = [
        Transitions.storer_writes,
        Transitions.mirror_sends,
        Transitions.dma_requests_d,
        Transitions.dma_sends_c,
        Transitions.network_delivers
    ]
    
    print("Starting Explicit Base & Bound FSM Random Walk...\n")
    try:
        for step in range(steps):
            enabled_effects = [t(state) for t in all_transitions if t(state) is not None]
            
            if not enabled_effects:
                print("Deadlock reached!")
                break
                
            chosen = random.choice(enabled_effects)
            desc = chosen()
            
            # Print every 500 steps to show progress
            if step % 500 == 0:
                print(f"Step {step}: {desc}")
                print(f"  {state}")
                
    except AssertionError as e:
        print(f"\n\033[91m{e}\033[0m")
        return

    print(f"\n\033[92mSuccess! Finished {steps} steps safely. No bugs detected!\033[0m")
    print(f"Final State: {state}")

if __name__ == "__main__":
    run_basebound_fsm()
