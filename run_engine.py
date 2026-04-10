import json
import requests
from datetime import datetime, date

TODAY = str(date.today())

# MLB schedule API (official)
SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"

params = {
    "sportId": 1,
    "date": TODAY
}

response = requests.get(SCHEDULE_URL, params=params)
data = response.json()

games = []

for date_block in data.get("dates", []):
    for game in date_block.get("games", []):
        games.append({
            "game_id": game["gamePk"],
            "start_time": game["gameDate"],
            "away": game["teams"]["away"]["team"]["name"],
            "home": game["teams"]["home"]["team"]["name"],
            "venue": game["venue"]["name"]
        })

output = {
    "date": TODAY,
    "last_updated": datetime.utcnow().isoformat() + "Z",
    "games": games,
    "disclaimer": (
        "This dashboard is provided for informational and educational purposes only. "
        "The information displayed may be inaccurate or change without notice. "
        "This does not constitute gambling, betting, or financial advice. "
        "Use at your own risk."
    )
}

with open("daily.json", "w") as f:
    json.dump(output, f, indent=2)
