"""Small OpenF1 client with a local JSON cache and polite rate limiting."""
 
import json
import time
from pathlib import Path
 
import pandas as pd
import requests
 
BASE_URL = "https://api.openf1.org/v1"
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "openf1"
 
MIN_SECONDS_BETWEEN_CALLS = 0.5  # free tier allows a few requests per second
MAX_RETRIES = 5
 
_last_call = 0.0
 
 
def _cache_path(endpoint, params):
    """Build a unique file name from the endpoint and its parameters."""
    parts = [f"{k}={params[k]}" for k in sorted(params)]
    name = "__".join(parts).replace(" ", "_") or "all"
    return CACHE_DIR / endpoint / f"{name}.json"
 
 
def _request(endpoint, params):
    """Call the API, waiting between calls and retrying on errors."""
    global _last_call
    for attempt in range(1, MAX_RETRIES + 1):
        wait = MIN_SECONDS_BETWEEN_CALLS - (time.time() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.time()
 
        try:
            r = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=30)
        except requests.RequestException as e:
            print(f"  network error ({e}), retry {attempt}/{MAX_RETRIES}")
            time.sleep(2 ** attempt)
            continue
 
        if r.status_code == 429 or r.status_code >= 500:
            print(f"  HTTP {r.status_code}, retry {attempt}/{MAX_RETRIES}")
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 404:
            return []  # OpenF1 answers 404 when a filter matches nothing
        r.raise_for_status()
        return r.json()
 
    raise RuntimeError(f"Giving up on {endpoint} {params}")
 
 
def get(endpoint, use_cache=True, **params):
    """Return OpenF1 data as a DataFrame, reading from the local cache when possible."""
    path = _cache_path(endpoint, params)
 
    if use_cache and path.exists():
        data = json.loads(path.read_text())
    else:
        data = _request(endpoint, params)
        # Never cache an empty answer: the session may simply not have happened yet.
        if data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
 
    return pd.DataFrame(data)
 