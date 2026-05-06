import pandas as pd
from typing import List, Dict
from datetime import timedelta
from src import config, db
from src.models import ProductionBatch, SKUMeta, Demand


class MaterialPlanner:
    def __init__(self, sku_master: Dict[str, SKUMeta]):
        self.sku_master = sku_master
        self.inventory = {}
        self._load_inventory()

    def _load_inventory(self):
        print("--- Loading Inventory for MRP ---")
        engine = db.get_engine()
        if not engine:
            print("[MRP Error] Database engine not initialized. Cannot load inventory.")
            return

        try:
            # ---> ENTERPRISE FIX: Added table prefix <---
            df = pd.read_sql("SELECT tank_name, current_value FROM pg_auto_tool_table_rm_status_data", engine)

            raw_levels = dict(zip(df['tank_name'], df['current_value']))
            for ing_key, tank_list in config.MRP_INGREDIENTS.items():
                total = 0.0
                for tank in tank_list:
                    val = raw_levels.get(tank, 0.0)
                    if pd.notna(val): total += float(val)
                self.inventory[ing_key] = total
        except Exception as e:
            print(f"[MRP Error] Could not load inventory: {e}")

    def check_plan_and_replenish(self, batches: List[ProductionBatch]) -> List[Demand]:
        print("--- Running MRP Simulation (JIT Replenishment Mode + Capacity Limits) ---")

        events = []
        for b in batches:
            events.append({"time": b.mkg_start_dt, "type": "CONSUME", "batch": b})
            events.append({"time": b.mkg_end_dt, "type": "PRODUCE", "batch": b})
        events.sort(key=lambda x: x["time"])

        sim_inv = self.inventory.copy()
        replenish_orders = []

        for b in batches: b.mrp_status = "OK"

        for evt in events:
            b = evt["batch"]
            desc_lower = str(b.desc).lower()

            if evt["type"] == "PRODUCE":
                produced_qty_kg = b.total_msu * getattr(config, 'MSU_UNIT_KG', 2571.0)

                if b.sku_code == config.GCAS_CLIMBAZOLE or "climbazole" in desc_lower:
                    sim_inv["climbazole"] = sim_inv.get("climbazole", 0.0) + produced_qty_kg
                    # Capacity Alert Logic
                    if sim_inv["climbazole"] > 3000.0:
                        warn_msg = "WARN: MAX CAP (3T) EXCEEDED"
                        b.mrp_status = warn_msg if b.mrp_status == "OK" else f"{b.mrp_status} | {warn_msg}"

                elif b.sku_code == config.GCAS_HC_BASE or "hc base" in desc_lower:
                    sim_inv["hc_base"] = sim_inv.get("hc_base", 0.0) + produced_qty_kg
                    # Capacity Alert Logic
                    if sim_inv["hc_base"] > 12000.0:
                        warn_msg = "WARN: MAX CAP (12T) EXCEEDED"
                        b.mrp_status = warn_msg if b.mrp_status == "OK" else f"{b.mrp_status} | {warn_msg}"

            elif evt["type"] == "CONSUME":
                sku = self.sku_master.get(b.sku_code)
                if not sku:
                    if b.mrp_status == "OK": b.mrp_status = "UNKNOWN_SKU"
                    continue

                sys_prefix = "6t" if "6T" in b.system else "12t"

                for ing_name in config.MRP_INGREDIENTS.keys():
                    recipe_key = f"{sys_prefix}_{ing_name}"
                    required_qty = sku.recipes.get(recipe_key, 0.0)

                    if required_qty > 0:
                        current = sim_inv.get(ing_name, 0.0)

                        if current < required_qty:
                            deficit = required_qty - current

                            can_replenish = False
                            rep_gcas = ""
                            rep_desc = ""
                            qty_to_order = 0.0

                            if ing_name == "hc_base":
                                can_replenish = True
                                rep_gcas = getattr(config, 'GCAS_HC_BASE', '')
                                rep_desc = "Auto-Replenishment HC Base (12T)"
                                qty_to_order = 5900.0
                                # Dynamic Safety Clamp to strictly prevent overflow above 12T (12000kg)
                                if current + qty_to_order > 12000.0:
                                    qty_to_order = max(0.0, 12000.0 - current)

                            elif ing_name == "climbazole":
                                can_replenish = True
                                rep_gcas = getattr(config, 'GCAS_CLIMBAZOLE', '')
                                rep_desc = "Auto-Replenishment Climbazole"
                                qty_to_order = 1200.0
                                # Dynamic Safety Clamp to strictly prevent overflow above 3T (3000kg)
                                if current + qty_to_order > 3000.0:
                                    qty_to_order = max(0.0, 3000.0 - current)

                            if can_replenish and qty_to_order > 0:
                                needed_time = b.mkg_start_dt - timedelta(minutes=30)
                                new_demand = Demand(
                                    order_id=f"AUTO_{len(replenish_orders) + 1}",
                                    material_code=rep_gcas,
                                    description=rep_desc,
                                    quantity=qty_to_order,
                                    pkg_start_dt=needed_time,
                                    pkg_end_dt=needed_time + timedelta(hours=1),
                                    line="INTERNAL"
                                )
                                replenish_orders.append(new_demand)

                                sim_inv[ing_name] += qty_to_order
                                print(
                                    f"   [!] JIT Shortage of {ing_name} (needs {deficit:.0f}kg). Queueing {qty_to_order:.0f}kg at {needed_time.strftime('%Y-%m-%d %H:%M')}.")
                                b.mrp_status = f"REPLENISHED: {ing_name.upper()}"
                            else:
                                if b.mrp_status == "OK":
                                    b.mrp_status = f"LOW: {ing_name.upper()}"

                        sim_inv[ing_name] -= required_qty

        return replenish_orders