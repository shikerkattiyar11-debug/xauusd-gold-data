import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from live_collector import LiveCollector


BASE_DIR = Path(__file__).resolve().parent
PORT = int(os.getenv("PORT", "10000"))


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def log_message(self, format, *args):
        return


def start_collector() -> None:
    collector = LiveCollector("XAU/USD", BASE_DIR / "data")
    try:
        collector.run()
    finally:
        collector.close()


def main() -> None:
    collector_thread = threading.Thread(target=start_collector, daemon=True)
    collector_thread.start()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), DashboardHandler)
    print(f"Dashboard listening on port {PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()