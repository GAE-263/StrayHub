#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SYSTEMD_SOURCE="$ROOT_DIR/infra/gce/systemd"
SYSTEMD_TARGET="/etc/systemd/system"
units=(
  strayhub-secrets.service
  strayhub-migrate.service
  strayhub.service
  strayhub-backup.service
  strayhub-backup.timer
)

fail() {
  printf '[Systemd install] FAIL: %s\n' "$*" >&2
  exit 1
}

[[ "${EUID:-$(id -u)}" == "0" ]] || fail "run as root"
id strayhub >/dev/null 2>&1 || fail "strayhub user is missing"
getent group docker >/dev/null 2>&1 || fail "docker group is missing"
[[ -d /opt/strayhub/current ]] || fail "canonical deployment path is missing"
[[ -f /etc/strayhub/production.env ]] || fail "production config is missing"

for unit in "${units[@]}"; do
  [[ -f "$SYSTEMD_SOURCE/$unit" ]] || fail "missing unit source: $unit"
  install -o root -g root -m 0644 "$SYSTEMD_SOURCE/$unit" "$SYSTEMD_TARGET/$unit"
done
chown root:strayhub /etc/strayhub
chmod 0750 /etc/strayhub
chown root:strayhub /etc/strayhub/production.env
chmod 0640 /etc/strayhub/production.env
install -d -o strayhub -g strayhub -m 0700 /var/lib/strayhub/secrets /var/lib/strayhub/backups
chown -R strayhub:strayhub /var/lib/strayhub/secrets

systemctl daemon-reload
systemctl enable strayhub.service strayhub-backup.timer

printf '[Systemd install] PASS: units installed and boot targets enabled\n'
