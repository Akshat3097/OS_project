"""
Click through the whole app in a real browser, the way an examiner would, in about two minutes.

    python -m eval.browser_check                 language model off: fast, same result every time
    python -m eval.browser_check --with-model    with os-tutor and the teach-back judge (slower; needs Ollama)
    python -m eval.browser_check --show          watch it happen instead of running headless

It starts its own server on a free port with a temporary database and chat folder (data/ is not touched), drives
Microsoft Edge (or Chrome) with Playwright, and records "Explain it back" with a fake microphone that plays
tests/data/srtf_explanation.webm, so the speech-to-text path is tested end to end. Screenshots of failed steps go to
eval/logs/browser/. Needs Playwright: .venv\\Scripts\\python -m pip install -r requirements-dev.txt (it uses the
installed Edge; no browser download).
"""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.request
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "eval" / "logs" / "browser"
CLIP = ROOT / "tests" / "data" / "srtf_explanation.webm"
SID = "browser-check"
# the pasted question the start screen offers, answered with the classic slip (waiting time = turnaround time)
WRONG_ANSWER = ("P1 0-2, P2 2-4, P3 4-5, P1 5-7, P2 7-8, P1 8-9; P1: CT 9, TAT 9, WT 9; P2: CT 8, TAT 7, WT 7; "
                "P3: CT 5, TAT 3, WT 3")
TYPED_EXPLANATION = ("SRTF always runs the process with the shortest remaining time. When a new process arrives the "
                     "scheduler compares it with the remaining time of the running process and preempts only if it is "
                     "strictly shorter. Waiting time is completion time minus arrival time minus burst time.")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def mic_wav(folder: Path) -> Path | None:
    """The recorded explanation as a 16 kHz WAV, the format Chromium's fake microphone plays."""
    try:
        import numpy as np
        sys.path.insert(0, str(ROOT))
        from tutor import speech
        if not speech.available():
            return None
        audio = speech.decode(str(CLIP))
    except Exception:
        return None
    path = folder / "explanation.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
    return path


class Run:
    def __init__(self, page, url: str, with_model: bool):
        self.page, self.url, self.with_model = page, url, with_model
        self.results: list[tuple[str, bool, float, str]] = []

    def prepare(self, view: str, toggle: bool = True, **keys) -> None:
        """A fresh page on one view, as a new visitor would see it (the language model switched off unless asked)."""
        p = self.page
        p.goto(self.url)
        values = {"sid": SID, "view": view, **keys}
        p.evaluate("v => { for (const [k, x] of Object.entries(v)) localStorage.setItem(k, JSON.stringify(x)); }", values)
        p.reload()
        p.wait_for_selector(".app", timeout=30000)
        p.wait_for_timeout(600)                     # the model status arrives right after the first paint
        box = p.locator("label.check", has_text="Use the language model").locator("input")
        if toggle and not self.with_model and box.count() and box.is_checked():
            box.uncheck()

    def new_chat(self) -> None:
        """Start a new conversation (the page reopens the visitor's latest one), as the sidebar button does."""
        self.page.get_by_role("button", name="New chat").click()
        self.page.wait_for_selector(".hero__example", timeout=15000)

    def step(self, name: str, fn) -> None:
        t0 = time.time()
        try:
            note = fn() or ""
            self.results.append((name, True, time.time() - t0, note))
        except Exception as e:  # keep going: the other steps start from a fresh page
            SHOTS.mkdir(parents=True, exist_ok=True)
            shot = SHOTS / f"{len(self.results) + 1:02d}_{name.split(':')[0].replace(' ', '_')}.png"
            try:
                self.page.screenshot(path=str(shot), full_page=True)
            except Exception:
                pass
            msg = str(e).splitlines()[0][:160] if str(e) else type(e).__name__
            self.results.append((name, False, time.time() - t0, f"{msg} (screenshot: {shot.relative_to(ROOT)})"))
            if os.environ.get("BROWSER_CHECK_TRACE"):
                traceback.print_exc()

    def send(self, text: str) -> None:
        # wait until the previous reply has finished streaming: the composer ignores Enter while the tutor is writing
        self.page.wait_for_function("!document.querySelector('.caret') && !document.querySelector('.thinking')",
                                    timeout=180000)
        box = self.page.locator(".composer textarea")
        box.fill(text)
        box.press("Enter")


