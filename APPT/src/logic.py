import re
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta, time

import pandas as pd
from src import config
from src.models import SKUMeta, Demand, ProductionBatch, VariantInfo


# ---------------------------------------------------------
# 1. PLAN ENRICHER
# ---------------------------------------------------------
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
        if demand.material_code in [config.GCAS_HC_BASE, config.GCAS_CLIMBAZOLE]:
            return None

        # 1. Try Exact Match
        if demand.description in self.bulk_map:
            return self.bulk_map[demand.description]

        # 2. Try Cleaned Match
        clean_desc = self._normalize_text(demand.description)
        if clean_desc in self.clean_bulk_map:
            return self.clean_bulk_map[clean_desc]

        return None

    def calculate_msu(self, quantity_cases: float, weight_per_case: float) -> float:
        total_kg = quantity_cases * weight_per_case
        return total_kg / config.MSU_UNIT_KG

    def select_system(self, demand: Demand, sku: Optional[SKUMeta], variant: VariantInfo) -> Tuple[str, int, float]:
        # 1. System Selection (Based on description strings and business rules)
        system = "12T"
        desc_lower = demand.description.lower()
        is_cond = any(kw in desc_lower for kw in config.RULE_CONDITIONER)

        # Force 6T for Conditioners or explicitly named 6T variants
        if "6t" in desc_lower or (variant.gcas != "UNKNOWN" and "6T" in str(variant.gcas)) or is_cond:
            system = "6T"

        # 2. MSU Calculation
        if demand.material_code == config.GCAS_CLIMBAZOLE:
            msu = 1200.0 / config.MSU_UNIT_KG
        elif demand.material_code == config.GCAS_HC_BASE:
            msu = demand.quantity / config.MSU_UNIT_KG
        else:
            msu = self.calculate_msu(demand.quantity, variant.weight_per_container if variant else 0)

        # Downgrade small batches to 6T automatically
        if system == "12T" and msu < config.MSU_THRESHOLD_6T:
            system = "6T"

            # 3. BCT Lookup (Robust / Safe Mode)
        bct = config.DEFAULT_DURATION
        if sku:
            val = None
            if system == "12T":
                val = getattr(sku, 'bct_12t', getattr(sku, 'bct', None))
            elif system == "6T":
                val = getattr(sku, 'bct_6t', getattr(sku, 'bct', None))

            if val is not None:
                try:
                    bct = int(val)
                except (ValueError, TypeError):
                    bct = config.DEFAULT_DURATION

        return system, bct, msu


