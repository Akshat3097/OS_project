"""
Screenshots of every screen, in the light and the dark theme, for checking the design and for the report.

    python -m eval.screenshots                 → eval/screens/<theme>_<screen>.png (language model off: quick)
    python -m eval.screenshots --only light

Starts its own server on a free port with a temporary database, like eval/browser_check.py.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from eval.browser_check import free_port

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "screens"
PASTED = ("Solve using SRTF: P1 arrives at 0 with burst 8, P2 at 1 with burst 4, P3 at 2 with burst 9, "
          "P4 at 3 with burst 5")

THEORY = "What is the convoy effect?"         # a checked answer, drawn as a paper
EXPLANATION = ("SRTF always runs the process with the shortest remaining time. It decides again whenever a process "
               "arrives or finishes, so a newcomer with a strictly shorter remaining time preempts the running one. "
               "On a tie the running process carries on.")


SAMPLE_NOTES = [
    {"title": "Formulas", "color": "butter", "pinned": True,
     "text": "- TAT = CT − AT\n- WT = TAT − BT\n- RT = first start − AT"},
    {"title": "Round Robin queue rule", "color": "sky", "source": "Saved from the chat",
     "text": "When a slice ends at the same moment a process arrives, the **new arrival joins the queue first**, then the preempted process."},
    {"title": "Banker's: Need", "color": "lilac",
     "text": "Need = Max − Allocation. Check Request ≤ Need first, then Request ≤ Available, then run the safety algorithm."},
    {"title": "SRTF tie", "color": "peach", "source": "Saved from the chat",
     "text": "On a tie the running process continues: preempt only when the newcomer is **strictly** shorter."},
    {"title": "Producer–consumer order", "color": "mint",
     "text": "`wait(empty)` before `wait(mutex)`. The other way round deadlocks when the buffer is full."},
]


def shoot(page, url: str, theme: str, out: Path) -> list[str]:
    done = []

    def open_view(view: str, toggle: bool = True, **keys):
        page.goto(url)
        values = {"sid": "Reviewer", "view": view, "theme": theme, **keys}
        page.evaluate("v => { for (const [k, x] of Object.entries(v)) localStorage.setItem(k, JSON.stringify(x)); }", values)
        page.reload()
        page.wait_for_selector(".app", timeout=30000)
        page.wait_for_timeout(800)
        box = page.locator("label.check", has_text="Use the language model").locator("input")
        if toggle and box.count() and box.is_checked():
            box.uncheck()

    def snap(name: str, full: bool = False):
        page.wait_for_timeout(500)
        path = out / f"{theme}_{name}.png"
        size = page.viewport_size
        if full:                                    # the app scrolls inside .scroll, so grow the window to fit it
            tall = page.evaluate("Math.max(0, ...[...document.querySelectorAll('.scroll')].map(e => e.scrollHeight))")
            page.set_viewport_size({"width": size["width"], "height": min(max(size["height"], tall + 40), 7000)})
            page.wait_for_timeout(400)
        page.screenshot(path=str(path), full_page=full)
        page.set_viewport_size(size)
        done.append(path.name)

    open_view("home")
    snap("0_home")
    open_view("chat")
    snap("1_chat_start")
    page.locator(".composer textarea").fill(PASTED)
    page.locator(".composer textarea").press("Enter")
    page.wait_for_selector("section[aria-label=Solution] .gantt__block", timeout=60000)
    page.wait_for_function("!document.querySelector('.caret') && !document.querySelector('.thinking')", timeout=60000)
    page.locator(".msg--tutor").last.scroll_into_view_if_needed()
    snap("2_chat_solution")
    page.locator(".composer textarea").fill(THEORY)
    page.locator(".composer textarea").press("Enter")
    page.wait_for_selector(".msg--tutor .paper--chat", timeout=60000)
    page.wait_for_function("!document.querySelector('.caret') && !document.querySelector('.thinking')", timeout=60000)
    page.locator(".paper--chat").last.scroll_into_view_if_needed()
    snap("2b_chat_theory")
    for text in ("Quiz me on round robin", "a"):                  # one question marked, the next one asked
        page.locator(".composer textarea").fill(text)
        page.locator(".composer textarea").press("Enter")
        page.wait_for_function("!document.querySelector('.caret') && !document.querySelector('.thinking')", timeout=60000)
        page.wait_for_selector(".qpaper--chat", timeout=60000)
    page.locator(".qpaper--chat").last.scroll_into_view_if_needed()
    snap("2c_chat_quiz")
    open_view("learn")
    snap("3_learn_lessons")
    open_view("learn", lesson="rr")
    page.wait_for_selector(".folder .paper--rule", timeout=15000)
    snap("3b_learn_understand", full=True)
    open_view("learn", lesson="srtf")
    page.locator(".stagebar__step").nth(1).click()
    page.wait_for_selector(".decision__choice", timeout=15000)
    for _ in range(3):
        page.get_by_role("button", name="Step →").click()
        page.wait_for_timeout(250)
    snap("4_learn_watch")
    page.locator(".stagebar__step").nth(2).click()                 # explain it back: the blackboard
    page.wait_for_selector(".chalkboard textarea", timeout=15000)
    page.locator(".chalkboard textarea").fill(EXPLANATION)
    snap("4b_learn_explain", full=True)
    page.locator(".stagebar__step").nth(3).click()                 # your question, on the question paper
    page.wait_for_selector(".question .qpaper", timeout=30000)
    if page.locator(".question .two-col").count():
        for col in range(2):
            page.locator(".question .two-col > div").nth(col).locator(".option").first.click()
    elif page.locator(".question .option, .question .qq__opt").count():
        page.locator(".question .option, .question .qq__opt").first.click()
    else:
        page.locator(".question .num-input").fill("3")
    page.get_by_role("button", name="Submit answer").click()
    page.wait_for_selector(".question .qq__why", timeout=30000)
    snap("4c_learn_question", full=True)
    page.locator(".stagebar__step").nth(4).click()                 # pointers: the lesson quiz
    page.locator("summary", has_text="Quick quiz on this lesson").click()
    page.wait_for_selector(".quiz-block .qpaper", timeout=15000)
    for k in range(page.locator(".quiz-block .qq").count()):
        page.locator(".quiz-block .qq").nth(k).locator(".qq__opt").nth(k % 2).click()
    page.get_by_role("button", name="Check answers").click()
    page.locator(".quiz-block").scroll_into_view_if_needed()
    snap("4d_learn_quiz", full=True)
    open_view("notes")
    page.evaluate("""async (notes) => {
        const have = await (await fetch('/api/notes?sid=Reviewer')).json();
        if (have.notes.length) return;
        for (const n of notes.slice().reverse()) {
            const made = await (await fetch('/api/notes', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                                          body: JSON.stringify({sid: 'Reviewer', ...n})})).json();
            if (n.pinned) await fetch('/api/notes/' + made.id, {method: 'PUT', headers: {'Content-Type': 'application/json'},
                                                               body: JSON.stringify({sid: 'Reviewer', pinned: true})});
        }
    }""", SAMPLE_NOTES)
    open_view("notes")
    page.wait_for_selector(".sticky", timeout=10000)
    snap("9_notes")
    open_view("labs")
    snap("5_labs")
    open_view("exam")
    snap("6_exam")
    open_view("progress")
    snap("7_progress")
    page.set_viewport_size({"width": 390, "height": 844})
    open_view("chat", toggle=False)                 # at phone width the switch is inside the closed drawer
    snap("8_phone_chat")
    open_view("learn", toggle=False, lesson="rr")
    page.wait_for_selector(".folder .paper--rule", timeout=15000)
    snap("8b_phone_lesson", full=True)
    open_view("learn", toggle=False, lesson="srtf")
    page.locator(".stagebar__step").nth(2).click()
    page.wait_for_selector(".chalkboard textarea", timeout=15000)
    page.locator(".chalkboard textarea").fill(EXPLANATION)
    snap("8c_phone_explain", full=True)
    page.set_viewport_size({"width": 1280, "height": 860})
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=["light", "dark"])
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    from playwright.sync_api import sync_playwright
    tmp = Path(tempfile.mkdtemp(prefix="os-tutor-shots-"))
    port = free_port()
    env = {**os.environ, "TUTOR_DB": str(tmp / "s.db"), "TUTOR_CHAT_DIR": str(tmp / "chats"),
           "TUTOR_NOTES_DIR": str(tmp / "notes")}
    server = subprocess.Popen([sys.executable, "-m", "server", "--port", str(port), "--no-browser"], cwd=ROOT, env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    OUT.mkdir(exist_ok=True)
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(url + "/api/speech", timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="msedge")
            page = browser.new_page(viewport={"width": 1280, "height": 860})
            for theme in ([a.only] if a.only else ["light", "dark"]):
                print(theme, ", ".join(shoot(page, url, theme, OUT)))
            browser.close()
    finally:
        server.terminate()
    print(f"\nScreenshots in {OUT}")


if __name__ == "__main__":
    main()
