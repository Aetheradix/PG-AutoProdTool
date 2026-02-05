import pandas as pd
import os
from typing import Dict, List
from datetime import datetime
from src import config
from src.models import SKUMeta, Demand


class DataLoader:
    def __init__(self, master_path: str, packing_path: str):
        self.master_path = master_path
        self.packing_path = packing_path

    def _clean_gcas(self, val) -> str:
        """
        Standardizes GCAS string.
        CRITICAL: We DO NOT remove quotes (') as they are significant identifiers.
        """
        s = str(val).strip()
        if s.lower() == 'nan': return ""
        return s

    def load_bulk_variant_map(self) -> Dict[str, str]:
        print(f"Loading Bulk Variant Map from: {self.master_path}...")
        try:
            df = pd.read_excel(self.master_path, sheet_name=config.SHEET_BULK_VARIANT,
                               header=config.BULK_VARIANT_HEADER_ROW)
        except Exception as e:
            print(f"[WARN] Could not read sheet '{config.SHEET_BULK_VARIANT}': {e}")
            return {}

        desc_to_gcas = {}
        # Robust column search
        df.columns = df.columns.astype(str).str.strip()
        col_desc = next((c for c in df.columns if "Description" in c), "Description")
        col_gcas = next((c for c in df.columns if "Bulk GCAS" in c), "Bulk GCAS")

        for _, row in df.iterrows():
            desc = str(row.get(col_desc, "")).strip()
            gcas = self._clean_gcas(row.get(col_gcas, ""))

            if desc and gcas:
                desc_to_gcas[desc] = gcas

        print(f"Loaded {len(desc_to_gcas)} exact GCAS mappings.")
        return desc_to_gcas

    def load_master_data(self) -> Dict[str, SKUMeta]:
        print(f"Loading Master BCT Data...")
        try:
            df = pd.read_excel(self.master_path, sheet_name=0, header=config.MASTER_HEADER_ROW)
        except Exception as e:
            raise IOError(f"Failed to read Master Excel: {e}")

        sku_map = {}

        for i, row in df.iterrows():
            gcas = self._clean_gcas(row.iloc[config.COL_IDX_GCAS])
            if not gcas: continue

            desc = str(row.iloc[config.COL_IDX_DESC]).strip()
            tech = str(row.iloc[config.COL_IDX_TECH]).strip()

            bct_map = {}
            for col_idx, sys_name in config.SYSTEM_COL_MAP.items():
                try:
                    val = row.iloc[col_idx]
                    # We check if it is a number (float or int)
                    if pd.notna(val) and str(val).replace('.', '').replace(' ', '').isdigit():
                        bct_map[sys_name] = float(val)
                except:
                    pass

            sku_obj = SKUMeta(gcas=gcas, description=desc, technology=tech, bct_by_system=bct_map)
            sku_map[gcas] = sku_obj

        print(f"Loaded {len(sku_map)} Master SKUs.")
        return sku_map

    def load_packing_plan(self) -> List[Demand]:
        print(f"Loading Packing Plan: {self.packing_path}...")
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

                d_val = row.get(config.COL_PACK_DATE)
                t_val = row.get(config.COL_PACK_TIME)
                dt_obj = datetime.now()
                try:
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
                    dt_obj = datetime.combine(d_part, t_part)
                except:
                    pass

                demands.append(Demand(
                    order_id=order, material_code=mat, description=desc,
                    quantity=qty, start_dt=dt_obj
                ))
                demands[-1].line = line
            except:
                continue

        print(f"Loaded {len(demands)} packing demands.")
        return demands