"""
Sync updated GoOnStay collection to Postman Cloud API using POSTMAN_API_KEY from .env
"""

import os
import json
import urllib.request
import urllib.error

def load_env(filepath='.env'):
    env_vars = {}
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

def main():
    env = load_env()
    api_key = env.get('POSTMAN_API_KEY')
    collection_uid = env.get('POSTMAN_COLLECTION_UID')

    print(f"Postman API Key found: {'Yes' if api_key else 'No'} ({api_key[:10]}...)")
    print(f"Collection UID: {collection_uid}")

    if not api_key or not collection_uid:
        print("Missing POSTMAN_API_KEY or POSTMAN_COLLECTION_UID in .env")
        return

    # Load updated master collection
    collection_path = "GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json"
    if not os.path.exists(collection_path):
        print(f"Collection file {collection_path} not found.")
        return

    with open(collection_path, 'r', encoding='utf-8') as f:
        col_data = json.load(f)

    # Postman PUT /collections/{collection_uid} expects payload: { "collection": { ... } }
    payload = {
        "collection": {
            "info": col_data.get("info", {}),
            "item": col_data.get("item", [])
        }
    }

    url = f"https://api.getpostman.com/collections/{collection_uid}"
    req_data = json.dumps(payload).encode('utf-8')

    headers = {
        "X-Api-Key": api_key,
        "Content-Type": "application/json"
    }

    import ssl
    ctx = ssl._create_unverified_context()

    req = urllib.request.Request(url, data=req_data, headers=headers, method="PUT")

    try:
        print(f"Sending PUT request to Postman Cloud API: {url}...")
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            resp_body = resp.read().decode('utf-8')
            res_json = json.loads(resp_body)
            print("Sync Success!")
            print("Response:", json.dumps(res_json.get("collection", {}), indent=2))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    main()
