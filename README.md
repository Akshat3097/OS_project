# Adaptive OS Tutor (BCSE303P project)

An LLM-based adaptive tutor for **CPU scheduling** and **process synchronization**.
The design keeps two jobs separate:

* **Deterministic code** (the *OS Engine*) computes and verifies every answer, finds the student's mistake, tracks their learning profile and decides the teaching strategy.
* **The LLM** (Llama 3.1 8B via Ollama, fine-tuned with QLoRA) only *phrases* the explanation, using facts the engine gives it. A guard blocks replies that leak the answer when the student is supposed to find it.

```
Student → UI → OS Engine (verify) → Error analysis → Student model (BKT) → Teaching strategy
                                                                   ↓ facts + instruction
                                              RAG course notes → LLM (Ollama) → Guard → feedback
```

## Quick start (Windows)

1. Install **Python 3.11 or newer** (python.org, tick "Add to PATH") and **Ollama** (ollama.com).
2. Double-click **`setup.bat`** once. It creates `.venv`, installs the packages (including faster-whisper for the
   microphone), builds the notes index, starts Ollama, pulls `llama3.1:8b` and `nomic-embed-text`, creates
   `os-tutor-prompt` (and `os-tutor` if `qlora\os-tutor.gguf` is there) and downloads the speech model. Running it
   again only adds what is missing.
3. Double-click **`start.bat`** every time. It starts Ollama if needed, loads the tutor model on the GPU so the first
   reply is quick, and opens the web app at http://localhost:8000.

To see what is installed and what is missing: `.venv\Scripts\python -m server.doctor`.
The older interfaces still start with `run_windows.bat` (Streamlit chat) and `run_classic.bat` (the original tabs).

The app also works **without Ollama** (feedback falls back to templates built from the same verified facts), which is useful if the GPU is busy.

**VRAM:** `llama3.1:8b` (4-bit, ~5 GB) + `nomic-embed-text` (~0.3 GB) fit together on an 8 GB GPU.

## The web app (FastAPI + React)

The same tutor as a proper web page: conversation history in a sidebar, streamed replies, Gantt charts, an answer
sheet with a live preview of your chart, and light and dark themes.

```bat
.venv\Scripts\python -m server
```
It opens http://localhost:8000 in your browser (`--port 9000` to change the port, `--no-browser` to skip opening it).
The page is already built (`web/dist`), so only Python is needed.

* `server/api.py`: FastAPI. `POST /api/message` streams the reply as one JSON object per line
  (`delta` pieces, then `done` with the cards); `/api/chat`, `/api/chats`, `/api/status`. Interactive API docs at
  http://localhost:8000/docs.
* `server/cards.py`: turns the agent's cards into JSON, computing every Gantt chart and table with the OS Engine.
* `web/`: the React page (Vite). To change it: install Node.js, then `cd web`, `npm install`, `npm run dev`
  (opens on :5173 and forwards `/api` to the Python server), and `npm run build` to update `web/dist`.

Both chat interfaces use the same conversation logic (`tutor/chat_agent.py`) and saved chats (`data/chats/`).

## The chat interface in Streamlit (`chat_app.py`)

One conversation, like talking to a tutor. The student says what they want and the tutor picks the tool:

