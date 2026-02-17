from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

@dataclass
class SKUMeta:
    gcas: str
    description: str
    technology: str
    tech_class: str
    bct_by_system: Dict[str, float]

@dataclass
class VariantInfo:
    gcas: str
    weight_per_container: float

@dataclass
class Demand:
    order_id: str
    material_code: str
    description: str
    quantity: float
    pkg_start_dt: datetime
    pkg_end_dt: datetime
    line: str

@dataclass
class ProductionBatch:
    id: str
    sku_code: str
    system: str
    shift: str
    mkg_start_dt: datetime
    bct: int
    mkg_end_dt: datetime
    buffer_min: int
    pkg_start_dt: datetime
    pkg_end_dt: datetime
    linked_order: str
    material: str
    desc: str
    total_msu: float
    line: str
    tech_type: str
    storage_tank: str = "TBD"  # <--- NEW FIELD