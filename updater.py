"""
Auto-update — provjeri GitHub za novu verziju i ponudi update.
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

GITHUB_RAW  = "https://raw.githubusercontent.com/elpaho/tacx-trainer-app/main"
VERSION_URL = f"{GITHUB_RAW}/version.py"
ZIP_URL     = f"{GITHUB_RAW}/dist/tacx_app_latest.zip"
USER_AGENT  = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
               "AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/124.0.0.0 Safari/537.36")


def _fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()


def _parse_version(text: str) -> str:
    m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else ""


def _version_tuple(v: str) -> tuple:
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
    app_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_zip = os.path.join(tempfile.gettempdir(), "tacx_app_update.zip")

    try:
        req = urllib.request.Request(ZIP_URL, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=120) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 65536  # 64KB chunks
            with open(tmp_zip, "wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if on_progress:
                        if total > 0:
                            on_progress(int(downloaded / total * 100))
                        else:
                            # Nema Content-Length — indeterminate, šalji -1
                            on_progress(-1)

        print(f"[update] Preuzeto {downloaded} bytes, raspakiravam...")

        # Raspakiraj — pregaziš sve fajlove osim konfiga
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            for member in zf.namelist():
                if member.endswith("intervals_config.json"):
                    continue
                parts = member.split("/", 1)
                if len(parts) < 2 or not parts[1]:
                    continue
                target = os.path.join(app_dir, parts[1])
                os.makedirs(os.path.dirname(target), exist_ok=True)
                if not member.endswith("/"):
                    with zf.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        print("[update] Instalacija završena")
        return True

    except Exception as e:
        print(f"[update] Download greška: {e}")
        return False
    finally:
        if os.path.exists(tmp_zip):
            os.remove(tmp_zip)


def restart_app():
    """Restartaj aplikaciju — Windows kompatibilno."""
    python = sys.executable
    script = os.path.abspath(sys.argv[0])
    print(f"[update] Restarting: {python} {script}")
    import subprocess
    # Kratka pauza da se Qt prozori zatvore
    import time
    time.sleep(0.5)
    subprocess.Popen([python, script],
                     creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0))
    os._exit(0)
