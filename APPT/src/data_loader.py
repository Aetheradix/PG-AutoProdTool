import pandas as pd
import os
from typing import Dict, List
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

    def load_bulk_variant_map(self) -> Dict[str, VariantInfo]:
        print(f"Loading Bulk Variant Map...")
        try:
            df = pd.read_excel(self.master_path, sheet_name=config.SHEET_BULK_VARIANT,
                               header=config.BULK_VARIANT_HEADER_ROW)
        except Exception as e:
            print(f"[WARN] Could not read sheet '{config.SHEET_BULK_VARIANT}': {e}")
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
                    w_val = row.get(col_weight, 0)
                    weight = float(w_val) if pd.notna(w_val) else 0.0
                except:
                    weight = 0.0

            if desc and gcas:
                variant_map[desc] = VariantInfo(gcas=gcas, weight_per_container=weight)

        print(f"Loaded {len(variant_map)} variants.")
        return variant_map

    def load_master_data(self) -> Dict[str, SKUMeta]:
        print(f"Loading Master BCT Data...")
        try:
            df = pd.read_excel(self.master_path, sheet_name=config.SHEET_MASTER_DATA, header=config.MASTER_HEADER_ROW)
        except Exception as e:
            raise IOError(f"Failed to read Master Excel: {e}")

        sku_map = {}
        col_single_dual_idx = config.COL_IDX_SINGLE_DUAL
        for idx, col_name in enumerate(df.columns):
            if "Single" in str(col_name) and "Dual" in str(col_name):
                col_single_dual_idx = idx
                break

        for i, row in df.iterrows():
            gcas = self._clean_gcas(row.iloc[config.COL_IDX_GCAS])
            if not gcas: continue

            desc = str(row.iloc[config.COL_IDX_DESC]).strip()
            tech = str(row.iloc[config.COL_IDX_TECH]).strip()

            tech_class = "Single"
            try:
                val = str(row.iloc[col_single_dual_idx]).strip()
                if "dual" in val.lower():
                    tech_class = "Dual"
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

            sku_obj = SKUMeta(gcas=gcas, description=desc, technology=tech, tech_class=tech_class,
                              bct_by_system=bct_map)
            sku_map[gcas] = sku_obj

        print(f"Loaded {len(sku_map)} Master SKUs.")
        return sku_map

    def load_packing_plan(self) -> List[Demand]:
        print(f"Loading Packing Plan...")
        try:
            df = pd.read_excel(self.packing_path, header=0)
        except Exception as e:
            raise IOError(f"Failed to read Packing Excel: {e}")

        demands = []
        for _, row in df.iterrows():
            try:
                # Essential fields
                order = str(row.get(config.COL_PACK_ORDER, ""))
                mat = str(row.get(config.COL_PACK_MATERIAL, ""))
                desc = str(row.get(config.COL_PACK_DESC, ""))
                qty = float(row.get(config.COL_PACK_QTY, 0))
                line = str(row.get(config.COL_PACK_LINE, ""))

                # Date/Time Parsing
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

                # Note: We completely ignore GCAS/System columns from input here.
                # Logic engine handles it.

                demands.append(
                    Demand(order_id=order, material_code=mat, description=desc, quantity=qty, start_dt=dt_obj,
                           line=line))
            except:
                continue
        return demands