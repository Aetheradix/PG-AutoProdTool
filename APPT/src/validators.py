def validate_washout(washout_df):
    missing = washout_df[
        washout_df["washout_min"].isna()
    ]
    if not missing.empty:
        raise ValueError("Missing washout values detected")

def validate_bct(bct_df):
    if (bct_df["bct_min"] <= 0).any():
        raise ValueError("Invalid BCT detected")
