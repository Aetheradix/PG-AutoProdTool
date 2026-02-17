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
        """Loads live tank levels from SQL."""
        print("--- Loading Inventory for MRP ---")
        try:
            # Using get_engine for pandas
            df = pd.read_sql("SELECT tank_name, current_value FROM rm_status_data", db.get_engine())
            raw_levels = dict(zip(df['tank_name'], df['current_value']))

            for ing_key, tank_list in config.MRP_INGREDIENTS.items():
                total = 0.0
                for tank in tank_list:
                    val = raw_levels.get(tank, 0.0)
                    if pd.notna(val):
                        total += float(val)
                self.inventory[ing_key] = total
        except Exception as e:
            print(f"[MRP Error] Could not load inventory: {e}")

    def check_plan_and_replenish(self, batches: List[ProductionBatch]) -> List[Demand]:
        print("--- Running MRP Simulation (Replenishment Mode) ---")

        events = []
        for b in batches:
            events.append({"time": b.mkg_start_dt, "type": "CONSUME", "batch": b})
            events.append({"time": b.mkg_end_dt, "type": "PRODUCE", "batch": b})

        events.sort(key=lambda x: x["time"])

        sim_inv = self.inventory.copy()
        replenish_orders = []

        # We don't need 'ordered_keys' anymore because crediting the inventory prevents duplicates naturally

        for b in batches: b.mrp_status = "OK"

        for evt in events:
            b = evt["batch"]
            desc_lower = str(b.desc).lower()

            if evt["type"] == "PRODUCE":
                produced_qty_kg = b.total_msu * config.MSU_UNIT_KG
                if b.sku_code == config.GCAS_CLIMBAZOLE or "climbazole" in desc_lower:
                    sim_inv["climbazole"] += produced_qty_kg
                elif b.sku_code == config.GCAS_HC_BASE or "hc base" in desc_lower:
                    sim_inv["hc_base"] += produced_qty_kg

            elif evt["type"] == "CONSUME":
                sku = self.sku_master.get(b.sku_code)
                if not sku:
                    b.mrp_status = "UNKNOWN_SKU"
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
                                rep_gcas = config.GCAS_HC_BASE
                                rep_desc = "Auto-Replenishment HC Base"
                                # Logic: If deficit is huge, order 12T size, else 6T size
                                qty_to_order = 5900.0 if deficit > 2900 else 2900.0

                            elif ing_name == "climbazole":
                                can_replenish = True
                                rep_gcas = config.GCAS_CLIMBAZOLE
                                rep_desc = "Auto-Replenishment Climbazole"
                                qty_to_order = 1200.0

                            if can_replenish:
                                # 1. Create Order
                                needed_time = b.mkg_start_dt
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

                                # 2. CRITICAL FIX: Credit Inventory IMMEDIATELY
                                # This simulates the order arriving just in time
                                sim_inv[ing_name] += qty_to_order

                                print(f"   [!] Shortage of {ing_name} (-{deficit:.0f}kg). Queueing {qty_to_order}kg.")

                                b.mrp_status = f"REPLENISHED: {ing_name.upper()}"
                            else:
                                # Cannot replenish automatically (e.g., SLS from supplier)
                                b.mrp_status = f"LOW: {ing_name.upper()}"

                        # Deduct consumption
                        sim_inv[ing_name] -= required_qty

        return replenish_orders