# ---------------------------------------------------------
# 2. SCHEDULER (INITIAL PLACEMENT & AGGREGATION)
# ---------------------------------------------------------
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
        print(f"--- Calculating Initial Schedule ({len(demands)} raw demands) ---")

        # --- STEP 1: PRE-PROCESS, FILTER & CALCULATE MSU ---
        enriched_demands = []
        skipped_auto = 0

        for d in demands:
            variant = self.enricher.find_variant_for_demand(d)

            # 1. Resolve GCAS
            gcas = variant.gcas if variant else "UNKNOWN"
            if d.material_code in [config.GCAS_HC_BASE, config.GCAS_CLIMBAZOLE]:
                gcas = d.material_code

            raw_gcas = str(gcas).strip().upper()

            # 2. BULLETPROOF FILTER: Drop Auto-Prepared / Missing GCAS Batches
            if raw_gcas in ['', 'NAN', 'NONE', 'NULL', 'UNKNOWN']:
                print(f"   > Dropping auto-prepared/unknown batch: {d.description}")
                skipped_auto += 1
                continue

            # 3. Calculate MSU
            msu = 0.0
            if gcas == config.GCAS_CLIMBAZOLE:
                msu = 1200.0 / config.MSU_UNIT_KG
            elif gcas == config.GCAS_HC_BASE:
                msu = d.quantity / config.MSU_UNIT_KG
            else:
                msu = self.enricher.calculate_msu(d.quantity, variant.weight_per_container if variant else 0)

            enriched_demands.append({
                "demand": d,
                "gcas": gcas,
                "variant": variant,
                "msu": msu
            })

        if skipped_auto > 0:
            print(f"   > Ignored {skipped_auto} un-routable auto-prepared batches.")

        # Sort chronologically by packing start time
        enriched_demands.sort(key=lambda x: x["demand"].pkg_start_dt)

        # --- STEP 2: AGGREGATE BATCHES GLOBALLY BY GCAS ---
        accumulating_demands = {}
        merged_demands_info = []

        for item in enriched_demands:
            gcas = item["gcas"]
            desc_lower = item["demand"].description.lower()
            is_replenish = "replenishment" in desc_lower

            # Dynamic Aggregation Limit: Cap Conditioners and 6T products at 2.3 MSU
            is_cond = any(kw in desc_lower for kw in config.RULE_CONDITIONER)
            is_explicit_6t = "6t" in desc_lower or (
                        item["variant"] and item["variant"].gcas != "UNKNOWN" and "6T" in str(item["variant"].gcas))

            max_msu_limit = config.MSU_THRESHOLD_6T if (is_cond or is_explicit_6t) else 4.6

            if is_replenish or gcas == "UNKNOWN":
                merged_demands_info.append(item)
                continue

            if gcas in accumulating_demands:
                current = accumulating_demands[gcas]
                combined_msu = current["msu"] + item["msu"]

                # Only merge if it safely fits in the designated system capacity
                if combined_msu <= max_msu_limit:
                    merged_demand = Demand(
                        order_id=f"{current['demand'].order_id} + {item['demand'].order_id}",
                        material_code=current["demand"].material_code,
                        description=current["demand"].description,
                        quantity=current["demand"].quantity + item["demand"].quantity,
                        pkg_start_dt=min(current["demand"].pkg_start_dt, item["demand"].pkg_start_dt),
                        pkg_end_dt=max(current["demand"].pkg_end_dt, item["demand"].pkg_end_dt),
                        line="MIXED" if current["demand"].line != item["demand"].line else current["demand"].line
                    )
                    accumulating_demands[gcas] = {
                        "demand": merged_demand,
                        "gcas": gcas,
                        "variant": current["variant"],
                        "msu": combined_msu
                    }
                else:
                    # Capacity full: Commit the current batch and start a new one
                    merged_demands_info.append(current)
                    accumulating_demands[gcas] = item
            else:
                accumulating_demands[gcas] = item

        for gcas, item in accumulating_demands.items():
            merged_demands_info.append(item)

        merged_demands_info.sort(key=lambda x: x["demand"].pkg_start_dt)
        print(f"   > Aggregated into {len(merged_demands_info)} unique making batches.")

        # --- STEP 3: ASSIGN TO PRODUCTION BATCHES ---
        batch_id_counter = 1
        self.batches = []

        for info in merged_demands_info:
            d = info["demand"]
            gcas = info["gcas"]
            variant = info["variant"]

            sku = self.enricher.master_data.get(gcas)
            system, bct, msu = self.enricher.select_system(d, sku, variant if variant else VariantInfo("UNK", 0.0))

            min_buffer = self._get_buffer_time(d.description)
            raw_mkg_end = d.pkg_start_dt - timedelta(minutes=min_buffer)
            raw_mkg_start = raw_mkg_end - timedelta(minutes=int(bct))
            final_mkg_start = self._apply_shift_constraints(raw_mkg_start)
            final_mkg_end = final_mkg_start + timedelta(minutes=int(bct))
            actual_buffer = int((d.pkg_start_dt - final_mkg_end).total_seconds() / 60)

            shift = self._get_shift(final_mkg_start)
            tech_type = "Single"
            if sku: tech_type = sku.tech_class

            bid = f"B{batch_id_counter:03d}"
            if "Replenishment" in d.description:
                bid = f"REP{batch_id_counter:02d}"

            batch = ProductionBatch(
                id=bid,
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


# ---------------------------------------------------------
# 3. TANK SCHEDULER (HYBRID OPTIMIZATION)
# ---------------------------------------------------------
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
        key = (str(prev_batch.sku_code).strip(), str(next_batch.sku_code).strip())
        if key in rules: return rules[key]
        return config.WASHOUT_DURATION

    def _get_shift(self, dt: datetime) -> str:
        """Helper to recalculate the shift based on mutated timestamps."""
        t = dt.time()
        if t >= time(7, 30) and t < time(15, 30): return "A"
        if t >= time(15, 30) and t < time(23, 30): return "B"
        return "C"

    def _push_past_shift_c(self, start_dt: datetime, duration_mins: int) -> datetime:
        """
        Intelligently pushes a batch forward until the entire batch avoids Shift C (23:30 - 07:30).
        """
        current_start = start_dt
        while True:
            end_dt = current_start + timedelta(minutes=duration_mins)
            overlap = False

            curr = current_start
            while curr < end_dt:
                t = curr.time()
                if t >= time(23, 30) or t < time(7, 30):
                    overlap = True
                    break
                curr += timedelta(minutes=10)

            if not overlap:
                t_end = end_dt.time()
                if (t_end > time(23, 30) or t_end < time(7, 30)) and t_end != time(7, 30) and t_end != time(23, 30):
                    overlap = True

            if overlap:
                t = current_start.time()
                if t >= time(23, 30):
                    current_start = (current_start + timedelta(days=1)).replace(hour=7, minute=30, second=0,
                                                                                microsecond=0)
                elif t < time(7, 30):
                    current_start = current_start.replace(hour=7, minute=30, second=0, microsecond=0)
                else:
                    current_start = (current_start + timedelta(days=1)).replace(hour=7, minute=30, second=0,
                                                                                microsecond=0)
            else:
                break

        return current_start

    def optimize(self, batches: List[ProductionBatch]) -> Tuple[List[ProductionBatch], List[dict]]:
        print("--- Optimizing Tank Queue (12T=JIT, 6T=Forward No-Shift-C) ---")

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

            if tank_name == "Tank_12T":
                # --- BACKWARD SCHEDULING (JIT) ---
                tank_batches.sort(key=lambda x: x.mkg_start_dt, reverse=True)
                for i, b in enumerate(tank_batches):
                    if i > 0:
                        next_b = tank_batches[i - 1]
                        is_b_cond = self._is_conditioner(b)
                        wash_dur = config.COND_POST_WASH if is_b_cond else self._get_matrix_washout(b, next_b)
                        gap = wash_dur + (config.COND_COOLDOWN if self._is_conditioner(next_b) else 0)

                        latest_end = next_b.mkg_start_dt - timedelta(minutes=gap)
                        if b.mkg_end_dt > latest_end:
                            b.mkg_end_dt = latest_end
                            b.mkg_start_dt = latest_end - timedelta(minutes=b.bct)

                    b.shift = self._get_shift(b.mkg_start_dt)
                    b.buffer_min = int((b.pkg_start_dt - b.mkg_end_dt).total_seconds() / 60)

                # Map washouts
                tank_batches.sort(key=lambda x: x.mkg_start_dt)
                for i in range(1, len(tank_batches)):
                    prev = tank_batches[i - 1]
                    curr = tank_batches[i]
                    is_prev_cond = self._is_conditioner(prev)
                    wash_dur = config.COND_POST_WASH if is_prev_cond else self._get_matrix_washout(prev, curr)
                    if wash_dur > 0:
                        washouts.append({
                            "System": curr.system,
                            "Start": prev.mkg_end_dt,
                            "End": prev.mkg_end_dt + timedelta(minutes=wash_dur),
                            "Desc": "COND WASH (60m)" if is_prev_cond else "WASHOUT"
                        })
                final_batches.extend(tank_batches)

            else:
                # --- ITERATIVE FORWARD SCHEDULING (6T / 1.25T) ---
                tank_batches.sort(key=lambda x: x.mkg_start_dt)
                anchor_dt = tank_batches[0].mkg_start_dt

                for iteration in range(15):
                    max_violation = 0

                    for i, b in enumerate(tank_batches):
                        if i == 0:
                            b.mkg_start_dt = self._push_past_shift_c(anchor_dt, b.bct)
                            b.mkg_end_dt = b.mkg_start_dt + timedelta(minutes=b.bct)
                        else:
                            prev = tank_batches[i - 1]
                            wash_dur = config.COND_POST_WASH if self._is_conditioner(
                                prev) else self._get_matrix_washout(prev, b)
                            gap = wash_dur + (config.COND_COOLDOWN if self._is_conditioner(b) else 0)

                            proposed_start = prev.mkg_end_dt + timedelta(minutes=gap)
                            b.mkg_start_dt = self._push_past_shift_c(proposed_start, b.bct)
                            b.mkg_end_dt = b.mkg_start_dt + timedelta(minutes=b.bct)

                        min_buf = config.BUFFER_COND if self._is_conditioner(b) else config.BUFFER_STD
                        current_buffer = (b.pkg_start_dt - b.mkg_end_dt).total_seconds() / 60

                        if current_buffer < min_buf:
                            violation = min_buf - current_buffer
                            if violation > max_violation:
                                max_violation = violation

                    if max_violation <= 0:
                        break
                    else:
                        anchor_dt -= timedelta(minutes=max_violation)

                # Assign final buffers and map washouts
                for i, b in enumerate(tank_batches):
                    b.shift = self._get_shift(b.mkg_start_dt)
                    b.buffer_min = int((b.pkg_start_dt - b.mkg_end_dt).total_seconds() / 60)

                    if i > 0:
                        prev = tank_batches[i - 1]
                        is_prev_cond = self._is_conditioner(prev)
                        wash_dur = config.COND_POST_WASH if is_prev_cond else self._get_matrix_washout(prev, b)
                        if wash_dur > 0:
                            washouts.append({
                                "System": b.system,
                                "Start": prev.mkg_end_dt,
                                "End": prev.mkg_end_dt + timedelta(minutes=wash_dur),
                                "Desc": "COND WASH (60m)" if is_prev_cond else "WASHOUT"
                            })
                final_batches.extend(tank_batches)

        return final_batches, washouts


# ---------------------------------------------------------
# 4. STORAGE ASSIGNER (SPLIT ROUTING + WASHOUT QUEUEING)
# ---------------------------------------------------------
class StorageAssigner:
    def __init__(self, tank_snapshot: pd.DataFrame, pst_wo_matrix: dict = None):
        self.pst_wo_matrix = pst_wo_matrix or {}
        self.tanks = {}
        self.portable_tanks = [f"TK#_{i}_#" for i in range(1, 29)]
        self.ronchi_tanks = ["TK#_51_#", "TK#_52_#", "TK#_53_#"]
        self.allowed_tanks = self.portable_tanks + self.ronchi_tanks

        if not tank_snapshot.empty:
            for _, row in tank_snapshot.iterrows():
                tid = row['tank_id']
                if tid not in self.allowed_tanks: continue

                is_usable = False
                code = int(row['color_code']) if pd.notna(row['color_code']) else 0
                gcas = str(row['current_gcas']).strip()
                if code in [1, 7, 14]: is_usable = True

                tank_type = "RONCHI" if tid in self.ronchi_tanks else "PORTABLE"

                self.tanks[tid] = {
                    "available_at": datetime(2000, 1, 1),
                    "status_code": code,
                    "current_gcas": gcas,
                    "is_usable": is_usable,
                    "type": tank_type
                }

    def assign_tanks(self, batches: List[ProductionBatch]):
        print("--- Assigning Storage Tanks (Split Routing + Dynamic Washouts) ---")
        batches.sort(key=lambda x: x.mkg_end_dt)

        for b in batches:
            needed_start = b.mkg_end_dt
            needed_end = b.pkg_end_dt
            gcas = str(b.sku_code).strip()
            is_12t = "12T" in b.system

            ronchi_candidates = []
            portable_candidates = []

            for tid, state in self.tanks.items():
                if not state["is_usable"]: continue

                tank_gcas = state["current_gcas"]
                is_clean = (state["status_code"] == 1)
                wash_time = 0

                # 1. Determine Washout Requirement
                if is_clean:
                    wash_time = 0
                elif tank_gcas == gcas:
                    wash_time = 0  # Continuous run of the same product
                else:
                    # Tank contains a different product. Lookup 20 min wash time in matrix.
                    key = (tank_gcas, gcas)
                    wash_time = self.pst_wo_matrix.get(key, 20)

                    # 2. Calculate when the tank is ACTUALLY ready
                ready_at = state["available_at"] + timedelta(minutes=wash_time)

                if ready_at > needed_start:
                    continue  # Tank won't finish washing in time

                # 3. Score the tank
                score = -1
                if wash_time == 0 and tank_gcas == gcas:
                    score = 1  # Best: Same product
                elif wash_time == 0 and is_clean:
                    score = 2  # Good: Already Clean
                else:
                    score = 3  # Viable: Needs a Washout

                idle_time = (needed_start - ready_at).total_seconds()

                if state["type"] == "RONCHI":
                    ronchi_candidates.append((score, idle_time, tid))
                else:
                    portable_candidates.append((score, idle_time, tid))

            ronchi_candidates.sort(key=lambda x: (x[0], x[1]))
            portable_candidates.sort(key=lambda x: (x[0], x[1]))

            assigned_tanks = []

            if is_12t:
                if ronchi_candidates:
                    assigned_tanks.append(ronchi_candidates[0][2])
                elif len(portable_candidates) >= 2:
                    assigned_tanks.append(portable_candidates[0][2])
                    assigned_tanks.append(portable_candidates[1][2])
            else:
                if portable_candidates:
                    assigned_tanks.append(portable_candidates[0][2])

            if assigned_tanks:
                b.storage_tank = " + ".join(assigned_tanks)

                for tank in assigned_tanks:
                    # The tank will now be busy until the packing ends, and will hold the new GCAS
                    self.tanks[tank]["available_at"] = needed_end
                    self.tanks[tank]["current_gcas"] = gcas
                    self.tanks[tank]["status_code"] = 7
            else:
                b.storage_tank = "NO_TANK_AVAILABLE"