"""
Chat-first tutor: one conversation, with the OS Engine, the class notes, the lessons and the student model
as tools the tutor calls behind the scenes.

Every turn:
  1. Route: pick ONE action. Clear cases are matched by rules (an answer to the open problem, a pasted
     problem, "hint", "quiz me", ...). Anything else goes to the LLM, which returns JSON
     {"action", "topic", "difficulty"}. If the LLM is offline or its JSON is invalid, a keyword router decides.
  2. Run: code carries out the action. The engine solves or checks, the notes are searched and the
     student model is updated.
  3. Reply: the LLM writes the reply from those verified facts. Replies that contain problem numbers are
     guarded: hints must not leak the answer, and numbers must come from the engine. Without the LLM, a
     template reply is used. Cards (problem, Gantt chart, results, quiz, progress) carry every number,
     straight from the engine.

The conversation state is a plain dict (JSON-friendly), so the UI can keep it in its session.
"""
from __future__ import annotations

import difflib
import json
import random
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace

from engine import bankers, deadlock, generator, question_bank, scheduling
from engine.generator import BankersProblem, SchedulingProblem, problem_from_dict
from engine.scheduling import ALGORITHMS, Process
from qlora.chat_style import CHAT_SYSTEM
from tutor import chat_parse as cp
from tutor import faq, prompts, strategy as strategy_mod, teachback
from tutor.lessons import LESSONS, scheduling_steps
from tutor.student_model import SKILLS, TOPIC_NAMES
from tutor.tutor import Tutor

LESSON = {l["id"]: l for l in LESSONS}
ALGO_LESSON = {"FCFS": "fcfs", "SJF": "sjf", "SRTF": "srtf", "RR": "rr", "PRIORITY_NP": "priority",
               "PRIORITY_P": "priority", "BANKERS": "bankers", "SEMAPHORE": "semaphores"}
SHORT = {"basics": "scheduling basics", "fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF", "rr": "Round Robin",
         "priority": "priority scheduling", "critical_section": "the critical section", "semaphores": "semaphores",
         "deadlock": "deadlocks", "bankers": "the Banker's algorithm", "bounded_buffer": "producer–consumer",
         "readers_writers": "readers–writers", "dining": "dining philosophers"}
PRACTICE_NAME = {"FCFS": "an FCFS", "SJF": "an SJF", "SRTF": "an SRTF", "RR": "a Round Robin", "PRIORITY_NP": "a priority",
                 "PRIORITY_P": "a preemptive priority", "BANKERS": "a Banker's", "SEMAPHORE": "a semaphore"}
DIFF_WORDS = {1: "an easy", 2: "a medium", 3: "a hard"}

OTHER_TOPICS = [
    (r"banker|safe\s*(state|sequence)|need\s*matrix|resource[- ]request", "bankers", "BANKERS"),
    (r"deadlock|coffman|circular\s*wait|hold\s*and\s*wait|resource[- ]allocation\s*graph|\bRAG\b|wait[- ]for\s*graph", "deadlock", None),
    (r"producer|consumer|bounded[- ]buffer", "bounded_buffer", "SEMAPHORE"),
    (r"readers?[- ]writers?|\breadcount\b", "readers_writers", "SEMAPHORE"),
    (r"dining|philosophers?|chopsticks?", "dining", "SEMAPHORE"),
    (r"semaphore|\bwait\s*\(|\bsignal\s*\(|\bmutex\b|producer|consumer|bounded[- ]buffer|readers?[- ]writers?|"
     r"dining\s*philosophers|sleeping\s*barber|\bP\s*\(\s*\w+\s*\)|\bV\s*\(\s*\w+\s*\)", "semaphores", "SEMAPHORE"),
    (r"critical\s*section|race\s*condition|mutual\s*exclusion|peterson|bakery|test[- ]and[- ]set|compare[- ]and[- ]swap|"
     r"bounded\s*waiting|spin\s*lock|\block(s|ing)?\b|synchroni[sz]ation", "critical_section", None),
    (r"turn\s*-?around|waiting\s*time|completion\s*time|response\s*time|gantt|\btat\b|\bwt\b|scheduling\s*(basics|criteria)|"
     r"cpu\s*scheduling|throughput|utili[sz]ation|context\s*switch|scheduler|preempt", "basics", "FCFS"),
]

RX = {
    "hint": r"\b(hint|stuck|clue|nudge|help me start|how (do|should|can) i (start|begin)|where (do|should) i (start|begin)|first step)\b",
    "reveal": r"\b(show|give|tell|reveal)\b[^.?!]{0,20}\b(answers?|solution|working|steps)\b|\bi give up\b|\bsolve it( for me)?\b|\bjust tell me\b",
    "solve": r"^\s*solve\b|\bsolve (it|this|these|the following|for me)\b|\b(show|give)\b[^.?!]{0,15}\b(solution|answers?|steps)\b|"
             r"\bstep[- ]by[- ]step\b|\bwork it out\b|\bsolve\b.*\busing\b|"
             r"\b(find|calculate|compute|draw|determine)\b|\bgantt chart\b|\bsafe\s*\??\s*$|"
             r"\b(is|whether|check if)\s+(it|this|the system|the state|system)\s+(is\s+)?(in\s+a\s+)?safe\b|\bsafe or (not|unsafe)\b|"
             r"\bsafe sequence\b|\bgranted\b",
    "practice": r"(?<!\bin )(?<!\bin real )(?<!\bin actual )\bpracti[cs]e\b|\btest me\b|\b(give me|another|new|next|one more|harder|easier|tougher|different)\b[^.?!]{0,30}"
                r"\b(problem|question|one|exercise|numerical)\b|^\s*(harder|easier|another( one)?|next( one)?|one more)\W*$|"
                r"\b(something|one|a bit) (harder|easier|tougher)\b|\bpast[- ](paper|year)\b|\bpyqs?\b|\bexam question\b",
    "quiz": r"\bquiz\b|\bmcqs?\b|multiple[- ]choice",
    "progress": r"\bmy progress\b|\bhow am i doing\b|\bhow('?m| am) i (doing|progressing)\b|\bmy (mastery|level|stats|scores?|strengths?|weak\w*)\b|"
                r"\bwhat should i (study|learn|practi[cs]e|do|revise|work on) next\b|\bwhere am i weak\b|\bshow (me )?(my )?progress\b|^\s*progress\W*$",
    "teachback": r"\blet me (try to |try and )?explain\b|\bi('ll| will| want to| wanna) explain\b|\bexplain it back\b|\bteach[- ]?back\b|\bcan i explain\b",
    "gaps": r"\b(parts?|bits?|ideas?|things?|points?) i (missed|got wrong|left out)\b|\bwhat i missed\b",
    "differently": r"\b(differently|another way|in a different way|simpler|more simply|in simple (words|terms)|easier way|eli5|"
                   r"dumb it down|still (don'?t|do not) (get|understand)|different (example|analogy)|another (example|analogy))\b",
    "explain": r"\b(explain|teach me|teach|what is|what's|whats|what are|how does|how do|i don'?t (get|understand)|confused|tell me about|"
               r"introduce|learn|walk me through|basics of|overview|recap|revise|go over)\b",
    "ask": r"\b(difference|differ|vs\.?|versus|compare|comparison|better|worse|advantages?|disadvantages?|why|when (should|would|do|does|is)|"
           r"which (one|is|algorithm)|can (a|an|the|two)|does (a|an|the)|is it (true|possible)|what happens|example of|notes say)\b",
    "try_first": r"\b(i'?ll|let me|i will|i want to|i'?d like to)\s+(try|attempt|solve|do|work)\b|\btry (it )?(first|myself|on my own)\b",
    "greet": r"^\s*(hi+|hello|hey|yo|hola|namaste|good (morning|evening|afternoon|night)|thanks?|thank you|ty|ok(ay)?|cool|great|nice|bye|"
             r"who are you|what can you do|help)\b[\s!.?]*$",
    "stop": r"^\s*(stop|quit|exit|cancel|skip|never ?mind|nvm|enough)\b",
    "my_answer": r"\b(my answer|my solution|i got|i get|answer\s*:|i did|is (this|it|my answer) (right|correct)|check (this|my|their|it))\b|"
                 r"\bmy (avg|average|wt|tat|ct|gantt|order|sequence|schedule|chart|values?|waiting|turnaround|safe)\b|"
                 r"\b(student|students|they|he|she|someone|friend)\s+(said|says|got|gets|wrote|writes|calculated|calculates|put|thinks|claims)\b|"
                 r"\bi (put|wrote|calculated|think)\b|\bis (this|that|it) (ok|okay|fine|valid)\b",
}
RXC = {k: re.compile(v, re.I) for k, v in RX.items()}
# "what else can you teach me?": the list of topics, not an explanation of one picked by the model
MENU = re.compile(r"what (else )?(can|could|do|will) you (teach|do|help|cover|explain|offer)|what (else|other topics|topics|"
                  r"can i learn|all)\b.*\b(teach|learn|cover|topics?|study)|\b(list|menu|show)\b.{0,15}\b(topics|lessons)\b|"
                  r"\bsyllabus\b|\bwhat topics\b|\bsomething else\b|\bnot this one\b|\banother topic\b|\bother topics?\b", re.I)
# a message that asks for teaching (a question, or a request to explain or show something)
ASKS = re.compile(r"\?|\b(what|why|how|when|which|who|explain|teach|tell|show|mean|meaning|difference|diff|example|"
                  r"again|differently|understand|confus\w*|doubt|help|elaborate|describe|define|definition)\b", re.I)
# ideas inside a lesson: a question about one of these gets a focused, notes-based answer instead of the whole lesson
SUBCONCEPT = re.compile(
    r"peterson|bakery|test[- ]and[- ]set|compare[- ]and[- ]swap|swap instruction|spin\s*lock|\bmutex|"
    r"sleeping barber|safe\s*(state|sequence)|need matrix|"
    r"resource[- ]allocation graph|wait[- ]for graph|coffman|circular wait|hold and wait|convoy|starvation|aging|"
    r"context switch|throughput|utili[sz]ation|response time|race condition|bounded waiting|monitor|condition variable|"
    r"multilevel|mlfq|binary semaphore|counting semaphore|busy[- ]wait|deadlock (prevention|avoidance|detection|recovery)", re.I)

ASK_VIDEOS = [(re.compile(p, re.I), key) for p, key in [
    (r"peterson", "peterson"), (r"test[- ]and[- ]set|\bswap instruction|synchroni[sz]ation hardware", "tas"),
    (r"\bmonitors?\b|condition variable", "monitors"), (r"resource[- ]allocation graph|\brag\b", "rag"),
    (r"deadlock (prevention|avoidance)|handling deadlocks?", "prevention"), (r"deadlock recovery|recover", "recovery"),
    (r"deadlock detection|wait[- ]for graph", "detection"), (r"cpu[- ]bound|i/?o[- ]bound|burst cycle", "burst_cycle"),
    (r"multi-?level", "mlfq")]]

ROUTER_SYSTEM = """You route messages in an Operating Systems tutoring app. Choose ONE action for the student's latest message:
- explain: teach or re-explain a topic
- ask: a specific question (a definition, a comparison, why or when something happens, what the class notes say)
- practice: the student wants a problem to solve
- quiz: the student wants multiple-choice questions
- teachback: the student wants to explain a topic in their own words
- progress: the student asks how they are doing or what to study next
- chat: greetings, thanks, small talk, or anything outside operating systems
Topics: basics, fcfs, sjf, srtf, rr, priority, critical_section, semaphores, bounded_buffer, readers_writers, dining, deadlock, bankers, none.
Reply with JSON only, e.g. {"action": "practice", "topic": "rr", "difficulty": "hard"}.
Examples:
"throw a tricky one at me on round robin" -> {"action": "practice", "topic": "rr", "difficulty": "hard"}
"why can't SJF be used in real systems" -> {"action": "ask", "topic": "sjf", "difficulty": "any"}
"I keep mixing up the conditions for deadlock" -> {"action": "explain", "topic": "deadlock", "difficulty": "any"}
"what's up" -> {"action": "chat", "topic": "none", "difficulty": "any"}"""

CHAT_RULES = (
    "\n\nHow this app works: an OS Engine computes every schedule and number exactly, and the app shows its "
    "results as cards next to your reply. Use only the numbers given to you in FACTS or EXAMPLE; never invent "
    "a new numeric example or calculate new values yourself. Write in Markdown with short paragraphs, speak to "
    "the student as 'you', and keep replies focused.")
SCOPE = ("If the message is outside operating systems, answer in one short line and steer back to CPU "
         "scheduling or process synchronization.")


# ============================================================================ data
@dataclass
class Route:
    action: str
    by: str = "rules"
    topic: str | None = None          # lesson id
    practice: str | None = None       # FCFS ... SEMAPHORE, PAST_PAPERS, NOTES_EXAMPLES
    difficulty: int | None = None
    style: str = "normal"
    payload: dict = field(default_factory=dict)


@dataclass
class Reply:
    action: str
    text: str = ""
    stream: Iterator[str] | None = None
    cards: list[dict] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    fallback: str = ""

    def chunks(self) -> Iterator[str]:
        """Yield the reply text (streamed from the LLM when there is a stream). Sets .text when done."""
        if self.stream is None:
            if self.text:
                yield self.text
            return
        parts: list[str] = []
        try:
            for c in self.stream:
                if c:
                    parts.append(c)
                    yield c
        except Exception as e:  # network / model error mid-reply
            self.meta["error"] = str(e)
            if not parts:
                self.meta["source"] = "template (LLM failed)"
                parts = [self.fallback]
                yield self.fallback
        self.stream = None
        self.text = "".join(parts).strip() or self.fallback

    def final(self) -> str:
        for _ in self.chunks():
            pass
        return self.text


def new_state(sid: str = "demo") -> dict:
    return {"sid": sid, "messages": [], "problem": None, "pending_problem": None, "quiz": None,
            "teachback": None, "topic": None, "last_gaps": None}


