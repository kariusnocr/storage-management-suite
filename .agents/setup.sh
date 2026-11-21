#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KAS_SHARED="${HOME}/.local/share/kas"
TESS_DIR="${KAS_SHARED}/tessdata"

mkdir -p "${TESS_DIR}"

# 1. Đảm bảo gói ngôn ngữ tiếng Việt OCR (`vie.traineddata`) cho Tesseract
if [ ! -f "${TESS_DIR}/vie.traineddata" ]; then
  if [ -f "/usr/share/tesseract-ocr/5/tessdata/vie.traineddata" ]; then
    ln -sf "/usr/share/tesseract-ocr/5/tessdata/vie.traineddata" "${TESS_DIR}/vie.traineddata"
  elif [ -f "${HOME}/storage_data/tessdata/vie.traineddata" ]; then
    ln -sf "${HOME}/storage_data/tessdata/vie.traineddata" "${TESS_DIR}/vie.traineddata"
  else
    curl -fsSL "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/vie.traineddata" -o "${TESS_DIR}/vie.traineddata" || true
  fi
fi

for f in eng.traineddata osd.traineddata; do
  if [ ! -e "${TESS_DIR}/${f}" ] && [ -f "/usr/share/tesseract-ocr/5/tessdata/${f}" ]; then
    ln -sf "/usr/share/tesseract-ocr/5/tessdata/${f}" "${TESS_DIR}/${f}"
  fi
done

# 2. Cài gói Python karius-academic-system ở chế độ editable để có lệnh `kas` và `kas-desktop`
python3 -m pip install --user --break-system-packages --no-build-isolation --no-deps -e "${REPO_ROOT}" >/dev/null 2>&1 || \
  python3 -m pip install --user --no-build-isolation --no-deps -e "${REPO_ROOT}" >/dev/null 2>&1 || true

# 3. Lưu biến môi trường vào ~/.bashrc (idempotent)
BASHRC="${HOME}/.bashrc"
touch "${BASHRC}"
grep -q 'export PATH="${HOME}/.local/bin:${PATH}"' "${BASHRC}" || echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> "${BASHRC}"
grep -q "TESSDATA_PREFIX=${TESS_DIR}" "${BASHRC}" || echo "export TESSDATA_PREFIX=${TESS_DIR}" >> "${BASHRC}"

export PATH="${HOME}/.local/bin:${PATH}"
export TESSDATA_PREFIX="${TESS_DIR}"

echo "Karius Academic System (KAS) 1.0.0 ready (CLI: $(command -v kas || echo 'python3 -m karius_academic_system'))."
