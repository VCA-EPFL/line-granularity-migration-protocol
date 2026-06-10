import random

N = 128
DMA_BATCH = 8

class GlobalState:
    """The snapshot of the base-and-bound generalized protocol with internal chip latency."""
    def __init__(self):
        self.source_mem = [0] * N
        self.dest_mem = [0] * N
        
        # --- NEW: Chip Internal Interconnect Buffers ---
        self.cpu_store_buffer = [] # FIFO: CPU writes wait here before hitting memory
        self.dma_to_mirror_req = [] # FIFO: DMA requesting d+1
        self.mirror_to_dma_grant = [] # FIFO: Mirror granting d+1
        self.dma_to_mirror_release = [] # FIFO: DMA releasing old_c
        
        # We need to track if DMA is already waiting for a grant to avoid spamming
        self.dma_waiting_for_grant = False 
        
        # Mirror Buffers
        self.mirror_b1 = [] # Buffer 1: Catches stranded stores (Append-only Log)
        self.mirror_b2 = [] # Buffer 2: Eligible for network transmission
        
        # Mirror's explicit view of its safe range [a, b]
        self.mirror_a = 0
        self.mirror_b = N - 1
        
        # Network (Modeled as a FIFO Queue)
        self.network_queue = [] # list of ("MIRROR"/"DMA", addr, val)
        
        # DMA Window
        self.dma_c = 0
        self.dma_d = -1  
        self.dma_internal_buffer = [] # list of (addr, val)

    def is_in_mirror_range(self, addr):
        if self.mirror_a <= self.mirror_b:
            return self.mirror_a <= addr <= self.mirror_b
        else:
            return addr >= self.mirror_a or addr <= self.mirror_b

    def __repr__(self):
        return f"DMA[{self.dma_c}..{self.dma_d}] | Mirror[{self.mirror_a}..{self.mirror_b}] | SB:{len(self.cpu_store_buffer)} | Net:{len(self.network_queue)}"