OS_WORDS = re.compile(
    r"process|\bcpu\b|schedul|thread|semaphore|deadlock|mutex|\block|synchroni|critical section|banker|safe (state|sequence)|"
    r"gantt|quantum|burst|arrival|turn\s*-?around|waiting time|completion time|response time|preempt|\bfcfs\b|\bsjf\b|"
    r"\bsrtf\b|round robin|\brr\b|priority|starvation|aging|race condition|peterson|bakery|monitor|producer|consumer|"
    r"readers?|writers?|philosopher|chopstick|resource|allocation|operating system|\bos\b|kernel|context switch|"
    r"ready queue|interrupt|\bwait\b|\bsignal\b|\btat\b|\bwt\b|\bct\b|convoy|throughput|utili[sz]ation|dispatch|"
    r"multilevel|mlfq|spin|busy[- ]wait|test[- ]and[- ]set|atomic|interleav|concurren|multiprogramming|time[- ]shar|"
    r"\bjobs?\b|queue|\bp\d\b|\bv\(|\bp\(", re.I)
REFERS = re.compile(r"\b(it|this|that|these|those|again|above|same|the example|the problem|the question)\b", re.I)


def _in_scope(r: "Route", text: str) -> "Route":
    """A message with no OS words, no topic and no reference to the conversation is general chat: "explain recursion",
    "solve 2x + 3 = 11" (the LLM router sent it to practice), "I am stressed about my exams" (it chose progress)."""
    if OS_WORDS.search(text) or resolve_topic(text)[0] or REFERS.search(text):
        return r
    if r.action in ("ask", "explain"):
        return Route("chat", by=r.by)
    if r.action in ("practice", "progress", "quiz", "teachback") and r.by == "LLM" and not RXC[r.action].search(text):
        return Route("chat", by=r.by)
    return r


PAST_CLAIM = re.compile(r"\b(you were|you had|you asked|you said|your previous|last time|earlier you|you've been working|"
                        r"you('re| are)? (saying|subtracted|added|wrote|answered|calculated|forgot|used|missed|meant|got|did))\b|"
                        r"remember\?|\b(practice|practise|quiz|flashcards?|notes|homework) (section|tab|page|mode)\b", re.I)
# named topics a small-talk reply should not bring up on its own (the course scope words "CPU scheduling" and
# "process synchronization" are fine: replies offer them all the time)
NAMED_TOPICS = [(r"round\s*robin|\bRR\b", "rr"), (r"\bSRTF\b|shortest remaining", "srtf"), (r"\bSJF\b|shortest job", "sjf"),
                (r"\bFCFS\b|first come", "fcfs"), (r"priority scheduling", "priority"), (r"semaphore", "semaphores"),
                (r"deadlock", "deadlock"), (r"banker", "bankers"), (r"critical section|race condition", "critical_section"),
                (r"producer|consumer|bounded buffer", "bounded_buffer"), (r"readers?[- ]writers?", "readers_writers"),
                (r"philosopher", "dining"), (r"gantt|turnaround|waiting time|completion time", "basics")]
IDENTITY = ("You are OS Tutor, a final-year project by Akshat and Mohammed Falah Ur Rahman Danish for the BCSE303 "
            "Operating Systems course at VIT. You run on Llama 3.1 8B, fine-tuned with QLoRA on the course material, "
            "locally on this laptop with Ollama; every number you give comes from a deterministic OS Engine, not from "
            "the language model. You do not know about news, weather or events. In this app the student can also use "
            "Learn (13 short lessons), Labs (try their own numbers), Exam (a timed mock CAT paper, marked automatically) "
            "and Progress (mastery per skill).")


def _invents_context(reply: str, text: str, state: dict) -> bool:
    """A small-talk reply that claims something about what the student did, brings up a topic that is neither the
    current one nor in the student's message, or contains numbers nobody gave it ("WT = 5 − 5 = 0")."""
    if PAST_CLAIM.search(reply):
        return True
    topic_now = state.get("topic")
    for pattern, lid in NAMED_TOPICS:
        if lid != topic_now and re.search(pattern, reply, re.I) and not re.search(pattern, text, re.I):
            return True
    allowed = set(re.findall(r"\d+", text + " " + IDENTITY))
    return any(n not in allowed for n in re.findall(r"\d+", reply))


# The model reading its own instructions back (found 24 Oct with eval/teacher_probe.py: "LESSON ANALOGY: …", "The OS
# Engine computes every schedule…"), and lines of the hint template the round-1 fine-tune learned ("Here's a hint." to
# open an explanation, "The full correct answer is below…"). The reply is cut at the sentence where one starts.
LEAK = re.compile(r"^[ \t>*_#-]*(LESSON NOTES|LESSON ANALOGY|KEY POINTS|CLASS NOTES|COURSE NOTES|STUDENT_LEVEL|STUDENT|"
                  r"TOPIC|EXAMPLE|FACTS|QUESTION|ABOUT YOU|CONTEXT)\b\s*[(:]|(?i:OS Engine computes every|never invent a "
                  r"new numeric|speak to the student as|use only (the )?numbers (given|from)|full correct answer is below|"
                  r"retry on your own|delete what you have)", re.M)
MID_LESSON = re.compile(r"^\s*([-*|]|\d+\.)\s")
HINT_OPENER = re.compile(r"^\s*(\*\*)?here(?:'s| is) a hint[.:!]?(\*\*)?\s*", re.I)
SENTENCE_END = re.compile(r"[.!?:](?=\s)|\n")


def clean_reply(text: str) -> str:
    """Drop a "Here's a hint." opener and everything from the first leaked instruction on."""
    text = HINT_OPENER.sub("", text, count=1)
    # links the model makes up ("(pastebin.com link hidden)", http://...): the tutor has no sources on the web
    text = re.sub(r"(?im)^.*(https?://|www\.|\b[\w-]+\.(com|org|net|io|in)\b|link hidden).*$\n?", "", text)
    text = re.sub(r"\n\s*(Try again|Retry)[.!]?\s*$", "", text.rstrip())       # the hint template's closing line
    text = re.sub(r"(?m)^\*\*(?=[^\n]*\*\*[^\n]*\*\*[^\n]*\*\*$)([^\n]*)\*\*$", r"\1", text)   # **a **b** c** → a **b** c
    m = LEAK.search(text)
    if m:
        ends = [e.end() for e in SENTENCE_END.finditer(text, 0, m.start())]
        text = text[:ends[-1] if ends else 0]
    return text.strip()


def substantial(text: str) -> bool:
    return len(re.findall(r"[A-Za-z]{2,}", text)) >= 12


def clean_stream(stream: Iterator[str], fallback: str, bad_start: re.Pattern | None = None) -> Iterator[str]:
    """clean_reply for a streamed reply: text is passed on a sentence at a time (so a leaked label is caught before it
    is shown), and only once there is enough of it; a reply with nothing left after cleaning becomes the fallback, and
    so does one whose beginning matches bad_start."""
    raw, shown = "", ""
    for piece in stream:
        raw += piece
        ends = [e.end() for e in SENTENCE_END.finditer(raw)]
        if not ends:
            continue
        upto = raw[:ends[-1]]
        clean = clean_reply(upto)
        if LEAK.search(HINT_OPENER.sub("", upto, count=1)):
            raw = upto
            break                                   # the rest is instructions read back: stop listening
        if substantial(clean) and len(clean) > len(shown):
            if not shown and bad_start is not None and bad_start.search(clean):
                yield fallback
                return
            yield clean[len(shown):]
            shown = clean
    clean = clean_reply(raw)
    if not shown and not substantial(clean):
        yield fallback
    elif len(clean) > len(shown):
        yield clean[len(shown):]


# course words a typo is matched against ("dinning philosphers", "explian rr", "semaphor"); words close to one of
# these (similarity ≥ 0.85, five letters or more) are corrected before routing
VOCAB = sorted(set("""explain explained example examples scheduling scheduler schedule process processes processor thread
threads semaphore semaphores deadlock deadlocks philosopher philosophers dining chopstick chopsticks producer consumer
reader readers writer writers critical section mutex mutual exclusion starvation preemptive preemption priority quantum
round robin banker bankers algorithm algorithms synchronization synchronisation condition race waiting turnaround
completion arrival burst difference between convoy effect safe unsafe sequence resource resources allocation request
problem question answer""".split()))
SHORTHAND = {"wat": "what", "wht": "what", "whta": "what", "waht": "what", "wats": "what is", "whats": "what is",
             "pls": "please", "plz": "please", "diff": "difference", "b/w": "between", "btw": "between", "expl": "explain"}


def fix_typos(text: str) -> str:
    def one(m: re.Match) -> str:
        w = m.group(0)
        low = w.lower()
        if low in SHORTHAND:
            return SHORTHAND[low]
        if len(low) < 5 or low in VOCAB:
            return w
        close = difflib.get_close_matches(low, VOCAB, n=1, cutoff=0.85)
        if not close or close[0] in low or (close[0].startswith(low) and close[0][len(low):] in ("s", "r", "d", "er", "ed", "es", "ing")):
            return w                           # "write" is a word, not a typo of "writer"
        return close[0]
    return re.sub(r"[A-Za-z][A-Za-z/']*", one, text)


QUANTITY = {"TAT": r"\btat\b|turn\s*-?\s*around(?:\s*time)?", "WT": r"\bwt\b|waiting(?:\s*time)?",
            "BT": r"\bbt\b|burst(?:\s*time)?", "CT": r"\bct\b|completion(?:\s*time)?", "AT": r"\bat\b(?=\s*(?:=|is|of|:)\s*\d)|arrival(?:\s*time)?"}


def formula_values(t: str) -> dict | None:
    """'if TAT is 8 and BT is 5 then WT is 13 right': the quantities given for ONE process, and a claimed value."""
    if re.search(r"\bP\s?\d", t, re.I) or len(re.findall(r"\d+", t)) > 4:
        return None
    vals = {}
    for k, pat in QUANTITY.items():
        m = re.search(rf"(?:{pat})\s*(?:is|=|:|of)?\s*(\d+(?:\.\d+)?)", t, re.I)
        if m:
            vals[k] = float(m.group(1))
    if len(vals) < 2:
        return None
    claim = re.search(r"\b(?:then|so)\b[^.?]*?\b(tat|wt|bt|ct|turn\s*-?around|waiting|burst|completion)\w*(?:\s*time)?\s*(?:is|=)\s*(\d+(?:\.\d+)?)", t, re.I)
    claimed = None
    if claim:
        word = claim.group(1).lower()
        key = next(k for k, pat in QUANTITY.items() if re.match(pat, word, re.I))
        claimed = (key, float(claim.group(2)))
        vals.pop(key, None)
    return {"values": vals, "claim": claimed}


def semaphore_claim(t: str) -> dict | None:
    """'semaphore S=1, P1 calls wait then P2 calls wait, ... both blocked?': the ops, in order, to trace."""
    init = dict((m.group(1), int(m.group(2))) for m in re.finditer(r"\b([A-Za-z]\w{0,7})\s*=\s*(-?\d+)", t)
                if m.group(1).lower() not in ("q", "at", "bt", "tat", "wt", "ct", "t"))
    if not init or not re.search(r"\bsemaphore|\bwait\b|\bsignal\b", t, re.I):
        return None
    sems = list(init)
    ops = []
    for m in re.finditer(r"\b(P\s?\d+)\b[^.,;]*?\b(wait|signal|down|up|P|V)\b(?:\s*\(\s*(\w+)\s*\))?", t):
        op = {"down": "wait", "p": "wait", "up": "signal", "v": "signal"}.get(m.group(2).lower(), m.group(2).lower())
        ops.append({"pid": m.group(1).replace(" ", "").upper(), "op": op, "sem": m.group(3) if m.group(3) in init else sems[0]})
    return {"initial": init, "ops": ops} if len(ops) >= 2 else None


CODE_REQUEST = re.compile(r"\b(write|give|show|send|implement|provide)\b[^.?!]{0,40}\b(code|program|implementation|script|function)\b|"
                          r"\bsemaphore\.h\b|\bpthreads?\b", re.I)
# requests from other subjects ("solve this knapsack problem", "explain TCP 3 way handshake"): polite template, no model
OFF_TOPIC = re.compile(r"\b(knapsack|differential|integral|derivative|calculus|equation|tcp|udp|http|dns|sql|leetcode|"
                       r"bubble sort|merge sort|quick ?sort|linked list|binary tree|vtop|scrap(e|ing)|python|javascript|"
                       r"html|css|weather|movie|cricket score)\b", re.I)


EXAMPLE_ASK = re.compile(r"^\W*((can|could) you |please |pls )?(give|show)( me)?( an?| another| one more| some)?"
                         r"( simple| small| quick| easy| short)?( [\w'–-]+){0,3} examples?\b|"
                         r"^\W*(an? |another )?examples?( please| pls)?\W*$|^\W*for example\W*$", re.I)
BANKERS_REQUEST = re.compile(r"\bP\s?(\d+)\b[^.?\n\d]{0,30}?\b(requests?|asks?|wants?|needs?|requires?)\b(?: for)?\s*"
                             r"[([]?\s*((?:\d+\s*[, ]\s*)*\d+)\s*[)\]]?", re.I)


def resolve_topic(text: str) -> tuple[str | None, str | None]:
    """(lesson id, practice topic) named in the text."""
    algos = cp.detect_algorithms(text)
    if algos:
        return ALGO_LESSON[algos[0]], algos[0]
    for pat, lid, prac in OTHER_TOPICS:
        if re.search(pat, text, re.I):
            return lid, prac
    return None, None


def difficulty_in(text: str) -> int | None:
    low = text.lower()
    if re.search(r"\b(hard|tricky|difficult|tough|challenging|exam[- ]level)\b", low):
        return 3
    if re.search(r"\b(medium|moderate|intermediate)\b", low):
        return 2
    if re.search(r"\b(easy|simple|basic|beginner)\b", low):
        return 1
    return None


def problem_topic(problem) -> str:
    kind = getattr(problem, "kind", "scheduling")
    return problem.algorithm if kind in ("scheduling", "advanced") else kind.upper()


