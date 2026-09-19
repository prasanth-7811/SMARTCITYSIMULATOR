# simulation/vehicle.py — Lightweight vehicle model.

from dataclasses import dataclass, field
from typing import List
import uuid


@dataclass
class Vehicle:
    vehicle_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    current_junction: str = ""
    destination_junction: str = ""
    route: List[str] = field(default_factory=list)
    wait_time: float = 0.0      # seconds spent waiting at signals
    travel_time: float = 0.0    # total travel time so far
    is_emergency: bool = False
    speed_factor: float = 1.0   # 1.0 = normal, >1 = faster (emergency)

    def is_at_destination(self) -> bool:
        return self.current_junction == self.destination_junction

    def next_junction(self) -> str:
        if len(self.route) > 1:
            return self.route[1]
        return self.destination_junction
