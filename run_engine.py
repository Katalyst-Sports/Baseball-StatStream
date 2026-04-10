import json
from datetime import datetime, date

output = {
    "date": str(date.today()),
    "last_updated": datetime.utcnow().isoformat() + "Z",
    "message": "Daily MLB engine ran successfully.",
    "games": [],
    "disclaimer": (
        "This dashboard is provided for informational and educational purposes only. "
        "The information displayed may be inaccurate or change without notice. "
        "This does not constitute gambling, betting, or financial advice. "
        "Use at your own risk."
    )
}

with open("daily.json", "w") as f:
    json.dump(output, f, indent=2)
