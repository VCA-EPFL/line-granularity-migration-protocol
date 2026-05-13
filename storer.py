import random

class Storer:
    """The Source CPU, writing to memory randomly."""
    def __init__(self, source_memory, mirror_buffer):
        self.source_memory = source_memory
        self.mirror_buffer = mirror_buffer
        self.store_interval = 1
        self.timer = 0
        self.prob_x = 0.20 # 20% chance to write to X every clock cycle

    def tick(self, clock):
        self.timer += 1
        if self.timer >= self.store_interval:
            self.timer = 0
            # Randomly decide if writing to X
            if random.random() < self.prob_x:
                # Write to Address X
                self.source_memory['val'] += 1
                val = self.source_memory['val']
                print(f"[{clock}] Storer: Wrote {val} to Source Address X")
                self.mirror_buffer.push(val)
            else:
                # Write to Not X
                pass # Ignored by our abstraction
