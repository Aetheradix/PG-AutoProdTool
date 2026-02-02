from typing import List, Dict, Tuple
from datetime import timedelta, datetime
import re
from src.models import ProductionBatch, Demand, SKUMeta
from src import config


class Scheduler:
    def __init__(self, master_data: Dict[str, SKUMeta], bom_map: Dict[str, str]):
        self.master_data = master_data
        self.bom_map = bom_map
        self.batches: List[ProductionBatch] = []
        self.batch_counter = 1
        self.keyword_map = self._build_lookup_tables()

    def _clean_text(self, text: str) -> str:
        if not text: return ""
        t = str(text).lower()
        noise = [r'h&s', r'head\s*&\s*shoulders', r'pantene', r'ptn', r'shm', r'shampoo', r'cond', r'conditioner',
                 r'in', r'gst', r'fc', r'ml', r'l', r'\d+x\d+', r'\d+', r'daily', r'care']
        for p in noise: t = re.sub(p, '', t)
        t = re.sub(r'[^a-z\s]', ' ', t)
        return " ".join(t.split())

    def _build_lookup_tables(self) -> Dict[str, str]:
        lookup = {}
        print("Building Text Search Index from Master Data...")
        for bulk_gcas, sku in self.master_data.items():
            keys_to_index = [sku.description, sku.technology]
            for k in keys_to_index:
                clean_key = self._clean_text(k)
                if len(clean_key) > 2: lookup[clean_key] = bulk_gcas
        print(f"Indexed {len(lookup)} variant keywords.")
        return lookup

    def _match_by_description(self, raw_desc: str) -> str:
        target = self._clean_text(raw_desc)
        if not target: return None
        for key, bulk_gcas in self.keyword_map.items():
            if key in target or target in key: return bulk_gcas
        if "clean" in target: return self._find_bulk_by_keyword("clean")
        if "cool" in target: return self._find_bulk_by_keyword("cool")
        if "smooth" in target: return self._find_bulk_by_keyword("smooth")
        if "hair fall" in target or "ahf" in target: return self._find_bulk_by_keyword("hair fall")
        return None

    def _find_bulk_by_keyword(self, keyword):
        for key, gcas in self.keyword_map.items():
            if keyword in key: return gcas
        return None

    def _get_best_system(self, sku: SKUMeta) -> Tuple[str, float]:
        if not sku.bct_by_system: return ("UNKNOWN", 0.0)
        systems = sku.bct_by_system
        twelve_ton = {k: v for k, v in systems.items() if "12T" in k}
        if twelve_ton:
            best = min(twelve_ton, key=twelve_ton.get)
            return best, twelve_ton[best]
        best = min(systems, key=systems.get)
        return best, systems[best]

    def _determine_shift(self, dt: datetime) -> str:
        h = dt.hour
        if 7 <= h < 15:
            return "B"
        elif 15 <= h < 23:
            return "C"
        else:
            return "A"

    def process_demands(self, demands: List[Demand]) -> List[ProductionBatch]:
        print(f"--- Scheduling {len(demands)} Demands ---")
        sorted_demands = sorted(demands, key=lambda d: d.packing_start_dt)
        matched_count = 0

        for demand in sorted_demands:
            req_sku = str(demand.sku_code).strip()
            bulk_sku_code = req_sku

            sku = self.master_data.get(bulk_sku_code)

            if not sku:
                found_gcas = self._match_by_description(demand.description)
                if found_gcas:
                    bulk_sku_code = found_gcas
                    sku = self.master_data.get(bulk_sku_code)

            if not sku: continue

            system, bct_min = self._get_best_system(sku)
            if system == "UNKNOWN": continue

            matched_count += 1
            buffer_delta = timedelta(minutes=sku.buffer_time_min)
            ready_dt = demand.packing_start_dt - buffer_delta
            bct_delta = timedelta(minutes=int(bct_min))
            start_dt = ready_dt - bct_delta

            batch = ProductionBatch(
                id=f"BATCH_{self.batch_counter:03d}",
                sku_code=bulk_sku_code,
                system=system,
                shift=self._determine_shift(start_dt),
                start_dt=start_dt,
                end_dt=ready_dt,
                duration_min=int(bct_min),
                type="NORMAL",
                linked_demand_id=f"{demand.id}|{req_sku}"
            )
            self.batches.append(batch)
            self.batch_counter += 1

        print(f"\nSCHEDULING COMPLETE.")
        print(f"Demands Processed: {len(demands)}")
        print(f"Successful Matches: {matched_count}")
        print(f"Batches Created:    {len(self.batches)}")
        return self.batches