import random
from network import Network
from memory import DestMemory
from mirror import MirrorBuffer
from dma import DMAEngine
from storer import Storer

def run_simulation(max_ticks=50):
    # Fixed seed to ensure we hit the bug predictably for demonstration
    random.seed(42) 
    
    clock = 0
    # Source memory is just a dict so it can be passed by reference
    source_memory = {'val': 0} 
    dest_memory = DestMemory()
    network = Network()
    
    # Network latencies
    mirror = MirrorBuffer(network, latency=4)
    dma = DMAEngine(network, source_memory, latency=10)
    storer = Storer(source_memory, mirror)

    print("Starting Simulation...\n")
    try:
        for clock in range(max_ticks):
            storer.tick(clock)
            dma.tick(clock)
            mirror.tick(clock)
            network.tick(clock, dest_memory)
    except AssertionError as e:
        print(f"\nSimulation stopped: {e}")
        return

    print("\nSimulation ended successfully (No bug hit).")

if __name__ == "__main__":
    run_simulation()
