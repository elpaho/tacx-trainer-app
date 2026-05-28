"""
Auto-update — provjeri GitHub za novu verziju i ponudi update.
Koristi raw.githubusercontent.com za provjeru version.py,
i preuzima dist/tacx_app_latest.zip ako je verzija novija.
"""
import urllib.request
import zipfile
import shutil
import sys
import os
import re
import tempfile
import logging

logger = logging.getLogger(__name__)

GITHUB_RAW   = "https://raw.githubusercontent.com/elpaho/tacx-trainer-app/main"
VERSION_URL  = f"{GITHUB_RAW}/version.py"
ZIP_URL      = f"{GITHUB_RAW}/dist/tacx_app_latest.zip"
USER_AGENT   = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36")


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()


def _parse_version(text: str) -> str:
    """Izvuci VERSION string iz version.py sadržaja."""
    m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else ""


def _version_tuple(v: str) -> tuple:
    """Pretvori 'v2.09' u (2, 9) za usporedbu."""
    return tuple(int(x) for x in re.findall(r'\d+', v))


def check_for_update(current_version: str) -> str | None:
    try:
        print(f"[update] Provjeravam... trenutna={current_version}")
        remote_text = _fetch_text(VERSION_URL)
        remote_version = _parse_version(remote_text)
        print(f"[update] Remote={remote_version}")
        if not remote_version:
            return None
        if _version_tuple(remote_version) > _version_tuple(current_version):
            print(f"[update] Nova verzija dostupna: {remote_version}")
            return remote_version
        print("[update] Već najnovija verzija")
    except Exception as e:
        print(f"[update] Greška: {e}")
    return None


def download_and_install(on_progress=None) -> bool:
    """
    Preuzmi zip s GitHuba i instaliraj (pregaziti trenutne fajlove).
    on_progress(pct: int) — opcionalni callback za progress (0-100).
    Vraća True ako je uspjelo.
    """
    app_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_zip = os.path.join(tempfile.gettempdir(), "tacx_app_update.zip")

    try:
        # Preuzmi zip
        req = urllib.request.Request(ZIP_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 8192
            with open(tmp_zip, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress and total > 0:
                        on_progress(int(downloaded / total * 100))

        # Raspakiraj — pregaziš sve fajlove osim konfiga
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            for member in zf.namelist():
                # Preskači lokalni config s API keyevima
                if member.endswith("intervals_config.json"):
                    continue
                # Strip prefix foldera (tacx_app/main.py → main.py)
                parts = member.split("/", 1)
                if len(parts) < 2 or not parts[1]:
                    continue
                target = os.path.join(app_dir, parts[1])
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if not member.endswith("/"):
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        return True

    except Exception as e:
        logger.error(f"Update download greška: {e}")
        return False
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)


def restart_app():
    """Restartaj aplikaciju."""
    os.execv(sys.executable, [sys.executable] + sys.argv)
