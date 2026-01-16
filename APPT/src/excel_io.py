import pandas as pd
import os
import sys
import re  # Added for regex parsing
from typing import Dict, List
from src import config
from src.models import SKUMeta, WashoutRule, ProductionBatch


class MasterDataLoader:
    def __init__(self, filepath: str):
        self.filepath = filepath
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Master Data file not found: {filepath}")

        print(f"Reading Excel file: {filepath} ...")
        try:
            self.xl = pd.ExcelFile(filepath)
        except Exception as e:
            raise IOError(f"Failed to open Excel file: {e}")

    def load_master_data(self) -> Dict[str, SKUMeta]:
        """Parses BCT and Buffer sheets."""
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
                        time_val = int(row[time_col])
                        buffer_map[gcas] = time_val
                    except:
                        continue

        # 2. LOAD BCT
        print(f"Loading BCT Data from '{config.SHEET_BCT}'...")
        if config.SHEET_BCT not in self.xl.sheet_names:
            raise ValueError(f"Sheet '{config.SHEET_BCT}' missing.")

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

                sku_objects[gcas] = SKUMeta(
                    code=gcas,
                    technology=tech,
                    buffer_time_min=buffer_map.get(gcas, 0),
                    bct_by_system=bct_map
                )
            except:
                pass

        print(f"Successfully loaded {len(sku_objects)} SKUs.")
        return sku_objects

    def load_washout_rules(self) -> List[WashoutRule]:
        """
        Parses Matrix-style washout sheets using Regex to find headers.
        """
        all_rules = []

        for sheet in config.SHEET_WASHOUT_LIST:
            if sheet not in self.xl.sheet_names:
                continue

            print(f"Parsing Washout Matrix: '{sheet}'...")
            df = self.xl.parse(sheet, header=None)

            # 1. Map Columns to TO_SKUs by scanning the Header Row
            to_gcas_map = {}  # {col_index: gcas_code}

            try:
                header_row = df.iloc[config.WASHOUT_HEADER_ROW]

                for col_idx, val in enumerate(header_row):
                    val_str = str(val)
                    # Regex: Find 'Gcas' followed by digits, or just large integers
                    # Matches "FOP Gcas 90275009" or "Gcas- 21055594"
                    match = re.search(r'Gcas\s*[-: ]?\s*(\d+)', val_str, re.IGNORECASE)

                    if match:
                        gcas = match.group(1)
                        to_gcas_map[col_idx] = gcas
                    elif str(val).isdigit() and len(str(val)) > 6:
                        # Fallback: if cell is just the number
                        to_gcas_map[col_idx] = str(val).strip()

                if not to_gcas_map:
                    #print(f"   [WARNING] No 'TO' GCAS codes found in Row {config.WASHOUT_HEADER_ROW} of {sheet}")
                    continue

                # 2. Iterate Data Rows for FROM_SKUs
                for r in range(config.WASHOUT_DATA_START_ROW, len(df)):
                    from_gcas = str(df.iloc[r, config.WASHOUT_FROM_COL]).strip()

                    if not from_gcas or from_gcas.lower() == 'nan':
                        continue

                    # 3. Get Intersection Values
                    for col_idx, to_gcas in to_gcas_map.items():
                        raw_val = df.iloc[r, col_idx]

                        duration = 0
                        # Logic: 'x' usually means 0 (No Washout) or Standard?
                        # Assuming 'x' = 0 (Compatible) for now.
                        # If cell is a number (e.g., 45), that's the time.
                        try:
                            duration = int(raw_val)
                        except:
                            # Handle 'x', 'X', '-', or text
                            if str(raw_val).lower().strip() == 'x':
                                duration = 0
                            else:
                                duration = 0  # Default to 0 if unclear

                        # We store ALL rules, even 0 min ones, to be explicit
                        all_rules.append(WashoutRule(
                            from_sku=from_gcas,
                            to_sku=to_gcas,
                            duration_min=duration,
                            system_class=sheet
                        ))

            except Exception as e:
                print(f"   [ERROR] Parsing failed for {sheet}: {e}")

        print(f"Successfully loaded {len(all_rules)} washout rules.")
        return all_rules

    def save_plan_to_excel(self, batches, filename="draft_plan.xlsx"):
        path = os.path.join(config.OUTPUT_DIR, filename)
        if not batches:
            df = pd.DataFrame(columns=["Batch ID", "SKU", "System", "Shift", "Start", "End", "Type"])
        else:
            df = pd.DataFrame([vars(b) for b in batches])
        df.to_excel(path, index=False)
        print(f"Saved: {path}")