import random

class GlobalState:
    """A snapshot of the entire system at any given moment."""
    def __init__(self):
        # Memory
        self.source_mem = 0
        self.dest_mem = 0
        
        # Buffers & Network
        self.mirror_buffer = []  # items waiting to be sent by mirror
        self.network_bag = []    # unordered bag of packets in flight: list of (type, value)
        
        # DMA State
        self.dma_state = "WAITING" # WAITING -> TRANSMITTING -> DONE
        self.dma_internal_buffer = None

    def __repr__(self):
        return f"State(src={self.source_mem}, dst={self.dest_mem}, net_bag={self.network_bag}, dma={self.dma_state})"

class Transitions:
    """
    Defines the set of all possible asynchronous actions.
    Each method acts as a Guard. If the action is possible in the current state,
    it returns a function (the Effect) that mutates the state. If not, it returns None.
    """
    @staticmethod
    def storer_writes(state: GlobalState):
        # Guard: Storer can theoretically always write.
        def effect():
            state.source_mem += 1
            state.mirror_buffer.append(state.source_mem)
            return "Storer wrote to X"
        return effect

    @staticmethod
    def mirror_sends(state: GlobalState):
        # Guard: Mirror buffer must have items waiting
        if len(state.mirror_buffer) > 0:
            def effect():
                val = state.mirror_buffer.pop(0)
                state.network_bag.append(("MIRROR", val))
                return f"Mirror pushed {val} to network bag"
            return effect
        return None

    @staticmethod
    def dma_reads(state: GlobalState):
        # Guard: DMA must be WAITING
        if state.dma_state == "WAITING":
            def effect():
                state.dma_internal_buffer = state.source_mem
                state.dma_state = "TRANSMITTING"
                return f"DMA read {state.dma_internal_buffer} from source"
            return effect
        return None

    @staticmethod
    def dma_sends(state: GlobalState):
        # Guard: DMA must be TRANSMITTING
        if state.dma_state == "TRANSMITTING":
            def effect():
                state.network_bag.append(("DMA", state.dma_internal_buffer))
                state.dma_state = "DONE"
                state.dma_internal_buffer = None
                return "DMA pushed its chunk to network bag"
            return effect
        return None

    @staticmethod
    def network_delivers(state: GlobalState):
        # Guard: Network bag must have packets in flight
        if len(state.network_bag) > 0:
            def effect():
                # Randomly pick ANY packet from the bag (simulating arbitrary out-of-order delivery)
                idx = random.randint(0, len(state.network_bag) - 1)
                packet_type, val = state.network_bag.pop(idx)
                
                # Check invariant!
                if val < state.dest_mem:
                    raise AssertionError(f"BUG DETECTED! Stale overwrite via {packet_type}. Current Dest: {state.dest_mem}, Incoming: {val}")
                
                state.dest_mem = val
                return f"Network delivered {val} via {packet_type}"
            return effect
        return None

def run_random_fsm(steps=50):
    random.seed(45) # Seeded to produce a nice trace
    state = GlobalState()
    
    # List of all possible transition definitions
    all_transitions = [
        Transitions.storer_writes,
        Transitions.mirror_sends,
        Transitions.dma_reads,
        Transitions.dma_sends,
        Transitions.network_delivers
    ]
    
    print("Starting FSM Random Walk...\n")
    
    try:
        for step in range(steps):
            # 1. Evaluate guards to find which actions are enabled right now
            enabled_effects = []
            for trans in all_transitions:
                effect = trans(state)
                if effect is not None:
                    enabled_effects.append(effect)
            
            if not enabled_effects:
                print("Deadlock reached! No valid actions.")
                break
                
            # 2. Randomly pick ONE enabled action
            chosen_effect = random.choice(enabled_effects)
            
            # 3. Execute the action to mutate the global state
            action_desc = chosen_effect()
            
            print(f"Step {step+1}: {action_desc}")
            print(f"  {state}")
            
    except AssertionError as e:
        print(f"\n\033[91m{e}\033[0m")
        print("Simulation stopped.")
        return

    print("\nFinished random walk safely.")

if __name__ == "__main__":
    run_random_fsm()
