"""
Prompt formats. The SAME format is used at runtime and in the QLoRA training data,
so fine-tuning teaches the model to follow these STRATEGY / FACTS blocks.
"""
from __future__ import annotations

import re

TUTOR_SYSTEM = (
    "You are a patient Operating Systems tutor for university students (CPU scheduling and process "
    "synchronization).\n"
    "Rules:\n"
    "1. Use only the numbers and facts given in FACTS. They were computed by a verified OS Engine. "
    "Never calculate new values yourself.\n"
    "2. Follow the STRATEGY and INSTRUCTION exactly. If REVEAL_ANSWER is no, do not state the correct answer, "
    "the correct process to run, or any correct value. Guide the student to find it.\n"
    "3. Match your explanation to STUDENT_LEVEL (beginner: simple words and one idea at a time; "
    "advanced: concise and technical).\n"
    "4. Speak directly to the student as 'you'. Be warm but brief: at most 120 words, no headings.\n"
    "5. COURSE NOTES are background you may use for definitions; prefer them over your own wording."
)

QA_SYSTEM = (
    "You are an Operating Systems tutor. Answer the student's question using the COURSE NOTES when they are "
    "relevant, and cite them like [1] or [2]. If the notes do not cover the question, say so briefly and answer "
    "from general OS knowledge. Do not invent numeric answers to scheduling problems; tell the student to use the "
    "Practice or Engine tab, which computes them exactly. Adapt to STUDENT_LEVEL. Keep answers under 200 words "
    "unless the student asks for more detail. Each note is labelled with its type. Prefer the student's own "
    "class notes (\"Teacher's notes\") and use their terms; if a textbook such as OSTEP defines something "
    "differently (for example, semaphore values that can go negative), mention both briefly."
)


def format_notes(chunks: list[dict]) -> str:
    if not chunks:
        return "(none)"
    out = []
    for i, c in enumerate(chunks, start=1):
        meta = c.get("meta", {})
        page = f" p.{meta['page']}" if meta.get("page") else ""
        out.append(f"[{i}] ({meta.get('type', 'Notes')}: {meta.get('source', '?')}{page} · "
                   f"{meta.get('subtopic', meta.get('topic', ''))}) {c['text']}")
    return "\n".join(out)


def strategy_prompt(strategy, notes: list[dict] | None = None) -> str:
    facts = "\n".join(f"- {f}" for f in strategy.facts)
    return (
        f"STRATEGY: {strategy.action}\n"
        f"REVEAL_ANSWER: {'yes' if strategy.reveal else 'no'}\n"
        f"STUDENT_LEVEL: {strategy.level}\n"
        f"INSTRUCTION: {strategy.instruction}\n"
        f"FACTS (verified by the OS Engine; use only these numbers):\n{facts}\n"
        f"COURSE NOTES:\n{format_notes(notes or [])}\n"
        f"Write the tutor's reply to the student now."
    )


def feedback_messages(strategy, notes: list[dict] | None = None) -> list[dict]:
    return [{"role": "system", "content": TUTOR_SYSTEM},
            {"role": "user", "content": strategy_prompt(strategy, notes)}]


def qa_messages(question: str, chunks: list[dict], level: str, history: list[dict] | None = None) -> list[dict]:
    msgs = [{"role": "system", "content": QA_SYSTEM}]
    for h in (history or [])[-6:]:
        msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content":
                 f"STUDENT_LEVEL: {level}\nCOURSE NOTES:\n{format_notes(chunks)}\n\nQUESTION: {question}"})
    return msgs


# ----------------------------------------------------------------------------- offline templates

def _second_person(text: str) -> str:
    text = text.replace("The student's", "Your").replace("the student's", "your")
    text = text.replace("The student", "You").replace("the student", "you")
    return text