def answer_help(kind: str) -> str:
    if kind == "bankers":
        return "Reply with whether it is safe and a safe sequence, like `safe: P1, P3, P4, P0, P2` (or just `unsafe`)."
    if kind == "semaphore":
        return "Reply with each semaphore's final value and the blocked processes, like `S = -1, blocked: P3`."
    if kind == "advanced":
        return "Reply with CT, TAT and WT for each process, like `P1: CT 21, TAT 21, WT 8`."
    return ("Type your answer here: the Gantt chart like `P1 0-3, P2 3-5, …` and the times like "
            "`P1: CT 9, TAT 9, WT 4` (all at once or one part at a time), or use the answer sheet under the problem.")


# ============================================================================ agent
class ChatAgent:
    def __init__(self, students, kb, client=None, use_llm: bool = True):
        self.students = students
        self.kb = kb
        self.client = client if use_llm else None
        self.online = self.client is not None and self.client.available()
        self.tutor = Tutor(students, kb, self.client if self.online else None)
        self.raise_errors = False          # tests set this to see exceptions instead of the apology reply

    @property
    def model_label(self) -> str:
        return f"LLM ({self.client.model})" if self.client else "template"

    # ------------------------------------------------------------------ public API
    def respond(self, state: dict, text: str, structured: dict | None = None) -> Reply:
        """Handle one student message. Consume reply.chunks() (or .final()), then call commit()."""
        text = (text or "").strip()
        if not text and structured is None:
            return Reply("empty", text="I'm listening: ask a question, paste a problem, or pick a suggestion.",
                         suggestions=["Explain Round Robin", "Give me a problem"], meta={"source": "template"})
        state["messages"].append({"role": "user", "content": text})
        text = fix_typos(text)                 # the saved message keeps the student's own spelling
        route = self.route(state, text, structured)
        if state.get("quiz") and route.action not in ("quiz_answer", "quiz_stop", "quiz"):
            state["quiz"] = None            # the student moved on: drop the unfinished quiz
        if state.get("teachback") and route.action not in ("teachback_assess", "teachback_stop"):
            state["teachback"] = None
        handler = getattr(self, f"_do_{route.action}", self._do_ask)
        try:
            reply = handler(state, text, route)
        except Exception as e:  # never leave the student without an answer
            if self.raise_errors:
                raise
            reply = Reply("error", text="Sorry, something went wrong on my side while handling that. "
                                        "Could you rephrase it, or try another request?",
                          meta={"error": f"{type(e).__name__}: {e}"})
        reply.meta.setdefault("action", route.action)
        reply.meta.setdefault("routed_by", route.by)
        reply.meta.setdefault("kind", reply.action)        # what was actually sent (the page styles theory as paper)
        if reply.meta.get("topic") in LESSON:
            reply.meta.setdefault("topic_name", LESSON[reply.meta["topic"]]["title"])
        if reply.stream is None and "source" not in reply.meta:
            reply.meta["source"] = "template"
        return reply

    def commit(self, state: dict, reply: Reply) -> None:
        if reply.stream is not None:
            reply.final()
        state["messages"].append({"role": "assistant", "content": reply.text, "cards": reply.cards,
                                  "suggestions": reply.suggestions, "meta": reply.meta})

    def welcome(self, state: dict) -> dict:
        name = state.get("sid") or "there"
        hist = self.students.history(state["sid"], limit=1)
        rec = self.students.recommend_next(state["sid"])
        if hist:
            text = (f"Welcome back, **{name}**! Pick up where you left off, or ask me anything about CPU scheduling "
                    f"and process synchronization. Based on your progress, I'd suggest "
                    f"**{TOPIC_NAMES.get(rec['topic'], rec['topic'])}** next.")
        else:
            text = (f"Hi **{name}**, I'm your OS tutor for **CPU scheduling** and **process synchronization**. "
                    "You can ask me to explain a topic, paste a question from a paper (I'll solve it or check "
                    "your answer step by step), practise problems at your level, take a quick quiz, or explain "
                    "a topic back to me.")
        return {"role": "assistant", "content": text, "cards": [], "meta": {"action": "welcome", "source": "template"},
                "suggestions": ["Explain Round Robin", "Give me a problem", "Quiz me on deadlocks", "How am I doing?"]}

    # ------------------------------------------------------------------ routing
    def route(self, state: dict, text: str, structured: dict | None = None) -> Route:
        if structured is not None:
            return Route("check", payload={"answer": structured, "structured": True})
        r = self._rules(state, text)
        if r is not None:
            return r
        if OFF_TOPIC.search(text) and not OS_WORDS.search(text):
            return Route("chat")
        if self.online:
            r = self._llm_route(state, text)
            if r is not None:
                return _in_scope(r, text)
        return _in_scope(self._keyword_route(state, text), text)

    def _rules(self, state: dict, text: str) -> Route | None:
        t = cp.norm(text)
        low = t.lower()
        prob_state = state.get("problem")
        problem = problem_from_dict(prob_state["problem"]) if prob_state else None

        # a quiz in progress
        if state.get("quiz"):
            if RXC["stop"].search(low):
                return Route("quiz_stop")
            choice = self._quiz_choice(state, t)
            if choice is not None:
                return Route("quiz_answer", payload={"choice": choice})
        # waiting for the student's explanation (teach-back)
        if state.get("teachback"):
            if RXC["stop"].search(low):
                return Route("teachback_stop")
            if len(t.split()) >= 5 and not any(RXC[k].search(low) for k in ("quiz", "progress", "practice", "hint")):
                return Route("teachback_assess")
        # the algorithm for a pasted problem that had none
        if state.get("pending_problem"):
            algos = cp.detect_algorithms(t)
            if algos:
                pend = state["pending_problem"]
                return Route("solve" if pend.get("solve") else "offer",
                             payload={"processes": pend["processes"], "algorithm": algos[0], "others": algos[1:],
                                      "quantum": cp.detect_quantum(t) or pend.get("quantum")})
        # an answer to the open problem, or a new pasted problem (maybe with the student's own answer)
        pasted = self._pasted(t)
        if problem is not None:
            ans = self._parse_answer(problem, t)
            same = pasted is not None and problem.kind == "scheduling" and _same_processes(pasted.payload, problem)
            if ans is not None and (pasted is None or same):
                return Route("check", payload={"answer": ans})
        busy = any(RXC[k].search(low) for k in ("quiz", "practice", "teachback", "progress")) or \
            (problem is not None and any(RXC[k].search(low) for k in ("hint", "reveal", "try_first")))
        if not busy:
            known = faq.lookup(t)
            if not known and state.get("topic") in LESSON and len(t.split()) <= 14:
                near = faq.lookup(f"{t} ({LESSON[state['topic']]['title']})")
                known = near if near and near["lesson"] == state["topic"] else None
            if known:
                return Route("faq", topic=known["lesson"], payload=known)
        if pasted is not None:
            return pasted
        if problem is not None:
            algos = cp.detect_algorithms(t)
            if (problem.kind == "scheduling" and algos and algos[0] != problem.algorithm
                    and re.search(r"\b(with|using|use|in|for|what if|now|try|solve)\b", low)
                    and not RXC["explain"].search(low) and not RXC["practice"].search(low)):
                return Route("solve", payload={"processes": [vars(p) for p in problem.processes], "algorithm": algos[0],
                                               "others": algos[1:], "quantum": cp.detect_quantum(t) or problem.quantum or 2})
            if RXC["hint"].search(low):
                return Route("hint")
            if RXC["reveal"].search(low):
                return Route("reveal")
            if RXC["try_first"].search(low):
                return Route("try_first")
            if problem.kind == "bankers":
                m = BANKERS_REQUEST.search(t)
                if m and int(m.group(1)) < len(problem.allocation):
                    req = [int(x) for x in re.findall(r"\d+", m.group(3))]
                    if len(req) == len(problem.available):
                        return Route("bankers_request", topic="bankers", payload={"pid": int(m.group(1)), "request": req})
            if re.search(r"\b(why|how come|how did|when does|when did)\b", low) and (
                    re.search(r"\bP\s?\d+\b|\bt\s*=\s*\d+|\bat\s*(time\s*)?\d+", t, re.I)):
                return Route("why")
        elif RXC["hint"].search(low) or RXC["reveal"].search(low):
            return Route("no_problem")

        lid, prac = resolve_topic(t)
        if EXAMPLE_ASK.search(low) and (lid or state.get("topic") in LESSON):
            return Route("example", topic=lid or state["topic"])
        if problem is None and re.search(r"\b(safe )?seq\w*\b", low) and re.search(r"\bsafe|\bbanker", low) and \
                re.search(r"\bP\s?\d", t) and not cp.parse_bankers_problem(t) and \
                re.search(r"\b(right|correct|ok|okay|valid|really|is it|is that)\b", low):
            return Route("need_matrices", topic="bankers")
        if problem is None and (f := formula_values(t)):
            return Route("formula", topic="basics", payload=f)
        if problem is None and (sem := semaphore_claim(t)):
            return Route("sem_trace", topic="semaphores", payload=sem)
        if CODE_REQUEST.search(t) and (lid or state.get("topic") in LESSON) and OS_WORDS.search(t):
            return Route("code", topic=lid or state["topic"])
        if MENU.search(low) and not lid:
            return Route("menu")
        if RXC["progress"].search(low):
            return Route("progress")
        if RXC["quiz"].search(low):
            return Route("quiz", topic=lid)
        if RXC["teachback"].search(low):
            return Route("teachback", topic=lid)
        if RXC["practice"].search(low):
            if re.search(r"past[- ](paper|year)|\bpyqs?\b|exam question", low):
                prac = "PAST_PAPERS"
            elif re.search(r"(class|lecture)[- ]?notes|from (the|my) notes", low):
                prac = "NOTES_EXAMPLES"
            d = difficulty_in(t)
            if problem is not None and re.search(r"\b(harder|tougher)\b", low):
                d = min(3, problem.difficulty + 1)
            elif problem is not None and re.search(r"\beasier\b", low):
                d = max(1, problem.difficulty - 1)
            if prac is None and problem is not None and re.search(r"\b(another|next|one more|harder|easier|tougher|similar)\b", low):
                prac = problem_topic(problem) if problem.kind != "advanced" else "PAST_PAPERS"
            if prac is None and lid in ("deadlock", "critical_section"):
                prac = "BANKERS" if lid == "deadlock" else "SEMAPHORE"
            if prac is None and lid is None and problem is None and state.get("topic") in LESSON:
                lid = state["topic"]
                prac = LESSON[lid].get("practice_topic") or {"deadlock": "BANKERS", "critical_section": "SEMAPHORE"}.get(lid)
            return Route("practice", topic=lid, practice=prac, difficulty=d)
        if RXC["gaps"].search(low) and state.get("last_gaps"):
            return Route("explain", topic=state.get("topic"), style="gaps")
        if RXC["differently"].search(low) and (lid or state.get("topic")):
            return Route("explain", topic=lid or state.get("topic"), style="simpler")
        if lid and SUBCONCEPT.search(low):
            return Route("ask", topic=lid)          # a specific idea (Peterson's, safe state, convoy effect...)
        if lid and RXC["explain"].search(low) and not RXC["ask"].search(low):
            return Route("explain", topic=lid)
        if lid and RXC["ask"].search(low):
            return Route("ask", topic=lid)
        if RXC["greet"].search(low):
            return Route("chat")
        return None

    def _pasted(self, t: str) -> Route | None:
        low = t.lower()
        split = RXC["my_answer"].search(t)
        prob_text, ans_text = (t[:split.start()], t[split.start():]) if split else (t, "")
        if split and not cp.parse_scheduling_problem(prob_text) and cp.parse_scheduling_problem(t):
            prob_text = t                       # the answer marker came before the data ("my avg WT ... P1 0 5")
        bankers_like = re.search(r"\balloc", low) and re.search(r"\bmax|\bclaim", low)
        sp = None if bankers_like else cp.parse_scheduling_problem(prob_text)
        if sp is not None:
            gantt_like = len(cp.parse_gantt_text(prob_text)) >= 2 and not re.search(r"\b(arrival|burst|AT|BT)\b", prob_text)
            if gantt_like:
                sp = None
        if sp is not None:
            markers = re.search(r"\b(arrival|burst|AT|BT|process(es)?|cpu|schedul\w*|quantum)\b", prob_text, re.I)
            if not sp["algorithms"] and not markers:
                sp = None
        if sp is not None:
            payload = {"processes": [vars(p) for p in sp["processes"]], "quantum": sp["quantum"],
                       "algorithm": sp["algorithms"][0] if sp["algorithms"] else None, "others": sp["algorithms"][1:]}
            pids = [x["pid"] for x in payload["processes"]]
            if ans_text and not cp.parse_scheduling_answer(ans_text, pids) and cp.parse_scheduling_answer(t, pids):
                ans_text = t                    # the answer started before the marker ("order P1 P3 ... is this right")
            elif not ans_text and re.search(r"\?|\bright\b|\bcorrect\b", t) and cp.parse_scheduling_answer(t, pids):
                ans_text = t                    # "TAT for P2 is 6?"
            if ans_text and cp.parse_scheduling_answer(ans_text, pids):
                payload["answer_text"] = ans_text
                return Route("pasted_check", payload=payload)
            rule = faq.lookup(re.sub(r"\d+", " ", t)) if re.search(r"\?|\b(right|correct|which|should|do we|does)\b", t) else None
            if rule:
                payload["note"] = rule["text"]
            asks = bool(RXC["solve"].search(low)) or bool(rule) or bool(re.search(r"\b(right|correct)\b", t))
            if not sp["algorithms"]:
                payload["solve"] = asks
                return Route("need_algorithm", payload=payload)
            return Route("solve" if asks else "offer", payload=payload)
        dp = cp.parse_detection_problem(prob_text)
        if dp is not None:
            return Route("detect", topic="deadlock", payload={"detection": dp})
        bp = cp.parse_bankers_problem(prob_text) or (cp.parse_bankers_problem(t) if split else None)
        if bp is not None:
            payload = {"bankers": bp}
            req = BANKERS_REQUEST.search(t)
            if req and not ans_text:
                pid, values = int(req.group(1)), [int(x) for x in re.findall(r"\d+", req.group(3))]
                if len(values) == len(bp["available"]) and 0 <= pid - bp.get("first_pid", 0) < len(bp["allocation"]):
                    return Route("bankers_request", topic="bankers", payload={**payload, "pid": pid, "request": values})
            if ans_text:
                payload["answer_text"] = ans_text
                return Route("pasted_check", payload=payload)
            return Route("solve" if RXC["solve"].search(low) else "offer", payload=payload)
        return None

    def _llm_route(self, state: dict, text: str) -> Route | None:
        msgs = [{"role": "system", "content": ROUTER_SYSTEM},
                {"role": "user", "content": f"Topic so far: {state.get('topic') or 'none'}\nStudent: {text}"}]
        try:
            raw = self.client.chat(msgs, options={"temperature": 0, "num_predict": 60}, fmt="json")
            d = json.loads(raw)
        except Exception:
            return None
        action = str(d.get("action", "")).lower().strip()
        if action not in ("explain", "ask", "practice", "quiz", "teachback", "progress", "chat"):
            return None
        topic = str(d.get("topic", "none")).lower().strip()
        topic = topic if topic in LESSON else None
        diff = {"easy": 1, "medium": 2, "hard": 3}.get(str(d.get("difficulty", "")).lower())
        prac = LESSON[topic].get("practice_topic") if topic else None
        if topic == "basics":
            prac = "FCFS"
        elif topic in ("deadlock", "critical_section"):
            prac = "BANKERS" if topic == "deadlock" else "SEMAPHORE"
        if action == "explain" and topic is None:
            action = "ask"
        # "ni", "ok", "i see a b c no p1 here": with "Topic so far: basics" the router tends to answer explain/ask on
        # that topic. Only teach when the message asks something or names a topic; otherwise it is small talk.
        if action in ("explain", "ask") and not resolve_topic(text)[0] and not ASKS.search(text):
            return Route("chat", by="LLM")
        return Route(action, by="LLM", topic=topic, practice=prac, difficulty=diff)

    def _keyword_route(self, state: dict, text: str) -> Route:
        lid, prac = resolve_topic(text)
        low = text.lower()
        if lid and RXC["explain"].search(low) and not RXC["ask"].search(low):
            return Route("explain", by="keywords", topic=lid)
        return Route("ask", by="keywords", topic=lid)

    # ------------------------------------------------------------------ LLM helpers
    def _history(self, state: dict, n: int = 6) -> list[dict]:
        msgs = [m for m in state["messages"][:-1] if m.get("content")]
        return [{"role": m["role"], "content": m["content"][:1500]} for m in msgs[-n:]]

    def _stream_reply(self, action: str, messages: list[dict], fallback: str, cards=None, suggestions=None,
                      meta=None) -> Reply:
        meta = dict(meta or {})
        if self.online:
            meta["source"] = self.model_label
            bad = MID_LESSON if action == "explain" else None
            return Reply(action, stream=clean_stream(self.client.chat_stream(messages), fallback, bad), fallback=fallback,
                         cards=cards or [],
                         suggestions=suggestions or [], meta=meta)
        meta["source"] = "template (LLM offline)" if self.client is None or not self.online else "template"
        return Reply(action, text=fallback, cards=cards or [], suggestions=suggestions or [], meta=meta)

    def _guarded_text(self, messages: list[dict], facts: list[str], fallback: str, meta: dict) -> str:
        """Non-streamed reply whose numbers are checked against the engine facts."""
        if not self.online:
            meta["source"] = "template (LLM offline)"
            return fallback
        try:
            t0 = time.time()
            text = self.client.chat(messages).strip()
            meta["latency"] = round(time.time() - t0, 1)
        except Exception as e:
            meta["error"] = str(e)
            meta["source"] = "template (LLM failed)"
            return fallback
        text = clean_reply(text)
        if not substantial(text):               # e.g. only "Here's a hint. - t = 0: P1 arrives." was left
            meta["source"] = "template (LLM reply too short)"
            return fallback
        dummy = SimpleNamespace(facts=facts, reveal=True, secrets={})
        issues = prompts.check_response(text, dummy)
        meta["issues"] = issues
        if any(i["type"] == "unverified_number" for i in issues):
            meta["source"] = "template (LLM reply used numbers the engine did not give)"
            meta["blocked_text"] = text
            return fallback
        meta["source"] = self.model_label
        return text

    def _level(self, state: dict, lesson_id: str | None = None, topic: str | None = None) -> str:
        sid = state["sid"]
        topic = topic or (LESSON[lesson_id].get("practice_topic") if lesson_id else None)
        if topic in ("FCFS", "SJF", "SRTF", "RR", "PRIORITY_NP", "PRIORITY_P", "BANKERS", "SEMAPHORE"):
            return self.students.level(sid, topic)
        return self.students.overall_level(sid)

    def _default_lesson(self, state: dict) -> str:
        if state.get("topic"):
            return state["topic"]
        prog = self.students.lesson_progress(state["sid"])
        for l in LESSONS:
            if not prog.get(l["id"], {}).get("completed"):
                return l["id"]
        return "basics"

    # ------------------------------------------------------------------ actions: teaching
    def _do_explain(self, state: dict, text: str, route: Route) -> Reply:
        lid = route.topic or self._default_lesson(state)
        lesson = LESSON[lid]
        state["topic"] = lid
        level = self._level(state, lid)
        notes = self.tutor.class_notes_for(lesson, k=2)
        cards = []
        watch = lesson.get("watch") or {}
        if watch.get("kind") in ("scheduling", "bankers", "semaphore"):
            cards.append({"type": "example", "lesson": lid, "intro": watch.get("intro", "")})
        if notes:
            cards.append(_sources_card(notes, "From your class notes", f"{text} {lesson['title']}"))
        from tutor import videos
        if videos.clips_for(lid):
            cards.append({"type": "video", "lesson": lid})
        example = _example_facts(lesson)
        extra = ""
        if route.style == "simpler":
            extra = ("The student read an explanation of this already and still finds it hard. Explain it differently: "
                     "use a NEW everyday situation from a college student's life in India (not the lesson analogy), map each "
                     "part of it to the OS idea, and keep the words simple.\n")
        elif route.style == "example":
            extra = ("The student asked for an example. Give one everyday example and one OS example (processes P1, P2 "
                     "and resources R1, R2), step by step, and say which rule of the topic each step shows.\n")
        elif route.style == "gaps" and state.get("last_gaps"):
            extra = "When the student explained this topic back, they missed these ideas. Teach exactly these:\n" + \
                    "\n".join(f"- {g}" for g in state["last_gaps"]) + "\n"
        body = (f"STUDENT_LEVEL: {level}\nTOPIC: {lesson['title']} (goal: {lesson['goal']})\n"
                f"LESSON NOTES (correct and course-specific; never contradict them):\n{lesson['concept'].strip()}\n"
                f"LESSON ANALOGY: {lesson['analogy']}\nKEY POINTS: {'; '.join(lesson['summary'])}\n"
                f"CLASS NOTES:\n{prompts.format_notes(notes)}\n"
                + (f"EXAMPLE (shown to the student as a card next to your reply, solved by the OS Engine): {example}\n" if example else "")
                + extra + f"\nSTUDENT: {text}\n\n"
                f"Write the reply about {lesson['title']} ONLY (do not explain any other algorithm or topic): an "
                "everyday example first, then the exact rule in the course's terms"
                + (", then one or two sentences on what to notice in the example card" if example else "")
                + ". At most 200 words. End with one short question that checks understanding (don't answer it).")
        # no chat history here: the lesson is the source of truth, and an earlier off-topic reply in the history made
        # the model explain Round Robin when asked for Scheduling basics
        msgs = [{"role": "system", "content": CHAT_SYSTEM + CHAT_RULES}, {"role": "user", "content": body}]
        if route.style == "simpler":
            fallback = lesson["alt"]
        elif route.style == "gaps" and state.get("last_gaps"):
            fallback = ("Let's go over the ideas you missed:\n\n" + "\n".join(f"- {g}" for g in state["last_gaps"])
                        + f"\n\n{lesson['concept'].strip()}")
        else:
            fallback = f"{lesson['analogy']}\n\n{lesson['concept'].strip()}\n\n**Key points:** " + "; ".join(lesson["summary"]) + "."
        short = SHORT[lid]
        sugg = [f"Quiz me on {short}", "Explain it differently"]
        if lesson.get("practice_topic"):
            sugg.append(f"Give me {PRACTICE_NAME[lesson['practice_topic']]} problem")
        sugg.append("Let me explain it back")
        return self._stream_reply("explain", msgs, fallback, cards, sugg, {"topic": lid, "style": route.style})

    def _do_ask(self, state: dict, text: str, route: Route) -> Reply:
        if route.topic:
            state["topic"] = route.topic
        level = self._level(state, route.topic)
        chunks = self.kb.search(text, k=3, client=self.client if self.online else None)
        cards = [_sources_card(chunks, "Sources", text)] if chunks else []
        system = (CHAT_SYSTEM + CHAT_RULES + "\n\nAnswer the student's question using the COURSE NOTES when they are "
                  "relevant, and cite them like [1]. Prefer the student's own class notes (\"Teacher's notes\") and use "
                  "their terms; if a textbook such as OSTEP defines something differently, mention both briefly. If the "
                  "notes do not cover it, say so briefly and answer from general OS knowledge. If the student needs the "
                  "numbers for a specific problem, ask them to paste the problem: the engine will solve it. " + SCOPE)
        msgs = [{"role": "system", "content": system}] + self._history(state) + [{"role": "user", "content":
                f"STUDENT_LEVEL: {level}\nCOURSE NOTES:\n{prompts.format_notes(chunks)}\n\nQUESTION: {text}"}]
        if chunks:
            fallback = (("Here are" if self.online else "The language model is offline, so here are") +
                        " the most relevant parts of the course notes:\n\n" +
                        "\n\n".join(f"**[{i}] {c['meta'].get('subtopic', '')} — {c['meta'].get('section', c['meta'].get('source', ''))}**\n"
                                    f"{c['text'].split(': ', 1)[-1]}" for i, c in enumerate(chunks, start=1)))
        else:
            fallback = "I couldn't find this in the course notes, and the language model is offline."
        from tutor import videos
        key = next((k for rx, k in ASK_VIDEOS if rx.search(text)), None)
        if key and videos.clips_for(key):
            cards.append({"type": "video", "lesson": key})
        lid = route.topic or state.get("topic")
        sugg = []
        if lid:
            sugg = [f"Explain {SHORT[lid]}", f"Quiz me on {SHORT[lid]}"]
            if LESSON[lid].get("practice_topic"):
                sugg.append(f"Give me {PRACTICE_NAME[LESSON[lid]['practice_topic']]} problem")
        return self._stream_reply("ask", msgs, fallback, cards, sugg, {"topic": lid})

    def _do_faq(self, state: dict, text: str, route: Route) -> Reply:
        lid = route.topic
        if lid:
            state["topic"] = lid
            sugg = [f"Explain {SHORT[lid]}", f"Quiz me on {SHORT[lid]}"]
            if LESSON[lid].get("practice_topic"):
                sugg.append(f"Give me {PRACTICE_NAME[LESSON[lid]['practice_topic']]} problem")
        else:
            sugg = ["What can you teach me?", "Explain Round Robin", "Quiz me on deadlocks"]
        from tutor import videos
        key = route.payload.get("video")
        cards = [{"type": "video", "lesson": key}] if key and videos.clips_for(key) else []
        return Reply("faq", text=route.payload["text"], cards=cards, suggestions=sugg,
                     meta={"source": "checked answer (tutor/faq.py)", "topic": lid})

    def _do_example(self, state: dict, text: str, route: Route) -> Reply:
        lid = route.topic
        lesson = LESSON[lid]
        watch = lesson.get("watch") or {}
        if watch.get("kind") not in ("scheduling", "bankers", "semaphore"):
            return self._do_explain(state, text, Route("explain", topic=lid, style="example"))
        state["topic"] = lid
        intro = watch.get("intro", "")
        text_out = (f"Here's a worked example of **{lesson['title']}**, solved by the OS Engine. Step through it below"
                    + (f": {intro}" if intro else ".") + "\n\nWhen you're ready, try one yourself.")
        sugg = [f"Quiz me on {SHORT[lid]}", "Explain it differently"]
        if lesson.get("practice_topic"):
            sugg.insert(0, f"Give me {PRACTICE_NAME[lesson['practice_topic']]} problem")
        return Reply("example", text=text_out, cards=[{"type": "example", "lesson": lid, "intro": intro}],
                     suggestions=sugg, meta={"source": "template", "topic": lid})

    def _do_bankers_request(self, state: dict, text: str, route: Route) -> Reply:
        if route.payload.get("bankers"):        # pasted together with the request
            self._new_problem_state(state, self._problem_from_payload(route.payload), source="pasted")
        problem = problem_from_dict(state["problem"]["problem"])
        first = (route.payload.get("bankers") or {}).get("first_pid", 0)
        pid, req = route.payload["pid"] - first, route.payload["request"]
        need = bankers.compute_need(problem.maximum, problem.allocation)
        r = bankers.request(problem.available, problem.maximum, problem.allocation, pid, req)
        v = lambda xs: "(" + ", ".join(str(x) for x in xs) + ")"
        name = f"P{pid + first}"
        lines = [f"**{name} requests {v(req)}.** The resource-request algorithm:", "",
                 f"1. Request ≤ Need? Need({name}) = {v(need[pid])}: " + ("yes." if r["reason"] != "exceeds_need" else
                 "**no**, so this is an error: a process may not ask for more than it declared.")]
        if r["reason"] != "exceeds_need":
            lines.append(f"2. Request ≤ Available? Available = {v(problem.available)}: " + (
                "yes." if r["reason"] != "must_wait" else f"**no**, so {name} must wait until resources are released."))
        if r["reason"] in ("safe", "unsafe"):
            new_need = [n - q for n, q in zip(need[pid], req)]
            lines.append(f"3. Pretend to grant it: Available becomes {v(r['new_available'])}, Allocation({name}) becomes "
                         f"{v(r['new_allocation'][pid])}, Need({name}) becomes {v(new_need)}.")
            if r["granted"]:
                seq = [f"P{int(x[1:]) + first}" for x in r["safety"]["sequence"]]
                lines.append(f"4. Safety check on that state: **safe**, with the sequence "
                             f"{', '.join(seq)}. So the request is **granted**.")
            else:
                lines.append(f"4. Safety check on that state: **unsafe** (no order lets every process finish). So the "
                             f"request is **not granted** now: {name} waits, and the state stays as it was.")
        from tutor import videos
        return Reply("bankers_request", text="\n".join(lines),
                     cards=[{"type": "video", "lesson": "bankers_request"}] if videos.clips_for("bankers_request") else [],
                     suggestions=["Is an unsafe state a deadlock?", "Quiz me on the Banker's algorithm",
                                  "Give me a Banker's problem"],
                     meta={"source": "template (OS Engine)", "topic": "bankers"})

    def _do_need_matrices(self, state: dict, text: str, route: Route) -> Reply:
        state["topic"] = "bankers"
        return Reply("need_matrices", text=(
            "To check a safe sequence I need the whole state: **Allocation** and **Max** (or Need) for every process, "
            "and **Available**. Need alone isn't enough, because Work grows by each finished process's *Allocation*, "
            "so whether the next process fits depends on what the earlier ones release.\n\nPaste the tables (any "
            "layout works, e.g. `Allocation: P0 0 1 0, P1 2 0 0 ... Max: ... Available: 3 3 2`) together with the "
            "sequence, and I'll check every step."),
            suggestions=["Explain the Banker's algorithm", "Give me a Banker's problem"], meta={"source": "template"})

    def _do_formula(self, state: dict, text: str, route: Route) -> Reply:
        v = dict(route.payload["values"])
        lines = []
        for _ in range(2):                              # fill in what follows from TAT = CT − AT and WT = TAT − BT
            if "TAT" not in v and "CT" in v and "AT" in v:
                v["TAT"] = v["CT"] - v["AT"]; lines.append(f"TAT = CT − AT = {v['CT']:g} − {v['AT']:g} = **{v['TAT']:g}**")
            if "WT" not in v and "TAT" in v and "BT" in v:
                v["WT"] = v["TAT"] - v["BT"]; lines.append(f"WT = TAT − BT = {v['TAT']:g} − {v['BT']:g} = **{v['WT']:g}**")
            if "TAT" not in v and "WT" in v and "BT" in v:
                v["TAT"] = v["WT"] + v["BT"]; lines.append(f"TAT = WT + BT = {v['WT']:g} + {v['BT']:g} = **{v['TAT']:g}**")
            if "BT" not in v and "TAT" in v and "WT" in v:
                v["BT"] = v["TAT"] - v["WT"]; lines.append(f"BT = TAT − WT = {v['TAT']:g} − {v['WT']:g} = **{v['BT']:g}**")
            if "CT" not in v and "TAT" in v and "AT" in v:
                v["CT"] = v["TAT"] + v["AT"]; lines.append(f"CT = TAT + AT = {v['TAT']:g} + {v['AT']:g} = **{v['CT']:g}**")
        claim = route.payload.get("claim")
        head = ""
        if claim and claim[0] in v:
            ok = abs(v[claim[0]] - claim[1]) < 1e-9
            head = (f"✓ Yes, {claim[0]} = {claim[1]:g}.\n\n" if ok else
                    f"✗ No: {claim[0]} is {v[claim[0]]:g}, not {claim[1]:g}.\n\n")
        if not lines:
            return Reply("formula", text="The formulas: TAT = CT − AT, WT = TAT − BT, RT = first start − AT. Give me "
                                         "two of the values for one process and I'll work out the rest.",
                         meta={"source": "template"})
        tail = ("\n\nWT can never be more than TAT: waiting is part of the turnaround." if claim and claim[0] == "WT"
                and claim[1] > v.get("TAT", claim[1]) else "")
        return Reply("formula", text=head + "\n".join(f"- {x}" for x in lines) + tail,
                     suggestions=["Give me a problem", "Explain scheduling basics"], meta={"source": "template (formula)"})

    def _do_sem_trace(self, state: dict, text: str, route: Route) -> Reply:
        from engine import semaphore
        p = route.payload
        r = semaphore.trace(p["initial"], p["ops"])
        lines = [f"Starting from {', '.join(f'{k} = {x}' for k, x in p['initial'].items())} (blocking definition):", ""]
        for s in r["steps"]:
            lines.append(f"{s['step']}. {s['pid']} calls {s['op']}({s['sem']}): {s['sem']} goes {s['value_before']} → "
                         f"{s['value_after']}. {s['effect']}" + (f", wakes {s['woken']}" if s.get("woken") else "") + ".")
        blocked = r["blocked"]
        lines += ["", f"**Blocked at the end:** {', '.join(blocked) if blocked else 'nobody'}. "
                      f"Final values: {', '.join(f'{k} = {x}' for k, x in r['final_values'].items())}."]
        said = re.search(r"\bboth\b|\ball\b", text, re.I) and re.search(r"\bblock", text, re.I)
        if said and len(blocked) < len({o['pid'] for o in p['ops']}):
            lines.append("\nSo not all of them are blocked: a wait() only blocks when it takes the value below 0; the "
                         "process whose wait() leaves it at 0 or more goes straight in.")
        return Reply("sem_trace", text="\n".join(lines), suggestions=["Quiz me on semaphores", "Give me a semaphore problem"],
                     meta={"source": "template (OS Engine)", "topic": "semaphores"})

    def _do_code(self, state: dict, text: str, route: Route) -> Reply:
        lesson = LESSON[route.topic]
        state["topic"] = route.topic
        text_out = (f"I teach the algorithm rather than write full programs, but here is **{lesson['title']}** in the "
                    "course's pseudocode. It maps straight onto C with POSIX threads: a semaphore is `sem_t s;` created "
                    "with `sem_init(&s, 0, value)`, `wait(s)` is `sem_wait(&s)`, `signal(s)` is `sem_post(&s)`, a mutex "
                    "lock is `pthread_mutex_lock` / `pthread_mutex_unlock`, and each process is a thread from "
                    "`pthread_create`.\n\n" + lesson["concept"].strip())
        return Reply("code", text=text_out, suggestions=[f"Quiz me on {SHORT[route.topic]}", "Let me explain it back"],
                     meta={"source": "template (lesson)", "topic": route.topic})

    def _do_chat(self, state: dict, text: str, route: Route) -> Reply:
        topic = LESSON[state["topic"]]["title"] if state.get("topic") in LESSON else "none yet"
        system = (CHAT_SYSTEM + "\n\nReply in English, in one or two short sentences. Mention what you can help with if "
                  "useful. " + SCOPE + "\nABOUT YOU: " + IDENTITY + f"\nCONTEXT: the topic so far is {topic}. Do not "
                  "claim anything else about what the student did or asked before, and do not make up numbers or "
                  "problems. If the message is unclear, ask what they would like to do. If the student sounds worried "
                  "or stressed, be kind and suggest one small next step (a short lesson, a practice problem or the mock exam).")
        msgs = [{"role": "system", "content": system}] + self._history(state, 2) + [{"role": "user", "content": text}]
        low = text.lower()
        out_of_scope = False
        if re.search(r"thank|thanks|\bty\b", low):
            fallback = "You're welcome! Want to keep going with a problem or a quick quiz?"
        elif re.search(r"\bbye\b", low):
            fallback = "Bye! Your progress is saved, so we can pick up from here next time."
        elif re.search(r"\b(hi|hello|hey|hola|namaste|yo|good (morning|afternoon|evening))\b", low):
            fallback = ("Hi! " + (f"We were on **{topic}**. " if state.get("topic") in LESSON else "") +
                        "Would you like an explanation, a problem to try, or a quick quiz?")
        elif re.search(r"stress|anxious|worried|scared|nervous|overwhelm|panic|tense", low):
            fallback = ("Exams can feel like a lot, and that's normal. One small step at a time: try a 10-minute lesson in "
                        "**Learn**, or a short **mock paper** in Exam mode to see where you stand. Want me to give you an "
                        "easy problem to warm up?")
        elif not OS_WORDS.search(text) and re.search(r"\b(write|code|program|implement|debug)\b.*\b(python|java|c\+\+|"
                                                     r"program|code|function|script|sort|website|app)\b|"
                                                     r"\bsolve\b.*[=+*/^]", low) or \
                (OFF_TOPIC.search(text) and not OS_WORDS.search(text)):
            out_of_scope = True
            fallback = ("That's outside what I can help with: I teach CPU scheduling and process synchronization. "
                        "Want an explanation, a problem to try, or a quick quiz?")
        elif not OS_WORDS.search(text) and (len(text.split()) >= 4 or ASKS.search(text)) and \
                not (state.get("topic") in LESSON and len(text.split()) < 4):          # "why?" after a lesson
            fallback = ("That's outside what I can help with: I teach CPU scheduling and process synchronization. "
                        "Want an explanation, a problem to try, or a quick quiz?")
        elif state.get("topic") in LESSON:
            fallback = (f"I'm not sure what you mean. We were on **{topic}**: would you like an explanation, a problem "
                        "to try, or a quick quiz?")
        else:
            fallback = ("Hi! I'm your OS tutor for CPU scheduling and process synchronization. Ask me to explain a "
                        "topic, paste a question, practise a problem, or take a quick quiz.")
        sugg = ["Explain Round Robin", "Give me a problem", "Quiz me on deadlocks", "How am I doing?"]
        meta: dict = {"source": "template"}
        out = fallback
        if self.online and not out_of_scope:
            # small talk is short, so check it before showing it: the model sometimes invents a past ("You were working
            # on Round Robin, remember?") or drifts to a topic nobody mentioned
            try:
                reply = clean_reply(self.client.chat(msgs))
                if reply and not _invents_context(reply, text, state):
                    out, meta["source"] = reply, self.model_label
                else:
                    meta["source"] = "template (model reply invented context)"
                    meta["blocked_text"] = reply
            except Exception as e:  # Ollama stopped: the template is fine
                meta["error"] = str(e)
        return Reply("chat", text=out, suggestions=sugg, meta=meta)

    # ------------------------------------------------------------------ actions: problems
    def _new_problem_state(self, state: dict, problem, reason: str | None = None, bank_item: dict | None = None,
                           source: str = "generated", revealed: bool = False) -> dict:
        ps = {"problem": problem.to_dict(), "pid": uuid.uuid4().hex[:10], "started": time.time(), "attempts": 0,
              "hints": 0, "revealed": revealed, "analysis": None, "solved": False, "reason": reason,
              "bank_item": bank_item, "source": source, "answer": None}
        state["problem"] = ps
        state["pending_problem"] = None
        lid = ALGO_LESSON.get(problem_topic(problem))
        if lid:
            state["topic"] = lid
        return ps

    def _do_practice(self, state: dict, text: str, route: Route) -> Reply:
        sid = state["sid"]
        topic, d, reason, item = route.practice, route.difficulty, None, None
        if topic in ("PAST_PAPERS", "NOTES_EXAMPLES"):
            got = question_bank.random_problem(source="papers" if topic == "PAST_PAPERS" else "notes")
            problem, item = got
            reason = ("Past paper: " if topic == "PAST_PAPERS" else "From your class notes: ") + \
                f"{item.get('paper', item.get('source', ''))} {item.get('question', '')}".strip()
        else:
            if topic is None:
                rec = self.students.recommend_next(sid)
                topic, reason = rec["topic"], rec["reason"]
                d = d or rec["difficulty"]
            elif d is None:
                d, why = self.students.difficulty_for(sid, topic)
                reason = f"Difficulty from your mastery ({why})."
            else:
                reason = "Difficulty as you asked."
            if topic == "BANKERS":
                problem = generator.generate_bankers(d)
            elif topic == "SEMAPHORE":
                problem = generator.generate_semaphore(d)
            else:
                problem = generator.generate_scheduling(topic, d)
        self._new_problem_state(state, problem, reason, item)
        kind = problem.kind
        if item:
            head = f"Here's a question from {'a past paper' if route.practice == 'PAST_PAPERS' else 'your class notes'}."
        else:
            name = TOPIC_NAMES.get(topic, topic)
            head = f"Here's {DIFF_WORDS.get(problem.difficulty, 'a')} **{name}** problem."
        text_out = f"{head}\n\n_{reason}_\n\n{answer_help(kind)}"
        lid = ALGO_LESSON.get(problem_topic(problem))
        sugg = ["Give me a hint", "Show me the solution"]
        if lid:
            sugg.append(f"Explain {SHORT[lid]} first")
        return Reply("practice", text=text_out, cards=[{"type": "problem", "problem": problem.to_dict(),
                                                        "bank_item": item}], suggestions=sugg,
                     meta={"source": "template", "topic": topic})

    def _problem_from_payload(self, payload: dict):
        if payload.get("bankers"):
            b = payload["bankers"]
            return BankersProblem(difficulty=2, available=b["available"], maximum=b["maximum"],
                                  allocation=b["allocation"], resources=b["resources"])
        algo = payload["algorithm"]
        q = payload.get("quantum") if algo == "RR" else None
        if algo == "RR" and not q:
            q = 2
        procs = [Process(**p) for p in payload["processes"]]
        return SchedulingProblem(algorithm=algo, difficulty=2, processes=procs, quantum=q)

    def _do_need_algorithm(self, state: dict, text: str, route: Route) -> Reply:
        p = route.payload
        state["pending_problem"] = {"processes": p["processes"], "quantum": p.get("quantum"), "solve": p.get("solve")}
        n = len(p["processes"])
        procs = ", ".join(f"{x['pid']} (AT {x['arrival']}, BT {x['burst']})" for x in p["processes"][:6])
        return Reply("need_algorithm", text=f"I can read {n} processes: {procs}. Which algorithm should I use?",
                     suggestions=["FCFS", "SJF", "SRTF", f"Round Robin with q = {p.get('quantum') or 2}",
                                  "Priority (non-preemptive)"])

    def _do_offer(self, state: dict, text: str, route: Route) -> Reply:
        state["pending_problem"] = None
        problem = self._problem_from_payload(route.payload)
        self._new_problem_state(state, problem, source="pasted")
        state["other_algorithms"] = route.payload.get("others") or []
        if problem.kind == "bankers":
            desc = f"a Banker's problem with {len(problem.allocation)} processes and {len(problem.available)} resource types"
        else:
            q = f" (q = {problem.quantum})" if problem.algorithm == "RR" else ""
            desc = f"**{ALGORITHMS[problem.algorithm]}**{q} with {len(problem.processes)} processes"
        text_out = (f"Got it: {desc}. Check the table below in case I misread anything.\n\n"
                    "Do you want to try it first (I'll check your answer step by step and give hints), "
                    "or see the full solution?")
        return Reply("offer", text=text_out, cards=[{"type": "problem", "problem": problem.to_dict()}],
                     suggestions=["I'll try it first", "Give me a hint to start", "Show me the full solution"])

    def _do_try_first(self, state: dict, text: str, route: Route) -> Reply:
        kind = problem_from_dict(state["problem"]["problem"]).kind
        return Reply("try_first", text=f"Go ahead! {answer_help(kind)} Ask for a hint any time.",
                     suggestions=["Give me a hint"])

    def _do_no_problem(self, state: dict, text: str, route: Route) -> Reply:
        return Reply("no_problem", text="There's no open problem right now. Want one at your level, or do you want to "
                                        "paste a question from a paper?",
                     suggestions=["Give me a problem", "Give me a past paper question"])

    def _do_solve(self, state: dict, text: str, route: Route) -> Reply:
        state["pending_problem"] = None
        problem = self._problem_from_payload(route.payload)
        self._new_problem_state(state, problem, source="pasted", revealed=True)
        others = route.payload.get("others") or []
        state["other_algorithms"] = others
        reply = self._solution_reply(state, problem, "solve", others)
        if route.payload.get("note"):
            reply.text = route.payload["note"] + "\n\n**Here is the engine's solution of your problem:**\n\n" + reply.text
        return reply

    def _do_detect(self, state: dict, text: str, route: Route) -> Reply:
        """A pasted deadlock-detection question (Allocation, Request, Available): the detection algorithm, worked out."""
        d = route.payload["detection"]
        first = d.get("first_pid", 0)
        names = [f"P{first + k}" for k in range(len(d["allocation"]))]
        det = deadlock.detect(d["available"], d["allocation"], d["request"], names=names)
        v = lambda x: " ".join(map(str, x))  # noqa: E731
        facts = [f"Available (Work at the start) = {v(d['available'])}"]
        facts += [f"{s['process']} can finish: Request {v(s['request'])} <= Work {v(s['work_before'])}; it releases "
                  f"{v(s['allocation_released'])}, so Work = {v(s['work_after'])}" for s in det["steps"]]
        if det["skipped"]:
            facts.append(f"{', '.join(det['skipped'])} hold nothing, so Finish starts true for them")
        facts.append(f"Deadlocked: {', '.join(det['deadlocked'])}" if det["deadlock"] else
                     f"No deadlock: every process can finish, in the order {', '.join(det['sequence'])}")
        fallback = ("Here is the detection algorithm, step by step (Work starts as Available; a process may finish when "
                    "its Request ≤ Work, and then releases what it holds):\n\n" + "\n".join(f"- {f}" for f in facts) +
                    ("\n\nAny order works as long as each Request fits in Work." if not det["deadlock"] else
                     "\n\nNobody left can be satisfied, so those processes wait for each other forever."))
        meta: dict = {}
        msgs = [{"role": "system", "content": CHAT_SYSTEM + CHAT_RULES},
                {"role": "user", "content": "FACTS (deadlock detection algorithm, from the OS Engine; the tables are shown "
                                            "as a card):\n" + "\n".join(f"- {f}" for f in facts) +
                 "\n\nExplain the result in a short numbered list (at most 6 items) using only numbers from FACTS, say "
                 "clearly whether the system is deadlocked, then ask one short question that checks understanding."}]
        text_out = self._guarded_text(msgs, facts, fallback, meta)
        state["topic"] = "deadlock"
        from tutor import videos
        cards = [{"type": "detection", **d}] + ([{"type": "video", "lesson": "detection"}] if videos.clips_for("detection") else [])
        sugg = ["Explain deadlock detection", "Quiz me on deadlocks", "What is a wait-for graph?", "Give me a Banker's problem"]
        return Reply("detect", text=text_out, cards=cards, suggestions=sugg, meta=meta)

    def _do_reveal(self, state: dict, text: str, route: Route) -> Reply:
        ps = state["problem"]
        ps["revealed"] = True
        problem = problem_from_dict(ps["problem"])
        return self._solution_reply(state, problem, "reveal", state.get("other_algorithms") or [])

    def _solution_reply(self, state: dict, problem, action: str, others: list[str]) -> Reply:
        facts, fallback = _solution_facts(problem)
        meta: dict = {}
        msgs = [{"role": "system", "content": CHAT_SYSTEM + CHAT_RULES},
                {"role": "user", "content": "FACTS (from the OS Engine; the full Gantt chart and table are shown to the "
                                            "student as a card):\n" + "\n".join(f"- {f}" for f in facts) +
                 "\n\nWalk the student through how this solution is built: the key decisions and the reason for each, "
                 "in a short numbered list (at most 6 items), then one line on the averages. Use only numbers from FACTS. "
                 "End with one short question that checks they understood a decision."}]
        text_out = self._guarded_text(msgs, facts, fallback, meta)
        if text_out is not fallback and problem.kind == "scheduling":
            text_out = _with_check_question(text_out, problem)
        elif text_out is not fallback and problem.kind == "bankers":
            text_out = _with_bankers_question(text_out, problem)
        sugg = [f"Now solve it with {ALGORITHMS[a].split(' (')[0]}" for a in others[:2]]
        topic = problem_topic(problem)
        lid = ALGO_LESSON.get(topic)
        sugg += ["Give me a similar problem"] + ([f"Quiz me on {SHORT[lid]}"] if lid else [])
        cards = [{"type": "solution", "problem": problem.to_dict(), "bank_item": (state.get("problem") or {}).get("bank_item")}]
        return Reply(action, text=text_out, cards=cards, suggestions=sugg[:4], meta=meta)

    def _do_why(self, state: dict, text: str, route: Route) -> Reply:
        ps = state["problem"]
        problem = problem_from_dict(ps["problem"])
        if not (ps.get("revealed") or ps.get("solved")) or problem.kind != "scheduling":
            return self._do_hint(state, text, route)
        res = problem.solve()
        asked = re.search(r"\b(P\s?\d+)\b", text, re.I)
        pid = cp.normalise_pid(asked.group(1)) if asked else None
        if pid in res.results and re.search(r"waiting|\bwt\b|turn\s*-?around|\btat\b|completion|\bct\b|finish|wait", text, re.I):
            return Reply("why", text=_metric_story(res, pid), suggestions=["Give me a similar problem"],
                         meta={"source": "template (OS Engine)"})
        m = re.search(r"\bt\s*=\s*(\d+)|\bat\s*(?:time\s*)?(\d+)", text, re.I)
        decisions = res.decisions
        if m:
            t_ = int(m.group(1) or m.group(2))
            d = scheduling.governing_decision(res, t_)
            decisions = [d] if d else decisions
        facts = [f"t = {d.time}: {d.reason}" for d in decisions if d.kind != "idle"][:8]
        fallback = "Here's what the engine decided:\n\n" + "\n".join(f"- {f}" for f in facts)
        meta: dict = {}
        msgs = [{"role": "system", "content": CHAT_SYSTEM + CHAT_RULES}] + self._history(state, 4) + [
            {"role": "user", "content": "FACTS (engine decisions for the open problem):\n" + "\n".join(f"- {f}" for f in facts)
             + f"\n\nSTUDENT: {text}\nAnswer in at most 100 words using only these facts."}]
        return Reply("why", text=self._guarded_text(msgs, facts, fallback, meta), meta=meta,
                     suggestions=["Give me a similar problem"])

    # ------------------------------------------------------------------ actions: checking
    def _parse_answer(self, problem, t: str) -> dict | None:
        kind = problem.kind
        if kind == "scheduling":
            return cp.parse_scheduling_answer(t, [p.pid for p in problem.processes])
        if kind == "advanced":
            m = cp.parse_metrics(t, [j.pid for j in problem.jobs])
            return {"metrics": m, "gantt": [], "averages": {}} if m else None
        if kind == "bankers":
            ans = cp.parse_bankers_answer(t, len(problem.allocation))
            if ans and not ans.get("sequence") and ("?" in t or RXC["explain"].search(t) or RXC["ask"].search(t)):
                return None
            return ans
        if kind == "semaphore":
            return cp.parse_semaphore_answer(t, list(problem.initial))
        return None

    def _do_pasted_check(self, state: dict, text: str, route: Route) -> Reply:
        p = route.payload
        if not p.get("bankers") and not p.get("algorithm"):
            return self._do_need_algorithm(state, text, Route("need_algorithm", payload={**p, "solve": False}))
        problem = self._problem_from_payload(p)
        self._new_problem_state(state, problem, source="pasted")
        ans = self._parse_answer(problem, p["answer_text"])
        if ans is None:
            return Reply("offer", text="I've read the problem, but I couldn't read your answer. " + answer_help(problem.kind),
                         cards=[{"type": "problem", "problem": problem.to_dict()}],
                         suggestions=["Show me the full solution", "Give me a hint"])
        return self._do_check(state, text, Route("check", payload={"answer": ans}))

    def _do_check(self, state: dict, text: str, route: Route) -> Reply:
        ps = state.get("problem")
        if not ps:
            return self._do_no_problem(state, text, route)
        problem = problem_from_dict(ps["problem"])
        kind = problem.kind
        raw = route.payload["answer"]
        if kind == "scheduling" and raw.get("order") and not raw.get("gantt") and not raw.get("metrics") \
                and not raw.get("averages"):
            return self._order_only(problem, raw["order"])
        if kind == "scheduling" and not route.payload.get("structured") and not raw.get("gantt") and not raw.get("metrics"):
            return self._averages_only(problem, raw.get("averages") or {}, raw.get("order"))
        if kind == "scheduling" and not route.payload.get("structured") and not raw.get("gantt") and \
                len(raw["metrics"]) < len(problem.processes):
            return self._values_only(problem, raw["metrics"], raw.get("averages") or {})
        answer = self._merge_answer(ps, problem, raw)
        ps["attempts"] += 1
        sid = state["sid"]
        analysis = self.tutor.check(problem, answer)
        need_skipped = False
        if kind == "bankers" and answer.get("need") is None:
            obs = analysis.get("observations", {})
            if obs.get("BANKERS_SAFETY") and not analysis.get("errors"):
                analysis["correct"] = True
                need_skipped = True
        changes = self.students.record_attempt(sid, problem.to_dict(), ps["pid"], analysis, ps["attempts"], ps["hints"],
                                               ps["revealed"], time.time() - ps["started"])
        topic = problem_topic(problem)
        strat = strategy_mod.decide(problem, analysis, self.students.level(sid, topic if topic in TOPIC_NAMES else "FCFS"),
                                    self.students.recurring_errors(sid), ps["attempts"], ps["hints"])
        ps["analysis"] = analysis
        slim = _slim_analysis(analysis)
        if analysis.get("correct"):
            ps["solved"] = True
        fb = self.tutor.feedback(strat, use_llm=self.online)
        meta = {"source": fb["source"], "strategy": strat.action, "facts": strat.facts, "issues": fb.get("issues", []),
                "rationale": strat.rationale, "reveal": strat.reveal}
        if fb.get("llm_text") and fb["llm_text"] != fb["text"]:
            meta["blocked_text"] = fb["llm_text"]
        if fb.get("latency"):
            meta["latency"] = round(fb["latency"], 1)
        text_out = fb["text"]
        if need_skipped:
            text_out += "\n\n_(I checked your verdict and sequence; the Need matrix wasn't part of your answer.)_"
        if kind == "semaphore" and analysis.get("semaphore_mode") == "busy_wait":
            text_out += ("\n\n_Your values follow the busy-waiting P/V from your Module 4 notes (S never goes below 0). "
                         "That definition is accepted too._")
        cards = [{"type": "marked", "problem": problem.to_dict(), "answer": _jsonable_answer(answer),
                  "analysis": slim, "revealed": ps["revealed"] or bool(analysis.get("correct")),
                  "changes": {SKILLS.get(k, k): v for k, v in (changes or {}).items()}}]
        lid = ALGO_LESSON.get(topic)
        if analysis.get("correct"):
            sugg = ["Another one", "Something harder"] + ([f"Quiz me on {SHORT[lid]}"] if lid else [])
        else:
            sugg = ["Give me a hint", "Show me the solution"] + ([f"Explain {SHORT[lid]} again"] if lid else [])
        return Reply("check", text=text_out, cards=cards, suggestions=sugg, meta=meta)

    def _merge_answer(self, ps: dict, problem, raw: dict) -> dict:
        kind = problem.kind
        prev = ps.get("answer") or {}
        if kind == "scheduling":
            gantt = raw.get("gantt") or prev.get("gantt") or []
            metrics = {k: dict(v) for k, v in (prev.get("metrics") or {}).items()}
            for pid, row in (raw.get("metrics") or {}).items():
                metrics.setdefault(pid, {}).update(row)
            ans = {"gantt": [tuple(x) for x in gantt], "metrics": metrics}
        elif kind == "advanced":
            metrics = {k: dict(v) for k, v in (prev.get("metrics") or {}).items()}
            for pid, row in (raw.get("metrics") or {}).items():
                metrics.setdefault(pid, {}).update(row)
            ans = {"metrics": metrics}
        elif kind == "bankers":
            ans = {"need": raw.get("need"), "safe": raw.get("safe") if raw.get("safe") is not None else prev.get("safe"),
                   "sequence": raw.get("sequence") or prev.get("sequence")}
        else:
            final = dict(prev.get("final") or {})
            final.update(raw.get("final") or {})
            blocked = raw.get("blocked") if raw.get("blocked") is not None else prev.get("blocked", [])
            ans = {"final": final, "blocked": blocked or []}
        ps["answer"] = _jsonable_answer(ans)
        return ans

    def _order_only(self, problem, order: list[str]) -> Reply:
        """'i got P1 P2 P1 P3 P2': compare the order of slices with the engine's, and explain the first difference."""
        res = problem.solve()
        merged = []
        for g in res.gantt:
            if g.pid != scheduling.IDLE and (not merged or merged[-1] != g.pid):
                merged.append(g.pid)
        theirs = [p for i, p in enumerate(order) if i == 0 or order[i - 1] != p]
        if theirs == merged:
            return Reply("check", text=f"✓ The order {' → '.join(theirs)} matches the engine's Gantt chart. Want to check "
                                       "the times as well? Send CT, TAT and WT for each process.",
                         suggestions=["Show me the full solution"], meta={"source": "engine comparison"})
        k = next((i for i, (a, b) in enumerate(zip(theirs, merged)) if a != b), min(len(theirs), len(merged)))
        segs = [g for g in res.gantt if g.pid != scheduling.IDLE]
        runs, last = [], None
        for g in segs:                               # one entry per change of process, like the student's list
            if g.pid != last:
                runs.append(g)
            last = g.pid
        why = ""
        if k < len(runs):
            g = runs[k]
            d = scheduling.governing_decision(res, g.start)
            why = f" At t = {g.start} the engine runs **{g.pid}**" + (f": {d.reason}" if d else ".")
            if problem.algorithm == "RR":
                why += (" (In Round Robin, a process that arrives exactly when a slice ends joins the queue before the "
                        "preempted process: that's the course convention.)")
        text_out = (f"✗ Not quite. Your order: {' → '.join(theirs)}\n\nThe engine's order: {' → '.join(merged)}\n\n"
                    f"They first differ at slice {k + 1}.{why}")
        return Reply("check", text=text_out, cards=[{"type": "solution", "problem": problem.to_dict()}],
                     suggestions=["Give me a similar problem", "Explain it differently"], meta={"source": "engine comparison"})

    def _values_only(self, problem, metrics: dict, avgs: dict) -> Reply:
        """A few values ('TAT for P2 is 6'): say which ones match the engine, without giving the right ones away."""
        res = problem.solve()
        field = {"CT": "completion", "TAT": "turnaround", "WT": "waiting"}
        lines, ok_all = [], True
        for pid, vals in metrics.items():
            for k, v in vals.items():
                eng = getattr(res.results[pid], field[k])
                ok = v == eng
                ok_all &= ok
                lines.append(f"- {k} of {pid} = {v}: {'✓ matches the engine' if ok else '✗ does not match the engine'}")
        for k, eng in (("WT", res.avg_wt), ("TAT", res.avg_tat)):
            if k in avgs:
                ok = abs(avgs[k] - eng) <= 0.011 or abs(avgs[k] - round(eng, 1)) <= 0.051
                ok_all &= ok
                lines.append(f"- Average {k} = {avgs[k]:g}: {'✓ matches the engine' if ok else '✗ does not match the engine'}")
        tail = ("Nice!" if ok_all else "Remember TAT = CT − AT and WT = TAT − BT. Want a hint, or the full solution?")
        return Reply("check", text="\n".join(lines) + "\n\n" + tail,
                     cards=[{"type": "problem", "problem": problem.to_dict()}],
                     suggestions=["Give me a hint", "Show me the full solution"], meta={"source": "engine comparison"})

    def _averages_only(self, problem, avgs: dict, order: list[str] | None = None) -> Reply:
        res = problem.solve()
        lines = []
        ok_all = True
        if order:
            merged = [g.pid for i, g in enumerate(res.gantt)
                      if g.pid != scheduling.IDLE and (i == 0 or res.gantt[i - 1].pid != g.pid)]
            theirs = [p for i, p in enumerate(order) if i == 0 or order[i - 1] != p]
            same = theirs == merged
            ok_all &= same
            lines.append(f"- Order {' → '.join(theirs)}: {'✓ matches the engine' if same else '✗ does not match the engine'}")
        for k, eng in (("WT", res.avg_wt), ("TAT", res.avg_tat)):
            if k in avgs:
                ok = abs(avgs[k] - eng) <= 0.011 or abs(avgs[k] - round(eng, 1)) <= 0.051
                ok_all &= ok
                lines.append(f"- Average {k} = {avgs[k]:g}: {'✓ matches the engine' if ok else '✗ does not match the engine'}")
        text_out = "\n".join(lines) + ("\n\nNice! " if ok_all else "\n\n") + \
            ("To see exactly where it goes wrong, send me your Gantt chart or the CT, TAT and WT of each process."
             if not ok_all else "If you want, send your per-process values too and I'll check those as well.")
        return Reply("check", text=text_out, suggestions=["Give me a hint", "Show me the solution"],
                     meta={"source": "engine comparison"})

    def _do_hint(self, state: dict, text: str, route: Route) -> Reply:
        ps = state.get("problem")
        if not ps:
            return self._do_no_problem(state, text, route)
        problem = problem_from_dict(ps["problem"])
        ps["hints"] += 1
        analysis = ps.get("analysis")
        strat = self.tutor.hint(state["sid"], problem, analysis, ps["attempts"], ps["hints"])
        if strat.reveal and not ps.get("solved"):
            ps["revealed"] = True
        fb = self.tutor.feedback(strat, use_llm=self.online)
        meta = {"source": fb["source"], "strategy": strat.action, "facts": strat.facts, "issues": fb.get("issues", []),
                "rationale": strat.rationale, "reveal": strat.reveal}
        if fb.get("llm_text") and fb["llm_text"] != fb["text"]:
            meta["blocked_text"] = fb["llm_text"]
        sugg = ["Another hint", "Show me the solution"] if ps["hints"] < 3 else ["Show me the solution"]
        return Reply("hint", text=fb["text"], suggestions=sugg, meta=meta)

    # ------------------------------------------------------------------ actions: quiz
    def _do_quiz(self, state: dict, text: str, route: Route) -> Reply:
        lid = route.topic or self._default_lesson(state)
        lesson = LESSON[lid]
        state["topic"] = lid
        n = min(3, len(lesson["mcq"]))
        order = random.sample(range(len(lesson["mcq"])), n)
        state["quiz"] = {"lesson": lid, "order": order, "i": 0, "score": 0, "opts": {}}
        head = f"Quick quiz on **{lesson['title']}**: {n} questions. Tap an option or reply with its letter.\n\n"
        q_text, card = self._quiz_question(state)
        return Reply("quiz", text=head + q_text, cards=[card], meta={"topic": lid})

    def _quiz_question(self, state: dict) -> tuple[str, dict]:
        qz = state["quiz"]
        lesson = LESSON[qz["lesson"]]
        idx = qz["order"][qz["i"]]
        item = lesson["mcq"][idx]
        perm = list(range(len(item["options"])))
        random.shuffle(perm)
        qz["opts"][str(qz["i"])] = perm
        opts = [item["options"][j][0] for j in perm]
        text = f"**Question {qz['i'] + 1} of {len(qz['order'])}.** {item['q']}"
        card = {"type": "quiz", "number": qz["i"] + 1, "options": opts, "key": f"{qz['lesson']}-{idx}-{uuid.uuid4().hex[:6]}",
                "q": item["q"], "of": len(qz["order"]), "title": lesson["title"]}   # drawn as a question paper
        return text, card

    @staticmethod
    def _mark_quiz_card(state: dict, number: int, picked: int, answer: int, grade: list[int] | None = None) -> None:
        """Write the student's tick and the right option onto the question's card, so the paper shows it marked."""
        for m in reversed(state["messages"]):
            if m["role"] != "assistant":
                continue
            for c in m.get("cards") or []:
                if c.get("type") == "quiz" and c.get("number") == number:
                    c["picked"], c["answer"] = picked, answer
                    if grade:
                        c["grade"] = grade
            return

    def _quiz_choice(self, state: dict, t: str) -> int | None:
        qz = state["quiz"]
        lesson = LESSON[qz["lesson"]]
        item = lesson["mcq"][qz["order"][qz["i"]]]
        perm = qz["opts"].get(str(qz["i"])) or list(range(len(item["options"])))
        opts = [item["options"][j][0] for j in perm]
        s = t.strip().lower()
        m = re.fullmatch(r"\(?(?:option\s*)?([a-d])\)?[.)]?\s*(?:[-:]\s*.*)?", s)
        if m and "abcd".index(m.group(1)) < len(opts):
            return "abcd".index(m.group(1))
        m = re.fullmatch(r"(?:option\s*)?([1-4])[.)]?", s)
        if m and int(m.group(1)) <= len(opts) and not any(o.strip() == m.group(1) for o in opts):
            return int(m.group(1)) - 1
        for k, o in enumerate(opts):
            if s == o.strip().lower().rstrip("."):
                return k
        return None

    def _do_quiz_answer(self, state: dict, text: str, route: Route) -> Reply:
        qz = state["quiz"]
        lesson = LESSON[qz["lesson"]]
        item = lesson["mcq"][qz["order"][qz["i"]]]
        perm = qz["opts"].get(str(qz["i"])) or list(range(len(item["options"])))
        chosen = item["options"][perm[route.payload["choice"]]]
        right = next(o for o in item["options"] if o[1])
        answer = next(k for k, j in enumerate(perm) if item["options"][j][1])
        last = qz["i"] + 1 == len(qz["order"])
        self._mark_quiz_card(state, qz["i"] + 1, route.payload["choice"], answer,
                             [qz["score"] + bool(chosen[1]), len(qz["order"])] if last else None)
        if chosen[1]:
            qz["score"] += 1
            out = f"✅ **Right.** {chosen[2]}"
        else:
            reason = re.sub(r"^Right[:,.!]\s*", "", right[2])          # the reason is written for picking it
            out = f"❌ **Not quite.** {chosen[2]}\n\nThe answer is **{right[0]}**: {reason[:1].upper() + reason[1:]}"
        qz["i"] += 1
        cards: list[dict] = []
        sugg: list[str] = []
        if qz["i"] < len(qz["order"]):
            q_text, card = self._quiz_question(state)
            out += "\n\n" + q_text
            cards.append(card)
        else:
            n, sc = len(qz["order"]), qz["score"]
            self.students.update_lesson(state["sid"], qz["lesson"], check_score=sc / n)
            out += f"\n\n**You got {sc} out of {n}.** " + ("Great work! " if sc == n else "")
            state["quiz"] = None
            lid = qz["lesson"]
            if sc < n:
                sugg.append(f"Explain {SHORT[lid]} again")
            if lesson.get("practice_topic"):
                sugg.append(f"Give me {PRACTICE_NAME[lesson['practice_topic']]} problem")
            nxt = LESSONS[(LESSONS.index(lesson) + 1) % len(LESSONS)]
            sugg.append(f"Quiz me on {SHORT[nxt['id']]}")
        return Reply("quiz_answer", text=out, cards=cards, suggestions=sugg, meta={"source": "lesson quiz (checked by hand)"})

    def _do_quiz_stop(self, state: dict, text: str, route: Route) -> Reply:
        qz = state["quiz"]
        state["quiz"] = None
        return Reply("quiz_stop", text=f"Quiz stopped. You had {qz['score']} right so far. What next?",
                     suggestions=["Give me a problem", "How am I doing?"])

    # ------------------------------------------------------------------ actions: teach-back
    def _do_teachback(self, state: dict, text: str, route: Route) -> Reply:
        lid = route.topic or self._default_lesson(state)
        state["topic"] = lid
        state["teachback"] = {"lesson": lid}
        lesson = LESSON[lid]
        return Reply("teachback", text=(f"Go ahead: explain **{lesson['title']}** in your own words, as if to a friend "
                                        "who missed the class. A few sentences is enough. I'll tell you what you "
                                        "covered and what's missing."),
                     suggestions=[], meta={"topic": lid})

    def _do_teachback_stop(self, state: dict, text: str, route: Route) -> Reply:
        state["teachback"] = None
        return Reply("teachback_stop", text="No problem. What would you like to do instead?",
                     suggestions=["Explain it to me first", "Give me a problem"])

    def _do_teachback_assess(self, state: dict, text: str, route: Route) -> Reply:
        lid = state["teachback"]["lesson"]
        lesson = LESSON[lid]
        if not teachback.enough_to_assess(text):              # keep waiting for a real explanation
            return Reply("teachback", text=f"That doesn't look like an explanation of **{lesson['title']}** yet. Tell me "
                                           "in your own words, in a few sentences, how it works. Or say *stop* to do "
                                           "something else.")
        state["teachback"] = None
        assessment = teachback.assess(lesson, text, self.client if self.online else None)
        ptr = teachback.pointers(lesson, assessment, [])
        self.students.record_teachback(state["sid"], lid, text, assessment)
        gaps = ptr["missing"] + ptr["partial"]
        state["last_gaps"] = gaps or None
        lines = [f"**{ptr['verdict']}.**"]
        if ptr["clear"]:
            lines.append("You explained clearly:\n" + "\n".join(f"- ✅ {s}" for s in ptr["clear"]))
        if ptr["partial"]:
            lines.append("Partly there:\n" + "\n".join(f"- 🟡 {s}" for s in ptr["partial"]))
        if ptr["missing"]:
            lines.append("Not mentioned yet:\n" + "\n".join(f"- ⬜ {s}" for s in ptr["missing"]))
        if ptr["misconceptions"]:
            lines.append("Watch out:\n" + "\n".join(f"- ⚠️ {s}" for s in ptr["misconceptions"]))
        short = SHORT[lid]
        sugg = (["Explain the parts I missed"] if gaps else []) + [f"Quiz me on {short}"]
        if lesson.get("practice_topic"):
            sugg.append(f"Give me {PRACTICE_NAME[lesson['practice_topic']]} problem")
        return Reply("teachback_assess", text="\n\n".join(lines), suggestions=sugg,
                     meta={"source": assessment.get("source", "rubric"), "topic": lid})

    # ------------------------------------------------------------------ actions: progress
    def _do_menu(self, state: dict, text: str, route: Route) -> Reply:
        """Everything the tutor teaches, grouped, with the next few topics as buttons (no LLM: it must be exact)."""
        now = state.get("topic")
        lines, group = [], None
        for l in LESSONS:
            if l["group"] != group:
                group = l["group"]
                lines.append(f"\n**{group}**")
            lines.append(f"- {l['title']}" + (" *(where we are now)*" if l["id"] == now else ""))
        order = [l["id"] for l in LESSONS]
        start = order.index(now) + 1 if now in order else 0
        nxt = [order[(start + k) % len(order)] for k in range(3)]
        text_out = ("Here is everything I can teach you:\n" + "\n".join(lines) +
                    "\n\nFor each one I can explain it, give you problems to solve (and check your answers), quiz you, "
                    "or listen while you explain it back. You can also open **Learn** for step-by-step lessons, **Labs** "
                    "to try your own numbers, or **Exam** for a timed mock CAT paper. Which one would you like?")
        sugg = [f"Explain {SHORT[l]}" for l in nxt] + ["Give me a problem"]
        return Reply("menu", text=text_out, suggestions=sugg, meta={"source": "template"})

    def _do_progress(self, state: dict, text: str, route: Route) -> Reply:
        sid = state["sid"]
        m = self.students.mastery(sid)
        rec = self.students.recommend_next(sid)
        recurring = self.students.recurring_errors(sid)
        seen = [v for v in m.values() if v["n_obs"] > 0]
        rec_name = TOPIC_NAMES.get(rec["topic"], rec["topic"])
        if not seen:
            out = ("You haven't solved any problems yet, so every skill starts at the same estimate. "
                   f"I'd start with **{rec_name}**.")
        else:
            best = max(seen, key=lambda v: v["p_known"])
            worst = min(seen, key=lambda v: v["p_known"])
            if len(seen) == 1:
                out = f"So far you've practised **{best['name']}**, estimated at {best['p_known']:.0%} mastery."
            else:
                out = (f"Strongest so far: **{best['name']}** ({best['p_known']:.0%}). "
                       f"Needs the most work: **{worst['name']}** ({worst['p_known']:.0%}).")
            if recurring:
                out += "\n\nA mistake you've repeated: " + "; ".join(f"**{r['label']}** ({r['count']} problems)" for r in recurring[:2]) + "."
            why = rec["reason"].rstrip(".")
            out += f"\n\nNext, I'd suggest **{rec_name}**. Why: {why[0].lower() + why[1:]}."
        lid = ALGO_LESSON.get(rec["topic"], "basics")
        card = {"type": "progress", "skills": [{"name": v["name"], "p": round(v["p_known"], 3), "n": v["n_obs"]}
                                               for v in m.values()]}
        sugg = [f"Give me {PRACTICE_NAME.get(rec['topic'], 'a')} problem", f"Explain {SHORT[lid]}",
                f"Quiz me on {SHORT[lid]}"]
        return Reply("progress", text=out, cards=[card], suggestions=sugg, meta={"source": "student model (BKT)"})


