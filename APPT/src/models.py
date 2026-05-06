from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

@dataclass
class SKUMeta:
    """
    Represents the Master Data for a specific SKU (Finished Good).
    Contains manufacturing specifications, cycle times, and raw material recipes.
    """
    gcas: str
    description: str
    technology: str
    tech_class: str
    bct_by_system: Dict[str, float]
    # Recipes: Key = '12T_sls', Value = Consumption Amount
    recipes: Dict[str, float] = field(default_factory=dict)

@dataclass
class VariantInfo:
    """
    Maps a bulk formulation description to its specific GCAS and container weight.
    """
    gcas: str
    weight_per_container: float

@dataclass
class Demand:
    """
    Represents a single production order (Packing PO) requested by the business.
    """
    order_id: str
    material_code: str
    description: str
    quantity: float
    pkg_start_dt: datetime
    pkg_end_dt: datetime
    line: str

@dataclass
class ProductionBatch:
    """
    The core output of the simulation engine. Represents a fully scheduled
    batch of liquid making, tied to a specific system, tank, and packing line.
    """
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
    storage_tank: str = "TBD"
    mrp_status: str = "OK"  # Used by JIT Replenishment to flag material shortages