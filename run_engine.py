import json
from datetime import datetime, date
from urllib.request import urlopen

TODAY = str(date.today())

url = (
    "https://statsapi.mlb.com/api/v1/schedule"
    f"?sportId=1&date={TODAY}&hydrate=probablePitcher"
)

with urlopen(url) as response:
    data = json.loads(response.read().decode("utf-8"))

games = []

for day in data.get("dates", []):
    for game in day.get("games", []):
       away_pitcher = (
    game["teams"]["away"].get("probablePitcher", {}).get("fullName")
)

home_pitcher = (
    game["teams"]["home"].get("probablePitcher", {}).get("fullName")
)

games.append({
    "game_id": game["gamePk"],
    "start_time": game["gameDate"],
    "away": game["teams"]["away"]["team"]["name"],
    "home": game["teams"]["home"]["team"]["name"],
    "venue": game["venue"]["name"],
    "away_starter": away_pitcher if away_pitcher else "TBD",
    "home_starter": home_pitcher if home_pitcher else "TBD"
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
