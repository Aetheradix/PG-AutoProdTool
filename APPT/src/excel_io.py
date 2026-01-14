import pandas as pd
import os
import sys
from typing import Dict, List, Optional
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
            raise IOError(f"Failed to open Excel file. Error: {e}")

    def _read_sheet_with_header_hunting(self, sheet_name: str, required_cols: List[str]) -> pd.DataFrame:
        """
        Scans the first 20 rows of a sheet to find the row that contains
        the required columns (handling metadata headers like 'Version', 'Prepared By').
        """
        # Read first 20 rows without header
        df_preview = self.xl.parse(sheet_name, header=None, nrows=20)

        header_row_idx = None

        # Scan rows to find one that contains at least one of our unique keywords
        # We search loosely (partial match) to be safe
        for idx, row in df_preview.iterrows():
            row_vals = [str(x).strip() for x in row.values]

            # Check if this row looks like a header
            # We assume if we find the 'sku' column name (e.g. "Material" or "GCAS"), it's the header
            matches = 0
            for col in required_cols:
                if col in row_vals:
                    matches += 1

            # If we match at least one specific column, we assume this is the header
            if matches >= 1:
                header_row_idx = idx
                break

        if header_row_idx is None:
            # Fallback: maybe the header is row 0 but named differently?
            # Return empty DF so the caller raises the specific "Missing Column" error
            print(f"[DEBUG] Could not find header row in '{sheet_name}' matching {required_cols}")
            return pd.DataFrame()

        # Reload the sheet using the correct header row
        print(f"   -> Found header at Row {header_row_idx} in '{sheet_name}'")
        df = self.xl.parse(sheet_name, header=header_row_idx)
        return df

    def _normalize_cols(self, df: pd.DataFrame, mapping: Dict[str, str], strict: bool = True) -> pd.DataFrame:
        if df.empty:
            if strict: raise ValueError("Sheet data is empty or header not found.")
            return df

        # Clean headers
        df.columns = df.columns.astype(str).str.strip()

        # Invert mapping
        reverse_map = {v: k for k, v in mapping.items()}

        # Check for missing
        missing = [v for v in mapping.values() if v not in df.columns]

        if missing:
            if strict:
                print(f"[DEBUG] Available Columns: {list(df.columns)}")
                print(f"[DEBUG] Missing Columns: {missing}")
                raise ValueError(f"Missing required columns: {missing}")
            else:
                return pd.DataFrame()  # Return empty if optional columns missing

        return df.rename(columns=reverse_map)[list(mapping.keys())]

    def load_master_data(self) -> Dict[str, SKUMeta]:
        # 1. LOAD BUFFER (Simple, clean sheet)
        buffer_map = {}
        if config.SHEET_BUFFER in self.xl.sheet_names:
            df_buf = self.xl.parse(config.SHEET_BUFFER)  # Buffer sheet seemed clean in inspection
            try:
                df_buf = self._normalize_cols(df_buf, config.COL_MAP_BUFFER)
                buffer_map = df_buf.groupby('sku')['buffer_min'].max().to_dict()
            except ValueError as e:
                print(f"[WARNING] Buffer Error: {e}")

        # 2. LOAD BCT (Needs header hunting)
        print(f"Scanning '{config.SHEET_BCT}'...")
        # We look for "Material" or "Cycle Time" to identify the header row
        req_cols = list(config.COL_MAP_BCT.values())
        df_bct = self._read_sheet_with_header_hunting(config.SHEET_BCT, req_cols)

        try:
            df_bct = self._normalize_cols(df_bct, config.COL_MAP_BCT)
        except ValueError:
            print("[CRITICAL] Could not map columns in BCT sheet. Check config.py.")
            return {}

        # 3. Aggregate
        sku_objects = {}
        for sku, group in df_bct.groupby('sku'):
            sku = str(sku).strip()
            if not sku or sku == 'nan': continue

            tech = group.iloc[0]['technology']
            bct_map = dict(zip(group['system'], group['bct_min']))
            buf = buffer_map.get(sku, 0)

            sku_objects[sku] = SKUMeta(sku, str(tech), int(buf), bct_map)

        print(f"Successfully loaded {len(sku_objects)} SKUs.")
        return sku_objects

    def load_washout_rules(self) -> List[WashoutRule]:
        rules = []
        for sheet in config.SHEET_WASHOUT_LIST:
            if sheet not in self.xl.sheet_names: continue

            print(f"Scanning '{sheet}'...")
            req_cols = list(config.COL_MAP_WASHOUT.values())
            df = self._read_sheet_with_header_hunting(sheet, req_cols)

            if df.empty:
                print(f"   [SKIP] Empty or unreadable: {sheet}")
                continue

            try:
                df = self._normalize_cols(df, config.COL_MAP_WASHOUT)
                sys_class = "ALL"
                if "-" in sheet: sys_class = sheet.split("-")[1].strip()

                for _, row in df.iterrows():
                    rules.append(WashoutRule(
                        str(row['from_sku']).strip(),
                        str(row['to_sku']).strip(),
                        int(row['duration']),
                        sys_class
                    ))
            except Exception as e:
                print(f"   [SKIP] Error parsing {sheet}: {e}")

        print(f"Successfully loaded {len(rules)} washout rules.")
        return rules

    def save_plan_to_excel(self, batches, filename="draft_plan.xlsx"):
        path = os.path.join(config.OUTPUT_DIR, filename)
        if not batches:
            df = pd.DataFrame(columns=["Batch ID", "SKU", "System", "Shift", "Start", "End", "Type"])
        else:
            df = pd.DataFrame([vars(b) for b in batches])
        df.to_excel(path, index=False)
        print(f"Saved: {path}")