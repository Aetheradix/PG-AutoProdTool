import pandas as pd
from typing import List, Dict
from src import config, db
from src.models import ProductionBatch, SKUMeta


class MaterialPlanner:
    def __init__(self, sku_master: Dict[str, SKUMeta]):
        self.sku_master = sku_master
        self.inventory = {}
        self._load_inventory()

    def _load_inventory(self):
        """Loads live tank levels from SQL and pools them by ingredient."""
        print("--- Loading Inventory for MRP ---")
        try:
            # Fetch latest levels
            df = pd.read_sql("SELECT tank_name, current_value FROM rm_status_data", db.get_connection())

            raw_levels = dict(zip(df['tank_name'], df['current_value']))

            # Aggregate based on config map
            for ing_key, tank_list in config.MRP_INGREDIENTS.items():
                total = 0.0
                for tank in tank_list:
                    val = raw_levels.get(tank, 0.0)
                    if pd.notna(val):
                        total += float(val)
                self.inventory[ing_key] = total
                # print(f"  > {ing_key.upper()}: {total:.2f} kg")

        except Exception as e:
            print(f"[MRP Error] Could not load inventory: {e}")

    def check_plan(self, batches: List[ProductionBatch]):
        """
        Simulates the plan and flags batches that cause stockouts.
        Updates the 'mrp_status' field on the batch.
        """
        print("--- Running MRP Simulation ---")

        # Sort by usage time (MKG Start)
        batches.sort(key=lambda x: x.mkg_start_dt)

        # Working copy of inventory so we don't mutate the live view permanently
        sim_inv = self.inventory.copy()

        for b in batches:
            sku = self.sku_master.get(b.sku_code)
            if not sku:
                b.mrp_status = "UNKNOWN_SKU"
                continue

            # Determine System Prefix (12T vs 6T)
            sys_prefix = "6t" if "6T" in b.system else "12t"

            shortages = []

            # Check each ingredient in the mapping
            for ing_name in config.MRP_INGREDIENTS.keys():
                # Construct recipe key, e.g., '12t_sls'
                recipe_key = f"{sys_prefix}_{ing_name}"

                required_qty = sku.recipes.get(recipe_key, 0.0)

                if required_qty > 0:
                    current_stock = sim_inv.get(ing_name, 0.0)
                    if current_stock >= required_qty:
                        sim_inv[ing_name] -= required_qty
                    else:
                        shortages.append(ing_name)
                        # We still subtract to show deepening debt?
                        # Or just stop? Let's subtract to track total deficit.
                        sim_inv[ing_name] -= required_qty

            if shortages:
                b.mrp_status = f"LOW: {', '.join(shortages).upper()}"
            else:
                b.mrp_status = "OK"

        print("MRP Simulation Complete.")