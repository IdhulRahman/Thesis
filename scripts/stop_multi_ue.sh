#!/usr/bin/env bash
# ==============================================================================
# Automated Multi-UE Teardown Script (VM-5 ue-emulator)
# Location on VM-5: /opt/oran/ue/scripts/stop_multi_ue.sh
# ==============================================================================

echo "Menghentikan semua proses nr-uesoftmodem..."
sudo pkill -9 nr-uesoftmodem || true

echo "Membersihkan semua antarmuka veth dan namespace UE..."
for ns in $(ip netns list | grep -oP '^ue\d+'); do
  ue_idx="${ns#ue}"
  echo "Menghapus $ns dan veth-ue${ue_idx}..."
  sudo ip link del "veth-ue${ue_idx}" 2>/dev/null || true
  sudo ip netns del "$ns" 2>/dev/null || true
done

rm -f /opt/oran/ue/active_ues.txt
echo "Seluruh UE berhasil dihentikan dan dibersihkan."
