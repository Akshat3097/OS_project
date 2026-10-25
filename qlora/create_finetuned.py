"""
Create the fine-tuned `os-tutor` model in Ollama from the merged GGUF the notebook exports.

    python -m qlora.create_finetuned                 # looks for qlora/os-tutor.gguf (or any *Q4_K_M*.gguf in qlora/)
    python -m qlora.create_finetuned path/to/file.gguf
    python -m qlora.create_finetuned --name os-tutor-v2   # second round: looks for qlora/os-tutor-v2.gguf

Recent Ollama versions no longer accept LoRA adapters (ADAPTER), so the adapter is merged into the model in
Colab and exported as a single GGUF file. This script copies the chat TEMPLATE from your installed
llama3.1:8b (so the prompt format matches exactly), adds the tutor persona, writes qlora/Modelfile.gguf and
runs `ollama create os-tutor`.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from qlora.chat_style import CHAT_SYSTEM

HERE = Path(__file__).resolve().parent
STOPS = ["<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>"]


def find_gguf(arg: str | None, name: str = "os-tutor") -> Path:
    if arg:
        p = Path(arg).expanduser().resolve()
        if not p.exists():
            raise SystemExit(f"File not found: {p}")
        return p
    preferred = HERE / f"{name}.gguf"
    if preferred.exists():
        return preferred
    if name != "os-tutor":                       # never fall back to the first model's file for v2
        raise SystemExit(f"Not found: {preferred}. Download {name}.gguf from Google Drive and save it there.")
    cands = sorted([p for p in HERE.rglob("*.gguf") if "q4_k_m" in p.name.lower()] or list(HERE.rglob("*.gguf")),
                   key=lambda p: p.stat().st_size)
    if not cands:
        raise SystemExit("No .gguf file found. Download os-tutor.gguf from Google Drive and save it as qlora\\os-tutor.gguf")
    return cands[0]


def base_template() -> str:
    try:
        out = subprocess.run(["ollama", "show", "llama3.1:8b", "--template"], capture_output=True, text=True,
                             encoding="utf-8", timeout=60)
    except FileNotFoundError:
        raise SystemExit("The 'ollama' command was not found. Is Ollama installed and running?")
    tpl = out.stdout or ""
    if tpl.endswith("\n"):                       # the newline `ollama show` prints after the template
        tpl = tpl[:-1]
    if out.returncode != 0 or "<|start_header_id|>" not in tpl:
        print("Could not read the llama3.1:8b template; using a standard Llama 3 template instead.")
        tpl = ("{{ if .System }}<|start_header_id|>system<|end_header_id|>\n\n{{ .System }}<|eot_id|>{{ end }}"
               "{{ if .Prompt }}<|start_header_id|>user<|end_header_id|>\n\n{{ .Prompt }}<|eot_id|>{{ end }}"
               "<|start_header_id|>assistant<|end_header_id|>\n\n{{ .Response }}<|eot_id|>")
    return tpl


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("gguf", nargs="?", help="the .gguf file (default: qlora/<name>.gguf)")
    ap.add_argument("--name", default="os-tutor", help="the Ollama model to create (default: os-tutor)")
    args = ap.parse_args()
    name = args.name
    gguf = find_gguf(args.gguf, name)
    size_gb = gguf.stat().st_size / 1e9
    print(f"Using {gguf} ({size_gb:.1f} GB)")
    if size_gb < 1:
        raise SystemExit("That file is too small to be the model; the download may not have finished.")
    tpl = base_template()
    if '"""' in tpl:
        raise SystemExit("Unexpected template format; send a screenshot of this message.")
    try:
        source = "./" + gguf.relative_to(HERE).as_posix()
    except ValueError:
        source = gguf.as_posix()
    modelfile = HERE / ("Modelfile.gguf" if name == "os-tutor" else f"Modelfile.{name}")
    modelfile.write_text(f"# {name}: Llama 3.1 8B fine-tuned with QLoRA (merged GGUF). Created by qlora/create_finetuned.py\n"
                         f"FROM {source}\n", encoding="utf-8")
    with open(modelfile, "a", encoding="utf-8") as f:
        f.write(f'TEMPLATE """{tpl}"""\n')
        f.write(f'SYSTEM """{CHAT_SYSTEM}"""\n')
        f.write("PARAMETER temperature 0.3\nPARAMETER num_ctx 4096\n")
        for s in STOPS:
            f.write(f'PARAMETER stop "{s}"\n')
    print(f"Wrote {modelfile}. Creating {name} in Ollama (copies the 4.9 GB file once, about a minute)...")
    r = subprocess.run(["ollama", "create", name, "-f", str(modelfile)])
    if r.returncode != 0:
        raise SystemExit("ollama create failed; send a screenshot of the message above.")
    print(f"\nDone. Try:  ollama run {name}     or:  python -m eval.chat_eval")


if __name__ == "__main__":
    main()
