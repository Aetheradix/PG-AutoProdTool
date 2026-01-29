from typing import List, Dict, Tuple
from datetime import timedelta, datetime
from src.models import ProductionBatch, Demand, SKUMeta
from src import config


class Scheduler:
    def __init__(self, master_data: Dict[str, SKUMeta]):
        self.master_data = master_data
        self.batches: List[ProductionBatch] = []
        self.batch_counter = 1

    def _get_best_system(self, sku: SKUMeta) -> Tuple[str, float]:
        """Prioritizes 12T systems if available."""
        if not sku.bct_by_system:
            return ("UNKNOWN", 0.0)

        systems = sku.bct_by_system
        # Prefer 12T
        twelve_ton = {k: v for k, v in systems.items() if "12T" in k}
        if twelve_ton:
            best = min(twelve_ton, key=twelve_ton.get)
            return best, twelve_ton[best]

        # Fallback
        best = min(systems, key=systems.get)
        return best, systems[best]

    def _determine_shift(self, dt: datetime) -> str:
        """Determines Shift Label based on hour."""
        h = dt.hour
        if 7 <= h < 15:
            return "B"
        elif 15 <= h < 23:
            return "C"
        else:
            return "A"

    def process_demands(self, demands: List[Demand]) -> List[ProductionBatch]:
        print(f"--- Scheduling {len(demands)} Demands ---")

        # Sort by packing time
        sorted_demands = sorted(demands, key=lambda d: d.packing_start_dt)

        missing_skus = set()
        compatible_skus = 0

        for demand in sorted_demands:
            # CLEANUP: Ensure strict string comparison
            req_sku = str(demand.sku_code).strip()

            sku = self.master_data.get(req_sku)

            if not sku:
                # Log the missing SKU to diagnose mismatch
                missing_skus.add(req_sku)
                print(f"[SKIP] Demand {demand.id}: SKU '{req_sku}' not found in Master Data.")
                continue

            system, bct_min = self._get_best_system(sku)
            if system == "UNKNOWN":
                print(f"[SKIP] Demand {demand.id}: SKU '{req_sku}' exists but has NO System/BCT defined.")
                continue

            compatible_skus += 1

            # CALCULATION (JIT)
            buffer_delta = timedelta(minutes=sku.buffer_time_min)
            ready_dt = demand.packing_start_dt - buffer_delta
            bct_delta = timedelta(minutes=int(bct_min))
            start_dt = ready_dt - bct_delta

            batch = ProductionBatch(
                id=f"BATCH_{self.batch_counter:03d}",
                sku_code=req_sku,
                system=system,
                shift=self._determine_shift(start_dt),
                start_dt=start_dt,
                end_dt=ready_dt,
                duration_min=int(bct_min),
                type="NORMAL",
                linked_demand_id=demand.id
            )

            self.batches.append(batch)
            self.batch_counter += 1

        # --- DIAGNOSTIC REPORT ---
        print("\n" + "=" * 40)
        print(f"SCHEDULING REPORT")
        print("=" * 40)
        print(f"Total Demands:    {len(demands)}")
        print(f"Compatible SKUs:  {compatible_skus}")
        print(f"Batches Created:  {len(self.batches)}")
        if missing_skus:
            print("-" * 40)
            print(f"MISSING MASTER DATA ({len(missing_skus)} SKUs):")
            print(f"These SKUs are in Packing Plan but NOT in BCT Sheet:")
            for s in list(missing_skus)[:10]:  # Print first 10
                print(f" - '{s}'")
            if len(missing_skus) > 10: print("... and others.")
            print("-" * 40)
        print("=" * 40 + "\n")

        return self.batches