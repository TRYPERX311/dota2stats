# opendota.py
import requests

OPENDOTA_BASE = "https://api.opendota.com/api"

def fetch_player_mmr(account_id: int) -> int | None:
    url = f"{OPENDOTA_BASE}/players/{account_id}"
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json().get("mmr_estimate", {}).get("estimate")
    except requests.RequestException:
        return None