CLOSINGS = {
    "START_HINT": "Start there: which processes have arrived, and which one does the rule pick?",
    "SOCRATIC_HINT": "Look at that moment again with the rule in mind. Which process should have the CPU, and why?",
    "TARGETED_HINT": "Apply the rule to exactly the processes listed above. Which one should get the CPU?",
    "REVEAL_STEP": "Now continue the rest on your own from that point and resubmit.",
    "ALGORITHM_REMINDER": "Using the correct rule, what should happen at the first point where your chart differs?",
    "FORMULA_REMINDER": "Can you recompute the marked values with this formula and resubmit?",
    "WORKED_EXAMPLE": "Now retry your original problem using exactly the same steps.",
    "CONFIRM_AND_EXTEND": "",
    "ASK_TO_COMPLETE": "Fill in the missing values and submit again.",
}
SKIP_PREFIXES = ("Problem:", "Detected error type:", "Detected error:")


def template_response(strategy) -> str:
    if strategy.action == "CONFIRM_AND_EXTEND":
        extra = [f for f in strategy.facts if f.startswith("For comparison")]
        q = ""
        if extra:
            q = " " + extra[0] + " Can you explain why?"
        return "Correct! Every part of your answer matches the OS Engine." + q
    lines = [_second_person(f) for f in strategy.facts if not f.startswith(SKIP_PREFIXES)]
    head = {"WORKED_EXAMPLE": "You have made this kind of mistake a few times, so let's look at a small worked example first.",
            "REVEAL_STEP": "Let's go through this step together."}.get(strategy.action, "Here's a hint.")
    body = "\n".join(("    - " + l.strip()) if l.startswith("  ") else f"- {l}" for l in lines)
    return f"{head}\n\n{body}\n\n{CLOSINGS.get(strategy.action, '')}".strip()


# ----------------------------------------------------------------------------- answer-leak guard

DECISIVE = re.compile(r"\b(should|must|correct|answer|next|is the one|gets the cpu|has to)\b", re.I)
NUM = re.compile(r"(?<![\w])(?<!\d\.)-?\d+(?:\.\d+)?(?![\w]|\.\d)")   # "6." at a sentence end counts


def _numbers(text: str) -> set[str]:
    return {m.group(0) for m in NUM.finditer(text)}


FIELD_WORDS = {"WT": r"waiting\s*time|\bWT\b|\bwaits?\b|\bwaited\b|\bwaiting\b",
               "TAT": r"turn\s*-?\s*around(\s*time)?|\bTAT\b",
               "CT": r"completion\s*time|\bCT\b|\bfinish(es|ed)?\b|\bcomplet(es|ed)\b|\bends?\b"}
OTHER_QUANTITY = re.compile(r"burst|\bBT\b|arriv|\bAT\b|priority|quantum|\bq\b|remaining|\bslot|\bstep", re.I)
PROCESS_NAME = re.compile(r"\bP\d+\b|(?<![\w.])[A-H](?=\s*[:(])")      # P2, or a worked-example label like "B:" / "B(AT=1"


def _ties(sentence: str, field: str, n: str, pid: str | None = None) -> bool:
    """Does the sentence state number n as the value of `field` ("WT for P2 is 4", "P2 waits 4", "4 units of waiting")?
    A different quantity named between them ("waiting time = TAT − burst 4") means the number belongs to that one,
    and a sentence about another process only ("B: WT = 6 − 4 = 2" in a worked example) is not about `pid`."""
    if pid and not re.search(rf"\b{re.escape(pid)}\b", sentence) and \
            any(m.group(0) != pid for m in PROCESS_NAME.finditer(sentence)):
        return False
    words = re.compile(FIELD_WORDS[field], re.I)
    for m in NUM.finditer(sentence):
        if m.group(0) != n:
            continue
        before = sentence[max(0, m.start() - 32):m.start()]
        after = sentence[m.end():m.end() + 24]
        hits = list(words.finditer(before))
        if hits and not OTHER_QUANTITY.search(before[hits[-1].end():]):
            return True
        first = words.search(after)
        if first and not OTHER_QUANTITY.search(after[:first.start()]):
            return True
    return False


