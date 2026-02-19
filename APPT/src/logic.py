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
            return VariantInfo(gcas=demand.material_code, weight_per_container=0)

        original_desc = demand.description.strip()
        if original_desc in self.bulk_map: return self.bulk_map[original_desc]
        demand_clean = self._normalize_text(original_desc)
        if demand_clean in self.clean_bulk_map: return self.clean_bulk_map[demand_clean]
        for key, variant in self.clean_bulk_map.items():
            if len(demand_clean) > 5 and (demand_clean in key or key in demand_clean):
                return variant
        desc_lower = original_desc.lower()
        for keyword in config.RULE_CLIMBAZOLE:
            if keyword in desc_lower: return VariantInfo(gcas=config.GCAS_CLIMBAZOLE, weight_per_container=0)
        return None

    def calculate_msu(self, quantity: float, weight_per_container: float) -> float:
        if weight_per_container <= 0 or quantity <= 0: return 0.0
        return (quantity * weight_per_container) / config.MSU_UNIT_KG

    def select_system(self, demand: Demand, sku: SKUMeta, variant: VariantInfo) -> Tuple[str, float, float]:
        desc_lower = str(demand.description).lower()

        # 1. Climbazole Premix (GCAS 91879323)
        if demand.material_code == config.GCAS_CLIMBAZOLE or any(k in desc_lower for k in config.RULE_CLIMBAZOLE):
            msu_size = 1200.0 / config.MSU_UNIT_KG
            return ("1.25T", 180, msu_size)

        # 2. HC Base (GCAS 95619314)
        if demand.material_code == config.GCAS_HC_BASE or any(k in desc_lower for k in config.RULE_HC_BASE):
            needed_kg = demand.quantity
            target = "12T"
            if needed_kg > 0 and needed_kg <= 2900:
                target = "6T"

            batch_kg = 5900.0 if target == "12T" else 2900.0
            msu_size = batch_kg / config.MSU_UNIT_KG
            return (target, self._get_bct(sku, target), msu_size)

        # Standard Logic for Consumer Goods
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

        # --- STEP 1: PRE-PROCESS & CALCULATE MSU ---
        enriched_demands = []
        for d in demands:
            variant = self.enricher.find_variant_for_demand(d)
            gcas = variant.gcas if variant else "UNKNOWN"
            if d.material_code in [config.GCAS_HC_BASE, config.GCAS_CLIMBAZOLE]:
                gcas = d.material_code

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

        # Sort chronologically by packing start time
        enriched_demands.sort(key=lambda x: x["demand"].pkg_start_dt)

        # --- STEP 2: AGGREGATE BATCHES GLOBALLY BY GCAS ---
        accumulating_demands = {}
        merged_demands_info = []
        max_12t_msu = 4.6  # Safe maximum physical capacity for a 12T system

        for item in enriched_demands:
            gcas = item["gcas"]
            is_replenish = "Replenishment" in item["demand"].description

            # Don't merge replenishments or unknown SKUs
            if is_replenish or gcas == "UNKNOWN":
                merged_demands_info.append(item)
                continue

            # If we are already tracking this GCAS, try to add to it
            if gcas in accumulating_demands:
                current = accumulating_demands[gcas]
                combined_msu = current["msu"] + item["msu"]

                if combined_msu <= max_12t_msu:
                    # It fits! Merge them together.
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
                    # It exceeds 12T capacity. Commit the old one and start a new pool.
                    merged_demands_info.append(current)
                    accumulating_demands[gcas] = item
            else:
                # Start tracking a new GCAS pool
                accumulating_demands[gcas] = item

        # Flush any remaining pools into the final list
        for gcas, item in accumulating_demands.items():
            merged_demands_info.append(item)

        # Re-sort the final merged list chronologically by earliest pkg_start_dt
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
# 3. TANK SCHEDULER (OPTIMIZATION)
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

        # FIXED: Matrix in SQL is (source, target), so it must be (prev, next)
        key = (str(prev_batch.sku_code).strip(), str(next_batch.sku_code).strip())

        if key in rules: return rules[key]
        return config.WASHOUT_DURATION

    def optimize(self, batches: List[ProductionBatch]) -> Tuple[List[ProductionBatch], List[dict]]:
        print("--- Optimizing Tank Queue (Forward Continuous Packing) ---")

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

            # 1. FORWARD SCHEDULING: Sort chronologically (earliest needed first)
            tank_batches.sort(key=lambda x: x.mkg_start_dt)

            scheduled = []
            last_scheduled_batch = None

            for b in tank_batches:
                if last_scheduled_batch is None:
                    # The very first batch of the week stays at its ideal time
                    scheduled.append(b)
                    last_scheduled_batch = b
                else:
                    is_prev_cond = self._is_conditioner(last_scheduled_batch)
                    is_curr_cond = self._is_conditioner(b)

                    wash_dur = 0
                    wash_type = None

                    # If the PREVIOUS batch was a conditioner, we must run a post-wash
                    if is_prev_cond:
                        wash_dur = config.COND_POST_WASH
                        wash_type = "COND_WASH"
                    else:
                        wash_dur = self._get_matrix_washout(last_scheduled_batch, b)
                        if wash_dur > 0: wash_type = "STD_WASH"

                    required_gap = wash_dur
                    if is_curr_cond:
                        required_gap += config.COND_COOLDOWN

                    # The moment the previous batch + wash/cooldown finishes, we start the next one!
                    earliest_start = last_scheduled_batch.mkg_end_dt + timedelta(minutes=required_gap)

                    # Snap the batch forward to run continuously
                    new_start = earliest_start
                    new_end = new_start + timedelta(minutes=b.bct)

                    b.mkg_start_dt = new_start
                    b.mkg_end_dt = new_end

                    # Recalculate the buffer time (it will now be much higher for later batches!)
                    b.buffer_min = int((b.pkg_start_dt - b.mkg_end_dt).total_seconds() / 60)

                    if wash_type:
                        desc = "COND WASH (60m)" if wash_type == "COND_WASH" else "WASHOUT"
                        washouts.append({
                            "System": b.system,
                            "Start": last_scheduled_batch.mkg_end_dt,
                            "End": last_scheduled_batch.mkg_end_dt + timedelta(minutes=wash_dur),
                            "Desc": desc
                        })

                    scheduled.append(b)
                    last_scheduled_batch = b
            final_batches.extend(scheduled)

        return final_batches, washouts


