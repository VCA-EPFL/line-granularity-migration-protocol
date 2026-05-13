class MirrorBuffer:
    """Intercepts stores and sends them over the network."""
    def __init__(self, network, latency):
        self.buffer = []
        self.network = network
        self.latency = latency
        self.tx_cooldown = 0
        self.tx_interval = 1 # Ticks required to transmit one item

    def push(self, val):
        self.buffer.append(val)

    def tick(self, clock):
        if self.tx_cooldown > 0:
            self.tx_cooldown -= 1
        
        if self.tx_cooldown == 0 and len(self.buffer) > 0:
            val = self.buffer.pop(0)
            deliver_at = clock + self.latency
            self.network.send(deliver_at, val, "MIRROR")
            print(f"[{clock}] MirrorBuffer: Transmitted {val}, arrives at {deliver_at}")
            self.tx_cooldown = self.tx_interval
