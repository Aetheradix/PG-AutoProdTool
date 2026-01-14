from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class SKUMeta:
    """
    Represents the static master data for a single SKU.
    Aggregated from BCT and Buffer sheets.
    """
    code: str
    technology: str  # e.g., 'Shampoo', 'Conditioner'
    buffer_time_min: int = 0
    # Mapping: System Name (e.g., '6T') -> Cycle Time in Minutes
    bct_by_system: Dict[str, float] = field(default_factory=dict)

    def get_bct(self, system: str) -> Optional[float]:
        """Returns BCT for a specific system, or None if not compatible."""
        return self.bct_by_system.get(system)

    def is_compatible(self, system: str) -> bool:
        return system in self.bct_by_system

@dataclass
class WashoutRule:
    """
    Represents a cleaning rule between two products.
    """
    from_sku: str
    to_sku: str
    duration_min: int
    system_class: str = "ALL"  # Apply to specific system class if needed

@dataclass
class ProductionBatch:
    """
    Represents a single scheduled unit of production.
    This is the main object the Scheduler will manipulate.
    """
    id: str  # Unique ID (e.g., "BATCH_001")
    sku_code: str
    system: str
    shift: str
    start_time_min: int  # Minutes from start of planning horizon (0 = Shift B start)
    end_time_min: int
    duration_min: int
    type: str = "NORMAL"  # NORMAL, WASHOUT, STARTUP, SHUTDOWN, PREMIX