# ============================================================================ helpers
SOURCE_STOP = set("the a an and or of to in on for is are be it its this that with as at by from can each when which what "
                  "how why does do not only all any one two into than then there their they them was were has have".split())


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in SOURCE_STOP}


def _excerpt(body: str, query: str, keep: int = 3) -> str:
    """The sentences of a notes passage that matter for this question, in their original order and never cut mid-word
    (the whole passage when it is short). Verbatim on purpose: this box shows the teacher's own words."""
    if len(body) <= 450:
        return body
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'])", body) if s.strip()]
    want = _words(query)
    ranked = sorted(range(len(sents)), key=lambda k: (-len(_words(sents[k]) & want), k))
    chosen = sorted(ranked[:keep])
    out = ""
    for prev, k in zip([None] + chosen, chosen):
        out += ("" if prev is None and k == 0 else " … " if prev is None or k != prev + 1 else " ") + sents[k]
    return out.strip() + (" …" if chosen[-1] != len(sents) - 1 else "")


def _source_label(meta: dict) -> str:
    src = meta.get("source", "")
    m = re.search(r"Module \d+", src)
    short = f"{m.group(0)} notes" if m else ("OSTEP textbook" if "OSTEP" in src or meta.get("type") == "Textbook (OSTEP)"
                                             else meta.get("type", "Notes"))
    page = f", p.{meta['page']}" if meta.get("page") else ""
    return f"{short} · {meta.get('section') or src}{page}"


