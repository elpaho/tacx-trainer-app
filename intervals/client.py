import asyncio
import base64
import json
import logging
import threading
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_URL = "https://intervals.icu/api/v1"
CONFIG_PATH = Path.home() / ".tacx_app" / "intervals_config.json"


def load_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH) as f:
                return json.load(f)
    except Exception:
        pass
    return {}



def save_config(athlete_id: str, api_key: str):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "athlete_id": athlete_id,
        "api_key":    api_key,
    }
    existing = load_config()
    if "local_athlete" in existing:
        data["local_athlete"] = existing["local_athlete"]
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def save_local_athlete(ftp: int, hr_max: int,
                       power_zones: list = None, hr_zones: list = None,
                       cadence_tolerance: int = 5):
    """Spremi FTP, HR max, zone i kadenca toleranciju lokalno."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = load_config()
    data["local_athlete"] = {
        "ftp":               ftp,
        "hr_max":            hr_max,
        "power_zones":       power_zones or [],
        "hr_zones":          hr_zones or [],
        "cadence_tolerance": cadence_tolerance,
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)


def load_local_athlete() -> dict:
    """
    Učitaj lokalno spremljene athlete podatke.
    Vraća dict s ključevima: ftp, hr_max, power_zones, hr_zones
    ili prazan dict ako nema podataka.
    """
    cfg = load_config()
    return cfg.get("local_athlete", {})


def _get(url: str, api_key: str) -> dict | list:
    """Sinhroni HTTP GET s Basic Auth — poziva se iz worker threada."""
    credentials = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Basic {credentials}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _fetch_all_sync(athlete_id: str, api_key: str) -> tuple[dict, list]:
    """
    Dohvati sve podatke sinhrono u jednom threadu.
    Vraća (athlete_dict, workouts_list).
    """
    # 1. Athlete profil
    athlete = _get(f"{BASE_URL}/athlete/{athlete_id}", api_key)
    if isinstance(athlete, list):
        athlete = athlete[0] if athlete else {}

    # 2. Treninzi za danas — BEZ resolve da dobijemo originalnu strukturu s text tagovima (slope)
    today = date.today().isoformat()
    url = (
        f"{BASE_URL}/athlete/{athlete_id}/events"
        f"?oldest={today}&newest={today}&category=WORKOUT"
    )
    events = _get(url, api_key)
    if not isinstance(events, list):
        events = []

    # Za svaki event dohvati puni detalj s workout_doc koji sadrži originalne korake i text tagove
    workouts = []
    for e in events:
        eid = e.get("id")
        if not eid:
            continue
        try:
            detail = _get(f"{BASE_URL}/athlete/{athlete_id}/events/{eid}", api_key)
            if isinstance(detail, dict) and detail.get("workout_doc"):
                workouts.append(detail)
            elif e.get("workout_doc"):
                workouts.append(e)
        except Exception as ex:
            logger.warning(f"Event detail greška {eid}: {ex}")
            if e.get("workout_doc"):
                workouts.append(e)

    return athlete, workouts


def fetch_all(athlete_id: str, api_key: str, on_done, on_error):
    """
    Pokreni dohvat u zasebnom threadu.
    on_done(athlete, workouts) — zove se iz worker threada
    on_error(str) — zove se iz worker threada
    """
    def _run():
        try:
            athlete, workouts = _fetch_all_sync(athlete_id, api_key)
            on_done(athlete, workouts)
        except Exception as e:
            logger.error(f"intervals fetch greška: {e}")
            on_error(str(e))

    t = threading.Thread(target=_run, daemon=True)
    t.start()
