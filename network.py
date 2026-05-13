class Network:
    """Models the network links between source and destination."""
    def __init__(self):
        # List of (delivery_tick, value, channel_name)
        self.in_flight = []

    def send(self, deliver_at, val, channel):
        self.in_flight.append((deliver_at, val, channel))

    def tick(self, clock, dest_memory):
        # Deliver packets that have reached their delivery time
        delivered = [p for p in self.in_flight if p[0] == clock]
        # Keep packets still in flight
        self.in_flight = [p for p in self.in_flight if p[0] > clock]
        
        for _, val, channel in delivered:
            dest_memory.receive(val, channel, clock)
