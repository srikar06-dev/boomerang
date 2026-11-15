#!/usr/bin/env bash
# Boomerang backend on the Arduino UNO Q (Debian 13, arm64). Run ON THE BOARD, from the repo root:
#     bash unoq/install_backend.sh
# Creates .venv, installs the backend, and registers a systemd service that starts it at every boot
# on port 8000. Copy your .env to the repo root first (it holds the AWS / Mongo keys; never commit it).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
[ -f .env ] || { echo "No .env in $REPO - copy it from your laptop first (scp)."; exit 1; }
chmod 600 .env

echo "== 1/4 system packages"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-dev git curl

echo "== 2/4 virtual environment"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip wheel

echo "== 3/4 Python packages (board needs no camera window: opencv-python-headless)"
# The board does not need pyserial, the GUI OpenCV or pytest. Try the pinned versions first;
# if one has no build for this Python, fall back to the newest release of the same packages.
grep -vE '^(opencv-python|pyserial|pytest)' backend/requirements.txt | sed 's/#.*//' | grep -v '^\s*$' > /tmp/boomerang-req.txt
echo "opencv-python-headless" >> /tmp/boomerang-req.txt
if ! .venv/bin/pip install -q --prefer-binary -r /tmp/boomerang-req.txt; then
    echo "   pinned versions failed on this board; installing latest compatible versions"
    sed 's/[=<>].*//' /tmp/boomerang-req.txt > /tmp/boomerang-req-loose.txt
    .venv/bin/pip install -q --prefer-binary -r /tmp/boomerang-req-loose.txt
fi
.venv/bin/python -c "import fastapi, boto3, pymongo, PIL, imagehash, cv2; print('   imports OK, OpenCV', cv2.__version__)"

echo "== 4/4 systemd service (starts at boot, restarts if it crashes)"
sudo tee /etc/systemd/system/boomerang.service >/dev/null <<UNIT
[Unit]
Description=Boomerang backend (FastAPI)
After=network-online.target
Wants=network-online.target

[Service]
User=$(whoami)
WorkingDirectory=$REPO/backend
Environment=PYTHONNOUSERSITE=1
ExecStart=$REPO/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now boomerang.service
sleep 4
if curl -fs http://localhost:8000/health; then
    echo; echo "== Done. Backend running on this board, port 8000. Logs: journalctl -u boomerang -f"
else
    echo "== Service started but /health did not answer yet. Check: journalctl -u boomerang -n 50"
fi
