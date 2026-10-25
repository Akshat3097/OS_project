"""Start the OS Tutor web app:  python -m server  [--port 8000] [--no-browser]"""
import argparse
import threading
import webbrowser

try:
    import fastapi  # noqa: F401
    import uvicorn
except ImportError:
    raise SystemExit("The web server needs FastAPI and Uvicorn. Install them with:\n"
                     "    .venv\\Scripts\\python -m pip install -r requirements.txt")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(2.5, lambda: webbrowser.open(url)).start()
    print(f"\n  OS Tutor is starting at {url}  (press Ctrl+C to stop)\n")
    uvicorn.run("server.api:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
