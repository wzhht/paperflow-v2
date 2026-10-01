from dataclasses import dataclass
from enum import Enum


class Publisher(str, Enum):
    ELSEVIER = "elsevier"
    SPRINGER_NATURE = "springer_nature"
    UNKNOWN = "unknown"


class Route(str, Enum):
    ELSEVIER = "elsevier"
    BUILDING_SIMULATION = "building_simulation"
    NATURE = "nature"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RouteDecision:
    doi: str
    publisher: Publisher
    route: Route
    supported: bool
    reason: str
