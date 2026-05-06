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
        # ---> ENTERPRISE FIX: Added table prefixes <---
        sources = {
            'FMT': 'pg_auto_tool_table_fmt_wo_matrix',
            'MMT_6T': 'pg_auto_tool_table_mmt_6t_matrix',
            'MMT_12T': 'pg_auto_tool_table_mmt_12t_matrix'
        }

        for key, table_name in sources.items():
            df = db.fetch_table(table_name)
            if df is None or df.empty:
                matrices[key] = {}
                continue

            mat_dict = {}
            df.columns = [str(c).lower() for c in df.columns]
            for _, row in df.iterrows():
                src = self._clean_gcas(row.get('source_gcas'))
                tgt = self._clean_gcas(row.get('target_gcas'))
                w_type = str(row.get('washout_type', '')).upper()
                duration = getattr(config, 'WASHOUT_DURATION', 20) if "WASH" in w_type else 0
                if src and tgt:
                    mat_dict[(src, tgt)] = duration
            matrices[key] = mat_dict

        return matrices

    def load_bulk_variant_map(self) -> Dict[str, VariantInfo]:
        print(f"Loading Bulk Variant Map from SQL (bulk_details)...")
        # ---> ENTERPRISE FIX: Added table prefix <---
        df = db.fetch_table("pg_auto_tool_table_bulk_details")
        if df is None or df.empty:
            return {}

        variant_map = {}
        for _, row in df.iterrows():
            desc = str(row.get('description', '')).strip()
            gcas = self._clean_gcas(row.get('bulk_gcas', ''))
            weight = float(row.get('weight_per_container_kg', 0.0) or 0.0)
            if desc and gcas:
                variant_map[desc] = VariantInfo(gcas=gcas, weight_per_container=weight)
        return variant_map

    def load_master_data(self) -> Dict[str, SKUMeta]:
        print(f"Loading Master SKU & Recipe Data from SQL (sku_master)...")
        # ---> ENTERPRISE FIX: Added table prefix <---
        df = db.fetch_table("pg_auto_tool_table_sku_master")
        if df is None or df.empty:
            return {}

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

    def load_active_equipment(self) -> dict:
        print("Loading Active Equipment from SQL (equipment_master)...")
        engine = db.get_engine()
        if not engine:
            print("[WARN] DB Engine not found for equipment.")
            return {"PORTABLE_TANKS": [], "RONCHI_TANKS": [], "LINES": []}

        try:
            # ---> ENTERPRISE FIX: Added table prefix <---
            query = "SELECT * FROM pg_auto_tool_table_equipment_master WHERE LOWER(status) = 'active'"
            df = pd.read_sql(query, engine)

            # Clean up column names in case they have spaces (like 'resource group')
            df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]

            # Dynamically sort the equipment into lists using the equipment_name column
            active_resources = {
                "PORTABLE_TANKS":
                    df[(df['equip_type'].str.lower() == 'tank') & (df['resource_group'].str.lower() == 'portable')][
                        'equipment_name'].tolist(),
                "RONCHI_TANKS":
                    df[(df['equip_type'].str.lower() == 'tank') & (df['resource_group'].str.lower() == 'ronchi')][
                        'equipment_name'].tolist(),
                "LINES": df[df['equip_type'].str.lower() == 'line']['equipment_name'].tolist()
            }
            print(
                f"   > Found {len(active_resources['PORTABLE_TANKS'])} Portable Tanks and {len(active_resources['RONCHI_TANKS'])} Ronchi Tanks.")
            return active_resources

        except Exception as e:
            print(f"Error loading equipment master from DB: {e}. Using fallback defaults.")
            # Failsafe: If the DB fails, use the hardcoded lists
            return {
                "PORTABLE_TANKS": [f"TK#_{i}_#" for i in range(1, 29)],
                "RONCHI_TANKS": ["TK#_51_#", "TK#_52_#", "TK#_53_#"],
                "LINES": []
            }

    def load_packing_plan(self, target_date=None):
        print("Loading Packing Plan from SQL (packing_po)...")
        demands = []
        engine = db.get_engine()
        if not engine:
            print("[WARN] DB Engine not found for packing plan.")
            return []

        try:
            # ---> ENTERPRISE FIX: Uses the config variable we set up earlier <---
            table_name = getattr(config, 'TABLE_PACKING_PO', 'pg_auto_tool_table_packing_po')
            query = f"SELECT line, order_no, p_code, description, batch_no, start_date, start_time, end_date, end_time, planned_qty FROM {table_name}"

            if target_date:
                # Format the Python datetime into a SQL-friendly string (YYYY-MM-DD)
                date_str = target_date.strftime('%Y-%m-%d')
                query += f" WHERE start_date = '{date_str}'"
                print(f"   > Filtering orders for date: {date_str}")

            df = pd.read_sql(query, engine)
            if df.empty:
                print("   > No demands found in DB for this date.")
                return []

            # Added errors='coerce' so a single bad cell value won't crash the entire load
            start_dates = pd.to_datetime(df['start_date'], errors='coerce')
            end_dates = pd.to_datetime(df['end_date'], errors='coerce')
            start_times = pd.to_timedelta(df['start_time'].astype(str), errors='coerce')
            end_times = pd.to_timedelta(df['end_time'].astype(str), errors='coerce')

            df['pkg_start_dt'] = start_dates + start_times
            df['pkg_end_dt'] = end_dates + end_times

            for _, row in df.iterrows():
                try:
                    qty = float(row['planned_qty'])
                    if qty <= 0 or pd.isna(row['pkg_start_dt']):
                        continue

                    d = Demand(
                        order_id=str(row['order_no']).strip(),
                        material_code=str(row['p_code']).strip(),
                        description=str(row['description']).strip(),
                        quantity=qty,
                        pkg_start_dt=row['pkg_start_dt'],
                        pkg_end_dt=row['pkg_end_dt'],
                        line=str(row['line']).strip()
                    )
                    demands.append(d)
                except Exception:
                    pass

        except Exception as e:
            print(f"SQL Read Error: {e}")

        return demands