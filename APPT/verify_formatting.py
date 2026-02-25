import pandas as pd
import numpy as np

def test_logic():
    # Mock data similar to what's in the DB
    data = {
        "tank_name": ["Betaine", "SLS", "GelN", "HCL"],
        "current_value": [51.7121, 82.6998, 5114.62, 22.1433]
    }
    df = pd.DataFrame(data)

    # Apply the same logic as in rm_data.py
    df["display_value"] = np.where(
        df["current_value"] > 100,
        df["current_value"].round(2).astype(str) + " kg",
        df["current_value"].round(2).astype(str) + " %"
    )

    print("Verification Results:")
    print(df)

    # Verification checks
    assert df.loc[df["tank_name"] == "Betaine", "display_value"].values[0] == "51.71 %"
    assert df.loc[df["tank_name"] == "GelN", "display_value"].values[0] == "5114.62 kg"
    assert df.loc[df["tank_name"] == "HCL", "display_value"].values[0] == "22.14 %"
    
    print("\nVerification successful!")

if __name__ == "__main__":
    test_logic()
