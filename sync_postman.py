#!/usr/bin/env python
"""
GoOnStay - Automatic Postman Collection Sync Script
Synchronizes the local consolidated Postman collection directly to the Postman Cloud Workspace
using the Postman REST API (https://api.getpostman.com).

Usage:
    python sync_postman.py
    python manage.py sync_postman
"""

import os
import sys
import json
import ssl
import urllib.request
import urllib.error
from datetime import datetime


def load_env(env_path='.env'):
    """Reads key-value pairs from .env file into os.environ if not already set."""
    if not os.path.exists(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k not in os.environ:
                os.environ[k] = v


def create_ssl_context():
    """Creates SSL context handling potential system date skew."""
    try:
        return ssl.create_default_context()
    except Exception:
        return ssl._create_unverified_context()


def get_postman_headers(api_key):
    return {
        'X-Api-Key': api_key,
        'Content-Type': 'application/json',
        'User-Agent': 'GoOnStay-PostmanSync/1.0'
    }


def find_or_create_collection_uid(api_key, ssl_ctx, collection_name, workspace_id=None):
    """Finds existing collection UID by name or returns None."""
    headers = get_postman_headers(api_key)
    url = 'https://api.getpostman.com/collections'
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            for col in data.get('collections', []):
                if col.get('name', '').strip().lower() == collection_name.strip().lower():
                    return col.get('uid')
    except Exception as e:
        print(f"[WARN] Could not search existing collections: {e}")
    return None


def sync_postman(collection_file=None):
    load_env()

    api_key = os.environ.get('POSTMAN_API_KEY')
    if not api_key:
        print("[ERROR] POSTMAN_API_KEY is not defined in .env or environment variables.")
        print("Please add POSTMAN_API_KEY=PMAK-... to your .env file.")
        return False

    # Locate collection file
    candidate_paths = [
        collection_file,
        'GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json',
        os.path.join('postman_collections', '01_GOONSTAY_COMPLETE_ALL_IN_ONE_POSTMAN_COLLECTION.json')
    ]
    target_file = None
    for p in candidate_paths:
        if p and os.path.exists(p):
            target_file = p
            break

    if not target_file:
        print("[ERROR] No consolidated Postman collection JSON file found.")
        return False

    with open(target_file, 'r', encoding='utf-8') as f:
        collection_data = json.load(f)

    col_name = collection_data.get('info', {}).get('name', 'GoOnStay Master Collection')
    folder_count = len(collection_data.get('item', []))

    # Total requests count
    def count_requests(items):
        cnt = 0
        for it in items:
            if 'item' in it:
                cnt += count_requests(it['item'])
            elif 'request' in it:
                cnt += 1
        return cnt

    total_requests = count_requests(collection_data.get('item', []))

    # SSL Context (use unverified fallback to handle system date skews safely)
    try:
        ssl_ctx = ssl.create_default_context()
        test_req = urllib.request.Request('https://api.getpostman.com/me', headers=get_postman_headers(api_key))
        with urllib.request.urlopen(test_req, context=ssl_ctx, timeout=5):
            pass
    except Exception:
        ssl_ctx = ssl._create_unverified_context()

    collection_uid = os.environ.get('POSTMAN_COLLECTION_UID')
    workspace_id = os.environ.get('POSTMAN_WORKSPACE_ID')

    if not collection_uid:
        print(f"[*] Searching for existing collection '{col_name}' on Postman...")
        collection_uid = find_or_create_collection_uid(api_key, ssl_ctx, col_name, workspace_id)

    payload = json.dumps({'collection': collection_data}).encode('utf-8')

    print(f"\n========================================================")
    print(f"🚀 Syncing to Postman Cloud...")
    print(f"   Collection: {col_name}")
    print(f"   File:       {target_file}")
    print(f"   Folders:    {folder_count}")
    print(f"   Endpoints:  {total_requests}")
    print(f"========================================================")

    if collection_uid:
        # Update existing collection (PUT)
        url = f"https://api.getpostman.com/collections/{collection_uid}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers=get_postman_headers(api_key),
            method='PUT'
        )
    else:
        # Create new collection (POST)
        url = 'https://api.getpostman.com/collections'
        if workspace_id:
            url += f"?workspace={workspace_id}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers=get_postman_headers(api_key),
            method='POST'
        )

    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=40) as resp:
            resp_data = json.loads(resp.read().decode('utf-8'))
            col_info = resp_data.get('collection', {})
            res_uid = col_info.get('uid', collection_uid)
            res_id = col_info.get('id', '')
            res_name = col_info.get('name', col_name)

            print(f"\n✅ POSTMAN SYNC SUCCESSFUL!")
            print(f"   Updated At:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   Collection:     {res_name}")
            print(f"   Collection UID: {res_uid}")
            if workspace_id:
                print(f"   Workspace Link: https://go.postman.co/workspace/{workspace_id}/collection/{res_uid}")
            else:
                print(f"   Postman Link:   https://go.postman.co/collection/{res_uid}")
            print(f"========================================================\n")
            return True

    except urllib.error.HTTPError as err:
        err_body = err.read().decode('utf-8', errors='replace')
        print(f"\n❌ [HTTP ERROR {err.code}] Postman Sync Failed:")
        print(err_body)
        return False
    except Exception as exc:
        print(f"\n❌ [ERROR] Postman Sync Failed: {exc}")
        return False


if __name__ == '__main__':
    specified_file = sys.argv[1] if len(sys.argv) > 1 else None
    success = sync_postman(specified_file)
    sys.exit(0 if success else 1)
