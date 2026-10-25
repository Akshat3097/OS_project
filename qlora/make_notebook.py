"""
Write the Colab/Kaggle notebooks:
  qlora/train_colab.ipynb       train (data built in, nothing to upload), merge, export os-tutor.gguf to Google Drive
  qlora/export_gguf_colab.ipynb export only, from os-tutor-lora.zip, if the training session ended before the export
  qlora/train_colab_v2.ipynb    second round: data v2, 2 epochs, checkpoints in Google Drive, os-tutor-v2.gguf
  qlora/train_colab_v3.ipynb    third round: data v3 (+ NotebookLM questions), 1 epoch, validation loss every
                                checkpoint and the best checkpoint kept (v2 reached a training loss of 0.04: memorised)

    python -m qlora.build_chat_dataset && python -m qlora.make_notebook
    python -m qlora.build_chat_dataset --student-frac 0.4 --out qlora/data/v2 && python -m qlora.make_notebook --v2
    python -m qlora.build_chat_dataset --student-frac 0.4 --extra qlora/data/notebooklm.jsonl --out qlora/data/v3
    python -m qlora.make_notebook --v3
"""
import base64
import gzip
import json
from pathlib import Path

from qlora.chat_style import CHAT_SYSTEM

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"


EXPORT_CODE = """
DO_GGUF = True
if DO_GGUF:
    model.save_pretrained_gguf("os-tutor-gguf", tokenizer, quantization_method="q4_k_m")
    print("export finished")
"""

COPY_CODE = """
import os, shutil
def find_q4():
    hits = []
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in ("drive", "sample_data") and not d.startswith(".")]
        hits += [os.path.join(root, f) for f in files if f.lower().endswith(".gguf") and "q4_k_m" in f.lower()]
    return hits
hits = find_q4()
assert hits, "No Q4_K_M .gguf file found. Did the export cell above finish without an error?"
src = max(hits, key=os.path.getsize)
print("model file:", src, f"({os.path.getsize(src) / 1e9:.1f} GB)")
if os.path.exists("/kaggle/working"):
    shutil.copy(src, "/kaggle/working/os-tutor.gguf")
    print("Kaggle: download os-tutor.gguf from the Output panel on the right.")
else:
    from google.colab import drive
    drive.mount("/content/drive")
    shutil.copy(src, "/content/drive/MyDrive/os-tutor.gguf")
    print("Copied to Google Drive -> My Drive -> os-tutor.gguf")
    print("Download it, save it on your laptop as qlora\\\\os-tutor.gguf and run qlora\\\\setup_ollama_models.bat")
"""


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n")}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": text.strip("\n")}


