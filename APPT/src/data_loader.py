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
        # (Same as before)
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
        # (Same as before)
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
        # (Same as before)
        print(f"Loading Master BCT Data from SQL (sku_master)...")
        df = db.fetch_table("sku_master")
        if df.empty: return {}
        sku_map = {}
        for _, row in df.iterrows():
            gcas = self._clean_gcas(row.get('gcas'))
            if not gcas: continue
            desc = str(row.get('description', '')).strip()
            tech = str(row.get('technology', '')).strip()
            tech_class = str(row.get('tech_class', 'Single')).strip()

            bct_map = {}
            val_12t_fmt = float(row.get('bct_12t_fmt') or 0)
            val_12t_mmt = float(row.get('bct_12t_mmt') or 0)
            val_6t_fmt = float(row.get('bct_6t_fmt') or 0)
            val_6t_mmt = float(row.get('bct_6t_mmt') or 0)

            if val_12t_fmt > 0: bct_map["12T"] = val_12t_fmt
            if val_12t_mmt > 0: bct_map["12T"] = val_12t_mmt
            if val_6t_fmt > 0: bct_map["6T"] = val_6t_fmt
            if val_6t_mmt > 0: bct_map["6T"] = val_6t_mmt

            sku_map[gcas] = SKUMeta(gcas=gcas, description=desc, technology=tech, tech_class=tech_class,
                                    bct_by_system=bct_map)
        return sku_map

    def load_packing_plan(self) -> List[Demand]:
        """
        Loads packing plan from SQL table `packing_po`.
        Filters out 'INM1' and 'INM2' lines.
        """
        print(f"Loading Packing Plan from SQL (packing_po)...")

        # 1. Fetch Table using SQL query via Pandas to filter efficiently
        # Or fetch all and filter in Python
        df = db.fetch_table(config.TABLE_PACKING_PO)

        if df.empty:
            print("[WARN] packing_po table is empty! Run src/upload_packing_po.py first.")
            return []

        demands = []

        # 2. Filter: Ignore INM1, INM2
        # Normalize column names just in case
        df.columns = [c.lower() for c in df.columns]

        # Define excluded lines
        excluded_lines = ['INM1', 'INM2']

        for _, row in df.iterrows():
            try:
                line = str(row.get(config.COL_SQL_LINE, "")).strip().upper()

                # SKIP if line is in exclusion list
                if line in excluded_lines:
                    continue

                order = str(row.get(config.COL_SQL_ORDER, ""))
                mat = str(row.get(config.COL_SQL_MATERIAL, ""))
                desc = str(row.get(config.COL_SQL_DESC, ""))
                qty = float(row.get(config.COL_SQL_QTY, 0))

                # Dates are already datetime objects from SQL
                dt_start = row.get(config.COL_SQL_START)
                dt_end = row.get(config.COL_SQL_END)

                # Basic validation
                if pd.isna(dt_start): continue
                if pd.isna(dt_end): dt_end = dt_start

                demands.append(Demand(
                    order_id=order,
                    material_code=mat,
                    description=desc,
                    quantity=qty,
                    pkg_start_dt=dt_start,
                    pkg_end_dt=dt_end,
                    line=line
                ))
            except Exception as e:
                # print(f"Skipping row: {e}")
                continue

        print(f"Loaded {len(demands)} valid demands (filtered out INM1/INM2).")
        return demands