"""A tiny fake Ollama server for testing the HTTP integration without a GPU.
Run: python tests/mock_ollama.py 11500   then point TUTOR_OLLAMA_URL at http://localhost:11500"""
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

REPLY = {"text": "Good effort! Look at t=5 again: which ready process has the shortest remaining time? P4 should run next."}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/tags":
            return self._json({"models": [{"name": "llama3.1:8b"}, {"name": "nomic-embed-text:latest"}]})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.path == "/api/chat" and data.get("format") == "json":
            import re as _re
            prompt = data["messages"][-1]["content"]
            block = prompt.split("KEY IDEAS:")[1].split("MISCONCEPTIONS")[0]
            ids = _re.findall(r"^- (\w+):", block, _re.M)
            ratings = {k: ("clear" if i % 2 == 0 else "missing") for i, k in enumerate(ids)}
            content = json.dumps({"ideas": ratings, "misconceptions": [], "did_well": "Clear rule.",
                                  "most_important_gap": "Waiting time."})
            return self._json({"message": {"role": "assistant", "content": content}, "done": True})
        if self.path == "/api/chat":
            if data.get("stream"):
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                for w in REPLY["text"].split(" "):
                    self.wfile.write((json.dumps({"message": {"content": w + " "}, "done": False}) + "\n").encode())
                self.wfile.write((json.dumps({"message": {"content": ""}, "done": True}) + "\n").encode())
                return
            return self._json({"message": {"role": "assistant", "content": REPLY["text"]}, "done": True})
        if self.path == "/api/embed":
            vecs = []
            for t in data["input"]:
                h = hashlib.sha256(t.encode()).digest()
                vecs.append([b / 255 for b in h[:16]])
            return self._json({"embeddings": vecs})
        self._json({"error": "not found"}, 404)


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 11500), H).serve_forever()
