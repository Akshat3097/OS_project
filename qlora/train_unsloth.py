"""
QLoRA fine-tuning of Llama 3.1 8B Instruct with Unsloth. The easiest way to run it is the notebook
qlora/train_colab.ipynb on a free Colab or Kaggle GPU (data is built in, nothing to upload). This script
does the same on your own CUDA machine (RTX 5070 laptop via WSL2/Linux):

    pip install unsloth
    python qlora/train_unsloth.py --gguf q4_k_m      # 1 epoch on qlora/data/train_all.jsonl, then merge + export
    # -> outputs/os-tutor-gguf/...Q4_K_M.gguf  (copy it to qlora/os-tutor.gguf, then: python -m qlora.create_finetuned)

Recent Ollama versions no longer accept LoRA adapters, so the adapter is merged into the model and exported as GGUF.

8 GB VRAM: batch size 1 + gradient accumulation 8, max_seq_length 2048, gradient checkpointing "unsloth".
RTX 50-series (Blackwell) needs a PyTorch build for CUDA 12.8+. Library argument names move quickly; the
code below tries both the old and new names.
"""
import argparse
import inspect
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="unsloth/Meta-Llama-3.1-8B-Instruct-bnb-4bit")
    ap.add_argument("--train", default=str(DATA / "train_all.jsonl"))
    ap.add_argument("--val", default=str(DATA / "val_all.jsonl"))
    ap.add_argument("--max-seq", type=int, default=2048)
    ap.add_argument("--r", type=int, default=16)
    ap.add_argument("--epochs", type=float, default=1)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--batch", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--gguf", default="", help="also export a GGUF with this quantization, e.g. q4_k_m (slow, ~5 GB)")
    args = ap.parse_args()

    from unsloth import FastLanguageModel, is_bfloat16_supported  # import first so Unsloth can patch
    from unsloth.chat_templates import get_chat_template, train_on_responses_only
    from datasets import load_dataset
    from trl import SFTConfig, SFTTrainer

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model, max_seq_length=args.max_seq, load_in_4bit=True)   # frozen 4-bit base
    model = FastLanguageModel.get_peft_model(                                       # small trainable LoRA adapters
        model, r=args.r, lora_alpha=args.r, lora_dropout=0, bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        use_gradient_checkpointing="unsloth", random_state=3407)
    tokenizer = get_chat_template(tokenizer, chat_template="llama-3.1")

    ds = load_dataset("json", data_files={"train": args.train, "validation": args.val})

    def to_text(batch):
        return {"text": [tokenizer.apply_chat_template(m, tokenize=False, add_generation_prompt=False)
                         for m in batch["messages"]]}
    ds = ds.map(to_text, batched=True, remove_columns=ds["train"].column_names)

    cfg = dict(dataset_text_field="text", per_device_train_batch_size=args.batch,
               gradient_accumulation_steps=args.grad_accum, warmup_steps=10, num_train_epochs=args.epochs,
               learning_rate=args.lr, logging_steps=10, optim="adamw_8bit", weight_decay=0.01,
               lr_scheduler_type="linear", seed=3407, bf16=is_bfloat16_supported(), fp16=not is_bfloat16_supported(),
               output_dir=f"{args.out}/checkpoints", report_to="none", save_strategy="no")
    names = inspect.signature(SFTConfig.__init__).parameters
    cfg["max_seq_length" if "max_seq_length" in names else "max_length"] = args.max_seq
    common = dict(model=model, train_dataset=ds["train"], eval_dataset=ds["validation"], args=SFTConfig(**cfg))
    try:
        trainer = SFTTrainer(tokenizer=tokenizer, **common)
    except TypeError:
        trainer = SFTTrainer(processing_class=tokenizer, **common)
    # loss only on the tutor's replies, not on the system prompt or the student's messages
    trainer = train_on_responses_only(trainer,
                                      instruction_part="<|start_header_id|>user<|end_header_id|>\n\n",
                                      response_part="<|start_header_id|>assistant<|end_header_id|>\n\n")
    print(trainer.train())
    print(trainer.evaluate())

    model.save_pretrained(f"{args.out}/os-tutor-lora")          # adapter only (~160 MB), a small backup
    tokenizer.save_pretrained(f"{args.out}/os-tutor-lora")
    print(f"Adapter written to {args.out}/os-tutor-lora")
    if args.gguf:                                                # merged model for Ollama
        model.save_pretrained_gguf(f"{args.out}/os-tutor-gguf", tokenizer, quantization_method=args.gguf)
        print(f"GGUF written under {args.out}. Copy the .gguf to qlora/os-tutor.gguf, then run\n"
              f"  python -m qlora.create_finetuned")


if __name__ == "__main__":
    main()
