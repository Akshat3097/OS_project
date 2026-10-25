"""
Write the Ollama Modelfiles for the customized tutor (all share the same persona as the training data).

    python -m qlora.make_modelfiles

  qlora/Modelfile.prompt   -> os-tutor-prompt : llama3.1:8b + persona + two example exchanges (works right away)
  qlora/Modelfile          -> os-tutor        : the merged GGUF from the notebook (hand-written reference)
  qlora/Modelfile.adapter  -> os-tutor        : the ADAPTER route, kept for older Ollama versions only

The fine-tuned model is normally created by `python -m qlora.create_finetuned` (writes qlora/Modelfile.gguf with
the exact chat template of your installed llama3.1:8b). Recent Ollama versions reject ADAPTER with
"LoRA adapters are no longer supported", which is why the notebook merges the adapter and exports one GGUF file.

Then:  ollama create os-tutor-prompt -f qlora/Modelfile.prompt   (and so on; see setup_ollama_models.bat)
"""
from pathlib import Path

from qlora.chat_style import CHAT_SYSTEM

HERE = Path(__file__).resolve().parent

PARAMS = """PARAMETER temperature 0.3
PARAMETER num_ctx 4096
PARAMETER stop "<|eot_id|>"
"""

EXAMPLES = [
    ("Explain round robin",
     "Think of **cricket nets practice**. Each batter gets 6 balls (the time quantum), then goes to the back of the "
     "line, even if they wanted more. A batter who gets out on ball 3 leaves early and the next one starts at once.\n\n"
     "Round Robin works the same way:\n"
     "- Keep a FIFO ready queue. The process at the front runs for at most one time quantum q.\n"
     "- If it finishes within q, it leaves and the next process starts immediately.\n"
     "- If not, the timer interrupts it and it goes to the back of the queue.\n"
     "- Your course's convention: a process that arrives exactly when a slice ends joins the queue before the "
     "preempted process.\n\n"
     "Quick check: q = 4 and a process needs 3 more units. What happens after it has run for 3 units?"),
    ("My FCFS answer: P1 (AT 0, BT 5) CT 5, TAT 5, WT 5; P2 (AT 2, BT 3) CT 8, TAT 6, WT 6. Is it right?",
     "Your completion and turnaround times are right. The waiting times aren't: for P1 you wrote 5, the same as its "
     "TAT. Turnaround is the whole stay in the system, including the time P1 was actually running on the CPU.\n\n"
     "What do you subtract from TAT to get only the time it spent waiting?"),
]


def _block(text: str) -> str:
    assert '"""' not in text
    return f'"""{text}"""'


def write() -> list[Path]:
    persona = f"SYSTEM {_block(CHAT_SYSTEM)}\n"
    shots = "".join(f"MESSAGE user {_block(u)}\nMESSAGE assistant {_block(a)}\n" for u, a in EXAMPLES)
    files = {
        "Modelfile.prompt": ("# os-tutor-prompt: customized by instructions and examples only (no training)\n"
                             "#   ollama create os-tutor-prompt -f qlora/Modelfile.prompt\n"
                             f"FROM llama3.1:8b\n{persona}{PARAMS}{shots}"),
        "Modelfile.adapter": ("# OLDER OLLAMA ONLY. Recent versions reply \"LoRA adapters are no longer supported\";\n"
                              "# use the merged GGUF instead:  python -m qlora.create_finetuned\n"
                              "#   (old route) unzip os-tutor-lora.zip into qlora/os-tutor-lora, then\n"
                              "#   ollama create os-tutor -f qlora/Modelfile.adapter\n"
                              f"FROM llama3.1:8b\nADAPTER ./os-tutor-lora\n{persona}{PARAMS}"),
        "Modelfile": ("# os-tutor from the merged GGUF the notebook exports (save it as qlora/os-tutor.gguf).\n"
                      "# Easiest:  python -m qlora.create_finetuned   (adds the exact chat template for you)\n"
                      "# By hand:  ollama create os-tutor -f qlora/Modelfile\n"
                      "# If replies look garbled, copy the TEMPLATE block from:  ollama show llama3.1:8b --modelfile\n"
                      f"FROM ./os-tutor.gguf\n{persona}{PARAMS}"),
    }
    out = []
    for name, text in files.items():
        p = HERE / name
        p.write_text(text, encoding="utf-8")
        out.append(p)
    return out


if __name__ == "__main__":
    for p in write():
        print("wrote", p)
