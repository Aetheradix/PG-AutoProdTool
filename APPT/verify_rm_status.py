
import asyncio
import pandas as pd
from src.api.routes.status import get_rm_data

async def verify():
    try:
        result = await get_rm_data()
        print(f"Success: {result['success']}")
        print(f"Count: {result['count']}")
        if result['data']:
            print("First record sample:")
            print(result['data'][0])
            if "DateandTime" in result['data'][0]:
                print(f"DateandTime found: {result['data'][0]['DateandTime']}")
            else:
                print("Error: DateandTime NOT found in data")
    except Exception as e:
        print(f"Error during verification: {e}")

if __name__ == "__main__":
    asyncio.run(verify())
