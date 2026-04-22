#!/bin/bash
# Start all SOST alpha services
set -e
echo "Starting SOST Alpha Stack..."
sudo cp ops/systemd/sost-alpha-*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sost-alpha-watcher sost-alpha-dashboard
sudo systemctl start sost-alpha-watcher sost-alpha-dashboard
echo "Services started. Check status with: scripts/check_alpha_health.sh"
