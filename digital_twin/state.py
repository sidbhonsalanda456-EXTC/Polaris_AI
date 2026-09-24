from typing import Dict, Any
from dataclasses import dataclass, field, asdict

@dataclass
class TwinComponent:
    id: str
    name: str
    category: str
    status: str  # NOMINAL, WARNING, CRITICAL, OFFLINE
    health_score: float  # 0.0 to 100.0
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
