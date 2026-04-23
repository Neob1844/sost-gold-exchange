#!/bin/bash
# Deploy SOST alpha services to VPS
# Run from the exchange repo root

set -euo pipefail

VPS="root@212.132.108.244"
REMOTE_DIR="/home/sost/SOST/sost-gold-exchange-private"
COMMS_DIR="/home/sost/SOST/sost-comms-private"

echo "=== Deploying SOST Alpha Stack to VPS ==="

# 1. Sync exchange repo
echo "Syncing exchange repo..."
ssh $VPS "cd $REMOTE_DIR && git pull origin main"

# 2. Sync comms repo
echo "Syncing comms repo..."
ssh $VPS "cd $COMMS_DIR && git pull origin main && npm install"

# 3. Install systemd services
echo "Installing systemd services..."
ssh $VPS "cp $REMOTE_DIR/ops/systemd/sost-alpha-*.service /etc/systemd/system/ && \
          cp $REMOTE_DIR/ops/systemd/sost-alpha-*.timer /etc/systemd/system/ && \
          cp $COMMS_DIR/ops/systemd/sost-relay.service /etc/systemd/system/ && \
          systemctl daemon-reload"

# 4. Enable and start services
echo "Starting services..."
ssh $VPS "systemctl enable sost-alpha-positions-export.timer && \
          systemctl start sost-alpha-positions-export.timer"

# 5. Run initial export
echo "Running initial position export..."
ssh $VPS "cd $REMOTE_DIR && python3 scripts/export_positions_json.py --output /opt/sost/website/api/positions_live.json"

echo "=== Deployment complete ==="
