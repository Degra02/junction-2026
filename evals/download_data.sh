#!/usr/bin/env bash
set -euo pipefail

# Downloads eval datasets. Run from anywhere — paths are relative to this script.
# Everything lands in evals/data/ (gitignored, never committed).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"

mkdir -p "$DATA_DIR"

# --- 1. SemEval-2020 Task 11 PTC v2 (technique eval, 1.1 MB, research-only) ---
SEMEVAL_DIR="$DATA_DIR/semeval2020"
if [ -d "$SEMEVAL_DIR/datasets/train-articles" ]; then
    echo "[semeval2020] already present ($(ls "$SEMEVAL_DIR/datasets/train-articles/" | wc -l) train articles)"
else
    echo "[semeval2020] downloading from Zenodo..."
    mkdir -p "$SEMEVAL_DIR"
    curl -fL -o "$SEMEVAL_DIR/datasets-v2.tgz" \
        "https://zenodo.org/records/3952415/files/datasets-v2.tgz?download=1"
    tar xzf "$SEMEVAL_DIR/datasets-v2.tgz" -C "$SEMEVAL_DIR"
    train=$(ls "$SEMEVAL_DIR/datasets/train-articles/" | wc -l)
    dev=$(ls "$SEMEVAL_DIR/datasets/dev-articles/" | wc -l)
    echo "[semeval2020] OK: $train train + $dev dev articles"
fi

# --- 2. VIGINUM Portal Kombat domain list (coordinated positives, public CSV) ---
VIGINUM_DIR="$DATA_DIR/viginum"
VIGINUM_CSV="$VIGINUM_DIR/portal_kombat_domains.csv"
if [ -f "$VIGINUM_CSV" ]; then
    echo "[viginum] already present ($(wc -l < "$VIGINUM_CSV") lines)"
else
    echo "[viginum] downloading Portal Kombat domain list from GitHub..."
    mkdir -p "$VIGINUM_DIR"
    # -f: an HTTP error fails the script instead of saving the error page as the CSV.
    curl -fL -o "$VIGINUM_CSV" \
        "https://raw.githubusercontent.com/VIGINUM-FR/Rapports-Techniques/main/202402%20-%20Portal%20Kombat/20241227_SGDSN_VIGINUM_NP_TLP-CLEAR_Portal-Kombat-domains.csv"
    if [ -f "$VIGINUM_CSV" ]; then
        echo "[viginum] OK: $(wc -l < "$VIGINUM_CSV") domains"
    else
        echo "[viginum] WARNING: download may have failed, check $VIGINUM_CSV"
    fi
fi

# --- 3. ClaimReview feed (fact_checker_debunk / hard_fact_checks source, ~190 MB) ---
# Every ClaimReview published through Google Fact Check Tools, as one schema.org DataFeed.
CLAIMREVIEW_JSON="$DATA_DIR/claimreview.json"
if [ -f "$CLAIMREVIEW_JSON" ]; then
    echo "[claimreview] already present ($(du -h "$CLAIMREVIEW_JSON" | cut -f1))"
else
    echo "[claimreview] downloading the Data Commons ClaimReview feed..."
    curl -fL -o "$CLAIMREVIEW_JSON" \
        "https://storage.googleapis.com/datacommons-feeds/claimreview/latest/data.json"
    echo "[claimreview] OK: $(du -h "$CLAIMREVIEW_JSON" | cut -f1)"
fi

# --- 4. SemEval-2021 Task 6 memes (semeval_memes, ~100 images, ~6 MB) ---
# "Free for general research use"; images and the derived labelled file stay in data/.
echo "[memes] building semeval_memes from the SemEval-2021 Task 6 corpus..."
(cd "$SCRIPT_DIR/.." && PYTHONPATH=evals/src uv run --frozen python -m propaganda_eval.cli fetch-memes)

# --- Summary ---
echo ""
echo "Data directory: $DATA_DIR"
echo "REMINDER: research-only datasets — never commit to the repo."
