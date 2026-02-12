import requests
import json
import random

BASE_URL = "http://127.0.0.1:8000/api/v1/bulk-details"

def test_bulk_details():
    # 1. Test GET (Read) to check for NaN errors
    print(f"Testing GET for all Bulk Details")
    try:
        response = requests.get(f"{BASE_URL}/?limit=10")
        print(f"GET Response Code: {response.status_code}")
        if response.status_code == 200:
            print("GET SUCCESS")
        else:
            print(f"GET FAILED: {response.text}")
    except Exception as e:
        print(f"GET Request FAILED: {e}")

    # 2. Test Create (POST) - Expecting failure if endpoint missing
    test_p_code = f"TEST_P_{random.randint(1000, 9999)}"
    payload = {
        "p_code": test_p_code,
        "description": "Test Bulk Detail",
        "size": "500ml",
        "brand": "Test Brand",
        "qty_per_container": 12
    }
    
    print(f"\nTesting CREATE for P-Code: {test_p_code}")
    new_id = None
    try:
        response = requests.post(f"{BASE_URL}/", json=payload)
        print(f"POST Response Code: {response.status_code}")
        print(f"POST Response Body: {response.text}")
        
        if response.status_code == 200:
            resp_json = response.json()
            new_id = resp_json.get("id")
            print(f"Created ID: {new_id}")
    except Exception as e:
        print(f"POST Request FAILED: {e}")

    # 3. Test DELETE
    if new_id:
        print(f"\nTesting DELETE for ID: {new_id}")
        try:
            response = requests.delete(f"{BASE_URL}/{new_id}")
            print(f"DELETE Response Code: {response.status_code}")
            if response.status_code == 200:
                print("DELETE SUCCESS")
            else:
                print(f"DELETE FAILED: {response.text}")
        except Exception as e:
            print(f"DELETE Request FAILED: {e}")
    else:
        print("Skipping DELETE test because CREATE failed or returned no ID")

if __name__ == "__main__":
    test_bulk_details()
