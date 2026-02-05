from dataclasses import dataclass, field
from typing import Dict
from datetime import datetime


@dataclass
class SKUMeta:
    """Master Data for a single Bulk SKU."""
    gcas: str
    description: str
    technology: str
    # Maps System Name -> Cycle Time (Minutes)
    bct_by_system: Dict[str, float] = field(default_factory=dict)


@dataclass
class Demand:
    """A row from the Packing Plan."""
    order_id: str
    material_code: str  # The Finished Good code (e.g. 839...)
    description: str
    start_dt: datetime
    quantity: float
    # These are filled by the Enricher
    bulk_gcas: str = None
    system: str = None


@dataclass
class ProductionBatch:
    """A scheduled production event."""
    id: str
    sku_code: str
    system: str
    shift: str
    start_dt: datetime
    end_dt: datetime
    duration_min: int
    linked_order: str