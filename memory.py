class DestMemory:
    """The destination machine's memory, acts as the invariant monitor."""
    def __init__(self):
        self.val = 0

    def receive(self, val, channel, clock):
        print(f"[{clock}] DestMemory: Received value={val} via {channel}")
        if val < self.val:
            print(f"[{clock}] \033[91mBUG DETECTED! Stale overwrite.\033[0m")
            print(f"      Current memory: {self.val}, Incoming DMA value: {val}")
            raise AssertionError("Stale overwrite detected!")
        self.val = val
