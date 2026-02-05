import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from src import config
from src.models import SKUMeta, Demand, ProductionBatch


class PlanEnricher:
    def __init__(self, master_data: Dict[str, SKUMeta], bulk_map: Dict[str, str]):
        self.master_data = master_data
        self.bulk_map = bulk_map

    def find_gcas_for_demand(self, demand: Demand) -> Optional[str]:
        # Exact match (Quotes are preserved in map keys)
        desc = demand.description.strip()
        if desc in self.bulk_map:
            return self.bulk_map[desc]

        # Special Rules
        desc_lower = desc.lower()
        for keyword in config.SPECIAL_SYSTEM_RULES:
            if keyword in desc_lower:
                return "PREMIX_CLIMBAZOLE"
        return None

    def select_system(self, demand: Demand, sku: SKUMeta) -> Tuple[str, float]:
        desc_lower = str(demand.description).lower()

        for keyword, sys_name in config.SPECIAL_SYSTEM_RULES.items():
            if keyword in desc_lower:
                return (sys_name, 180)

                # FALLBACK: If Master Data has no BCTs for this SKU
        if not sku or not sku.bct_by_system:
            return ("System TBD", config.DEFAULT_DURATION)

        systems = sku.bct_by_system

        # Pick 12T if available
        twelve_t = {k: v for k, v in systems.items() if "12T" in k}
        if twelve_t:
            best = min(twelve_t, key=twelve_t.get)
            return (best, twelve_t[best])

        # Pick 6T
        six_t = {k: v for k, v in systems.items() if "6T" in k}
        if six_t:
            best = min(six_t, key=six_t.get)
            return (best, six_t[best])

        return ("System TBD", config.DEFAULT_DURATION)


class Scheduler:
    def __init__(self, enricher: PlanEnricher):
        self.enricher = enricher
        self.batches = []

    def run(self, demands: List[Demand]) -> List[ProductionBatch]:
        print(f"--- Processing {len(demands)} Demands ---")
        batch_id_counter = 1

        for d in demands:
            # 1. GCAS
            gcas = self.enricher.find_gcas_for_demand(d)
            if not gcas:
                print(f"[WARN] No GCAS map found for: {d.description}")
                gcas = "UNKNOWN_GCAS"

            system = "System TBD"
            bct = config.DEFAULT_DURATION

            # 2. System
            if gcas == "PREMIX_CLIMBAZOLE":
                system = "1.25T"
                bct = 180
            else:
                sku = self.enricher.master_data.get(gcas)
                # Note: sku might be None if GCAS is in Bulk Map but not in Master BCT Data
                system, bct = self.enricher.select_system(d, sku)

            # 3. Schedule
            start_dt = d.start_dt - timedelta(minutes=int(bct))
            shift = self._get_shift(start_dt)

            batch = ProductionBatch(
                id=f"B{batch_id_counter:03d}",
                sku_code=gcas,
                system=system,
                shift=shift,
                start_dt=start_dt,
                end_dt=d.start_dt,
                duration_min=int(bct),
                linked_order=d.order_id
            )
            batch.line = getattr(d, 'line', '')
            batch.material = d.material_code
            batch.desc = d.description

            self.batches.append(batch)
            batch_id_counter += 1

        return self.batches

    def _get_shift(self, dt: datetime) -> str:
        h = dt.hour
        if 7 <= h < 15:
            return "B"
        elif 15 <= h < 23:
            return "C"
        else:
            return "A"