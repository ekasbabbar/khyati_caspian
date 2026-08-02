#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR=/opt/khyati/app
SERVICE=khyati.service
TARGET_SHA="${1:-}"

if [[ ! "$TARGET_SHA" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "Usage: sudo $0 <40-character-git-sha>" >&2
  exit 2
fi

cd "$APP_DIR"
PREVIOUS_SHA=$(sudo -u khyati git rev-parse HEAD)

rollback() {
  local exit_code=$?
  echo "Deployment failed; rolling back to $PREVIOUS_SHA" >&2
  sudo -u khyati git checkout --detach "$PREVIOUS_SHA" || true
  sudo -u khyati .venv/bin/pip install -r requirements.txt || true
  install -m 644 deploy/aws/khyati.service /etc/systemd/system/khyati.service || true
  systemctl daemon-reload || true
  systemctl restart "$SERVICE" || true
  exit "$exit_code"
}
trap rollback ERR

systemctl stop "$SERVICE"
sudo -u khyati git fetch --prune origin
sudo -u khyati git checkout --detach "$TARGET_SHA"
sudo -u khyati .venv/bin/pip install -r requirements.txt
sudo -u khyati .venv/bin/python -m unittest discover -s tests -q
install -m 644 deploy/aws/khyati.service /etc/systemd/system/khyati.service
systemctl daemon-reload
systemctl restart "$SERVICE"
sleep 10
systemctl is-active --quiet "$SERVICE"
trap - ERR
echo "Khyati deployed at $TARGET_SHA"
