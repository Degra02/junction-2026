"""The pretrained models behind the single-actor signals, loaded once at import (D5, D6).

- Techniques: `Mishtar4/persuasion-detector-xlm-roberta`, 23 SemEval-2023 persuasion
  techniques, multi-label, per-label thresholds shipped with the model. MIT.
- NLI: `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7`, entailment / neutral /
  contradiction, cross-lingual. MIT.

Both run on CPU (D13). Weights download to `HF_HOME` on first start.
"""

import numpy as np
import torch
from huggingface_hub import hf_hub_download
from transformers import AutoModelForSequenceClassification, AutoTokenizer

TECHNIQUE_MODEL = "Mishtar4/persuasion-detector-xlm-roberta"
TECHNIQUE_REVISION = "9d288fd34c871e76fae490e08ec2b7b9b7e1485a"
NLI_MODEL = "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7"
NLI_REVISION = "b5113eb38ab63efdd7f280f8c144ea8b13f978ce"

_BATCH = 8

_technique_tokenizer = AutoTokenizer.from_pretrained(TECHNIQUE_MODEL, revision=TECHNIQUE_REVISION)
_technique_model = AutoModelForSequenceClassification.from_pretrained(
    TECHNIQUE_MODEL, revision=TECHNIQUE_REVISION
).eval()
TECHNIQUE_LABELS: list[str] = [
    _technique_model.config.id2label[i] for i in range(_technique_model.config.num_labels)
]
TECHNIQUE_THRESHOLDS: np.ndarray = np.load(
    hf_hub_download(TECHNIQUE_MODEL, "thresholds.npy", revision=TECHNIQUE_REVISION)
)

_nli_tokenizer = AutoTokenizer.from_pretrained(NLI_MODEL, revision=NLI_REVISION)
_nli_model = AutoModelForSequenceClassification.from_pretrained(
    NLI_MODEL, revision=NLI_REVISION
).eval()
_NLI_ORDER = [
    {v.lower(): k for k, v in _nli_model.config.id2label.items()}[name]
    for name in ("entailment", "neutral", "contradiction")
]


def technique_probabilities(texts: list[str]) -> np.ndarray:
    """Per-technique probabilities, shape `(len(texts), len(TECHNIQUE_LABELS))`."""
    if not texts:
        return np.zeros((0, len(TECHNIQUE_LABELS)), dtype=np.float32)
    out = np.zeros((len(texts), len(TECHNIQUE_LABELS)), dtype=np.float32)
    for batch in _length_batches(texts):
        inputs = _technique_tokenizer(
            [texts[i] for i in batch],
            return_tensors="pt",
            truncation=True,
            max_length=256,
            padding=True,
        )
        with torch.inference_mode():
            out[batch] = torch.sigmoid(_technique_model(**inputs).logits).numpy()
    return out


def nli(pairs: list[tuple[str, str]]) -> np.ndarray:
    """`[entailment, neutral, contradiction]` probabilities for each `(premise, hypothesis)`."""
    if not pairs:
        return np.zeros((0, 3), dtype=np.float32)
    out = np.zeros((len(pairs), 3), dtype=np.float32)
    for batch in _length_batches([p + h for p, h in pairs]):
        inputs = _nli_tokenizer(
            [pairs[i][0] for i in batch],
            [pairs[i][1] for i in batch],
            return_tensors="pt",
            truncation="only_first",
            max_length=320,
            padding=True,
        )
        with torch.inference_mode():
            probs = torch.softmax(_nli_model(**inputs).logits, dim=-1).numpy()
        out[batch] = probs[:, _NLI_ORDER]
    return out


def _length_batches(texts: list[str]) -> list[list[int]]:
    """Indices grouped by similar length, so padding wastes little compute."""
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
    return [order[i : i + _BATCH] for i in range(0, len(order), _BATCH)]
