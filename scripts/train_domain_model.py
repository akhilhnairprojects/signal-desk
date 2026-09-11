"""Fine-tune the sentiment model on accumulated domain feedback.

The Transcript Analyzer's "Teach the analyzer" panel records tone
corrections into the transcript_feedback table. Once enough labelled
examples exist, this script fine-tunes the transformer on them so the model
adapts to this domain's language (network infrastructure sales calls).

Run this locally or on a Colab GPU - not on Streamlit Cloud:
    python scripts/train_domain_model.py

The tuned model saves to models/domain-sentiment/. To use it, point
SENTIMENT_MODEL in src/config.py at that path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config, store

MIN_EXAMPLES = 50
LABEL_MAP = {"Positive": "positive", "Mixed / Neutral": "neutral",
             "Negative": "negative"}
OUT_DIR = Path("models/domain-sentiment")


def main() -> None:
    feedback = store.load("transcript_feedback")
    feedback = feedback[feedback["corrected"].isin(LABEL_MAP)]
    n = len(feedback)
    if n < MIN_EXAMPLES:
        print(f"{n} labelled corrections so far; fine-tuning needs at least "
              f"{MIN_EXAMPLES} to be worthwhile. Keep recording corrections "
              "in the Transcript Analyzer - the dataset builds itself.")
        return

    try:
        import torch  # noqa: F401
        from datasets import Dataset
        from transformers import (AutoModelForSequenceClassification,
                                  AutoTokenizer, Trainer, TrainingArguments)
    except ImportError:
        print("Fine-tuning needs torch, transformers and datasets installed "
              "(pip install torch transformers datasets). Run this on a "
              "laptop or Colab, not on Streamlit Cloud.")
        return

    tokenizer = AutoTokenizer.from_pretrained(config.SENTIMENT_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(
        config.SENTIMENT_MODEL)
    label2id = {v.lower(): k for k, v in model.config.id2label.items()}

    ds = Dataset.from_dict({
        "text": feedback["excerpt"].tolist(),
        "label": [label2id[LABEL_MAP[c].lower()]
                  for c in feedback["corrected"]],
    }).map(lambda x: tokenizer(x["text"], truncation=True, padding=True),
           batched=True)

    args = TrainingArguments(
        output_dir=str(OUT_DIR / "checkpoints"),
        num_train_epochs=2, per_device_train_batch_size=8,
        learning_rate=2e-5, logging_steps=10, save_strategy="no",
        report_to=[],
    )
    Trainer(model=model, args=args, train_dataset=ds).train()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUT_DIR)
    tokenizer.save_pretrained(OUT_DIR)
    print(f"Domain model saved to {OUT_DIR}/. Point SENTIMENT_MODEL in "
          "src/config.py at this path to use it.")


if __name__ == "__main__":
    main()
