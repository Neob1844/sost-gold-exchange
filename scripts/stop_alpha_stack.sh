#!/bin/bash
echo "Stopping SOST Alpha Stack..."
sudo systemctl stop sost-alpha-dashboard sost-alpha-watcher 2>/dev/null
echo "Stopped."
