from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime

@dataclass
class SKUMeta:
    gcas: str
    description: str
    technology: str
    tech_class: str = "Single"  # "Single" or "Dual"
    bct_by_system: Dict[str, float] = field(default_factory=dict)

@dataclass
class VariantInfo:
    gcas: str
    weight_per_container: float = 0.0

@dataclass
class Demand:
    order_id: str
    material_code: str
    description: str
    quantity: float
    start_dt: datetime
    line: str = ""

@dataclass
class ProductionBatch:
    id: str
    sku_code: str
    system: str
    shift: str
    start_dt: datetime
    end_dt: datetime
    duration_min: int
    linked_order: str
    # Extra fields
    material: str = ""
    desc: str = ""
    total_msu: float = 0.0
    line: str = ""
    tech_type: str = "" # To display Single/Dual in output