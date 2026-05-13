class DMAEngine:
    """Scans memory and streams it over the network."""
    def __init__(self, network, source_memory_ref, latency):
        self.network = network
        self.source_memory = source_memory_ref
        self.latency = latency
        self.state = "WAITING" # WAITING -> TRANSMITTING -> DONE
        self.timer = 0
        
        self.hit_time = 20       # Tick at which it reaches Address X
        self.tx_interval = 3     # Ticks taken to process and transmit the chunk
        self.dma_buffer = None

    def tick(self, clock):
        if self.state == "WAITING":
            if clock == self.hit_time:
                # DMA reaches address X and reads into its local buffer
                self.dma_buffer = self.source_memory['val']
                print(f"[{clock}] DMAEngine: Read value {self.dma_buffer} from Source")
                self.state = "TRANSMITTING"
                self.timer = 0
        elif self.state == "TRANSMITTING":
            self.timer += 1
            if self.timer >= self.tx_interval:
                deliver_at = clock + self.latency
                self.network.send(deliver_at, self.dma_buffer, "DMA")
                print(f"[{clock}] DMAEngine: Transmitted {self.dma_buffer}, arrives at {deliver_at}")
                
                self.state = "DONE"
                self.dma_buffer = None
        elif self.state == "DONE":
            pass # Ignore X for the rest of the simulation
