"""Manual/live smoke-test entry point for the V4 retrieval boundary."""
from psy29_v4_retrieval import run

if __name__ == "__main__":
    result = run()
    print("PSY29 V4 DATA GATE")
    print(f"TRADING_DATE={result['trading_date']}")
    print(f"EXPECTED={result['expected']}")
    print(f"PUBLISHED={result['published']}")
    print(f"FETCHED={result['fetched']}")
    print(f"PARSED={result['parsed']}")
    print(f"VALIDATED={result['validated']}")
    print(f"FAILED={result['failed']}")
    print(f"DATASET_STATUS={result['status']}")
    for row in result['audit']:
        print(row['symbol'], row['fetch'], row['parse'], row['validate'], row['fresh'], row['complete'])
