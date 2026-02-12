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
        # (Same as before - reading from SQL)
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
        """
        Loads Bulk Variant Map from SQL table `bulk_details`.
        """
        print(f"Loading Bulk Variant Map from SQL (bulk_details)...")
        df = db.fetch_table("bulk_details")

        if df.empty:
            print("[WARN] bulk_details table is empty! Run src/migrate_to_sql.py first.")
            return {}

        variant_map = {}
        # Columns in SQL: description, bulk_gcas, weight_per_container_kg
        for _, row in df.iterrows():
            desc = str(row.get('description', '')).strip()
            gcas = self._clean_gcas(row.get('bulk_gcas', ''))
            weight = float(row.get('weight_per_container_kg', 0.0))

            if desc and gcas:
                variant_map[desc] = VariantInfo(gcas=gcas, weight_per_container=weight)

        print(f"Loaded {len(variant_map)} variants from SQL.")
        return variant_map

    def load_master_data(self) -> Dict[str, SKUMeta]:
        """
        Loads SKU Master Data from SQL table `sku_master`.
        """
        print(f"Loading Master BCT Data from SQL (sku_master)...")
        df = db.fetch_table("sku_master")

        if df.empty:
            print("[WARN] sku_master table is empty! Run src/migrate_to_sql.py first.")
            return {}

        sku_map = {}
        for _, row in df.iterrows():
            gcas = self._clean_gcas(row.get('gcas'))
            if not gcas: continue

            desc = str(row.get('description', '')).strip()
            tech = str(row.get('technology', '')).strip()
            tech_class = str(row.get('tech_class', 'Single')).strip()

            # Reconstruct the bct_by_system dictionary expected by Logic
            # Note: Logic expects specific keys like "12T FMT", "12T" etc.
            # Since we simplified config to just "12T" and "6T", we map these columns:

            bct_map = {}
            # "12T" could come from FMT or MMT column. We take the max or first available.
            # Or simpler: map all 4, let logic pick best.

            # Since we merged FMT/MMT in config.SYSTEM_COL_MAP to just "12T",
            # we need to be careful. The Logic looks for "12T".
            # Let's populate "12T" with whichever value exists (FMT or MMT).

            val_12t_fmt = float(row.get('bct_12t_fmt') or 0)
            val_12t_mmt = float(row.get('bct_12t_mmt') or 0)
            val_6t_fmt = float(row.get('bct_6t_fmt') or 0)
            val_6t_mmt = float(row.get('bct_6t_mmt') or 0)

            # If logic asks for "12T", give it the valid one.
            # If both exist, maybe take MMT if tech_class is Dual?
            # For now, let's just populate the specific keys if logic ever expands,
            # AND the generic keys "12T"/"6T"

            if val_12t_fmt > 0: bct_map["12T"] = val_12t_fmt
            if val_12t_mmt > 0: bct_map["12T"] = val_12t_mmt  # Overwrite/Fallback

            if val_6t_fmt > 0: bct_map["6T"] = val_6t_fmt
            if val_6t_mmt > 0: bct_map["6T"] = val_6t_mmt

            sku_map[gcas] = SKUMeta(
                gcas=gcas,
                description=desc,
                technology=tech,
                tech_class=tech_class,
                bct_by_system=bct_map
            )

        print(f"Loaded {len(sku_map)} Master SKUs from SQL.")
        return sku_map

    def _parse_dt(self, row, col_date, col_time):
        # (Same helper)
        d_val = row.get(col_date)
        t_val = row.get(col_time)
        try:
            if pd.isna(d_val) or pd.isna(t_val): return None
            if isinstance(d_val, datetime):
                d_part = d_val.date()
            else:
                d_part = pd.to_datetime(d_val, dayfirst=True).date()
            if isinstance(t_val, datetime):
                t_part = t_val.time()
            elif hasattr(t_val, 'hour'):
                t_part = t_val
            else:
                t_part = pd.to_datetime(str(t_val)).time()
            return datetime.combine(d_part, t_part)
        except:
            return None

    def load_packing_plan(self) -> List[Demand]:
        # Remains Excel (User Input)
        print(f"Loading Packing Plan from Excel...")
        try:
            df = pd.read_excel(self.packing_path, header=0)
        except Exception as e:
            raise IOError(f"Failed to read Packing Excel: {e}")
        demands = []
        for _, row in df.iterrows():
            try:
                order = str(row.get(config.COL_PACK_ORDER, ""))
                mat = str(row.get(config.COL_PACK_MATERIAL, ""))
                desc = str(row.get(config.COL_PACK_DESC, ""))
                qty = float(row.get(config.COL_PACK_QTY, 0))
                line = str(row.get(config.COL_PACK_LINE, ""))
                dt_start = self._parse_dt(row, config.COL_PACK_START_DATE, config.COL_PACK_START_TIME)
                dt_end = self._parse_dt(row, config.COL_PACK_END_DATE, config.COL_PACK_END_TIME)
                if not dt_start: continue
                if not dt_end: dt_end = dt_start
                demands.append(
                    Demand(order_id=order, material_code=mat, description=desc, quantity=qty, pkg_start_dt=dt_start,
                           pkg_end_dt=dt_end, line=line))
            except:
                continue
        return demands