def build_cells_v1() -> list:
    raw = (DATA / "train_all.jsonl").read_bytes() + b"\n=====SPLIT=====\n" + (DATA / "val_all.jsonl").read_bytes()
    blob = base64.b64encode(gzip.compress(raw, 9)).decode()
    n_train = sum(1 for _ in open(DATA / "train_all.jsonl", encoding="utf-8"))
    cells = [
        md(f"""
# OS Tutor: QLoRA fine-tuning of Llama 3.1 8B

Fine-tunes Llama 3.1 8B Instruct on {n_train} tutoring examples (explanations, engine-verified worked solutions,
answer checking, quizzes, teach-back feedback, class-notes Q&A), merges the LoRA adapter into the model and exports
one GGUF file (~4.9 GB) for Ollama. (Recent Ollama versions no longer load LoRA adapters, hence the merged file.)

**Colab:** Runtime → Change runtime type → **T4 GPU**, then Runtime → **Run all**. Allow Google Drive access when
asked at the end: the model file is copied to *My Drive* as `os-tutor.gguf` (needs ~5 GB free in Drive).
**Kaggle:** Settings → Accelerator **GPU T4** and **Internet on**, then **Run all**. Download `os-tutor.gguf`
from the Output panel.

Takes about 60–80 minutes on a T4 (install ~3 min, model download ~3 min, training ~35–45 min, export ~20 min).
Then on your laptop: save the file as `qlora\\os-tutor.gguf` and run `qlora\\setup_ollama_models.bat`.
If the session ends before the export, don't retrain: use `export_gguf_colab.ipynb` with `os-tutor-lora.zip`.
"""),
        code("""
!nvidia-smi --query-gpu=name,memory.total --format=csv
!pip install -q unsloth
"""),
        md("## 1. Training data (built in)"),
        code(f"""
import base64, gzip, json, os, pathlib
DATA = "{blob}"
raw = gzip.decompress(base64.b64decode(DATA)).decode("utf-8")
train_txt, val_txt = raw.split("\\n=====SPLIT=====\\n")
pathlib.Path("data").mkdir(exist_ok=True)
open("data/train.jsonl", "w", encoding="utf-8").write(train_txt)
open("data/val.jsonl", "w", encoding="utf-8").write(val_txt)
print(len(train_txt.splitlines()), "training examples,", len(val_txt.splitlines()), "validation examples")
print(json.loads(train_txt.splitlines()[0])["messages"][1]["content"][:300])
"""),
        md("## 2. Settings"),
        code("""
import torch
EPOCHS = 1            # 1 is enough to change the style; 2 fits the data more closely (twice the time)
MAX_SEQ = 2048
LORA_R = 16
LR = 2e-4
gpu_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
BATCH, ACCUM = (2, 4) if gpu_gb > 12 else (1, 8)      # effective batch 8 either way
print(f"GPU memory {gpu_gb:.0f} GB -> batch {BATCH} x accumulation {ACCUM}")
"""),
        md("## 3. Load Llama 3.1 8B in 4-bit and add LoRA adapters"),
        code("""
from unsloth import FastLanguageModel, is_bfloat16_supported
from unsloth.chat_templates import get_chat_template, train_on_responses_only

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit", max_seq_length=MAX_SEQ, load_in_4bit=True)
model = FastLanguageModel.get_peft_model(
    model, r=LORA_R, lora_alpha=LORA_R, lora_dropout=0, bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    use_gradient_checkpointing="unsloth", random_state=3407)
tokenizer = get_chat_template(tokenizer, chat_template="llama-3.1")
model.print_trainable_parameters()
"""),
        md("## 4. Train (loss only on the tutor's replies)"),
        code("""
import inspect
from datasets import load_dataset
from trl import SFTConfig, SFTTrainer

ds = load_dataset("json", data_files={"train": "data/train.jsonl", "validation": "data/val.jsonl"})
def to_text(batch):
    return {"text": [tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=False) for m in batch["messages"]]}
ds = ds.map(to_text, batched=True, remove_columns=ds["train"].column_names)

cfg = dict(dataset_text_field="text", per_device_train_batch_size=BATCH, gradient_accumulation_steps=ACCUM,
           warmup_steps=10, num_train_epochs=EPOCHS, learning_rate=LR, logging_steps=10, optim="adamw_8bit",
           weight_decay=0.01, lr_scheduler_type="linear", seed=3407, bf16=is_bfloat16_supported(),
           fp16=not is_bfloat16_supported(), output_dir="checkpoints", report_to="none", save_strategy="no")
names = inspect.signature(SFTConfig.__init__).parameters
cfg["max_seq_length" if "max_seq_length" in names else "max_length"] = MAX_SEQ
common = dict(model=model, train_dataset=ds["train"], eval_dataset=ds["validation"], args=SFTConfig(**cfg))
try:
    trainer = SFTTrainer(tokenizer=tokenizer, **common)
except TypeError:
    trainer = SFTTrainer(processing_class=tokenizer, **common)
trainer = train_on_responses_only(trainer,
    instruction_part="<|start_header_id|>user<|end_header_id|>\\n\\n",
    response_part="<|start_header_id|>assistant<|end_header_id|>\\n\\n")
stats = trainer.train()
print(stats)
print(trainer.evaluate())
"""),
        md("## 5. Try it"),
        code(f"""
FastLanguageModel.for_inference(model)
SYSTEM = {json.dumps(CHAT_SYSTEM)}
for q in ["Explain SRTF to me like I'm new to it",
          "In round robin, if a new process arrives exactly when the quantum ends, who goes first?",
          "Quiz me on deadlocks"]:
    msgs = [{{"role": "system", "content": SYSTEM}}, {{"role": "user", "content": q}}]
    ids = tokenizer.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda")
    out = model.generate(input_ids=ids, max_new_tokens=350, temperature=0.3, do_sample=True)
    print("\\n>>>", q, "\\n" + tokenizer.decode(out[0][ids.shape[1]:], skip_special_tokens=True))
"""),
        md("## 6. Save the adapter (small backup, ~160 MB)"),
        code("""
import shutil
model.save_pretrained("os-tutor-lora")                  # adapter only
tokenizer.save_pretrained("os-tutor-lora")              # so the zip is self-contained
shutil.make_archive("os-tutor-lora", "zip", "os-tutor-lora")
print(sorted(os.listdir("os-tutor-lora")))
if os.path.exists("/kaggle/working"):
    shutil.copy("os-tutor-lora.zip", "/kaggle/working/os-tutor-lora.zip")
else:
    from google.colab import files
    files.download("os-tutor-lora.zip")
"""),
        md("""
## 7. Merge and export the model for Ollama (GGUF, ~15–25 minutes)
Merges the adapter into Llama 3.1 8B and quantizes to Q4_K_M (~4.9 GB), the same size class as `llama3.1:8b`.
"""),
        code(EXPORT_CODE),
        md("## 8. Copy the model file to Google Drive"),
        code(COPY_CODE),
    ]
    return cells