def _sources_card(chunks: list[dict], title: str, query: str = "") -> dict:
    items = []
    for i, c in enumerate(chunks, start=1):
        meta = c.get("meta", {})
        text, section = c["text"], meta.get("section") or ""
        at = text.find(section) if section else -1          # stored as "Module 3 class notes: topic — section: body"
        body = text[at + len(section):].lstrip(": ").strip() if at >= 0 else text.split(": ", 1)[-1]
        items.append({"n": i, "label": _source_label(meta), "text": _excerpt(body, query + " " + section),
                      "full": body[:3000]})
    return {"type": "sources", "title": title, "items": items}


def _example_facts(lesson: dict) -> str:
    w = lesson.get("watch") or {}
    if w.get("kind") == "scheduling":
        res = scheduling.run(w["algorithm"], w["processes"], w.get("quantum"))
        procs = ", ".join(f"{p.pid} (AT {p.arrival}, BT {p.burst}" + (f", priority {p.priority}" if w["algorithm"].startswith("PRIORITY") else "") + ")"
                          for p in w["processes"])
        chart = ", ".join(f"{s.pid} {s.start}-{s.end}" for s in res.gantt)
        q = f", q = {w['quantum']}" if w.get("quantum") else ""
        return f"{ALGORITHMS[w['algorithm']]}{q}; processes {procs}; Gantt chart {chart}; average WT {res.avg_wt:.2f}."
    if w.get("kind") == "bankers":
        return "the textbook Banker's example (5 processes, 3 resource types), with the safe sequence found step by step."
    if w.get("kind") == "semaphore":
        return w.get("intro", "a semaphore trace")
    return ""


