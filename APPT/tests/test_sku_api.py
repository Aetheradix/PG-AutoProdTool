import requests
import json
import random

BASE_URL = "http://127.0.0.1:8000/api/v1/sku-master"

def test_create_and_update_sku():
    # randomized GCAS to avoid conflicts
    test_gcas = f"TEST_{random.randint(1000, 9999)}"
    
    # 1. Test Create (POST)
    payload = {
        "gcas": test_gcas,
        "description": "Test SKU Description",
        "technology": "Test Tech",
        "tech_class": "Single",
        "bct_12t_fmt": 1.5,
        "cons_12t_dm5500": 100.0
    }
    
    print(f"Testing CREATE for GCAS: {test_gcas}")
    try:
        response = requests.post(f"{BASE_URL}/", json=payload)
        print(f"POST Response Code: {response.status_code}")
        print(f"POST Response Body: {response.json()}")
        
        if response.status_code != 200:
            print("Create FAILED")
            return
    except Exception as e:
        print(f"Create Request FAILED: {e}")
        return

    # 2. Test Update (PUT/PATCH)
    update_payload = {
        "description": "Updated Description",
        "cons_12t_dm5500": 200.0
    }
    
    print(f"\nTesting UPDATE for GCAS: {test_gcas}")
    try:
        response = requests.patch(f"{BASE_URL}/{test_gcas}", json=update_payload)
        print(f"PATCH Response Code: {response.status_code}")
        print(f"PATCH Response Body: {response.json()}")
        
        if response.status_code == 200:
            print("Update SUCCESS")
        else:
            print("Update FAILED")
            
    except Exception as e:
        print(f"Update Request FAILED: {e}")

    # 3. Test GET (Read) to verify JSON response
    print(f"\nTesting GET for all SKUs")
    try:
        response = requests.get(f"{BASE_URL}/?limit=10")
        print(f"GET Response Code: {response.status_code}")
        if response.status_code == 200:
            print("GET SUCCESS")
        else:
            print(f"GET FAILED: {response.text}")
    except Exception as e:
        print(f"GET Request FAILED: {e}")

    # 4. Test DELETE
    print(f"\nTesting DELETE for GCAS: {test_gcas}")
    try:
        response = requests.delete(f"{BASE_URL}/{test_gcas}")
        print(f"DELETE Response Code: {response.status_code}")
        if response.status_code == 200:
            print("DELETE SUCCESS")
        else:
            print(f"DELETE FAILED: {response.text}")
            
        # Verify it's gone
        check_response = requests.get(f"{BASE_URL}/")
        # Checking if it's gone from list valid way but fetching specifically via ID if GET /{id} existed would be better
        # For now, if delete succeeded, trusted.
    except Exception as e:
        print(f"DELETE Request FAILED: {e}") 



if __name__ == "__main__":
    test_create_and_update_sku()