def build() -> Path:
    return _write(build_cells_v1(), "train_colab.ipynb")

V2_SETUP = """
# Where everything is kept: Google Drive on Colab (survives a disconnect), the output folder on Kaggle
import os, pathlib
if os.path.exists("/kaggle/working"):
    WORK = "/kaggle/working"
else:
    from google.colab import drive
    drive.mount("/content/drive")
    WORK = "/content/drive/MyDrive/os-tutor-v2"
pathlib.Path(WORK, "checkpoints").mkdir(parents=True, exist_ok=True)
print("saving to", WORK)
"""

V2_TRAIN = """
import glob, inspect
from datasets import load_dataset
from trl import SFTConfig, SFTTrainer

ds = load_dataset("json", data_files={"train": TRAIN_FILE, "validation": VAL_FILE})
def to_text(batch):
    return {"text": [tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=False) for m in batch["messages"]]}
ds = ds.map(to_text, batched=True, remove_columns=ds["train"].column_names)

cfg = dict(dataset_text_field="text", per_device_train_batch_size=BATCH, gradient_accumulation_steps=ACCUM,
           warmup_steps=10, num_train_epochs=EPOCHS, learning_rate=LR, logging_steps=10, optim="adamw_8bit",
           weight_decay=0.01, lr_scheduler_type="linear", seed=3407, bf16=is_bfloat16_supported(),
           fp16=not is_bfloat16_supported(), output_dir=f"{WORK}/checkpoints", report_to="none",
           save_strategy="steps", save_steps=40, save_total_limit=2)          # a checkpoint every ~10 minutes
names = inspect.signature(SFTConfig.__init__).parameters
cfg["max_seq_length" if "max_seq_length" in names else "max_length"] = MAX_SEQ
common = dict(model=model, train_dataset=ds["train"], eval_dataset=ds["validation"], args=SFTConfig(**cfg))
try:
    trainer = SFTTrainer(tokenizer=tokenizer, **common)
except TypeError:
    trainer = SFTTrainer(processing_class=tokenizer, **common)
trainer = train_on_responses_only(trainer,
    instruction_part="<|start_header_id|>user<|end_header_id|>\\n\\n",
    response_part="<|start_header_id|>assistant<|end_header_id|>\\n\\n")
resume = bool(glob.glob(f"{WORK}/checkpoints/checkpoint-*"))
print("Resuming from the last checkpoint in Drive" if resume else "Starting a new training run")
stats = trainer.train(resume_from_checkpoint=resume or None)
print(stats)
print(trainer.evaluate())
"""

V3_EVAL = """
names = inspect.signature(SFTConfig.__init__).parameters
cfg.update(per_device_eval_batch_size=BATCH, eval_steps=40, load_best_model_at_end=True,
           metric_for_best_model="eval_loss", greater_is_better=False)
cfg["eval_strategy" if "eval_strategy" in names else "evaluation_strategy"] = "steps"
"""

V2_COPY = COPY_CODE[:COPY_CODE.index("if os.path.exists")] + """
dest = f"{WORK}/os-tutor-v2.gguf"          # Drive on Colab, the output folder on Kaggle
shutil.copy(src, dest)
print("Copied to", dest)
print("On the laptop: save it as qlora\\\\os-tutor-v2.gguf, then run  python -m qlora.create_finetuned --name os-tutor-v2")
"""


def build_v2() -> Path:
    """Second fine-tuning round: data v2 (student-style phrasing), 2 epochs, checkpoints in Google Drive, os-tutor-v2.gguf."""
    return build_round("v2", epochs=2)


def build_v3() -> Path:
    """Third round: data v3 (v2 + NotebookLM questions checked by import_notebooklm.py), 1 epoch, best checkpoint by
    validation loss."""
    return build_round("v3", epochs=1, evaluate=True)


