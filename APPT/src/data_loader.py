import pandas as pd
import os
from typing import Dict, List, Tuple
from datetime import datetime
from src import config
from src.models import SKUMeta, Demand, VariantInfo


class DataLoader:
    def __init__(self, master_path: str, packing_path: str):
        self.master_path = master_path
        self.packing_path = packing_path

    def _clean_gcas(self, val) -> str:
        s = str(val).strip()
        if s.lower() == 'nan': return ""
        return s

    def load_washout_matrices(self) -> Dict[str, Dict[Tuple[str, str], int]]:
        """
        Loads all washout CSVs into a dict of dicts:
        {
            'FMT': { ('SrcGCAS', 'TgtGCAS'): 20, ... },
            'MMT_6T': ...
        }
        """
        matrices = {}
        files = {
            'FMT': config.WO_FILE_FMT,
            'MMT_6T': config.WO_FILE_MMT_6T,
            'MMT_12T': config.WO_FILE_MMT_12T
        }

        for key, filename in files.items():
            path = os.path.join(config.INPUT_DIR, filename)
            if not os.path.exists(path):
                print(f"[WARN] Washout file not found: {filename}")
                matrices[key] = {}
                continue

            try:
                df = pd.read_csv(path)
                # Expected: Source_GCAS, Target_GCAS, Washout_Type (WASH/X)
                mat_dict = {}
                for _, row in df.iterrows():
                    src = self._clean_gcas(row.get('Source_GCAS'))
                    tgt = self._clean_gcas(row.get('Target_GCAS'))
                    w_type = str(row.get('Washout_Type', '')).upper()

                    duration = 0
                    if "WASH" in w_type:
                        duration = config.WASHOUT_DURATION

                    if src and tgt:
                        mat_dict[(src, tgt)] = duration
                matrices[key] = mat_dict
                print(f"Loaded {len(mat_dict)} washout rules for {key}.")
            except Exception as e:
                print(f"[ERROR] Reading {filename}: {e}")
                matrices[key] = {}

        return matrices

    def load_bulk_variant_map(self) -> Dict[str, VariantInfo]:
        # (Same as before)
        print(f"Loading Bulk Variant Map...")
        try:
            df = pd.read_excel(self.master_path, sheet_name=config.SHEET_BULK_VARIANT,
                               header=config.BULK_VARIANT_HEADER_ROW)
        except Exception as e:
            return {}

        variant_map = {}
        df.columns = df.columns.astype(str).str.strip()
        col_desc = next((c for c in df.columns if config.COL_VAR_DESC in c), config.COL_VAR_DESC)
        col_gcas = next((c for c in df.columns if config.COL_VAR_GCAS in c), config.COL_VAR_GCAS)
        col_weight = next((c for c in df.columns if config.COL_VAR_WEIGHT in c), None)

        for _, row in df.iterrows():
            desc = str(row.get(col_desc, "")).strip()
            gcas = self._clean_gcas(row.get(col_gcas, ""))
            weight = 0.0
            if col_weight:
                try:
                    w_val = row.get(col_weight, 0); weight = float(w_val) if pd.notna(w_val) else 0.0
                except:
                    weight = 0.0

            if desc and gcas:
                variant_map[desc] = VariantInfo(gcas=gcas, weight_per_container=weight)
        return variant_map

    def load_master_data(self) -> Dict[str, SKUMeta]:
        # (Same as before)
        try:
            df = pd.read_excel(self.master_path, sheet_name=config.SHEET_MASTER_DATA, header=config.MASTER_HEADER_ROW)
        except Exception as e:
            raise IOError(f"Failed to read Master Excel: {e}")

        sku_map = {}
        col_single_dual_idx = config.COL_IDX_SINGLE_DUAL
        for idx, col_name in enumerate(df.columns):
            if "Single" in str(col_name) and "Dual" in str(col_name):
                col_single_dual_idx = idx;
                break

        for i, row in df.iterrows():
            gcas = self._clean_gcas(row.iloc[config.COL_IDX_GCAS])
            if not gcas: continue
            desc = str(row.iloc[config.COL_IDX_DESC]).strip()
            tech = str(row.iloc[config.COL_IDX_TECH]).strip()
            tech_class = "Single"
            try:
                val = str(row.iloc[col_single_dual_idx]).strip()
                if "dual" in val.lower(): tech_class = "Dual"
            except:
                pass

            bct_map = {}
            for col_idx, sys_name in config.SYSTEM_COL_MAP.items():
                try:
                    val = row.iloc[col_idx]
                    if pd.notna(val) and str(val).replace('.', '').isdigit():
                        bct_map[sys_name] = float(val)
                except:
                    pass
            sku_map[gcas] = SKUMeta(gcas=gcas, description=desc, technology=tech, tech_class=tech_class,
                                    bct_by_system=bct_map)
        return sku_map

    def _parse_dt(self, row, col_date, col_time):
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
        # (Same as before)
        print(f"Loading Packing Plan...")
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