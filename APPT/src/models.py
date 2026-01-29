from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime

@dataclass
class SKUMeta:
    """Static master data for a single SKU."""
    code: str
    technology: str
    buffer_time_min: int = 0
    bct_by_system: Dict[str, float] = field(default_factory=dict)

@dataclass
class WashoutRule:
    from_sku: str
    to_sku: str
    duration_min: int
    system_class: str = "ALL"

@dataclass
class Demand:
    """Represents a row from the SAP Packing Plan."""
    id: str
    sku_code: str
    description: str
    quantity: float
    packing_start_dt: datetime  # Exact Date & Time packing starts
    line: str

@dataclass
class ProductionBatch:
    """A scheduled bulk making batch."""
    id: str
    sku_code: str
    system: str
    shift: str
    start_dt: datetime
    end_dt: datetime
    duration_min: int
    type: str = "NORMAL"
    linked_demand_id: str = ""