def build_round(tag: str, epochs: int, evaluate: bool = False) -> Path:
    data = DATA / tag
    raw = (data / "train_all.jsonl").read_bytes() + b"\n=====SPLIT=====\n" + (data / "val_all.jsonl").read_bytes()
    blob = base64.b64encode(gzip.compress(raw, 9)).decode()
    n_train = sum(1 for _ in open(data / "train_all.jsonl", encoding="utf-8"))
    v1 = build_cells_v1()
    load_cell = next(c for c in v1 if "FastLanguageModel.from_pretrained" in c["source"])
    try_cell = next(c for c in v1 if "for_inference" in c["source"])
    assert "os-tutor-v2.gguf" in V2_COPY and "MyDrive/os-tutor.gguf" not in V2_COPY
    train_code = V2_TRAIN.replace("common = dict(", (V3_EVAL if evaluate else "") + "common = dict(", 1)
    about = ("**1 epoch**, with the **validation loss checked at every checkpoint** and the **best checkpoint kept** "
             "(round 2's training loss fell to 0.04 over 2 epochs: it had memorised its replies)" if evaluate else
             "**2 epochs** instead of 1")
    cells = [
        md(f"""
# OS Tutor {tag}: QLoRA fine-tuning round {tag[1:]} (Llama 3.1 8B)

What changed from the first round: {n_train} training examples, about a fifth of them rewritten the way students type
(short, informal, typos: "sir pls explain srtf", "whats the wt of p2??") with the same engine-verified answers;
{about}; a **checkpoint is saved to Google Drive** every ~10 minutes, so a disconnect loses at most
a few minutes; the model is exported as **os-tutor-v2.gguf**, so the first model stays as it is.

**Colab (works from a phone too):** Runtime → Change runtime type → **T4 GPU**, then Runtime → **Run all** and allow
Google Drive access. Everything is saved in *My Drive → os-tutor-v2*.
**If the session disconnects:** open the notebook again and **Run all**. Training continues from the last checkpoint.

Takes about 2–2½ hours on a T4 (training ~1h45, export ~20 min). Then on the laptop: save
`os-tutor-v2.gguf` as `qlora\\os-tutor-v2.gguf` and run `python -m qlora.create_finetuned --name os-tutor-v2`.
"""),
        code("""
!nvidia-smi --query-gpu=name,memory.total --format=csv
!pip install -q unsloth
"""),
        md("## 1. Google Drive (checkpoints and the finished model go there)"),
        code(V2_SETUP),
        md("## 2. Training data v2 (built in; a `data/train.jsonl` + `data/val.jsonl` in the Drive folder replaces it)"),
        code(f"""
import base64, gzip, json
TRAIN_FILE, VAL_FILE = f"{{WORK}}/data/train.jsonl", f"{{WORK}}/data/val.jsonl"
if os.path.exists(TRAIN_FILE) and os.path.exists(VAL_FILE):
    print("using the data files in", WORK + "/data")
else:
    DATA = "{blob}"
    raw = gzip.decompress(base64.b64decode(DATA)).decode("utf-8")
    train_txt, val_txt = raw.split("\\n=====SPLIT=====\\n")
    pathlib.Path("data").mkdir(exist_ok=True)
    TRAIN_FILE, VAL_FILE = "data/train.jsonl", "data/val.jsonl"
    open(TRAIN_FILE, "w", encoding="utf-8").write(train_txt)
    open(VAL_FILE, "w", encoding="utf-8").write(val_txt)
print(sum(1 for _ in open(TRAIN_FILE, encoding="utf-8")), "training examples,",
      sum(1 for _ in open(VAL_FILE, encoding="utf-8")), "validation examples")
"""),
        md("## 3. Settings"),
        code("""
import torch
EPOCHS = 2
MAX_SEQ = 2048
LORA_R = 16
LR = 2e-4
gpu_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
BATCH, ACCUM = (2, 4) if gpu_gb > 12 else (1, 8)      # effective batch 8 either way
print(f"GPU memory {gpu_gb:.0f} GB -> batch {BATCH} x accumulation {ACCUM}")
"""),
        md("## 4. Load Llama 3.1 8B in 4-bit and add LoRA adapters"),
        code(load_cell["source"]),
        md("## 5. Train (loss only on the tutor's replies; resumes from Drive if a checkpoint exists)"),
        code(train_code),
        md("## 6. Try it, including a student-style question"),
        code(try_cell["source"].replace('"Quiz me on deadlocks"]', '"Quiz me on deadlocks", "sir whats the diff between sjf n srtf pls"]')),
        md("## 7. Save the adapter to Drive (small backup, ~160 MB)"),
        code("""
import shutil
model.save_pretrained("os-tutor-v2-lora")
tokenizer.save_pretrained("os-tutor-v2-lora")
shutil.make_archive(f"{WORK}/os-tutor-v2-lora", "zip", "os-tutor-v2-lora")
print("saved", f"{WORK}/os-tutor-v2-lora.zip")
"""),
        md("## 8. Merge and export the model for Ollama (GGUF Q4_K_M, ~15–25 minutes)"),
        code(EXPORT_CODE),
        md("## 9. Copy the model file to Google Drive"),
        code(V2_COPY),
    ]
    if tag != "v2":
        for c in cells:
            c["source"] = c["source"].replace("os-tutor-v2", f"os-tutor-{tag}").replace("data v2", f"data {tag}") \
                .replace("EPOCHS = 2", f"EPOCHS = {epochs}")
    return _write(cells, f"train_colab_{tag}.ipynb")


