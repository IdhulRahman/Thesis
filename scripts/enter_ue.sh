#!/usr/bin/env bash
# ==============================================================================
# Interactive Diagnostic Shell Access into UE Namespace (VM-5 ue-emulator)
# Location on VM-5: /opt/oran/ue/scripts/enter_ue.sh
# ==============================================================================

ns="${1:-ue1}"
if ! ip netns list | grep -q "^$ns\b"; then
  echo "Namespace $ns tidak ditemukan! Namespace yang sedang aktif:"
  ip netns list
  exit 1
fi

echo "Masuk ke dalam namespace $ns (Ketik 'exit' untuk kembali ke shell host)..."
sudo ip netns exec "$ns" bash --rcfile <(echo "
  export PS1='\[\e[1;33m\][$ns]#\[\e[0m\] '
")
