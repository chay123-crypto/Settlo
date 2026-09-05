"""
Fetch live test transactions directly from Razorpay Test API using credentials in .env
and export them to input CSV files for reconciliation.
"""
import sys
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.razorpay_client import fetch_settlements

def main():
    print("Connecting to Razorpay Test API...")
    try:
        data = fetch_settlements(params={"count": 50})
        items = data.get("items", [])
        print(f"Successfully fetched {len(items)} settlements from Razorpay Test API!")
        if items:
            print("Sample settlement item from live Razorpay API:")
            print(items[0])
        else:
            print("No settlement records found in your Razorpay Test account yet.")
            print("Tip: Go to Razorpay Test Dashboard -> Create a Test Payment first.")
    except Exception as e:
        print(f"Error fetching from Razorpay API: {e}")

if __name__ == "__main__":
    main()
