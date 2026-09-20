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
    current_road: str = ""      # road_id the vehicle is traversing ('' = at junction)
    road_position: float = 0.0  # progress along current_road (0=start, 1=end)

    def is_at_destination(self) -> bool:
        return self.current_junction == self.destination_junction

    def next_junction(self) -> str:
        if len(self.route) > 1:
            return self.route[1]
        return self.destination_junction

    @property
    def is_in_transit(self) -> bool:
        """True when the vehicle is travelling along a road (not at a junction)."""
        return bool(self.current_road) and 0.0 < self.road_position < 1.0
