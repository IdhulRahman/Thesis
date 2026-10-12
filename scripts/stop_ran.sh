#!/bin/bash
# ==============================================================================
# 5G OAI Split RAN Stopper (VM-4 oai-ran)
# Location on VM-4: /opt/oran/ran/stop_ran.sh
# ==============================================================================

echo "Stopping all OAI RAN processes (CU, DU-1, DU-2)..."
sudo pkill -9 nr-softmodem
sleep 1
echo "All RAN processes stopped."