def _solution_facts(problem) -> tuple[list[str], str]:
    kind = problem.kind
    if kind == "scheduling":
        res = problem.solve()
        steps = scheduling_steps(res)
        facts = [f"Problem: {problem.statement()}"]
        facts += [f"{s['event']} {s['reason']}" for s in steps]
        facts.append("Gantt chart: " + ", ".join(f"{s.pid} {s.start}-{s.end}" for s in res.gantt))
        facts += [f"{p.pid}: CT {res.results[p.pid].completion}, TAT {res.results[p.pid].turnaround}, "
                  f"WT {res.results[p.pid].waiting}" for p in problem.processes]
        facts.append(f"Average TAT {res.avg_tat:.2f}, average WT {res.avg_wt:.2f}")
        shown = steps[:8]
        fallback = "Here's how the engine builds the schedule:\n\n" + "\n".join(
            f"{i}. {s['event']} {s['reason']}" for i, s in enumerate(shown, start=1))
        if len(steps) > len(shown):
            fallback += f"\n\n…and {len(steps) - len(shown)} more decisions in the same way (all of them are in the card)."
        fallback += f"\n\nAverage TAT = **{res.avg_tat:.2f}**, average WT = **{res.avg_wt:.2f}**. The full chart and table are below."
        return facts, fallback
    if kind == "bankers":
        eng = problem.solve()
        facts = [f"Need = Max − Allocation: " + "; ".join(f"P{i} {' '.join(map(str, r))}" for i, r in enumerate(eng["need"]))]
        vec = lambda xs: "(" + ", ".join(map(str, xs)) + ")"
        for s in eng["steps"]:
            facts.append(f"Step {s['step']}: {s['process']} can finish, since Need {vec(s['need'])} ≤ Work "
                         f"{vec(s['work_before'])}; it releases {vec(s['allocation_released'])}, so Work becomes "
                         f"{vec(s['work_after'])}.")
        if eng["safe"]:
            facts.append("Safe. Safe sequence: " + ", ".join(eng["sequence"]))
            fallback = ("First compute **Need = Max − Allocation** for every process. Then start with Work = Available and "
                        "repeatedly pick a process whose Need ≤ Work; when it finishes, add its Allocation to Work.\n\n"
                        f"Every process can finish, so the state is **safe**, with sequence **{', '.join(eng['sequence'])}**. "
                        "Each step is in the table below.")
        else:
            facts.append("Unsafe. Processes that can never finish: " + ", ".join(eng["stuck"]))
            fallback = ("Compute **Need = Max − Allocation**, then keep finishing any process whose Need ≤ Work and add "
                        f"its Allocation back. Here, **{', '.join(eng['stuck'])}** can never finish, so the state is "
                        "**unsafe**. The steps are in the table below.")
        return facts, fallback
    if kind == "semaphore":
        eng = problem.solve()
        facts = [f"Step {s['step']}: {s['pid']} {s['op']}({s['sem']}): {s['value_before']} -> {s['value_after']}. {s['effect']}"
                 for s in eng["steps"]]
        facts.append(f"Final values {eng['final_values']}; blocked {eng['blocked'] or 'none'}")
        fallback = "Here's the trace, one operation at a time:\n\n" + "\n".join(f"- {f}" for f in facts)
        return facts, fallback
    res = problem.solve()
    facts = [f"{r.pid}: CT {r.completion}, TAT {r.turnaround}, WT {r.waiting}" for r in res.results.values()]
    fallback = "The engine's full solution is in the card below: the Gantt chart and every process's times."
    return facts, fallback


