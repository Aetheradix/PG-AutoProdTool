import pandas as pd
import os
import sys
import re
from datetime import datetime
from typing import Dict, List
from src import config
from src.models import SKUMeta, WashoutRule, Demand


class MasterDataLoader:
    def __init__(self, filepath: str):
        self.filepath = filepath
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        print(f"Reading Master Data: {filepath} ...")
        self.xl = pd.ExcelFile(filepath)

    def load_master_data(self) -> Dict[str, SKUMeta]:
        # 1. LOAD BUFFER
        buffer_map = {}
        if config.SHEET_BUFFER in self.xl.sheet_names:
            print(f"Loading Buffer Times from '{config.SHEET_BUFFER}'...")
            df_buf = self.xl.parse(config.SHEET_BUFFER)
            df_buf.columns = df_buf.columns.astype(str).str.strip()
            sku_col = config.COL_MAP_BUFFER['sku']
            time_col = config.COL_MAP_BUFFER['buffer_min']
            if sku_col in df_buf.columns and time_col in df_buf.columns:
                for _, row in df_buf.iterrows():
                    gcas = str(row[sku_col]).strip()
                    try:
                        buffer_map[gcas] = int(row[time_col])
                    except:
                        continue

        # 2. LOAD BCT
        print(f"Loading BCT Data from '{config.SHEET_BCT}'...")
        if config.SHEET_BCT not in self.xl.sheet_names:
            print(f"[ERROR] Sheet '{config.SHEET_BCT}' not found.")
            return {}

        df = self.xl.parse(config.SHEET_BCT, header=config.BCT_HEADER_ROW)
        sku_objects = {}

        for idx, row in df.iloc[1:].iterrows():
            try:
                gcas = str(row.iloc[config.BCT_COL_GCAS]).strip()
                if not gcas or gcas.lower() == 'nan': continue

                tech = str(row.iloc[config.BCT_COL_TECH]).strip()
                desc = str(row.iloc[config.BCT_COL_DESC]).strip()

                bct_map = {}
                for col_idx, sys_name in config.BCT_SYSTEM_MAP.items():
                    val = row.iloc[col_idx]
                    try:
                        if pd.notna(val) and str(val).strip() != '-':
                            bct_map[sys_name] = float(val)
                    except:
                        pass

                sku_objects[gcas] = SKUMeta(
                    code=gcas,
                    description=desc,
                    technology=tech,
                    buffer_time_min=buffer_map.get(gcas, 0),
                    bct_by_system=bct_map
                )
            except Exception as e:
                pass

        print(f"Successfully loaded {len(sku_objects)} SKUs.")
        return sku_objects

    def load_washout_rules(self) -> List[WashoutRule]:
        # Placeholder for Phase 3
        return []

    def load_bom_mapping(self) -> Dict[str, str]:
        # Placeholder (Text matching is handling the load now)
        return {}

    def save_plan_to_excel(self, batches, filename="draft_plan.xlsx"):
        path = os.path.join(config.OUTPUT_DIR, filename)
        if not batches: return
        data = [{
            "Batch ID": b.id, "Shift": b.shift,
            "Start Time": b.start_dt.strftime("%Y-%m-%d %H:%M"),
            "End Time": b.end_dt.strftime("%Y-%m-%d %H:%M"),
            "FOP SKU": b.linked_demand_id.split("|")[1] if "|" in b.linked_demand_id else "",
            "Bulk SKU": b.sku_code,
            "System": b.system, "Duration": b.duration_min,
            "Type": b.type, "Order": b.linked_demand_id.split("|")[0]
        } for b in batches]
        pd.DataFrame(data).to_excel(path, index=False)
        print(f"Plan saved to: {path}")


class PackingPlanLoader:
    def __init__(self, filepath: str):
        self.filepath = filepath
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Packing Plan not found: {filepath}")
        self.xl = pd.ExcelFile(filepath)

    def load_demands(self) -> List[Demand]:
        print(f"Reading Packing Plan: {self.filepath}...")
        df = self.xl.parse(config.SHEET_PACKING)
        df.columns = df.columns.astype(str).str.strip()
        demands = []
        for _, row in df.iterrows():
            try:
                raw_id = row.get(config.COL_MAP_PACKING['id'])
                raw_sku = str(row.get(config.COL_MAP_PACKING['sku'])).strip()
                raw_qty = row.get(config.COL_MAP_PACKING['quantity'], 0)
                raw_desc = row.get(config.COL_MAP_PACKING['description'], "")
                raw_line = row.get(config.COL_MAP_PACKING['line'], "")
                if not raw_id or str(raw_id).lower() == 'nan': continue

                d_val = row.get(config.COL_MAP_PACKING['start_date'])
                t_val = row.get(config.COL_MAP_PACKING['start_time'])
                final_dt = None
                if isinstance(d_val, datetime):
                    date_part = d_val.date()
                else:
                    date_part = pd.to_datetime(d_val, dayfirst=True).date()
                if isinstance(t_val, datetime):
                    time_part = t_val.time()
                elif hasattr(t_val, 'hour'):
                    time_part = t_val
                else:
                    time_part = pd.to_datetime(str(t_val)).time()
                final_dt = datetime.combine(date_part, time_part)
                demands.append(Demand(str(raw_id), raw_sku, raw_desc, float(raw_qty), final_dt, raw_line))
            except:
                continue
        print(f"Successfully loaded {len(demands)} packing demands.")
        return demands