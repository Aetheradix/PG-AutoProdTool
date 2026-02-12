import requests
import json

BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_pagination():
    # 1. Test SKU Master Pagination
    print("Testing SKU Master Pagination...")
    try:
        limit = 5
        response = requests.get(f"{BASE_URL}/sku-master?page=1&limit={limit}")
        print(f"SKU Master Page 1 Response Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("data", [])
            pagination = data.get("pagination", {})
            
            print(f"Items received: {len(items)}")
            print(f"Pagination Metadata: {pagination}")
            
            if len(items) <= limit and pagination.get("current_page") == 1:
                print("SKU Master Page 1 SUCCESS")
            else:
                print("SKU Master Page 1 FAILED: Incorrect item count or page number")
                
            # Test Page 2
            if pagination.get("total_pages", 0) > 1:
                resp2 = requests.get(f"{BASE_URL}/sku-master?page=2&limit={limit}")
                if resp2.status_code == 200:
                    pg2_data = resp2.json()
                    print(f"SKU Master Page 2 Current Page: {pg2_data.get('pagination', {}).get('current_page')}")
        else:
            print(f"SKU Master Page 1 FAILED: {response.text}")
            
    except Exception as e:
        print(f"SKU Master Request FAILED: {e}")

    # 2. Test Bulk Details Pagination
    print("\nTesting Bulk Details Pagination...")
    try:
        limit = 5
        response = requests.get(f"{BASE_URL}/bulk-details?page=1&limit={limit}")
        print(f"Bulk Details Page 1 Response Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("data", [])
            pagination = data.get("pagination", {})
            
            print(f"Items received: {len(items)}")
            print(f"Pagination Metadata: {pagination}")
            
            if len(items) <= limit and pagination.get("current_page") == 1:
                print("Bulk Details Page 1 SUCCESS")
            else:
                print("Bulk Details Page 1 FAILED: Incorrect item count or page number")
        else:
            print(f"Bulk Details Page 1 FAILED: {response.text}")
            
    except Exception as e:
        print(f"Bulk Details Request FAILED: {e}")

if __name__ == "__main__":
    test_pagination()
