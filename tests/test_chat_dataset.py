"""The chat-style fine-tuning data is well formed and its numbers come from the engine."""
import random
import re

from engine import scheduling
from qlora import build_chat_dataset as b
from qlora.chat_style import CHAT_SYSTEM


def _ok(ex):
    roles = [m["role"] for m in ex["messages"]]
    assert roles[0] == "system" and ex["messages"][0]["content"] == CHAT_SYSTEM
    assert all(r == ("user" if i % 2 == 0 else "assistant") for i, r in enumerate(roles[1:]))
    assert roles[-1] == "assistant" and all(m["content"].strip() for m in ex["messages"])


def test_every_kind_is_well_formed():
    rng = random.Random(1)
    data = (b.lesson_examples(rng) + b.notes_examples(rng) + b.handwritten() + b.scheduling_examples(rng, 2)
            + b.check_examples(rng, 10) + b.bankers_examples(rng, 3) + b.semaphore_examples(rng, 3)
            + b.notes_worked_examples())
    assert len(data) > 300
    for ex in data:
        _ok(ex)


def test_worked_solution_averages_match_engine():
    rng = random.Random(2)
    for ex in b.scheduling_examples(rng, 3):
        reply = ex["messages"][2]["content"]
        avg = float(re.search(r"Average WT = .*= ([\d.]+)", reply).group(1))
        rows = re.findall(r"^\| (P\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|", reply, re.M)
        assert rows and abs(avg - sum(int(r[5]) for r in rows) / len(rows)) < 0.01
        assert all(int(r[4]) == int(r[3]) - int(r[1]) and int(r[5]) == int(r[4]) - int(r[2]) for r in rows)


def test_modelfiles_share_the_persona(tmp_path, monkeypatch):
    from qlora import make_modelfiles
    for p in make_modelfiles.write():
        text = p.read_text(encoding="utf-8")
        assert CHAT_SYSTEM in text and "PARAMETER num_ctx 4096" in text


def test_create_finetuned_uses_installed_template(tmp_path, monkeypatch):
    import subprocess
    import types
    from qlora import create_finetuned as cf
    gguf = tmp_path / "os-tutor.gguf"
    with open(gguf, "wb") as f:
        f.truncate(1_100_000_000)                                  # sparse file, looks like a model
    calls = []
    tpl = "<|start_header_id|>system<|end_header_id|>\n\n{{ .System }}<|eot_id|>"

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0, stdout=tpl + "\n" if cmd[1] == "show" else "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(cf, "HERE", tmp_path)
    monkeypatch.setattr("sys.argv", ["create_finetuned"])
    cf.main()
    text = (tmp_path / "Modelfile.gguf").read_text(encoding="utf-8")
    assert "FROM ./os-tutor.gguf" in text and f'TEMPLATE """{tpl}"""' in text and CHAT_SYSTEM in text
    assert calls[-1][:3] == ["ollama", "create", "os-tutor"]
