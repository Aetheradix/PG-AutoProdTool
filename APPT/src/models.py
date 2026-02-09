from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime


@dataclass
class SKUMeta:
    gcas: str
    description: str
    technology: str
    tech_class: str = "Single"
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
    pkg_start_dt: datetime  # Renamed for clarity
    pkg_end_dt: datetime  # New
    line: str = ""


@dataclass
class ProductionBatch:
    id: str
    sku_code: str
    system: str
    shift: str

    # Timeline
    mkg_start_dt: datetime
    bct: int
    mkg_end_dt: datetime
    buffer_min: int
    pkg_start_dt: datetime
    pkg_end_dt: datetime

    linked_order: str
    material: str = ""
    desc: str = ""
    total_msu: float = 0.0
    line: str = ""
    tech_type: str = ""