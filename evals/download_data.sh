#!/usr/bin/env bash
set -euo pipefail

# Downloads the SemEval-2020 Task 11 PTC v2 dataset (1.1 MB, research-only licence).
# Run from anywhere — the script finds evals/data/ relative to itself.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"
ZENODO_URL="https://zenodo.org/records/3952415/files/datasets-v2.tgz?download=1"
ARCHIVE="$DATA_DIR/datasets-v2.tgz"
EXPECTED_ARTICLES=446  # 371 train + 75 dev

mkdir -p "$DATA_DIR"

if [ -d "$DATA_DIR/datasets/train-articles" ]; then
    count=$(ls "$DATA_DIR/datasets/train-articles/" | wc -l)
    echo "Dataset already present ($count train articles). Delete $DATA_DIR/datasets/ to re-download."
    exit 0
fi

echo "Downloading SemEval-2020 Task 11 PTC v2 from Zenodo..."
curl -L -o "$ARCHIVE" "$ZENODO_URL"

echo "Extracting..."
tar xzf "$ARCHIVE" -C "$DATA_DIR"

# Verify
train=$(ls "$DATA_DIR/datasets/train-articles/" | wc -l)
dev=$(ls "$DATA_DIR/datasets/dev-articles/" | wc -l)
total=$((train + dev))

if [ "$total" -ne "$EXPECTED_ARTICLES" ]; then
    echo "WARNING: expected $EXPECTED_ARTICLES articles, got $total (train=$train, dev=$dev)"
else
    echo "OK: $train train + $dev dev articles"
fi

# Create hard-negative directories
for set_name in fact_checks satire op_eds wire_copy press_releases; do
    mkdir -p "$DATA_DIR/hard_negatives/$set_name"
done
echo "Hard-negative directories ready in $DATA_DIR/hard_negatives/"

echo "Done. Data is in $DATA_DIR/datasets/"
echo "REMINDER: research-only licence — never commit this data."
