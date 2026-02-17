import requests
import json

BASE_URL = "http://localhost:8000/api/v1/rm-data"

def test_rm_data():
    print("--- Testing GET /api/v1/rm-data ---")
    try:
        response = requests.get(BASE_URL)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Success: {data['success']}")
            print(f"Count: {data['count']}")
            if data['data']:
                first_item = data['data'][0]
                tank_name = first_item['tank_name']
                old_value = first_item['deadstock_value']
                print(f"First Tank: {tank_name}, Deadstock: {old_value}")
                
                print(f"\n--- Testing POST /api/v1/rm-data/update-deadstock ---")
                new_value = old_value + 1.0
                payload = {"tank_name": tank_name, "deadstock_value": new_value}
                post_response = requests.post(f"{BASE_URL}/update-deadstock", json=payload)
                print(f"POST Status Code: {post_response.status_code}")
                print(f"POST Response: {post_response.json()}")
                
                if post_response.status_code == 200:
                    print(f"\n--- Verifying Update ---")
                    verify_response = requests.get(BASE_URL)
                    verify_data = verify_response.json()
                    updated_item = next((item for item in verify_data['data'] if item['tank_name'] == tank_name), None)
                    if updated_item:
                        print(f"Updated Deadstock: {updated_item['deadstock_value']}")
                        if updated_item['deadstock_value'] == new_value:
                            print("Verification SUCCESSFUL!")
                        else:
                            print("Verification FAILED: Value mismatch.")
                    
                    # Revert
                    print(f"\n--- Reverting Value ---")
                    revert_payload = {"tank_name": tank_name, "deadstock_value": old_value}
                    requests.post(f"{BASE_URL}/update-deadstock", json=revert_payload)
                    print("Value reverted.")
            else:
                print("No data found to test update.")
        else:
            print(f"Error: {response.text}")
    except Exception as e:
        print(f"Error during testing: {e}")

if __name__ == "__main__":
    test_rm_data()
