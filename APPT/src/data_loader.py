import pandas as pd
import os
from typing import Dict, List
from datetime import datetime
from src import config, db
from src.models import SKUMeta, Demand, VariantInfo


class DataLoader:
    def __init__(self, master_path: str, packing_path: str):
        self.master_path = master_path
        self.packing_path = packing_path

    def _clean_gcas(self, val) -> str:
        s = str(val).strip()
        if s.lower() == 'nan': return ""
        return s

    def load_washout_matrices(self) -> Dict[str, Dict]:
        print("Loading Washout Matrices from SQL...")
        matrices = {}
        sources = {'FMT': 'fmt_wo_matrix', 'MMT_6T': 'mmt_6t_matrix', 'MMT_12T': 'mmt_12t_matrix'}
        for key, table_name in sources.items():
            df = db.fetch_table(table_name)
            if df.empty:
                matrices[key] = {}
                continue
            mat_dict = {}
            df.columns = [c.lower() for c in df.columns]
            for _, row in df.iterrows():
                src = self._clean_gcas(row.get('source_gcas'))
                tgt = self._clean_gcas(row.get('target_gcas'))
                w_type = str(row.get('washout_type', '')).upper()
                duration = config.WASHOUT_DURATION if "WASH" in w_type else 0
                if src and tgt: mat_dict[(src, tgt)] = duration
            matrices[key] = mat_dict
        return matrices

    def load_bulk_variant_map(self) -> Dict[str, VariantInfo]:
        print(f"Loading Bulk Variant Map from SQL (bulk_details)...")
        df = db.fetch_table("bulk_details")
        if df.empty: return {}
        variant_map = {}
        for _, row in df.iterrows():
            desc = str(row.get('description', '')).strip()
            gcas = self._clean_gcas(row.get('bulk_gcas', ''))
            weight = float(row.get('weight_per_container_kg', 0.0))
            if desc and gcas:
                variant_map[desc] = VariantInfo(gcas=gcas, weight_per_container=weight)
        return variant_map

    def load_master_data(self) -> Dict[str, SKUMeta]:
        import pandas as pd

        print(f"Loading Master SKU & Recipe Data from SQL (sku_master)...")
        df = db.fetch_table("sku_master")
        if df is None or df.empty: return {}

        # 1. BULLETPROOF THE COLUMNS: Make everything lowercase and replace spaces with underscores
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        sku_map = {}

        # Identify recipe columns dynamically
        recipe_cols = [c for c in df.columns if str(c).startswith('cons_')]

        for _, row in df.iterrows():
            gcas = self._clean_gcas(row.get('gcas'))
            if not gcas: continue

            desc = str(row.get('description', '')).strip()
            tech = str(row.get('technology', '')).strip()

            # 2. SMART TECH CLASS EXTRACTION
            raw_tech_class = row.get('tech_class')
            tc_str = str(raw_tech_class).strip().lower()

            # If it's a NaN, null, or blank string, default to Single
            if pd.isna(raw_tech_class) or tc_str in ['nan', 'none', '', 'null']:
                tech_class = "Single"
            # If the database says "dual", "fmt+mmt", or "mmt", flag it as Dual!
            elif "dual" in tc_str or "mmt" in tc_str or "+" in tc_str:
                tech_class = "Dual"
            else:
                tech_class = "Single"

            bct_map = {}
            val_12t_fmt = float(row.get('bct_12t_fmt') or 0)
            val_12t_mmt = float(row.get('bct_12t_mmt') or 0)
            val_6t_fmt = float(row.get('bct_6t_fmt') or 0)
            val_6t_mmt = float(row.get('bct_6t_mmt') or 0)

            if val_12t_fmt > 0: bct_map["12T"] = val_12t_fmt
            if val_12t_mmt > 0: bct_map["12T"] = val_12t_mmt
            if val_6t_fmt > 0: bct_map["6T"] = val_6t_fmt
            if val_6t_mmt > 0: bct_map["6T"] = val_6t_mmt

            # Extract Recipe
            recipes = {}
            for col in recipe_cols:
                val = float(row.get(col) or 0)
                if val > 0:
                    # Clean key: 'cons_12t_sls' -> '12T_sls'
                    key = col.replace('cons_', '')
                    recipes[key.lower()] = val

            sku_map[gcas] = SKUMeta(
                gcas=gcas,
                description=desc,
                technology=tech,
                tech_class=tech_class,  # Safely cleaned and standardized!
                bct_by_system=bct_map,
                recipes=recipes
            )

        return sku_map

    def load_packing_plan(self, target_date=None) -> List[Demand]:
        print("Loading Packing Plan from SQL (packing_po)...")
        demands = []
        try:
            # 1. Add the Target Date Filter to the SQL Query (handles start_date + start_time)
            query = """SELECT line, order_no, p_code, description, batch_no, 
                              IFNULL(CONCAT(start_date, ' ', start_time), start_date) AS start_datetime, 
                              IFNULL(CONCAT(end_date, ' ', end_time), end_date) AS end_datetime, 
                              planned_qty FROM packing_po"""

            if target_date:
                date_str = target_date.strftime('%Y-%m-%d')
                query += f" WHERE start_date = '{date_str}'"
                print(f"   > Filtering orders for date: {date_str}")

            df = pd.read_sql(query, db.get_engine())
            if df.empty:
                print("   > No demands found in DB for this date.")
                return []

            for _, row in df.iterrows():
                try:
                    qty = float(row['planned_qty'])
                    if qty <= 0: continue

                    d = Demand(
                        order_id=str(row['order_no']).strip(),
                        material_code=str(row['p_code']).strip(),
                        description=str(row['description']).strip(),
                        quantity=qty,
                        pkg_start_dt=pd.to_datetime(row['start_datetime']),
                        pkg_end_dt=pd.to_datetime(row['end_datetime']),
                        line=str(row['line']).strip()
                    )
                    demands.append(d)
                except Exception as e:
                    pass

        except Exception as e:
            print(f"Error loading packing plan from DB: {e}")

        print(f"Loaded {len(demands)} demands.")
        return demands