# ---------------------------------------------------------
# 4. STORAGE ASSIGNER
# ---------------------------------------------------------
class StorageAssigner:
    def __init__(self, tank_snapshot: pd.DataFrame):
        self.tanks = {}

        # Define allowed tanks specifically requested
        self.portable_tanks = [f"TK#_{i}_#" for i in range(1, 29)]
        self.ronchi_tanks = ["TK#_51_#", "TK#_52_#", "TK#_53_#"]
        self.allowed_tanks = self.portable_tanks + self.ronchi_tanks

        if not tank_snapshot.empty:
            for _, row in tank_snapshot.iterrows():
                tid = row['tank_id']

                # Filter out any tank not in the allowed list
                if tid not in self.allowed_tanks:
                    continue

                is_usable = False
                code = int(row['color_code']) if pd.notna(row['color_code']) else 0
                gcas = str(row['current_gcas']).strip()

                if code in [1, 7, 14]:
                    is_usable = True

                tank_type = "RONCHI" if tid in self.ronchi_tanks else "PORTABLE"

                self.tanks[tid] = {
                    "available_at": datetime(2000, 1, 1),  # Safe historical date to prevent overflow
                    "status_code": code,
                    "current_gcas": gcas,
                    "is_usable": is_usable,
                    "type": tank_type
                }

    def assign_tanks(self, batches: List[ProductionBatch]):
        print("--- Assigning Storage Tanks (Unified Pool) ---")
        batches.sort(key=lambda x: x.mkg_end_dt)

        for b in batches:
            needed_start = b.mkg_end_dt
            needed_end = b.pkg_end_dt
            gcas = str(b.sku_code).strip()

            candidates = []

            for tid, state in self.tanks.items():
                if not state["is_usable"]: continue
                # REMOVED the system size constraint! Any batch can go to any tank.
                if state["available_at"] > needed_start: continue

                score = -1

                # 1. Dirty + Same Product (Best)
                if state["status_code"] == 7 and state["current_gcas"] == gcas:
                    score = 1
                # 2. Clean (Good)
                elif state["status_code"] == 1:
                    score = 2
                # 3. Washout Due (Okay)
                elif state["status_code"] == 14:
                    score = 3
                # 4. Dirty + Diff Product (Okay, needs wash)
                elif state["status_code"] == 7:
                    score = 4

                if score > 0:
                    # Calculate idle time to tie-break (minimize time tank sits empty)
                    idle_time = (needed_start - state["available_at"]).total_seconds()
                    candidates.append((score, idle_time, tid))

            # Sort by Score (primary), then by Idle Time ascending (secondary)
            candidates.sort(key=lambda x: (x[0], x[1]))

            if candidates:
                best_tank = candidates[0][2]
                b.storage_tank = best_tank

                self.tanks[best_tank]["available_at"] = needed_end
                self.tanks[best_tank]["current_gcas"] = gcas
                self.tanks[best_tank]["status_code"] = 7
            else:
                b.storage_tank = "NO_TANK_AVAILABLE"