def _same_processes(payload: dict, problem) -> bool:
    procs = payload.get("processes") or []
    return {(p["pid"], p["arrival"], p["burst"]) for p in procs} == \
        {(p.pid, p.arrival, p.burst) for p in problem.processes}


def _jsonable_answer(ans: dict) -> dict:
    out = {}
    for k, v in ans.items():
        if k == "gantt" and v:
            out[k] = [list(x) for x in v]
        else:
            out[k] = v
    return out


def _slim_analysis(a: dict) -> dict:
    keep = ("kind", "correct", "gantt_given", "gantt_correct", "metrics_given", "metrics_correct", "cells",
            "divergence", "student_gantt", "need_cells", "sequence_check", "semaphore_mode", "wt_modes")
    out = {k: a.get(k) for k in keep if k in a}
    out["errors"] = [{k: e.get(k) for k in ("type", "label", "category", "count", "misconception")}
                     for e in a.get("errors", [])]
    out["root_cause"] = {k: a["root_cause"].get(k) for k in ("type", "label", "category")} if a.get("root_cause") else None
    if out.get("student_gantt"):
        out["student_gantt"] = [list(x) for x in out["student_gantt"]]
    return json.loads(json.dumps(out, default=str))


def _metric_story(res, pid: str) -> str:
    """Where one process's CT, TAT and WT come from, from the engine's schedule."""
    r = res.results[pid]
    runs = [g for g in res.gantt if g.pid == pid]
    others = [g for g in res.gantt if g.pid not in (pid, scheduling.IDLE) and g.end > r.arrival and g.start < r.completion]
    ran = ", ".join(f"{g.start}–{g.end}" for g in runs)
    busy = ", ".join(f"{g.pid} ({max(g.start, r.arrival)}–{g.end})" for g in others)
    out = (f"**{pid}** arrived at **{r.arrival}** and needs **{r.burst}** units of CPU. It ran {ran}, so it finished at "
           f"**{r.completion}**.\n\n- TAT = CT − AT = {r.completion} − {r.arrival} = **{r.turnaround}**\n"
           f"- WT = TAT − BT = {r.turnaround} − {r.burst} = **{r.waiting}**")
    if r.waiting and busy:
        out += f"\n\nThose {r.waiting} units are time it spent in the ready queue while the CPU ran {busy}."
    elif not r.waiting:
        out += "\n\nIt never waited: the CPU was free whenever it was ready."
    return out


