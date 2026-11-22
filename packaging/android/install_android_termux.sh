#!/usr/bin/env bash
# ==============================================================================
# Karius Academic System (KAS) v1.7.0 — Trình Cài Đặt 1 Lệnh Trên Android Termux
# Cú pháp:
#   curl -fsSL https://raw.githubusercontent.com/kariusnocr/storage-management-suite/main/packaging/android/install_android_termux.sh | bash
# ==============================================================================
set -euo pipefail

REPO="${KAS_REPO:-kariusnocr/storage-management-suite}"
PORT="${KAS_PORT:-8765}"
NO_LAUNCH="${KAS_NO_LAUNCH:-0}"

echo ""
echo "=================================================================="
echo "  KARIUS ACADEMIC SYSTEM (KAS) v1.7.0 - TRINH CAI DAT ANDROID TERMUX"
echo "=================================================================="
echo ""

if command -v pkg >/dev/null 2>&1; then
  echo "[1/5] Cap nhat goi Termux & cai dat Python, Git, OCR Tesseract, FFmpeg, 7-Zip, Poppler..."
  pkg update -y
  pkg install -y python git tesseract ffmpeg p7zip poppler curl
else
  echo "[1/5] Moi truong Linux/POSIX tieu chuan (khong phai Termux pkg) — kiem tra Python 3..."
fi

if command -v termux-setup-storage >/dev/null 2>&1 && [ ! -d "$HOME/storage/shared" ]; then
  echo "[2/5] Yeu cau quyen truy cap bo nho chia se Android (termux-setup-storage)..."
  termux-setup-storage || true
else
  echo "[2/5] Bo nho Android da san sang."
fi

echo "[3/5] Cai dat goi Karius Academic System (KAS)..."
python3 -m pip install --upgrade pip
python3 -m pip install --upgrade "git+https://github.com/${REPO}.git"

echo "[4/5] Tai du lieu OCR Tieng Viet (vie+eng) & khoi tao Kho Tai Lieu Android..."
kas setup --only ocr_data || true
kas android init-vault || true

# Tao loi tat 1 cham cho Termux:Widget (~/.shortcuts/KAS.sh)
mkdir -p "$HOME/.shortcuts"
cat > "$HOME/.shortcuts/KAS.sh" <<EOF
#!/usr/bin/env bash
kas ui --host 127.0.0.1 --port ${PORT} --stdlib --open
EOF
chmod +x "$HOME/.shortcuts/KAS.sh"

echo "[5/5] Hoan tat cai dat Karius Academic System (KAS) tren Android!"
kas version || true
kas android info || true

if [ "$NO_LAUNCH" != "1" ]; then
  echo ""
  echo "Dang khoi chay giao dien KAS tai http://127.0.0.1:${PORT} ..."
  exec kas ui --host 127.0.0.1 --port "${PORT}" --stdlib --open
fi
