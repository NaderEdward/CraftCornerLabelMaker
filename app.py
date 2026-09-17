from __future__ import annotations

import threading
import time
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def _open_browser_when_ready() -> None:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(URL, timeout=1)
            break
        except urllib.error.HTTPError:
            break
        except Exception:
            time.sleep(0.25)
    webbrowser.open(URL)


def main() -> None:
    import uvicorn
    from server.main import app

    threading.Thread(target=_open_browser_when_ready, daemon=True).start()
    print(f"Craft Corner Label Maker running at {URL}")
    print("Close this window to stop the server.")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
