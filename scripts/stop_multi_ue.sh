#!/usr/bin/env bash
# ==============================================================================
# Automated Multi-UE Teardown Script (VM-5 ue-emulator)
# Location on VM-5: /opt/oran/ue/scripts/stop_multi_ue.sh
# ==============================================================================

echo "Menghentikan nr-uesoftmodem secara graceful (SIGINT)..."
sudo pkill -2 nr-uesoftmodem 2>/dev/null || true
sleep 2

# Force kill jika masih ada proses membandel
if pgrep -f nr-uesoftmodem >/dev/null 2>&1; then
  echo "Membersihkan sisa proses dengan SIGKILL..."
  sudo pkill -9 nr-uesoftmodem 2>/dev/null || true
fi

echo "Membersihkan antarmuka veth dan namespace UE..."
for ns in $(ip netns list | grep -oP '^ue\d+'); do
  ue_idx="${ns#ue}"
  sudo ip link del "veth-ue${ue_idx}" 2>/dev/null || true
  sudo ip netns del "$ns" 2>/dev/null || true
done

rm -f /opt/oran/ue/active_ues.txt
rm -f /opt/oran/ue/trafgen.pid
echo "Seluruh UE berhasil dibersihkan secara elegan."