def check_response(text: str, strategy) -> list[dict]:
    """Return issues: 'revealed_answer' (blocks the reply) or 'unverified_number' (warning only)."""
    issues: list[dict] = []
    fact_nums = _numbers(" ".join(strategy.facts))
    if not strategy.reveal:
        secrets = strategy.secrets or {}
        for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
            if sentence.strip().endswith("?"):
                continue
            for pid in secrets.get("pids", []):
                if re.search(rf"\b{re.escape(pid)}\b", sentence) and DECISIVE.search(sentence):
                    issues.append({"type": "revealed_answer", "detail": f"Names {pid} as the answer: “{sentence.strip()}”"})
        for n in secrets.get("numbers", []):
            if str(n) in _numbers(text) and str(n) not in fact_nums:
                issues.append({"type": "revealed_answer", "detail": f"Mentions the hidden correct value {n}."})
        # a hidden value that is ALSO a number in the problem data (e.g. WT 4 when a burst is 4) can't be judged by the
        # number alone: block it only where the reply ties it to the hidden quantity ("P2's waiting time is 4")
        for sv in secrets.get("values", []):
            n = str(sv["value"])
            if n not in fact_nums or n not in _numbers(text):
                continue
            for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
                if not sentence.strip().endswith("?") and _ties(sentence, sv["field"], n, sv["pid"]):
                    issues.append({"type": "revealed_answer",
                                   "detail": f"Gives the hidden {sv['field']} of {sv['pid']} ({n}): “{sentence.strip()}”"})
                    break
    extra = sorted(_numbers(text) - fact_nums, key=lambda x: float(x))
    extra = [n for n in extra if n not in {"0", "1", "2", "3"}]  # small counting words are common
    if extra:
        issues.append({"type": "unverified_number", "detail": f"Numbers not in the engine facts: {', '.join(extra)}"})
    return issues


# ----------------------------------------------------------------------------- Learn mode

LESSON_SYSTEM = (
    "You are a patient Operating Systems teacher for a university student who is learning this topic for the first "
    "time. Stay consistent with the LESSON NOTES (they define the rules and conventions of this course, e.g. lower "
    "priority number = higher priority). Never contradict them. Use plain words, short sentences and Markdown. "
    "If you use a numeric example, keep it tiny (at most 3 processes or steps) and double-check it against the rules."
)


def lesson_messages(lesson: dict, level: str, notes: list[dict], question: str | None = None,
                    history: list[dict] | None = None) -> list[dict]:
    body = (f"STUDENT_LEVEL: {level}\nLESSON: {lesson['title']}\nGOAL: {lesson['goal']}\n"
            f"LESSON NOTES:\n{lesson['concept'].strip()}\nSUMMARY: {'; '.join(lesson['summary'])}\n"
            f"COURSE NOTES:\n{format_notes(notes)}\n\n")
    if question is None:
        body += ("The student read the lesson notes but did not fully understand them. Explain the same idea in a "
                 "simpler way: start with a NEW real-life situation from a college student's everyday life in India "
                 "(for example a canteen queue, railway booking, cricket, a shared hostel washing machine, UPI "
                 "payments), not the one in the notes. Map each part of the situation to the OS idea, then give one "
                 "tiny example. At most 170 words. End with one short question that checks understanding (do not answer it).")
    else:
        body += (f"The student asks: {question}\nAnswer it in 3 to 6 sentences (at most 150 words), using the lesson "
                 "notes. If the question is vague or broad (\"why does this matter?\", \"what's the point?\"), read it as a "
                 "question about this lesson: say why its rule matters in practice (what it does to waiting time, "
                 "fairness or response time) and point to the lesson's own example. Use only numbers that appear in "
                 "the lesson notes: never make up a new numeric example. Do not just repeat the summary, and "
                 "do not add a reference line. If the question is outside this lesson, answer briefly and say which "
                 "lesson covers it. End with one short question that checks understanding (do not answer it).")
    msgs = [{"role": "system", "content": LESSON_SYSTEM}]
    for h in (history or [])[-4:]:
        msgs.append(h)
    msgs.append({"role": "user", "content": body})
    return msgs