def build_export() -> Path:
    cells = [
        md("""
# OS Tutor: export the fine-tuned model for Ollama (no retraining)

Use this if the training notebook's session ended before its export step. You need **os-tutor-lora.zip**, which the
training notebook downloaded (or zip the files in your `qlora\\os-tutor-lora` folder).

**Colab:** Runtime → Change runtime type → **T4 GPU**, then Runtime → **Run all**. When the upload button appears in
section 1, choose `os-tutor-lora.zip`. At the end allow Google Drive access: the file is copied to *My Drive* as
`os-tutor.gguf` (~4.9 GB). About 25–30 minutes in total.
Then on your laptop: save it as `qlora\\os-tutor.gguf` and run `qlora\\setup_ollama_models.bat`.
"""),
        code("""
!nvidia-smi --query-gpu=name,memory.total --format=csv
!pip install -q unsloth
"""),
        md("## 1. Upload the adapter (os-tutor-lora.zip, or the files inside it)"),
        code("""
import os, shutil, zipfile
from google.colab import files
os.makedirs("os-tutor-lora", exist_ok=True)
for name in files.upload():
    if name.lower().endswith(".zip"):
        with zipfile.ZipFile(name) as z:
            z.extractall("os-tutor-lora")
    else:
        shutil.move(name, os.path.join("os-tutor-lora", name))
ADAPTER = next(root for root, _, fs in os.walk("os-tutor-lora") if "adapter_config.json" in fs)
print(ADAPTER, sorted(os.listdir(ADAPTER)))
"""),
        md("## 2. Load Llama 3.1 8B with the trained adapter"),
        code("""
import json
from transformers import AutoTokenizer
base = json.load(open(os.path.join(ADAPTER, "adapter_config.json")))["base_model_name_or_path"]
print("base model:", base)
if not os.path.exists(os.path.join(ADAPTER, "tokenizer_config.json")):
    AutoTokenizer.from_pretrained(base).save_pretrained(ADAPTER)
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(model_name=ADAPTER, max_seq_length=2048, load_in_4bit=True)
"""),
        md("## 3. Quick check that it is the fine-tuned tutor"),
        code(f"""
FastLanguageModel.for_inference(model)
SYSTEM = {json.dumps(CHAT_SYSTEM)}
msgs = [{{"role": "system", "content": SYSTEM}}, {{"role": "user", "content": "Explain SRTF to me like I'm new to it"}}]
ids = tokenizer.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda")
out = model.generate(input_ids=ids, max_new_tokens=250, temperature=0.3, do_sample=True)
print(tokenizer.decode(out[0][ids.shape[1]:], skip_special_tokens=True))
"""),
        md("## 4. Merge and export (GGUF Q4_K_M, ~15–25 minutes)"),
        code(EXPORT_CODE),
        md("## 5. Copy the model file to Google Drive"),
        code(COPY_CODE),
    ]
    return _write(cells, "export_gguf_colab.ipynb")


def _write(cells, name: str) -> Path:
    nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []},
                                       "kernelspec": {"display_name": "Python 3", "name": "python3"},
                                       "language_info": {"name": "python"}},
          "nbformat": 4, "nbformat_minor": 0}
    path = HERE / name
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
    return path

if __name__ == "__main__":
    import sys
    builders = [build_v2] if "--v2" in sys.argv else [build_v3] if "--v3" in sys.argv else [build, build_export]
    for p in (b() for b in builders):
        print("wrote", p, f"({p.stat().st_size / 1e6:.1f} MB)")
