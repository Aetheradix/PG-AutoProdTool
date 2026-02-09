import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta, time
from src import config
from src.models import SKUMeta, Demand, ProductionBatch, VariantInfo


class PlanEnricher:
    def __init__(self, master_data: Dict[str, SKUMeta], bulk_map: Dict[str, VariantInfo]):
        self.master_data = master_data
        self.bulk_map = bulk_map
        self.clean_bulk_map = {}
        for desc, variant in bulk_map.items():
            clean_key = self._normalize_text(desc)
            if clean_key: self.clean_bulk_map[clean_key] = variant

    def _normalize_text(self, text: str) -> str:
        if not text: return ""
        t = str(text).upper()
        for noise in config.MATCHING_NOISE_WORDS:
            pattern = r'\b' + re.escape(noise) + r'\b'
            t = re.sub(pattern, '', t)
        return re.sub(r'[^A-Z0-9]', '', t)

    def find_variant_for_demand(self, demand: Demand) -> Optional[VariantInfo]:
        original_desc = demand.description.strip()
        if original_desc in self.bulk_map: return self.bulk_map[original_desc]

        demand_clean = self._normalize_text(original_desc)
        if demand_clean in self.clean_bulk_map: return self.clean_bulk_map[demand_clean]

        for key, variant in self.clean_bulk_map.items():
            if len(demand_clean) > 5 and (demand_clean in key or key in demand_clean):
                return variant

        desc_lower = original_desc.lower()
        for keyword in config.RULE_CLIMBAZOLE:
            if keyword in desc_lower:
                return VariantInfo(gcas="PREMIX_CLIMBAZOLE", weight_per_container=0)
        return None

    def calculate_msu(self, quantity: float, weight_per_container: float) -> float:
        if weight_per_container <= 0 or quantity <= 0: return 0.0
        return (quantity * weight_per_container) / config.MSU_UNIT_KG

    def select_system(self, demand: Demand, sku: SKUMeta, variant: VariantInfo) -> Tuple[str, float, float]:
        desc_lower = str(demand.description).lower()

        for kw in config.RULE_CLIMBAZOLE:
            if kw in desc_lower: return ("1.25T", 180, 0.0)

        msu = self.calculate_msu(demand.quantity, variant.weight_per_container)
        target_size = "12T"
        if msu > 0 and msu < config.MSU_THRESHOLD_6T: target_size = "6T"

        for kw in config.RULE_CONDITIONER:
            if kw in desc_lower: return ("6T MMT", self._get_bct(sku, "6T MMT"), msu)

        for kw in config.RULE_HC_BASE:
            if kw in desc_lower:
                tgt = f"{target_size} MMT"
                return (tgt, self._get_bct(sku, tgt), msu)

        tech_type = sku.tech_class if sku else "Single"
        target_tech = "MMT" if tech_type.lower() == "dual" else "FMT"
        tgt = f"{target_size} {target_tech}"
        return (tgt, self._get_bct(sku, tgt), msu)

    def _get_bct(self, sku: SKUMeta, target_system: str) -> float:
        if not sku: return config.DEFAULT_DURATION
        if target_system in sku.bct_by_system: return sku.bct_by_system[target_system]
        size = target_system.split()[0]
        for sys_name, duration in sku.bct_by_system.items():
            if size in sys_name: return duration
        return config.DEFAULT_DURATION


class Scheduler:
    def __init__(self, enricher: PlanEnricher):
        self.enricher = enricher
        self.batches = []

    def _get_buffer_time(self, description: str) -> int:
        desc_lower = description.lower()
        for kw in config.RULE_CONDITIONER:
            if kw in desc_lower:
                return config.BUFFER_COND
        return config.BUFFER_STD

    def _apply_shift_constraints(self, dt: datetime) -> datetime:
        """Snaps time to safe slot if it falls inside a Blackout Window."""
        t = dt.time()
        for rule in config.SHIFT_CONSTRAINTS:
            # Construct time objects for comparison
            r_start = time(rule['start'][0], rule['start'][1])
            r_end = time(rule['end'][0], rule['end'][1])
            r_snap = rule['snap']  # (H, M)

            # Check range (handling simple intra-day ranges)
            if r_start <= t <= r_end:
                # Snap BACK to the earlier time
                return dt.replace(hour=r_snap[0], minute=r_snap[1], second=0, microsecond=0)
        return dt

    def _get_shift(self, dt: datetime) -> str:
        t = dt.time()
        # Shift A: 07:30 to 15:30
        if t >= time(7, 30) and t < time(15, 30): return "A"
        # Shift B: 15:30 to 23:30
        if t >= time(15, 30) and t < time(23, 30): return "B"
        # Shift C: 23:30 to 07:30 (Crossing Midnight)
        return "C"

    def run(self, demands: List[Demand]) -> List[ProductionBatch]:
        print(f"--- Processing {len(demands)} Demands ---")
        batch_id_counter = 1

        for d in demands:
            variant = self.enricher.find_variant_for_demand(d)
            gcas = variant.gcas if variant else "UNKNOWN"

            system = "System TBD"
            bct = config.DEFAULT_DURATION
            msu = 0.0

            if gcas == "PREMIX_CLIMBAZOLE":
                system = "1.25T"
                bct = 180
            else:
                sku = self.enricher.master_data.get(gcas)
                system, bct, msu = self.enricher.select_system(d, sku, variant if variant else VariantInfo("UNK"))

            # --- TIMELINE CALCULATION (Updated with Constraints) ---
            min_buffer = self._get_buffer_time(d.description)

            # 1. Theoretical End of Making (latest possible)
            # Pkg Start - Min Buffer
            raw_mkg_end = d.pkg_start_dt - timedelta(minutes=min_buffer)

            # 2. Theoretical Start of Making
            # End - BCT
            raw_mkg_start = raw_mkg_end - timedelta(minutes=int(bct))

            # 3. Apply Shift Constraints (Snap Back if needed)
            final_mkg_start = self._apply_shift_constraints(raw_mkg_start)

            # 4. Recalculate End and Buffer based on Final Start
            # (We keep duration fixed, so End moves earlier too)
            final_mkg_end = final_mkg_start + timedelta(minutes=int(bct))

            # Buffer increases if we snapped back
            actual_buffer = int((d.pkg_start_dt - final_mkg_end).total_seconds() / 60)

            shift = self._get_shift(final_mkg_start)

            tech_type = "Single"
            sku_obj = self.enricher.master_data.get(gcas)
            if sku_obj: tech_type = sku_obj.tech_class

            batch = ProductionBatch(
                id=f"B{batch_id_counter:03d}",
                sku_code=gcas,
                system=system,
                shift=shift,
                mkg_start_dt=final_mkg_start,
                bct=int(bct),
                mkg_end_dt=final_mkg_end,
                buffer_min=actual_buffer,
                pkg_start_dt=d.pkg_start_dt,
                pkg_end_dt=d.pkg_end_dt,
                linked_order=d.order_id,
                material=d.material_code,
                desc=d.description,
                total_msu=msu,
                line=d.line,
                tech_type=tech_type
            )
            self.batches.append(batch)
            batch_id_counter += 1

        return self.batches