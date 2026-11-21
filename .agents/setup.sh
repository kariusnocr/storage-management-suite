#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export PIP_NO_INPUT=1

# 1. Ensure required Python packages (openpyxl, Pillow, numpy) are importable.
if ! python3 -c "import openpyxl, PIL, numpy" >/dev/null 2>&1; then
  python3 -m pip install --user --quiet --no-input --break-system-packages openpyxl pillow numpy 2>/dev/null \
    || python3 -m pip install --user --quiet --no-input openpyxl pillow numpy
fi

# 2. Ensure runtime data directories exist outside the Git repository.
STORAGE_DATA_DIR="${STORAGE_DATA_DIR:-$HOME/storage_data}"
mkdir -p \
  "$STORAGE_DATA_DIR/tessdata" \
  "$STORAGE_DATA_DIR/runs" \
  "$STORAGE_DATA_DIR/reports" \
  "$STORAGE_DATA_DIR/snapshots" \
  "$STORAGE_DATA_DIR/content_cache" \
  "$STORAGE_DATA_DIR/media_cache"

# 3. Configure Tesseract tessdata with Vietnamese + English (vie+eng) support.
SYS_TESSDATA=""
for cand in \
  "/usr/share/tesseract-ocr/5/tessdata" \
  "/usr/share/tesseract-ocr/4.00/tessdata" \
  "/usr/share/tessdata"; do
  if [ -d "$cand" ]; then
    SYS_TESSDATA="$cand"
    break
  fi
done

if [ -n "$SYS_TESSDATA" ]; then
  for item in eng.traineddata osd.traineddata vie.traineddata pdf.ttf configs tessconfigs; do
    if [ -e "$SYS_TESSDATA/$item" ]; then
      ln -sfn "$SYS_TESSDATA/$item" "$STORAGE_DATA_DIR/tessdata/$item"
    fi
  done
fi

if [ ! -s "$STORAGE_DATA_DIR/tessdata/vie.traineddata" ]; then
  TMP_VIE="$STORAGE_DATA_DIR/tessdata/vie.traineddata.tmp"
  rm -f "$TMP_VIE"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh api -H "Accept: application/vnd.github.raw" \
      repos/tesseract-ocr/tessdata_fast/contents/vie.traineddata > "$TMP_VIE" 2>/dev/null || rm -f "$TMP_VIE"
  elif command -v curl >/dev/null 2>&1; then
    curl -fsSL \
      "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/vie.traineddata" \
      -o "$TMP_VIE" 2>/dev/null || rm -f "$TMP_VIE"
  fi
  if [ -s "$TMP_VIE" ]; then
    mv "$TMP_VIE" "$STORAGE_DATA_DIR/tessdata/vie.traineddata"
  else
    rm -f "$TMP_VIE"
  fi
fi

# 4. Persist environment variables idempotently in ~/.bashrc for non-interactive shells.
touch "$HOME/.bashrc"
sed -i '/case \$- in/,/esac/d' "$HOME/.bashrc" 2>/dev/null || true

persist_export() {
  local line="$1"
  grep -qxF "$line" "$HOME/.bashrc" || echo "$line" >> "$HOME/.bashrc"
}

persist_export 'export PATH="$HOME/.local/bin:$PATH"'
persist_export 'export STORAGE_DATA_DIR="$HOME/storage_data"'
persist_export 'export STORAGE_GITHUB_REPO="kariusnocr/storage-management-suite"'
if [ -e "$STORAGE_DATA_DIR/tessdata/eng.traineddata" ] || [ -e "$STORAGE_DATA_DIR/tessdata/vie.traineddata" ]; then
  persist_export 'export TESSDATA_PREFIX="$HOME/storage_data/tessdata"'
fi

# 5. Verify core Python imports.
python3 -c "import openpyxl, PIL, numpy; print('storage-management-suite env ready')"
