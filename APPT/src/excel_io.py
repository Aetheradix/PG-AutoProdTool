import pandas as pd
from pathlib import Path
import re


# ==============================
# Path Configuration
# ==============================
BASE_DIR = Path(__file__).resolve().parents[1]


# ==============================
# Column Normalization Utility
# ==============================
def _normalize(col: str) -> str:
    """
    Normalize Excel column headers:
    - lowercase
    - remove spaces, newlines
    - remove special characters
    """
    col = col.lower()
    col = re.sub(r"\s+", "", col)
    col = re.sub(r"[^a-z0-9]", "", col)
    return col


# ==============================
# Master Data Loader
# ==============================
class MasterDataLoader:
    def __init__(self, filename="Master Data - Auto Production Planning.xlsm"):
        self.filepath = BASE_DIR / "data" / "input" / filename

    # ---------- Public API ----------
    def load(self):
        return {
            "bct": self._load_bct(),
            "buffer": self._load_buffer(),
            "washout": self._load_washout(),
        }

    # ---------- BCT Loader ----------
    def _load_bct(self):
        df = pd.read_excel(self.filepath, sheet_name="BCT Data ")
        df.columns = df.columns.astype(str)

        raw_cols = {_normalize(c): c for c in df.columns}

        rename_map = {
            raw_cols.get("gcas"): "sku",
            raw_cols.get("system"): "system",
            raw_cols.get("technology"): "technology",
            raw_cols.get("bctmin"): "bct_min",
            raw_cols.get("batchcycletimemin"): "bct_min",
            raw_cols.get("batchcycletime"): "bct_min",
        }

        rename_map = {k: v for k, v in rename_map.items() if k is not None}
        df = df.rename(columns=rename_map)

        required = ["sku", "system", "technology", "bct_min"]
        self._assert_columns(df, required, "BCT Data")

        return df[required]

    # ---------- Buffer Time Loader ----------
    def _load_buffer(self):
        df = pd.read_excel(self.filepath, sheet_name="Buffer Time")
        df.columns = df.columns.astype(str)

        raw_cols = {_normalize(c): c for c in df.columns}

        rename_map = {
            raw_cols.get("gcas"): "sku",
            raw_cols.get("buffertimemin"): "buffer_min",
            raw_cols.get("buffertime"): "buffer_min",
        }

        rename_map = {k: v for k, v in rename_map.items() if k is not None}
        df = df.rename(columns=rename_map)

        required = ["sku", "buffer_min"]
        self._assert_columns(df, required, "Buffer Time")

        return df[required]

    # ---------- Washout Loader ----------
    def _load_washout(self):
        """
        Converts multiple washout matrices into a single normalized table:
        from_sku | to_sku | system | technology | washout_min
        """

        sheet_map = {
            "Washout Matrix - FMT": ("FMT", None),
            "Washout Matrix - 6T MMT": ("MMT", "6T"),
            "Washout Matrix - 12T MMT": ("MMT", "12T"),
            "Washout Matrix - PST": ("PST", None),
        }

        records = []

        for sheet, (technology, system) in sheet_map.items():
            df = pd.read_excel(self.filepath, sheet_name=sheet)
            df.columns = df.columns.astype(str)

            from_col = df.columns[0]
            to_cols = df.columns[1:]

            for _, row in df.iterrows():
                from_sku = row[from_col]

                for to_sku in to_cols:
                    washout = row[to_sku]

                    if pd.notna(washout):
                        records.append({
                            "from_sku": from_sku,
                            "to_sku": to_sku,
                            "technology": technology,
                            "system": system,
                            "washout_min": washout
                        })

        washout_df = pd.DataFrame(records)

        required = ["from_sku", "to_sku", "technology", "system", "washout_min"]
        self._assert_columns(washout_df, required, "Washout Matrix")

        return washout_df

    # ---------- Internal Validator ----------
    @staticmethod
    def _assert_columns(df, required_cols, sheet_name):
        missing = set(required_cols) - set(df.columns)
        if missing:
            raise ValueError(
                f"{sheet_name} missing required columns: {missing}"
            )