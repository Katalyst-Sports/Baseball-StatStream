import json
from datetime import datetime
from urllib.request import urlopen
from zoneinfo import ZoneInfo

# =====================================================
# CONFIG
# =====================================================

BASE = "https://statsapi.mlb.com/api"
MLB_TZ = ZoneInfo("America/New_York")
NOW = datetime.now(MLB_TZ)
TODAY = NOW.date().isoformat()
SEASON = NOW.year

# =====================================================
# UTILS
# =====================================================

def fetch(url):
    with urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def n(x):
    return x if x is not None else 0

# =====================================================
# PITCHER FUNCTIONS (SAFE)
# =====================================================

def pitcher_hand(pid):
    try:
        return fetch(f"{BASE}/v1/people/{pid}")["people"][0]["pitchHand"]["code"]
    except Exception:
        return "N/A"

def pitcher_era(pid):
    try:
        return fetch(
            f"{BASE}/v1/people/{pid}/stats"
            f"?stats=season&group=pitching&season={SEASON}"
        )["stats"][0]["splits"][0]["stat"].get("era", "N/A")
    except Exception:
        return "N/A"

def pitcher_last5(pid):
    """
    Bulletproof last‑5 start processing.
    Handles missing logs, openers, rookies, empty API payloads.
    NEVER crashes.
    """
    try:
        data = fetch(
            f"{BASE}/v1/people/{pid}/stats"
            f"?stats=gameLog&group=pitching&season={SEASON}"
        )

