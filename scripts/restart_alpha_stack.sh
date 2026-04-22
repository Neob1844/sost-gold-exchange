#!/bin/bash
echo "Restarting SOST Alpha Stack..."
sudo systemctl restart sost-alpha-watcher
sleep 2
sudo systemctl restart sost-alpha-dashboard
echo "Restarted. Check: scripts/check_alpha_health.sh"
