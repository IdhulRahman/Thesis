#!/bin/bash
# ==============================================================================
# 5G OAI Split RAN Background Launcher (VM-4 oai-ran)
# Location on VM-4: /opt/oran/ran/start_ran.sh
# ==============================================================================

BIN_DIR="/opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build"
CONF_DIR="/opt/oran/ran/conf"
LOG_DIR="/opt/oran/ran"

echo "=== Stopping previous RAN processes (if any) ==="
sudo pkill -9 nr-softmodem 2>/dev/null
sleep 2

# Preserve and sanitize terminal state
stty sane 2>/dev/null || true

echo "=== 1. Starting CU in background ==="
cd "$BIN_DIR"
nohup sudo ./nr-softmodem -O "$CONF_DIR/cu_gnb.conf" \
  --e2_agent.near_ric_ip_addr 10.102.0.66 \
  --e2_agent.sm_dir /usr/local/lib/flexric/ \
  < /dev/null > "$LOG_DIR/cu.log" 2>&1 &

echo "Waiting for CU to establish N2 (AMF) and E2 (Near-RT RIC)..."
sleep 4

echo "=== 2. Starting DU-1 (Cell-1, Port 4043, Telnet 9090, 3/4 Sampling -E) in background ==="
nohup sudo ./nr-softmodem -O "$CONF_DIR/du_gnb1.conf" --rfsim -E \
  --telnetsrv --telnetsrv.listenport 9090 \
  < /dev/null > "$LOG_DIR/du1.log" 2>&1 &
sleep 2

echo "=== 3. Starting DU-2 (Cell-2, Port 4044, Baseline Control) in background ==="
nohup sudo ./nr-softmodem -O "$CONF_DIR/du_gnb2.conf" --rfsim \
  < /dev/null > "$LOG_DIR/du2.log" 2>&1 &
sleep 2

echo ""
echo "=== RAN Process Status ==="
ps aux | grep "[n]r-softmodem"
echo ""
echo "=== Cell In-Service Verification ==="
grep -E "is in service|associated AMF" "$LOG_DIR/cu.log"
echo "OAI Split RAN successfully started in background."

# Ensure terminal echo and newline handling are cleanly restored
stty sane 2>/dev/null || true