| You type | What happens |
|---|---|
| "explain SRTF like I'm new to it", "explain it differently" | The lesson and your class notes are given to the LLM; a worked example solved by the engine appears as a card. |
| A question pasted from a paper (tables, `P1(0,5)`, `P1 AT=0 BT=5`, column lists, Banker's matrices) | The problem is read and shown back as a table. You choose: try it first (answers are checked step by step) or see the full solution. "Now solve it with RR q=2" re-runs it with another algorithm. |
| "give me a hard Round Robin problem", "another one", "something harder", "a past paper question" | Adaptive practice: topic and difficulty come from the student model unless you say otherwise. |
| An answer: `P1 0-3, P2 3-5`, `P1: CT 9, TAT 9, WT 4`, a CT/TAT/WT table, `safe: P1, P3, P0`, `S = -1, blocked: P3` | Checked by the OS Engine: first mistake, a hint (not the answer), mastery update. Parts can be sent separately, or use the answer form. |
| "hint", "show me the solution", "why does P2 run at 3?" | Hints escalate; the full solution comes as a card with every decision. |
| "quiz me on deadlocks", "let me explain semaphores", "how am I doing?" | Multiple-choice quiz, teach-back with a rubric, or progress from the student model. |

Each turn is routed by rules when the intent is clear (fast and predictable) and by the LLM (JSON) otherwise, with a
keyword fallback. Numbers always come from the engine, and replies that carry numbers are guarded. Turn on
*Show how each reply was made* in the sidebar to see the route, the strategy, the engine facts and the guard result.
Conversations are saved per student in `data/chats/`. The logic is in `tutor/chat_agent.py` (routing and tools) and
`tutor/chat_parse.py` (reading problems and answers).

## The classic interface (`app.py`)

| Tab | What it shows |
|---|---|
| 📘 Learn | 10 lessons that teach from scratch: **Understand** (real-life examples first, then the rule, then *📒 What your class notes say*; "Explain it differently" asks the LLM for a new everyday example) → **Watch** (a worked example, one decision at a time) → **Explain it back** (the student explains the topic for a minute by voice or text; the tutor finds which key ideas they understood) → **Your question** (one engine-generated question on the weakest idea) → **Pointers** (what they got right, what to add, misconceptions, then practice). |
| 📝 Practice | Adaptive problems (FCFS, SJF, SRTF, RR, Priority, Banker's, semaphores), plus *📄 Past paper questions* and *📒 Class-notes examples* (the worked examples from your Module 3 notes). Enter a Gantt chart / metrics, get root-cause error analysis, hints that escalate, worked examples for recurring mistakes. The full solution also gives CPU utilisation, throughput and context switches, counted the way the notes count them. "Why this response?" shows the strategy, the verified facts sent to the LLM and the guard result. |
| 💬 Ask the tutor | Free questions answered from the course notes (RAG) with sources. |
| ⚙️ OS Engine | Run any algorithm on your own data, compare averages, see decision traces; Banker's safety and request; semaphore tracing. |
| 📈 My progress | Mastery per skill (Bayesian Knowledge Tracing), recurring misconceptions, interaction log, next recommendation. |
| 🏗️ How it works | Architecture and component status. |

**Demo shortcuts:** in Practice, open *Demo shortcuts* to fill a typical correct or wrong answer in one click.

## Voice input for "Explain it back"

Two ways, both work offline:
* **In-app microphone:** `pip install faster-whisper`. `setup.bat` downloads the speech model (`small.en`, about
  460 MB) and the server loads it at start-up. Plugged in, a one-minute answer is transcribed on the CPU in about 10 s.
  On battery it is much slower: set `TUTOR_WHISPER_MODEL=base.en` (about 3 s, but mishears more course terms).
  Set `TUTOR_WHISPER_DEVICE=cuda` to use the GPU.
* **Windows voice typing:** click in the text box and press **Win + H**. No setup.

The student can correct the transcript before pressing *Check my understanding*. With Ollama running, an LLM judge
rates each key idea (clear / partial / missing) and spots misconceptions; otherwise a keyword rubric does it.
Every explanation, its ratings and the follow-up questions are saved in `data/tutor.db` (table `teachbacks`).

## Course material already included (RAG)

`rag/sources/` already holds your course material, cleaned and split by topic:

| File | What it is |
|---|---|
| `notes_module3_cpu_scheduling.md` | Module 3 class notes, scheduling part: concepts, every worked example with its answers (FCFS, SJF, SRTF, priority, RR, RR with priority, I/O bursts, MLQ, MLFQ, multiprocessor), slide numbers in each heading |
| `notes_module3_deadlocks.md` | Module 3, deadlocks: conditions, RAG / wait-for graph, prevention, avoidance, Banker's Examples 1–2 with requests, detection, recovery, the Theory "Deadlock problem" worked out |
| `notes_module4_synchronization.md` | Module 4: IPC, race conditions, critical section, Peterson, Bakery, test-and-set / CAS, semaphores, monitors, bounded buffer, readers–writers, dining philosophers, UNIX IPC; plus the Theory slides (locks, condition variables, semaphores, concurrency bugs, threads) |
| `notes_module2_processes_and_extra_slides.md` | Module 2 process slides (states, PCB, queues, context switch) and the "Extra" OSTEP-based scheduling slides (MLFQ rules, lottery/stride, multiprocessor) |
| `notes_conventions_checked.md` | The conventions the notes use and the 4 slips the engine found in them |
| `cpu-intro.pdf`, `cpu-mechanisms.pdf`, `threads-*.pdf` | OSTEP chapters 4, 6 and 26–32 (from the Theory folder) |
| `pyq_bcse303_*.md` | Patterns and conventions from the past CAT papers |

Left out on purpose: Module 1 (introduction, OS structures), Module 5 and the Theory memory slides (memory management, paging, segmentation, virtual memory), system calls / fork / exec, and the Lab folder. They are outside this tutor's two topics.

To add more, put PDFs, `.md` or `.txt` files in `rag/sources/`, then press **Rebuild** / **+ Embeddings** in the sidebar or run `python -m rag.ingest --embed`. File names tag the source type: `solution`/`answer` → Solutions, `pyq`/`paper`/`exam`/`cat1`/`fat` → Previous-year question paper, `notes`/`unit`/`module` → Teacher's notes, OSTEP chapter file names (`cpu-sched*.pdf`, `threads-*.pdf`) → Textbook (OSTEP). For a `.md` file, set `type:` in the front matter instead. Typed PDFs work; scanned PDFs need OCR first. When sources disagree, search slightly prefers your class notes, and the tutor is told to use their terms.

The OSTEP scheduling chapters (`cpu-sched.pdf`, `cpu-sched-mlfq.pdf`, `cpu-sched-lottery.pdf`, `cpu-sched-multi.pdf`) were not in the notes folder; you can add them from https://pages.cs.wisc.edu/~remzi/OSTEP/ (search understands OSTEP's names: STCF = SRTF, FIFO = FCFS).

**Question bank:** `data/question_bank/vit_bcse303_papers.json` holds 20 questions from 9 BCSE303L CAT papers, and
`data/question_bank/teacher_notes_examples.json` holds 33 worked examples from the class notes, each with the answer printed
in the paper or notes. `engine/advanced.py` solves the exam-style ones (I/O bursts, multilevel and multilevel feedback queues,
decimal times). To add more, copy `data/question_bank/TEMPLATE.json.example` to a new `.json` file. Run
`python -m engine.question_bank` to compare the engine with every official answer; a mismatch is either a different
convention (the script says which) or a slip in the key, explained in the item's `notes`.

## Project layout

```
engine/      OS Engine: scheduling.py, bankers.py, semaphore.py, generator.py
tutor/       error_analysis.py, student_model.py (SQLite + BKT), strategy.py, prompts.py (+ guard), llm.py, tutor.py,
             lessons.py + lesson_extras.py (Learn mode content), teachback.py (Explain it back), speech.py (Whisper),
             chat_agent.py (chat routing and tools), chat_parse.py (reading pasted problems and typed answers)
rag/         store.py (chunking, BM25, embeddings, rank fusion), ingest.py, knowledge/ (seed notes), sources/ (your files)
qlora/       chat data, Colab notebooks, train_unsloth.py, create_finetuned.py, Modelfiles, compare.py
eval/        run_eval.py (in-app feedback across model variants), chat_eval.py (the chat models on their own)
tests/       pytest suite (+ mock_ollama.py for testing without a GPU)
server/      FastAPI web server (api.py) and card data (cards.py); web/ the React page (dist/ = built)
chat_app.py  the chat interface in Streamlit; app.py, learn_ui.py the classic tabs; ui.py, config.py
data/question_bank/   past-paper questions and class-notes examples (JSON)
```

## Fine-tuning (QLoRA) and the terminal demo

**1. Show a customized model right away (no training).**
`qlora\setup_ollama_models.bat` creates `os-tutor-prompt`: Llama 3.1 8B plus the tutor's instructions and two example
exchanges (`qlora/Modelfile.prompt`). Then `ollama run os-tutor-prompt`, or

```bat
python -m qlora.compare                     # base vs customized, side by side, prompts from qlora/demo_prompts.txt
python -m qlora.compare "Explain SRTF"      # one prompt
python -m qlora.compare --chat --models os-tutor
```

**2. Train on a free GPU.** Open `qlora/train_colab.ipynb` in Google Colab (File → Upload notebook,
Runtime → T4 GPU → Run all) or Kaggle (Import notebook, GPU T4, Internet on). The data is built into the notebook.
Training takes about 40–60 minutes; the notebook then merges the LoRA adapter into the model, exports one GGUF file
(Q4_K_M, ~4.9 GB, ~20 more minutes) and copies it to Google Drive as `os-tutor.gguf`. It also downloads
`os-tutor-lora.zip` (~160 MB, the adapter alone) as a backup: if the session ends before the export, run
`qlora/export_gguf_colab.ipynb` with that zip instead of retraining.

**3. Load it into Ollama.** Download `os-tutor.gguf` from Drive, save it as `qlora\os-tutor.gguf` and run
`qlora\setup_ollama_models.bat` again (or `python -m qlora.create_finetuned`). It copies the chat template of your
installed `llama3.1:8b`, adds the tutor persona, writes `qlora/Modelfile.gguf` and creates `os-tutor`.
`python -m qlora.compare` then shows all three: base, prompt-customized and fine-tuned.

Why a merged file: recent Ollama versions reject `ADAPTER` lines with "LoRA adapters are no longer supported".
`qlora/Modelfile.adapter` is kept only for older versions.

**The training data** (`python -m qlora.build_chat_dataset`, then `python -m qlora.make_notebook`):

| Kind | Examples | Source |
|---|---|---|
| Worked solutions (6 scheduling algorithms, Banker's safety and requests, semaphore traces, notes and past-paper examples) | ~340 | Every number from the OS Engine |
| Checking a student's answer (first mistake → hint → answer if asked) | ~180 | Engine + error types the app detects |
| Class-notes questions (with module and slide numbers) | ~170 | `rag/sources/notes_*.md`, past-paper notes |
| Explanations, "explain it differently", quizzes, teach-back feedback | ~150 | The 10 lessons |
| Misconceptions, conventions, exam advice, scope | ~30 | Written by hand |
| App feedback in the strategy format (Practice tab) | ~470 | `python -m qlora.build_dataset` |

The persona text is in `qlora/chat_style.py` and is shared by the data and the Modelfiles. On your own GPU (WSL2):
`pip install unsloth` then `python qlora/train_unsloth.py`.

Note: `ollama run os-tutor` talks to the model alone, without the OS Engine, so its numbers are not checked. The app is
where every number is verified.

## Evaluation

```bat
python -m eval.run_eval --models llama3.1:8b os-tutor --n 60 --include-template
python -m eval.run_eval --models llama3.1:8b --no-rag
```
Reports answer-leak rate, unverified-number rate (hallucination proxy), guiding-question rate, length and latency on held-out scenarios. Learning gains are measured separately with a pre-test / post-test.

Chat models on their own (base vs prompt-customized vs fine-tuned), scored against the OS Engine:

```bat
python -m eval.chat_eval                         every installed one of llama3.1:8b, os-tutor-prompt, os-tutor
python -m eval.chat_eval --n 6                   quicker
```
Checks the average waiting time of fresh scheduling problems, Banker's safe/unsafe, 10 course-convention facts and
hint-first replies to a wrong answer; writes `eval/results_chat.md` (a table for the report).

## Tests

```bat
pip install pytest
python -m pytest -q
```
The engine is checked against textbook examples (Silberschatz: FCFS convoy, SJF, SRTF avg WT 6.5, RR q=4, priority, Banker's <P1, P3, P4, P0, P2> and request cases).

## Conventions (checked against the class notes and past answer keys)

* Ties → earlier arrival, then list order. SRTF / preemptive priority preempt only when strictly better.
* Priority: lower number = higher priority, unless the question says otherwise (the engine supports both).
* Round Robin: a process arriving exactly when a slice ends joins the queue before the preempted process.
* Waiting time with I/O: the notes' tables use WT = TAT − CPU (I/O counted as waiting); slide 19's formula excludes it.
  The tutor accepts both and tells the student which one they used.
* CPU utilisation and throughput use the total time from 0 to the last completion; context switches = changes from one
  process to another in the Gantt chart (an idle gap between two runs of the same process is not a switch).
* Multilevel feedback queue: new processes enter the top queue; using a whole quantum moves a process down one level.
  "Round Robin with priority" (Module 3, slide 86): a higher priority waits for the running time slice to end.
* Semaphores: the Module 4 notes define P/V with busy waiting (S never below 0); OSTEP and the Theory slides use the
  blocking version (−k = k waiting). The engine traces both and the tutor accepts either.
* Banker's: any valid safe sequence is accepted (the notes list several); the engine's own scan is cyclic.

If your course uses a different convention, the engine has options for it (`lower_is_higher`, `new_arrivals_first`,
`queue_preempt`, semaphore `style`).

## Troubleshooting

* *Ollama not reachable*: start the Ollama app or run `ollama serve`. If Ollama runs elsewhere, set `TUTOR_OLLAMA_URL`.
* *Model not in the list*: `ollama pull <model>` then refresh the page.
* *Want a fresh learning profile*: sidebar → Reset my progress (data lives in `data/tutor.db`).
