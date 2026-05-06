import os
import requests
from requests.exceptions import RequestException

# Allow environment variable override for CI/CD pipelines, fallback to localhost
API_HOST = os.getenv("API_HOST", "http://localhost:8000")
BASE_URL = f"{API_HOST}/api/v1/rm-data"


def test_rm_data():
    print(f"--- Testing GET {BASE_URL} ---")
    try:
        # Added a 10-second timeout so the test doesn't hang infinitely if the server is down
        response = requests.get(BASE_URL, timeout=10)
        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            # Use safe .get() to prevent KeyErrors if the API response structure changes
            print(f"Success: {data.get('success', False)}")
            print(f"Count: {data.get('count', 0)}")

            rm_items = data.get('data', [])
            if rm_items:
                first_item = rm_items[0]
                tank_name = first_item.get('tank_name')
                old_value = float(first_item.get('deadstock_value', 0.0))
                print(f"First Tank: {tank_name}, Deadstock: {old_value}")

                print(f"\n--- Testing POST {BASE_URL}/update-deadstock ---")
                new_value = old_value + 1.0
                payload = {"tank_name": tank_name, "deadstock_value": new_value}

                post_response = requests.post(f"{BASE_URL}/update-deadstock", json=payload, timeout=10)
                print(f"POST Status Code: {post_response.status_code}")
                print(f"POST Response: {post_response.json()}")

                if post_response.status_code == 200:
                    print(f"\n--- Verifying Update ---")
                    verify_response = requests.get(BASE_URL, timeout=10)
                    verify_data = verify_response.json()

                    updated_item = next(
                        (item for item in verify_data.get('data', []) if item.get('tank_name') == tank_name), None)

                    if updated_item:
                        current_val = float(updated_item.get('deadstock_value', 0.0))
                        print(f"Updated Deadstock: {current_val}")
                        if current_val == new_value:
                            print("Verification SUCCESSFUL!")
                        else:
                            print("Verification FAILED: Value mismatch.")
                    else:
                        print("Verification FAILED: Could not find the tank in the updated data.")

                    # Revert to original state to keep the database clean
                    print(f"\n--- Reverting Value ---")
                    revert_payload = {"tank_name": tank_name, "deadstock_value": old_value}
                    revert_resp = requests.post(f"{BASE_URL}/update-deadstock", json=revert_payload, timeout=10)

                    if revert_resp.status_code == 200:
                        print("Value successfully reverted.")
                    else:
                        print("WARNING: Failed to revert value. Manual DB cleanup may be required.")
            else:
                print("No data found in the database to test the update functionality.")
        else:
            print(f"Error: Received unexpected status code. Body: {response.text}")

    except RequestException as e:
        print(f"Network or request error during testing: {e}")
    except Exception as e:
        print(f"Unexpected error during testing: {e}")


if __name__ == "__main__":
    test_rm_data()