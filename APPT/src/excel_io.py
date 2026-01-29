import pandas as pd
import os
import sys
import re
from datetime import datetime, timedelta
from typing import Dict, List
from src import config
from src.models import SKUMeta, WashoutRule, ProductionBatch, Demand


class MasterDataLoader:
    def __init__(self, filepath: str):
        self.filepath = filepath
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        print(f"Reading: {filepath} ...")
        self.xl = pd.ExcelFile(filepath)

    # ... [Keep previous load_master_data and load_washout_rules methods exactly as they were] ...
    # (If you need me to paste them again, let me know, but they stay the same)

    def load_master_data(self) -> Dict[str, SKUMeta]:
        # ... (Paste Phase 1 code here) ...
        # [Abbreviated for brevity - ensure you keep the regex logic from Phase 1]

        # 1. LOAD BUFFER
        buffer_map = {}
        if config.SHEET_BUFFER in self.xl.sheet_names:
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
        if config.SHEET_BCT not in self.xl.sheet_names: return {}
        df = self.xl.parse(config.SHEET_BCT, header=config.BCT_HEADER_ROW)
        sku_objects = {}
        for idx, row in df.iloc[1:].iterrows():
            try:
                gcas = str(row.iloc[config.BCT_COL_GCAS]).strip()
                tech = str(row.iloc[config.BCT_COL_TECH]).strip()
                if not gcas or gcas.lower() == 'nan': continue
                bct_map = {}
                for col_idx, sys_name in config.BCT_SYSTEM_MAP.items():
                    val = row.iloc[col_idx]
                    try:
                        if pd.notna(val) and str(val).strip() != '-':
                            bct_map[sys_name] = float(val)
                    except:
                        pass
                sku_objects[gcas] = SKUMeta(gcas, tech, buffer_map.get(gcas, 0), bct_map)
            except:
                pass
        return sku_objects

    def load_washout_rules(self) -> List[WashoutRule]:
        # ... (Paste Phase 1 regex logic here) ...
        all_rules = []
        for sheet in config.SHEET_WASHOUT_LIST:
            if sheet not in self.xl.sheet_names: continue
            df = self.xl.parse(sheet, header=None)
            to_gcas_map = {}
            try:
                header_row = df.iloc[config.WASHOUT_HEADER_ROW]
                for col_idx, val in enumerate(header_row):
                    match = re.search(r'Gcas\s*[-: ]?\s*(\d+)', str(val), re.IGNORECASE)
                    if match:
                        to_gcas_map[col_idx] = match.group(1)
                    elif str(val).isdigit() and len(str(val)) > 6:
                        to_gcas_map[col_idx] = str(val).strip()

                for r in range(config.WASHOUT_DATA_START_ROW, len(df)):
                    from_gcas = str(df.iloc[r, config.WASHOUT_FROM_COL]).strip()
                    if not from_gcas or from_gcas == 'nan': continue
                    for col_idx, to_gcas in to_gcas_map.items():
                        raw_val = df.iloc[r, col_idx]
                        try:
                            duration = int(raw_val)
                        except:
                            duration = 0
                        all_rules.append(WashoutRule(from_gcas, to_gcas, duration, sheet))
            except:
                pass
        return all_rules

    def save_plan_to_excel(self, batches, filename="draft_plan.xlsx"):
        path = os.path.join(config.OUTPUT_DIR, filename)
        if not batches: return

        # Convert to simple dictionary for Excel
        data = []
        for b in batches:
            data.append({
                "Batch ID": b.id,
                "Shift": b.shift,
                "Start Time": b.start_dt.strftime("%Y-%m-%d %H:%M"),
                "End Time": b.end_dt.strftime("%Y-%m-%d %H:%M"),
                "SKU": b.sku_code,
                "System": b.system,
                "Duration (min)": b.duration_min,
                "Type": b.type,
                "Linked Demand": b.linked_demand_id
            })

        df = pd.DataFrame(data)
        df.to_excel(path, index=False)
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

        # Normalize Headers
        df.columns = df.columns.astype(str).str.strip()

        demands = []

        for _, row in df.iterrows():
            try:
                # Extract simple fields
                raw_id = row.get(config.COL_MAP_PACKING['id'])
                raw_sku = str(row.get(config.COL_MAP_PACKING['sku'])).strip()
                raw_qty = row.get(config.COL_MAP_PACKING['quantity'], 0)
                raw_desc = row.get(config.COL_MAP_PACKING['description'], "")
                raw_line = row.get(config.COL_MAP_PACKING['line'], "")

                # Skip empty rows
                if not raw_id or str(raw_id).lower() == 'nan': continue

                # Parse Date and Time
                # SAP often provides Date as 'datetime' and Time as 'datetime.time' or string
                d_val = row.get(config.COL_MAP_PACKING['start_date'])
                t_val = row.get(config.COL_MAP_PACKING['start_time'])

                final_dt = None

                # Robust Date Parsing
                if isinstance(d_val, datetime):
                    date_part = d_val.date()
                else:
                    # Try string parsing DD.MM.YYYY
                    date_part = pd.to_datetime(d_val, dayfirst=True).date()

                # Robust Time Parsing
                time_part = None
                if isinstance(t_val, datetime):
                    time_part = t_val.time()
                elif hasattr(t_val, 'hour'):  # is datetime.time
                    time_part = t_val
                else:
                    # Try string parsing
                    time_part = pd.to_datetime(str(t_val)).time()

                final_dt = datetime.combine(date_part, time_part)

                demands.append(Demand(
                    id=str(raw_id),
                    sku_code=raw_sku,
                    description=raw_desc,
                    quantity=float(raw_qty),
                    packing_start_dt=final_dt,
                    line=raw_line
                ))

            except Exception as e:
                print(f"[WARNING] Skipping row in packing plan: {e}")
                continue

        print(f"Successfully loaded {len(demands)} packing demands.")
        return demands