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
            if keyword in desc_lower: return VariantInfo(gcas="PREMIX_CLIMBAZOLE", weight_per_container=0)
        return None

    def calculate_msu(self, quantity: float, weight_per_container: float) -> float:
        if weight_per_container <= 0 or quantity <= 0: return 0.0
        return (quantity * weight_per_container) / config.MSU_UNIT_KG

    def select_system(self, demand: Demand, sku: SKUMeta, variant: VariantInfo) -> Tuple[str, float, float]:
        desc_lower = str(demand.description).lower()

        # 1. Climbazole
        for kw in config.RULE_CLIMBAZOLE:
            if kw in desc_lower: return ("1.25T", 180, 0.0)

        msu = self.calculate_msu(demand.quantity, variant.weight_per_container)
        target_size = "12T"
        if msu > 0 and msu < config.MSU_THRESHOLD_6T: target_size = "6T"

        # 3. Conditioner
        for kw in config.RULE_CONDITIONER:
            if kw in desc_lower:
                return ("6T", self._get_bct(sku, "6T"), msu)

        return (target_size, self._get_bct(sku, target_size), msu)

    def _get_bct(self, sku: SKUMeta, target_system: str) -> float:
        if not sku: return config.DEFAULT_DURATION
        if target_system in sku.bct_by_system: return sku.bct_by_system[target_system]
        return config.DEFAULT_DURATION


class Scheduler:
    def __init__(self, enricher: PlanEnricher):
        self.enricher = enricher
        self.batches = []

    def _get_buffer_time(self, description: str) -> int:
        desc_lower = description.lower()
        for kw in config.RULE_CONDITIONER:
            if kw in desc_lower: return config.BUFFER_COND
        return config.BUFFER_STD

    def _apply_shift_constraints(self, dt: datetime) -> datetime:
        t = dt.time()
        for rule in config.SHIFT_CONSTRAINTS:
            r_start = time(rule['start'][0], rule['start'][1])
            r_end = time(rule['end'][0], rule['end'][1])
            r_snap = rule['snap']
            if r_start <= t <= r_end:
                return dt.replace(hour=r_snap[0], minute=r_snap[1], second=0, microsecond=0)
        return dt

    def _get_shift(self, dt: datetime) -> str:
        t = dt.time()
        if t >= time(7, 30) and t < time(15, 30): return "A"
        if t >= time(15, 30) and t < time(23, 30): return "B"
        return "C"

    def run_initial_schedule(self, demands: List[Demand]) -> List[ProductionBatch]:
        print(f"--- Calculating Initial Schedule ({len(demands)} demands) ---")
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

            min_buffer = self._get_buffer_time(d.description)
            raw_mkg_end = d.pkg_start_dt - timedelta(minutes=min_buffer)
            raw_mkg_start = raw_mkg_end - timedelta(minutes=int(bct))
            final_mkg_start = self._apply_shift_constraints(raw_mkg_start)
            final_mkg_end = final_mkg_start + timedelta(minutes=int(bct))
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


class TankScheduler:
    def __init__(self, washout_matrices: Dict[str, Dict]):
        self.washout_matrices = washout_matrices

    def _is_conditioner(self, batch: ProductionBatch) -> bool:
        desc_lower = str(batch.desc).lower()
        for kw in config.RULE_CONDITIONER:
            if kw in desc_lower: return True
        return False

    def _get_matrix_washout(self, prev_batch: ProductionBatch, next_batch: ProductionBatch) -> int:
        if str(prev_batch.sku_code).strip() == str(next_batch.sku_code).strip(): return 0

        matrix_key = "FMT"
        if "6T" in next_batch.system: matrix_key = "MMT_6T"

        rules = self.washout_matrices.get(matrix_key, {})
        key = (str(next_batch.sku_code).strip(), str(prev_batch.sku_code).strip())

        if key in rules: return rules[key]
        return config.WASHOUT_DURATION

    def optimize(self, batches: List[ProductionBatch]) -> Tuple[List[ProductionBatch], List[dict]]:
        print("--- Optimizing Tank Queue (Hidden Cooldown) ---")

        tanks = {"Tank_12T": [], "Tank_6T": [], "Tank_1.25T": [], "Other": []}
        for b in batches:
            if "12T" in b.system:
                tanks["Tank_12T"].append(b)
            elif "6T" in b.system:
                tanks["Tank_6T"].append(b)
            elif "1.25T" in b.system:
                tanks["Tank_1.25T"].append(b)
            else:
                tanks["Other"].append(b)

        final_batches = []
        washouts = []

        for tank_name, tank_batches in tanks.items():
            if not tank_batches: continue
            tank_batches.sort(key=lambda x: x.mkg_start_dt, reverse=True)

            scheduled = []
            last_scheduled_batch = None

            for b in tank_batches:
                if last_scheduled_batch is None:
                    scheduled.append(b)
                    last_scheduled_batch = b
                else:
                    # 'b' is EARLIER, 'last' is LATER

                    is_b_cond = self._is_conditioner(b)
                    is_last_cond = self._is_conditioner(last_scheduled_batch)

                    # 1. Determine Washout Duration (Standard or Cond Post-Wash)
                    wash_dur = 0
                    wash_type = None

                    if is_b_cond:
                        wash_dur = config.COND_POST_WASH
                        wash_type = "COND_WASH"
                    else:
                        wash_dur = self._get_matrix_washout(last_scheduled_batch, b)
                        if wash_dur > 0: wash_type = "STD_WASH"

                    # 2. Determine Required Gap (Wash + Cooldown)
                    # Gap starts from b.End
                    required_gap_after_b = wash_dur

                    if is_last_cond:
                        # If next batch is Cond, we need 30m idle time AFTER any washout
                        required_gap_after_b += config.COND_COOLDOWN

                    # 3. Calculate 'b' Latest End Time
                    # b.End must be <= last.Start - required_gap
                    latest_end = last_scheduled_batch.mkg_start_dt - timedelta(minutes=required_gap_after_b)

                    if b.mkg_end_dt > latest_end:
                        new_end = latest_end
                        new_start = new_end - timedelta(minutes=b.bct)
                        b.mkg_end_dt = new_end
                        b.mkg_start_dt = new_start
                        b.buffer_min = int((b.pkg_start_dt - b.mkg_end_dt).total_seconds() / 60)

                    # 4. Generate Visuals (ONLY Washouts, No Cooldown Blocks)
                    if wash_type:
                        desc = "COND WASH (60m)" if wash_type == "COND_WASH" else "WASHOUT"
                        washouts.append({
                            "System": b.system,
                            "Start": b.mkg_end_dt,
                            "End": b.mkg_end_dt + timedelta(minutes=wash_dur),
                            "Desc": desc
                        })

                    scheduled.append(b)
                    last_scheduled_batch = b
            final_batches.extend(scheduled)

        return final_batches, washouts