def _with_check_question(text: str, problem) -> str:
    """Replace the reply's closing question with one about a real engine decision: a preemption if there was one,
    else the second dispatch ("Why does P2 get the CPU at t = 5?")."""
    paras = text.rstrip().split("\n\n")
    if paras and paras[-1].rstrip().endswith("?"):
        paras = paras[:-1]
    ds = [d for d in problem.solve().decisions if d.kind != "idle" and d.chosen and d.chosen != scheduling.IDLE]
    pick = next((d for d in ds if d.kind == "preempt"), ds[1] if len(ds) > 1 else (ds[0] if ds else None))
    if pick is None:
        return "\n\n".join(paras)
    return "\n\n".join(paras + [f"Quick check: why does **{pick.chosen}** get the CPU at t = {pick.time}?"])


def _with_bankers_question(text: str, problem) -> str:
    """Replace the reply's closing question with one about the safety algorithm's own steps."""
    paras = text.rstrip().split("\n\n")
    if paras and paras[-1].rstrip().endswith("?"):
        paras = paras[:-1]
    eng = problem.solve()
    if eng["safe"] and eng["steps"]:
        s = eng["steps"][0]
        q = f"Quick check: why can **{s['process']}** finish first, and what does Work become after it?"
    elif eng["stuck"]:
        q = f"Quick check: what does **{eng['stuck'][0]}** still need, and why can't Work ever cover it?"
    else:
        return "\n\n".join(paras)
    return "\n\n".join(paras + [q])
