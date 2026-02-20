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

        if demand.description in self.bulk_map:
            return self.bulk_map[demand.description]

        clean_desc = self._normalize_text(demand.description)
        if clean_desc in self.clean_bulk_map:
            return self.clean_bulk_map[clean_desc]

        return None

    def calculate_msu(self, quantity_cases: float, weight_per_case: float) -> float:
        total_kg = quantity_cases * weight_per_case
        return total_kg / config.MSU_UNIT_KG

    def select_system(self, demand: Demand, sku: Optional[SKUMeta], variant: VariantInfo) -> Tuple[str, int, float]:
        system = "12T"
        desc_lower = demand.description.lower()
        is_cond = any(kw in desc_lower for kw in config.RULE_CONDITIONER)

        if "6t" in desc_lower or (variant.gcas != "UNKNOWN" and "6T" in str(variant.gcas)) or is_cond:
            system = "6T"

        if demand.material_code == config.GCAS_CLIMBAZOLE:
            msu = 1200.0 / config.MSU_UNIT_KG
        elif demand.material_code == config.GCAS_HC_BASE:
            msu = demand.quantity / config.MSU_UNIT_KG
        else:
            msu = self.calculate_msu(demand.quantity, variant.weight_per_container if variant else 0)

        if system == "12T" and msu < config.MSU_THRESHOLD_6T:
            system = "6T"

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

        enriched_demands = []
        skipped_auto = 0

        for d in demands:
            variant = self.enricher.find_variant_for_demand(d)

            gcas = variant.gcas if variant else "UNKNOWN"
            if d.material_code in [config.GCAS_HC_BASE, config.GCAS_CLIMBAZOLE]:
                gcas = d.material_code

            raw_gcas = str(gcas).strip().upper()

            if raw_gcas in ['', 'NAN', 'NONE', 'NULL', 'UNKNOWN']:
                print(f"   > Dropping auto-prepared/unknown batch: {d.description}")
                skipped_auto += 1
                continue

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

        enriched_demands.sort(key=lambda x: x["demand"].pkg_start_dt)

        # --- STEP 2: AGGREGATE BATCHES DYNAMICALLY ---
        accumulating_demands = {}
        merged_demands_info = []

        for item in enriched_demands:
            gcas = item["gcas"]
            desc_lower = item["demand"].description.lower()
            is_replenish = "replenishment" in desc_lower

            # DYNAMIC LIMITS
            is_cond = any(kw in desc_lower for kw in config.RULE_CONDITIONER)
            is_explicit_6t = "6t" in desc_lower or (
                        item["variant"] and item["variant"].gcas != "UNKNOWN" and "6T" in str(item["variant"].gcas))

            # Restrict conditioners to max ~1.2 MSU (approx 2 batches)
            if is_cond:
                max_msu_limit = 1.2
            elif is_explicit_6t:
                max_msu_limit = config.MSU_THRESHOLD_6T
            else:
                max_msu_limit = 4.6

            if is_replenish or gcas == "UNKNOWN":
                merged_demands_info.append(item)
                continue

            if gcas in accumulating_demands:
                current = accumulating_demands[gcas]
                combined_msu = current["msu"] + item["msu"]

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
        t = dt.time()
        if t >= time(7, 30) and t < time(15, 30): return "A"
        if t >= time(15, 30) and t < time(23, 30): return "B"
        return "C"

    def _avoid_shift_c(self, start_dt: datetime, duration_mins: int, forward: bool = True) -> datetime:
        """Bidirectional engine to ensure a batch strictly avoids 23:30 - 07:30."""
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
                curr += timedelta(minutes=5)

            if not overlap:
                t_end = end_dt.time()
                if (t_end > time(23, 30) or t_end < time(7, 30)) and t_end != time(7, 30) and t_end != time(23, 30):
                    overlap = True

            if overlap:
                if forward:
                    if current_start.time() >= time(23, 30):
                        current_start = (current_start + timedelta(days=1)).replace(hour=7, minute=30, second=0,
                                                                                    microsecond=0)
                    else:
                        current_start = current_start.replace(hour=7, minute=30, second=0, microsecond=0)
                else:
                    if current_start.time() <= time(7, 30):
                        target_end = (current_start - timedelta(days=1)).replace(hour=23, minute=30, second=0,
                                                                                 microsecond=0)
                    elif current_start.time() >= time(23, 30):
                        target_end = current_start.replace(hour=23, minute=30, second=0, microsecond=0)
                    else:
                        target_end = current_start.replace(hour=23, minute=30, second=0, microsecond=0)

                    current_start = target_end - timedelta(minutes=duration_mins)
            else:
                break

        return current_start

    def optimize(self, batches: List[ProductionBatch]) -> Tuple[List[ProductionBatch], List[dict]]:
        print("--- Optimizing Tank Queue (Shift Isolation & Fluid Routing) ---")

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
                # --- BACKWARD SCHEDULING ---
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

                    # SHIFT EJECTION: Pull backward if line is not INT2
                    if b.line != "INT2":
                        b.mkg_start_dt = self._avoid_shift_c(b.mkg_start_dt, b.bct, forward=False)
                        b.mkg_end_dt = b.mkg_start_dt + timedelta(minutes=b.bct)

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
                # --- FORWARD SCHEDULING ---
                tank_batches.sort(key=lambda x: x.mkg_start_dt)
                anchor_dt = tank_batches[0].mkg_start_dt

                for iteration in range(15):
                    max_violation = 0

                    for i, b in enumerate(tank_batches):
                        if i == 0:
                            proposed_start = anchor_dt
                        else:
                            prev = tank_batches[i - 1]
                            wash_dur = config.COND_POST_WASH if self._is_conditioner(
                                prev) else self._get_matrix_washout(prev, b)
                            gap = wash_dur + (config.COND_COOLDOWN if self._is_conditioner(b) else 0)
                            proposed_start = prev.mkg_end_dt + timedelta(minutes=gap)

                        # SHIFT EJECTION: Push forward if line is not INT2
                        if b.line != "INT2":
                            b.mkg_start_dt = self._avoid_shift_c(proposed_start, b.bct, forward=True)
                        else:
                            b.mkg_start_dt = proposed_start

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

                # Map washouts
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
# 4. STORAGE ASSIGNER (FAST-RELEASE + UNIVERSAL CIP + DEDICATED TANKS)
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

                code = int(row['color_code']) if pd.notna(row['color_code']) else 0
                gcas = str(row['current_gcas']).strip()
                tank_type = "RONCHI" if tid in self.ronchi_tanks else "PORTABLE"

                self.tanks[tid] = {
                    "available_at": datetime(2000, 1, 1),
                    "status_code": code,
                    "current_gcas": gcas,
                    "is_usable": True,
                    "type": tank_type
                }

    def assign_tanks(self, batches: List[ProductionBatch]):
        print("--- Assigning Storage Tanks (Pkg Start Release + Dedicated Tanks) ---")
        batches.sort(key=lambda x: x.mkg_end_dt)

        cond_pref_tanks = ["TK#_25_#", "TK#_26_#", "TK#_27_#", "TK#_28_#"]
        cond_fallback_tanks = [f"TK#_{i}_#" for i in range(1, 25)]

        for b in batches:
            needed_start = b.mkg_end_dt
            tank_freed_at = b.pkg_start_dt
            gcas = str(b.sku_code).strip()

            # --- 1. DEDICATED TANK ROUTING FOR INTERMEDIATES ---
            if gcas == config.GCAS_HC_BASE:
                b.storage_tank = "HC Base Tank"
                continue
            elif gcas == config.GCAS_CLIMBAZOLE:
                b.storage_tank = "Climbazole Tank"
                continue

            is_12t = "12T" in b.system
            is_cond = any(kw in b.desc.lower() for kw in config.RULE_CONDITIONER)
            is_int2 = (b.line == "INT2")

            ronchi_candidates = []
            portable_candidates = []

            for tid, state in self.tanks.items():
                if not state["is_usable"]: continue

                tank_gcas = state["current_gcas"]
                is_clean = (state["status_code"] == 1)
                wash_time = 0

                if is_clean:
                    wash_time = 0
                elif tank_gcas == gcas:
                    wash_time = 0
                else:
                    wash_time = self.pst_wo_matrix.get((tank_gcas, gcas), 20)

                ready_at = state["available_at"] + timedelta(minutes=wash_time)

                if ready_at > needed_start:
                    continue

                score = 0
                if wash_time == 0 and tank_gcas == gcas:
                    score = 1
                elif wash_time == 0 and is_clean:
                    score = 2
                else:
                    score = 3

                penalty = 0
                if is_cond:
                    if tid in cond_pref_tanks:
                        penalty = 0
                    elif tid in cond_fallback_tanks:
                        penalty = 10
                    else:
                        continue
                elif is_int2:
                    if state["type"] == "RONCHI":
                        penalty = 0
                    elif state["type"] == "PORTABLE":
                        penalty = 5
                    else:
                        continue
                else:
                    if state["type"] == "PORTABLE":
                        penalty = 0
                    elif state["type"] == "RONCHI" and is_12t:
                        penalty = 5
                    else:
                        penalty = 10

                final_score = score + penalty
                idle_time = (needed_start - ready_at).total_seconds()

                if state["type"] == "RONCHI":
                    ronchi_candidates.append((final_score, idle_time, tid, wash_time))
                else:
                    portable_candidates.append((final_score, idle_time, tid, wash_time))

            ronchi_candidates.sort(key=lambda x: (x[0], x[1]))
            portable_candidates.sort(key=lambda x: (x[0], x[1]))

            assigned_tanks = []

            if is_12t:
                path_ronchi = ronchi_candidates[0] if ronchi_candidates else None
                path_portable = None

                if len(portable_candidates) >= 2:
                    max_score = max(portable_candidates[0][0], portable_candidates[1][0])
                    total_idle = portable_candidates[0][1] + portable_candidates[1][1]
                    path_portable = (max_score, total_idle,
                                     portable_candidates[0][2], portable_candidates[0][3],
                                     portable_candidates[1][2], portable_candidates[1][3])

                if path_ronchi and path_portable:
                    if path_ronchi[0] <= path_portable[0]:
                        assigned_tanks.append((path_ronchi[2], path_ronchi[3]))
                    else:
                        assigned_tanks.extend(
                            [(path_portable[2], path_portable[3]), (path_portable[4], path_portable[5])])
                elif path_ronchi:
                    assigned_tanks.append((path_ronchi[2], path_ronchi[3]))
                elif path_portable:
                    assigned_tanks.extend([(path_portable[2], path_portable[3]), (path_portable[4], path_portable[5])])
            else:
                if portable_candidates:
                    assigned_tanks.append((portable_candidates[0][2], portable_candidates[0][3]))

            if assigned_tanks:
                tank_labels = []
                for tank_id, w_time in assigned_tanks:
                    label = f"{tank_id} [Wash {w_time}m]" if w_time > 0 else tank_id
                    tank_labels.append(label)

                    self.tanks[tank_id]["available_at"] = tank_freed_at
                    self.tanks[tank_id]["current_gcas"] = gcas
                    self.tanks[tank_id]["status_code"] = 7

                b.storage_tank = " + ".join(tank_labels)

                if is_cond and any(tk_id in cond_fallback_tanks for tk_id, _ in assigned_tanks):
                    warning = "WARN: Non-standard Cond tank"
                    b.mrp_status = warning if not b.mrp_status or b.mrp_status == "OK" else f"{b.mrp_status} | {warning}"
            else:
                b.storage_tank = "NO_TANK_AVAILABLE"