class Transitions:
    # 1. CPU generates a write and puts it in its local store buffer
    @staticmethod
    def cpu_executes_store(state: GlobalState):
        def effect():
            addr = random.randint(0, N - 1)
            state.cpu_store_buffer.append(addr)
            return f"CPU executed store for addr {addr} (queued in Store Buffer)"
        return effect

    # 2. Memory Controller drains the store buffer, updating memory and Mirror
    @staticmethod
    def mem_controller_commits_store(state: GlobalState):
        if len(state.cpu_store_buffer) > 0:
            def effect():
                addr = state.cpu_store_buffer.pop(0)
                state.source_mem[addr] += 1
                val = state.source_mem[addr]
                
                # Mirror snoops the memory commit
                if state.is_in_mirror_range(addr):
                    state.mirror_b2.append((addr, val))
                else:
                    state.mirror_b1.append((addr, val))
                    
                return f"MemCtrl committed store {val} to addr {addr}"
            return effect
        return None

    # 3. Mirror sends to network
    @staticmethod
    def mirror_sends(state: GlobalState):
        if len(state.mirror_b2) > 0:
            def effect():
                addr, val = state.mirror_b2.pop(0)
                state.network_queue.append(("MIRROR", addr, val))
                return f"Mirror sent {val} for addr {addr}"
            return effect
        return None

    # 4. DMA requests d+1 by sending a message
    @staticmethod
    def dma_sends_request(state: GlobalState):
        if not state.dma_waiting_for_grant and state.dma_d < N - 1 and (state.dma_d - state.dma_c + 1) < DMA_BATCH:
            def effect():
                target_d = state.dma_d + 1
                state.dma_to_mirror_req.append(target_d)
                state.dma_waiting_for_grant = True
                return f"DMA sent request for addr {target_d} to interconnect"
            return effect
        return None

    # 5. Mirror processes request and grants it (if safe)
    @staticmethod
    def mirror_processes_request(state: GlobalState):
        if len(state.dma_to_mirror_req) > 0:
            target_d = state.dma_to_mirror_req[0]
            # Handshake safety check
            has_pending = any(a == target_d for (a, v) in state.mirror_b2)
            if not has_pending:
                def effect():
                    state.dma_to_mirror_req.pop(0)
                    state.mirror_a = (state.mirror_a + 1) % N
                    state.mirror_to_dma_grant.append(target_d)
                    return f"Mirror yielded {target_d} and sent grant message"
                return effect
        return None

    # 6. DMA receives grant, updates d, reads memory
    @staticmethod
    def dma_receives_grant(state: GlobalState):
        if len(state.mirror_to_dma_grant) > 0:
            def effect():
                target_d = state.mirror_to_dma_grant.pop(0)
                state.dma_d = target_d
                val = state.source_mem[target_d]
                state.dma_internal_buffer.append((target_d, val))
                state.dma_waiting_for_grant = False
                return f"DMA received grant, locked {target_d}, and read val {val}"
            return effect
        return None

    # 7. DMA transmits chunk, releases c by sending a message
    @staticmethod
    def dma_sends_and_releases(state: GlobalState):
        if len(state.dma_internal_buffer) > 0:
            addr, val = state.dma_internal_buffer[0]
            if addr == state.dma_c:
                def effect():
                    state.dma_internal_buffer.pop(0)
                    state.network_queue.append(("DMA", addr, val))
                    
                    old_c = state.dma_c
                    state.dma_c += 1
                    state.dma_to_mirror_release.append(old_c)
                    
                    return f"DMA sent chunk for {old_c} to net, sent release message"
                return effect
        return None

    # 8. Mirror processes release message, sweeps B1
    @staticmethod
    def mirror_processes_release(state: GlobalState):
        if len(state.dma_to_mirror_release) > 0:
            def effect():
                old_c = state.dma_to_mirror_release.pop(0)
                state.mirror_b = (state.mirror_b + 1) % N
                
                swept = []
                remaining = []
                for (a, v) in state.mirror_b1:
                    if a == old_c:
                        swept.append((a, v))
                    else:
                        remaining.append((a, v))
                
                state.mirror_b1 = remaining
                state.mirror_b2.extend(swept)
                
                return f"Mirror received release for {old_c}, claimed it, swept {len(swept)} writes."
            return effect
        return None

    # 9. Network delivery
    @staticmethod
    def network_delivers(state: GlobalState):
        if len(state.network_queue) > 0:
            def effect():
                packet_type, addr, val = state.network_queue.pop(0)
                if val < state.dest_mem[addr]:
                    raise AssertionError(f"BUG DETECTED! Stale overwrite via {packet_type} at addr {addr}. Current: {state.dest_mem[addr]}, Incoming: {val}")
                
                state.dest_mem[addr] = val
                return f"Network delivered {val} for addr {addr} via {packet_type}"
            return effect
        return None

def run_basebound_fsm(steps=10000):
    random.seed(45)
    state = GlobalState()
    
    all_transitions = [
        Transitions.cpu_executes_store,
        Transitions.mem_controller_commits_store,
        Transitions.mirror_sends,
        Transitions.dma_sends_request,
        Transitions.mirror_processes_request,
        Transitions.dma_receives_grant,
        Transitions.dma_sends_and_releases,
        Transitions.mirror_processes_release,
        Transitions.network_delivers
    ]
    
    print("Starting Asynchronous Chip FSM Random Walk...\n")
    try:
        for step in range(steps):
            enabled_effects = [t(state) for t in all_transitions if t(state) is not None]
            
            if not enabled_effects:
                print("Deadlock reached!")
                break
                
            chosen = random.choice(enabled_effects)
            desc = chosen()
            
            if step % 500 == 0:
                pass # Muting step prints to focus on errors
                
    except AssertionError as e:
        print(f"\n\033[91m{e}\033[0m")
        return

    print(f"\n\033[92mSuccess! Finished {steps} steps safely. No bugs detected!\033[0m")
    print(f"Final State: {state}")

if __name__ == "__main__":
    run_basebound_fsm()