def steps(r: Run, has_mic: bool) -> None:
    p = r.page
    wait = 180000 if r.with_model else 60000

    def start_screen():
        r.prepare("chat")
        p.wait_for_selector(".hero .explore", timeout=15000)
        assert p.locator(".hero__block").count() >= 4, "the starting suggestions are missing"
        if p.locator(".model-pick").count():
            name = p.locator(".model-pick__name").inner_text()
            assert "recommended" in name, f"the sidebar does not start on the recommended model: {name!r}"
            return name
        return "Ollama is off: template replies"

    def home():
        r.prepare("home")
        p.wait_for_selector(".ov__item", timeout=15000)
        assert p.locator(".ov__item").count() == 4, "the Home overview should show four numbers"
        assert p.locator(".hcard").count() >= 4, "Home cards are missing"
        p.get_by_role("button", name="Start lesson").first.wait_for(timeout=10000)
        return f"{p.locator('.hcard').count()} cards, 4 numbers, next lesson ready"

    def chat_solution():
        r.prepare("chat")
        r.new_chat()
        p.get_by_role("button", name="Try a pasted question").click()
        p.wait_for_selector(".card--task", timeout=wait)
        r.send("show me the solution")
        p.wait_for_selector("section[aria-label='Solution'] .gantt__block", timeout=wait)
        blocks = p.locator('section[aria-label=Solution] .gantt__block').count()
        p.wait_for_function("!document.querySelector('.caret') && !document.querySelector('.thinking')", timeout=wait)
        p.locator(".save-note").last.click()
        p.wait_for_selector(".save-note.is-done", timeout=15000)
        return f"{blocks} blocks in the Gantt chart; reply saved to notes"

    def chat_mistake():
        r.prepare("chat")
        r.new_chat()
        p.get_by_role("button", name="Try a pasted question").click()
        p.wait_for_selector(".card--task", timeout=wait)
        r.send("let me try it first")
        p.wait_for_function("document.querySelectorAll('.msg--tutor').length >= 3", timeout=wait)
        r.send(WRONG_ANSWER)
        p.wait_for_selector(".card--fix", timeout=wait)
        head = p.locator(".card--fix .card__title").inner_text()
        assert "WT" in head or "waiting" in head.lower(), f"the slip was not named: {head!r}"
        return head

    def learn_watch():
        r.prepare("learn", lesson="srtf")
        p.locator(".stagebar__step").nth(1).click()
        p.wait_for_selector(".decision__choice", timeout=15000)
        before = p.locator(".gantt__block").count()
        for _ in range(3):
            p.get_by_role("button", name="Step →").click()
        p.wait_for_timeout(500)
        after = p.locator(".gantt__block").count()
        assert after > before, "the Gantt chart did not grow while stepping"
        assert "gets the CPU" in p.locator(".decision__choice").inner_text()
        return f"chart grew from {before} to {after} blocks"

    def learn_explain():
        r.prepare("learn", lesson="srtf")
        p.locator(".stagebar__step").nth(2).click()
        how = "typed"
        if has_mic:
            p.wait_for_selector(".rec-btn:not([disabled])", timeout=20000)
            p.get_by_role("button", name="Record your explanation").click()
            p.wait_for_selector(".rec-btn.is-on", timeout=10000)
            loudest = 0
            for _ in range(50):                                            # about 15 s, watching the level bar
                p.wait_for_timeout(300)
                loudest = max(loudest, int(p.locator(".level").get_attribute("aria-valuenow") or 0))
            assert loudest > 5, "the microphone level never moved while recording"
            p.locator(".rec-btn.is-on").click()
            p.wait_for_function("document.querySelector('.explain__box textarea').value.length > 40", timeout=120000)
            text = p.locator(".explain__box textarea").input_value()
            assert "remaining" in text.lower(), f"the transcript looks wrong: {text[:80]!r}"
            assert p.locator(".recorder__playback audio").count() == 1, "no playback of the recording"
            how = f"recorded (level up to {loudest}%), transcribed, playback ready"
        else:
            p.locator(".explain__box textarea").fill(TYPED_EXPLANATION)
        p.get_by_role("button", name="Check my understanding").click()
        p.wait_for_selector(".assessment", timeout=wait)
        head = p.locator(".assessment__head").inner_text()
        assert "of" in head, f"no assessment: {head!r}"
        p.locator(".stage-nav__next").click()                                 # Your question
        p.wait_for_selector(".question .qpaper", timeout=wait)
        if p.locator(".question .two-col").count():                          # semaphore: value and outcome
            for col in range(2):
                p.locator(".question .two-col > div").nth(col).locator(".option").first.click()
        elif p.locator(".question .option, .question .qq__opt").count():
            p.locator(".question .option, .question .qq__opt").first.click()
        else:
            p.locator(".question .num-input").fill("3")
        p.get_by_role("button", name="Submit answer").click()
        p.wait_for_selector(".question .qq__why", timeout=wait)
        p.locator(".stage-nav__next").click()                                 # Pointers
        p.wait_for_selector(".verdict-title", timeout=wait)
        return f"{how}; {head.split('.')[0]}"

    def labs():
        r.prepare("labs", labTab="scheduler")
        p.wait_for_selector(".compare li", timeout=20000)
        assert p.locator(".compare li").count() == 6, "the scheduler lab does not compare six algorithms"
        p.get_by_role("tab", name="Banker's algorithm").click()
        p.get_by_role("button", name="Unsafe state").click()
        p.wait_for_timeout(500)
        p.get_by_role("button", name="Show all").first.click()
        p.wait_for_selector(".verdict--no", timeout=10000)
        assert "unsafe" in p.locator(".verdict--no").first.inner_text().lower()
        p.get_by_role("tab", name="Semaphores").click()
        p.wait_for_selector(".timeline", timeout=10000)
        p.get_by_role("tab", name="Deadlocks").click()
        p.wait_for_selector("svg.rag", timeout=10000)
        verdict = p.locator(".lab > .verdict").first.inner_text()
        return f"scheduler, unsafe Banker's state, semaphore timeline, deadlock graph ({verdict.split('.')[0]})"

    def notes():
        r.prepare("notes")
        p.wait_for_selector(".sticky", timeout=15000)                 # the reply saved in the chat step
        before = p.locator(".sticky").count()
        p.get_by_role("button", name="New note").click()
        p.get_by_label("Note text").fill("WT = TAT − BT, so WT can never be more than TAT.")
        p.get_by_role("button", name="Save note").click()
        p.wait_for_function(f"document.querySelectorAll('.sticky:not(.sticky--edit)').length > {before}", timeout=15000)
        assert "never be more than TAT" in p.locator(".board").inner_text()
        return f"{before} saved from the chat, 1 written here"

    def exam():
        r.prepare("exam")
        p.on("dialog", lambda d: d.accept())
        p.get_by_role("button", name="Start the paper").click()
        p.wait_for_selector(".exam-bar", timeout=wait)
        p.locator(".exam-q").nth(0).locator("input").first.fill("P1 0-2, P2 2-4")
        p.locator(".exam-bar .primary").click()
        p.wait_for_selector(".score__big", timeout=wait)
        return "marked: " + p.locator(".score__big").inner_text().replace("\n", " ")

    def progress():
        r.prepare("progress")
        p.wait_for_selector(".tiles", timeout=20000)
        tried = p.locator(".tile__value").first.inner_text()
        assert tried.strip() not in ("", "0"), "the attempts made above do not show on the Progress page"
        return f"{tried} problems tried"

    def phone():
        p.set_viewport_size({"width": 390, "height": 844})
        wide = []
        for view in ("home", "chat", "learn", "labs", "notes", "exam", "progress"):
            r.prepare(view, toggle=False)           # the sidebar is an off-screen drawer at phone width
            p.wait_for_timeout(400)
            w = p.evaluate("document.documentElement.scrollWidth")
            if w > 392:
                wide.append(f"{view} ({w}px)")
        p.set_viewport_size({"width": 1280, "height": 900})
        assert not wide, "wider than a phone screen: " + ", ".join(wide)
        return "home, chat, learn, labs, notes, exam, progress fit 390px"

    for name, fn in (("Home dashboard", home), ("Start screen", start_screen), ("Chat: pasted question, then the solution", chat_solution),
                     ("Chat: a wrong answer gets its mistake named", chat_mistake),
                     ("Learn: animated worked example", learn_watch),
                     ("Learn: explain it back, question, pointers", learn_explain),
                     ("Labs: all four tabs", labs), ("Notes: saved reply and a new note", notes),
                     ("Exam: take and submit a paper", exam),
                     ("Progress: the attempts show up", progress), ("Phone width", phone)):
        r.step(name, fn)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--with-model", action="store_true", help="use the language model (Ollama) as well")
    ap.add_argument("--show", action="store_true", help="show the browser window")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright is not installed:  .venv\\Scripts\\python -m pip install -r requirements-dev.txt")

    tmp = Path(tempfile.mkdtemp(prefix="os-tutor-check-"))
    port = free_port()
    env = {**os.environ, "TUTOR_DB": str(tmp / "check.db"), "TUTOR_CHAT_DIR": str(tmp / "chats"),
           "TUTOR_NOTES_DIR": str(tmp / "notes")}
    log = open(tmp / "server.log", "w", encoding="utf-8")
    server = subprocess.Popen([sys.executable, "-m", "server", "--port", str(port), "--no-browser"], cwd=ROOT, env=env,
                              stdout=log, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(url + "/api/speech", timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit(f"The server did not start; see {tmp / 'server.log'}")
        wav = mic_wav(tmp)
        errors: list[str] = []
        with sync_playwright() as pw:
            flags = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
            if wav:
                flags.append(f"--use-file-for-fake-audio-capture={wav}")
            browser = None
            for channel in ("msedge", "chrome", None):
                try:
                    browser = pw.chromium.launch(channel=channel, headless=not args.show, args=flags)
                    used = {"msedge": "Edge", "chrome": "Chrome"}.get(channel, "Chromium")
                    break
                except Exception:
                    continue
            if browser is None:
                raise SystemExit("No browser found: install Microsoft Edge or Chrome, or run:  python -m playwright install chromium")
            ctx = browser.new_context(viewport={"width": 1280, "height": 900}, permissions=["microphone"])
            page = ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            run = Run(page, url, args.with_model)
            print(f"Checking {url} in {used} ({'with the language model' if args.with_model else 'language model off'}"
                  f"{', microphone: recorded clip' if wav else ', microphone: typed instead (faster-whisper missing)'})\n")
            steps(run, has_mic=wav is not None)
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        log.close()

    ok = all(passed for _, passed, _, _ in run.results) and not errors
    for name, passed, secs, note in run.results:
        print(f"  {'✓' if passed else '✗'} {name:<46} {secs:5.1f}s  {note}")
    if errors:
        print("\n  ✗ JavaScript errors on the page:\n    " + "\n    ".join(errors[:5]))
    print(f"\n{'All checks passed.' if ok else 'Some checks FAILED.'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
