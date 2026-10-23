# OAI Split RAN & User Equipment (CU/DU/F1/nrUE) Troubleshooting

This document contains validated diagnostic procedures, root-cause analyses, and resolutions for issues in the **ran-ue** domain.

---

## Case 23b — VM-4 Cannot Reach VM-3 5GC Containers (100% Packet Loss on 192.168.70.x)

### Symptom
On VM-4 (`10.102.0.167`), `ping 10.102.0.164` (VM-3 host) succeeds with 0% packet loss, but `ping 192.168.70.138` (AMF container) fails with 100% packet loss:

```text
PING 192.168.70.138 (192.168.70.138) 56(84) bytes of data.
--- 192.168.70.138 ping statistics ---
2 packets transmitted, 0 received, 100% packet loss, time 1004ms
```

### Cause
Four distinct factors can block external routed traffic between VM-4 and the VM-3 5GC containers:
1. **Missing Static Route on VM-4:** If `192.168.70.0/24 via 10.102.0.164` is not present in VM-4's routing table (`ip route show`), VM-4 falls back to its default gateway, dropping the packets before reaching VM-3.
2. **Accidental Static Route on VM-3 Host:** If `ip route add 192.168.70.0/24 via 10.102.0.164` was mistakenly executed on VM-3 itself, a duplicate conflicting route (`192.168.70.0/24 via 10.102.0.164 dev ens33`) is created that takes precedence over `192.168.70.0/24 dev demo-oai`. This loops traffic back to `ens33` causing `Destination Host Unreachable`.
3. **Docker `FORWARD` Filter Chain & Bridge Policy:** Docker defaults the `FORWARD` iptables chain policy to `DROP`. Unless explicitly accepted at rule position 1 of `FORWARD` or permitted in `DOCKER-USER`, Docker drops routed ingress packets between `ens33` and `demo-oai`.
4. **Docker `raw` Table PREROUTING Anti-Spoofing Rule (Root Cause for Zero FORWARD Packets):** When creating user-defined bridge networks, Docker daemon installs anti-spoofing packet filtering rules in the netfilter `raw` table:
   ```text
   -A PREROUTING -d 192.168.70.138/32 ! -i demo-oai -j DROP
   -A PREROUTING -d 192.168.70.142/32 ! -i demo-oai -j DROP
   -A PREROUTING -d 192.168.70.143/32 ! -i demo-oai -j DROP
   ```
   Because routed packets from VM-4 arrive via physical NIC `ens33` (`! -i demo-oai`), the Linux kernel silently drops the packets in the `raw` table **before the packets ever reach the routing decision or the `FORWARD` filter chain** (causing `FORWARD` packet counters to show `pkts = 0` and `tcpdump -i any` to show packets on `ens33` but never on `demo-oai`).

### Solution

#### On VM-4 (`oai-ran`):
Ensure the static route to VM-3 5GC is present:
```bash
sudo ip route add 192.168.70.0/24 via 10.102.0.164
ip route show | grep 192.168.70
```

#### On VM-3 (`oai-5gc`):

```bash
# 1. Bypass Docker raw table PREROUTING anti-spoofing drop rule
sudo iptables -t raw -I PREROUTING 1 -i ens33 -d 192.168.70.0/24 -j ACCEPT

# 2. Allow routed forwarding across ens33 and demo-oai
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv4.conf.all.forwarding=1
sudo sysctl -w net.ipv4.conf.ens33.forwarding=1
echo 1 | sudo tee /proc/sys/net/ipv4/conf/demo-oai/forwarding 2>/dev/null || true

sudo iptables -I FORWARD 1 -i ens33 -o demo-oai -j ACCEPT
sudo iptables -I FORWARD 2 -i demo-oai -o ens33 -j ACCEPT

# 3. Add MASQUERADE on demo-oai so container returns traffic to host gateway
sudo iptables -t nat -I POSTROUTING -o demo-oai -j MASQUERADE

# 4. Remove any accidental static route on VM-3 itself if present
sudo ip route del 192.168.70.0/24 via 10.102.0.164 2>/dev/null || true
```

---

# VM-4 — OAI RAN

---

## Case 24b — Git Clone Failed with RPC failed; curl 92 HTTP/2 stream CANCEL / early EOF

### Symptom
When cloning the official `openairinterface5g` repository:

```text
error: RPC failed; curl 92 HTTP/2 stream 0 was not closed cleanly: CANCEL (err 8)
error: RPC failed; curl 56 GnuTLS recv error (-9): Error decoding the received TLS packet.
error: 5 bytes of body are still expected
fetch-pack: unexpected disconnect while reading sideband packet
fatal: early EOF
fatal: fetch-pack: invalid index-pack output
```

### Cause
Ubuntu's default `git` package is linked against `libcurl-gnutls`. GnuTLS has known issues decoding compressed TLS sideband packets on large git pack transfers when network latency or MTU fragmentation occurs.

### Solution
1. Use tarball download via `wget` (~25 MB):
   ```bash
   cd /opt/oran/ran
   wget -c https://github.com/duranta-project/openairinterface5g/archive/refs/heads/develop.tar.gz -O oai-develop.tar.gz
   mkdir -p openairinterface5g
   tar -xzf oai-develop.tar.gz -C openairinterface5g --strip-components=1
   ```
2. Or use shallow git clone with buffer optimizations:
   ```bash
   git config --global core.compression 0
   git config --global http.postBuffer 524288000
   git config --global http.version HTTP/1.1
   git clone --depth 1 -b develop https://github.com/OPENAIRINTERFACE/openairinterface5g.git
   ```

---

## Case 25b — FlexRIC Tarball Download Fails with HTTP 429 Too Many Requests

### Symptom
When downloading the FlexRIC archive from GitLab EURECOM:

```text
--2026-09-27 10:11:07--  https://gitlab.eurecom.fr/mosaic5g/flexric/-/archive/master/flexric-master.tar.gz
Resolving gitlab.eurecom.fr (gitlab.eurecom.fr)... 193.55.113.249
Connecting to gitlab.eurecom.fr (gitlab.eurecom.fr)|193.55.113.249|:443... connected.
HTTP request sent, awaiting response... 429 Too Many Requests
2026-09-27 10:11:07 ERROR 429: Too Many Requests.
gzip: stdin: unexpected end of file
tar: Child returned status 1
```

### Cause
GitLab EURECOM has an automated rate-limiting policy on dynamic on-the-fly archive generation (`/-/archive/master/...tar.gz`) to protect server CPU resources, returning HTTP 429 for archive generation requests.

### Solution
Do not download the archive tarball. Use a shallow `git clone` directly from the Git repository endpoint, which is lightweight (~8.5 MB) and not subject to the archive generator rate limit:

```bash
cd /opt/oran/ran
rm -rf openairinterface5g/openair2/E2AP/flexric
git clone --depth 1 https://gitlab.eurecom.fr/mosaic5g/flexric.git openairinterface5g/openair2/E2AP/flexric
```

---

## Case 26b — SIMDE Installation Fails with Git Timeout (curl 28) during `./build_oai -I`

### Symptom
During the `./build_oai -I` dependency installation step:

```text
Installing SIMDE from source without test cases (header files only)
Cloning into '/tmp/simde'...
remote: Enumerating objects: 12918, done.
remote: Counting objects: 100% (579/579), done.
remote: Compressing objects: 100% (304/304), done.
error: RPC failed; curl 28 Operation too slow. Less than 1000 bytes/sec transferred the last 600 seconds
error: 487 bytes of body are still expected
fetch-pack: unexpected disconnect while reading sideband packet
fatal: early EOF
fatal: fetch-pack: invalid index-pack output
/opt/oran/ran/openairinterface5g/cmake_targets/tools/build_helper: line 492: cd: /tmp/simde: No such file or directory
fatal: not a git repository (or any of the parent directories): .git
cp: cannot stat '../simde': No such file or directory
BUILD SHOULD BE SUCCESSFUL
```

### Cause
OAI's `cmake_targets/tools/build_helper` attempts to clone the full repository of `simde-no-tests` without `--depth 1`. On networks with higher latency or packet filtering, the un-shallow transfer times out after 600 seconds (`curl 28 Operation too slow`). Although the script concludes with `BUILD SHOULD BE SUCCESSFUL`, the header files in `/usr/include/simde` are missing, which breaks the subsequent `nr-softmodem` build.

### Solution
SIMDe (SIMD Everywhere) is a **header-only** library. Either install the distro package or perform a shallow clone manually:

#### Option 1: Install official package (instant)
```bash
sudo apt update && sudo apt install -y libsimde-dev
```

#### Option 2: Shallow clone manual copy
```bash
sudo rm -rf /tmp/simde
git clone --depth 1 https://github.com/simd-everywhere/simde-no-tests.git /tmp/simde
sudo cp -r /tmp/simde/simde /usr/include/
```

Verify the header installation:
```bash
ls -d /usr/include/simde
# Expected: /usr/include/simde
```

---

## Case 27 — GCC 11 Internal Compiler Error (Segmentation fault) on FlexRIC `kpm_sm` `_Generic` Macro

### Symptom
When compiling FlexRIC Service Models with `gcc-11` (Ubuntu 22.04 default compiler) under `-O2`:

```text
FAILED: openair2/E2AP/flexric/src/sm/kpm_sm/kpm_sm_v02.03/CMakeFiles/kpm_sm.dir/kpm_sm_ric.c.o 
during RTL pass: expand
/opt/oran/ran/openairinterface5g/openair2/E2AP/flexric/src/sm/kpm_sm/kpm_sm_v02.03/dec/kpm_dec_generic.h:38:33: internal compiler error: Segmentation fault
   38 | #define kpm_dec_func_def(T,U,V) _Generic ((T), \
```

### Cause
GCC 11.4 (Ubuntu 22.04 default) has a known upstream bug in the RTL `expand` pass that segfaults when evaluating functions that return large ASN.1-generated structures under optimization (`-O2` / `-funroll-loops`). This bug is fixed upstream in **GCC 12.3+**.

### Solution
Install and activate **GCC 12** via `update-alternatives`:

```bash
# 1. Install GCC 12 & G++ 12 from official Ubuntu repositories
sudo apt update && sudo apt install -y gcc-12 g++-12

# 2. Configure GCC 12 as default system compiler
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-12 100 --slave /usr/bin/g++ g++ /usr/bin/g++-12
sudo update-alternatives --install /usr/bin/cc cc /usr/bin/gcc 100
sudo update-alternatives --install /usr/bin/c++ c++ /usr/bin/g++ 100

# Verify active compiler version (should report GCC 12.3.0)
gcc --version
```

---

## Case 30 — F1-U GTP-U Socket Bind Collision on VM-4 (`bind: Address already in use: 127.0.0.1 2153`)

### Symptom
When starting DU-1 (`du_gnb1.conf`) after CU (`cu_gnb.conf`) is already active on VM-4:

```text
[GTPU]   Initializing UDP for local address 127.0.0.1 with port 2153
[GTPU]   bind: Address already in use
[GTPU]   failed to bind socket: 127.0.0.1 2153 
[GTPU]   can't create GTP-U instance

Assertion (gtpInst > 0) failed!
In F1AP_DU_task() /opt/oran/ran/openairinterface5g/openair2/F1AP/f1ap_du_task.c:121
cannot create DU F1-U GTP module
```

### Cause
CU (`cu_gnb.conf`), DU-1 (`du_gnb1.conf`), and DU-2 (`du_gnb2.conf`) run as separate Linux processes on the same host (VM-4) using the local loopback interface (`127.0.0.1`).  
Because CU binds to `127.0.0.1:2153` (`local_s_portd = 2153`), DU-1 cannot bind to the exact same UDP port on `127.0.0.1` (`local_n_portd = 2153`).  
DU-2 does not experience this error because it uses port `2154` (`local_n_portd = 2154`).

### Solution
Differentiate the F1-U listening UDP ports across all three nodes:
- **CU:** listens on `127.0.0.1:2153` (`local_s_portd = 2153`)
- **DU-1:** binds to `127.0.0.1:2155` (`local_n_portd = 2155`, sending to CU at `remote_n_portd = 2153`)
- **DU-2:** binds to `127.0.0.1:2154` (`local_n_portd = 2154`, sending to CU at `remote_n_portd = 2153`)

Update `/opt/oran/ran/conf/du_gnb1.conf`:
```bash
sed -i 's/local_n_portd.*=.*2153/local_n_portd   = 2155/g' /opt/oran/ran/conf/du_gnb1.conf
```

Verify the setting:
```bash
grep -E "local_n_portd|remote_n_portd" /opt/oran/ran/conf/du_gnb1.conf
# Output:
# local_n_portd   = 2155;
# remote_n_portd  = 2153;
```

---

## Case 37 — Packet Drop / Ping Timeout from RAN (VM-4) to 5GC Docker Subnet (`192.168.70.0/24`) via Host VM-3

### Symptom
When testing reachability from VM-4 (`oai-ran` — `10.102.0.167`) to the 5G Core AMF container (`192.168.70.138`) or UPF containers:
```bash
ping -c 2 192.168.70.138
# Output:
# 2 packets transmitted, 0 received, 100% packet loss, time 1020ms
```
However, ping from VM-4 to the physical host VM-3 (`10.102.0.164`) succeeds with 0% packet loss.

### Cause
By default on Ubuntu and Docker:
1. **Docker FORWARD Chain Rejection:** Docker inserts a default `-j DROP` rule at the bottom of the `FORWARD` filter chain. Forwarded IP packets arriving on external host interfaces (e.g. `ens33`) destined for internal container bridge networks (`192.168.70.0/24`) are discarded.
2. **Reverse Path Filtering (`rp_filter`):** The Linux kernel performs strict reverse-path checks. Because the source address belongs to `10.102.0.0/24` and enters an interface with a different local subnet routing, the kernel flags it as a martian/spoofed packet and drops it silently.
3. **UFW / Firewall Rules:** Active firewall configurations reject forwarded inter-subnet packets by default.

### Solution
Apply the following routing and forwarding configuration on **VM-3 (`10.102.0.164`)**:

```bash
# 1. Disable UFW if active
sudo ufw disable 2>/dev/null || true

# 2. Enable kernel forwarding and disable reverse-path filtering across all interfaces
sudo sysctl -w net.ipv4.ip_forward=1
sudo sysctl -w net.ipv4.conf.all.rp_filter=0
sudo sysctl -w net.ipv4.conf.default.rp_filter=0
for f in /proc/sys/net/ipv4/conf/*/rp_filter; do echo 0 | sudo tee $f > /dev/null; done

# 3. Allow packet forwarding in DOCKER-USER and FORWARD iptables chains
sudo iptables -I DOCKER-USER 1 -j ACCEPT
sudo iptables -I FORWARD 1 -j ACCEPT

# 4. Enable bidirectional NAT masquerading for the container bridge network
sudo iptables -t nat -I POSTROUTING 1 -d 192.168.70.0/24 -j MASQUERADE
sudo iptables -t nat -I POSTROUTING 2 -s 192.168.70.0/24 -j MASQUERADE
```

On **VM-4 (`10.102.0.167`)**, ensure the static route exists:
```bash
sudo ip route replace 192.168.70.0/24 via 10.102.0.164
ping -c 2 192.168.70.138
# Expected: 2 packets transmitted, 2 received, 0% packet loss
```

---

## Case 38 — OAI gNB CU E2 Agent Inactive / Disabled (`E2 agent is DISABLED`)

### Symptom
When starting OAI CU softmodem with `sudo ./nr-softmodem -O /opt/oran/ran/conf/cu_gnb.conf`, CU connects to 5GC AMF via N2, but no E2 connection is initiated toward Near-RT RIC (`ric_e2term`).  
Alternatively, the logs show:
```text
E2 agent is DISABLED (for activation, define .e2_agent.{near_ric_ip_addr,sm_dir} parameters)
```
And `ric_e2term` on VM-2 does not receive any SCTP connection.

### Cause
In the OpenAirInterface `develop` branch, the E2 agent argument parser (`openair2/E2AP/e2_agent_arg.c`) checks parameter readiness using `config_isparamset()`. If the configuration file structure uses nested syntax or if the config loader initializes before the main RRC context is populated, `config_isparamset()` may evaluate to false, keeping `oai_args.enabled = false` and disabling the E2 agent thread.

### Solution
Pass the E2 agent parameters explicitly via command-line arguments when launching `nr-softmodem`:

```bash
cd /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build

sudo ./nr-softmodem -O /opt/oran/ran/conf/cu_gnb.conf \
  --e2_agent.near_ric_ip_addr 10.102.0.66 \
  --e2_agent.sm_dir /usr/local/lib/flexric/ \
  2>&1 | tee /opt/oran/ran/cu.log
```

Expected output verifying active E2 initialization:
```text
After RCconfig_NR_E2agent /usr/local/lib/flexric/ 10.102.0.66
[E2 NODE]: mcc = 208 mnc = 95 mnc_digit = 2 nb_id = 3584
[E2 NODE]: Args 10.102.0.66 /usr/local/lib/flexric/
```

And in `ric_e2mgr` logs on VM-2:
```bash
#RanConnectStatusChangeManager.ChangeStatus - RAN name: gnb_208_095_00000e00, currentStatus: UNKNOWN_CONNECTION_STATUS, nextStatus: CONNECTED
```

---

## Case 39 — OAI nrUE Softmodem Immediate Abort on Deprecated Command-Line Option `--sa`

### Symptom
When starting `nr-uesoftmodem` with the flag `--sa`:
```text
[CONFIG] unknown option: --sa
[ENB_APP] [CONFIG] 1 unknown option(s) in command line starting with  (section ALLSECTIONS)
[NR_PHY] called by: config_check_unknown_cmdlineopt() Exiting OAI softmodem: exit_fun
[NR_PHY] UE main thread is ending
```
The softmodem performs radio cell detection, RACH, and RRC connection, but immediately aborts and exits.

### Cause
In the OpenAirInterface `develop` branch, Standalone (SA) mode has been set as the default operation mode for `nr-uesoftmodem`. The `--sa` command-line flag was deprecated and removed from the active parameter definition list. The strict option validator in `config_cmdline.c` treats `--sa` as an unknown command-line option and forcefully terminates the softmodem.

### Solution
Remove the `--sa` flag from the command line invocation. `nr-uesoftmodem` automatically defaults to Standalone mode:

```bash
cd /opt/oran/ue/openairinterface5g/cmake_targets/ran_build/build

sudo ./nr-uesoftmodem \
  -r 106 \
  --numerology 1 \
  --band 78 \
  -C 3619200000 \
  --rfsim \
  --rfsimulator.serveraddr 10.102.0.167 \
  --rfsimulator.serverport 4043 \
  -O /opt/oran/ue/conf/ue_slice1.conf
```

---

## Case 41 — User-Plane Packet Drop on F1-U: Stale TEID Mapping in gNB CU (`no tunnel mapping, drop`)

### Symptom
On VM-5, `nr-uesoftmodem` successfully establishes a PDU session, and `oaitun_ue1` is configured with IP `12.1.1.2`. On VM-3, `oai-upf-slice1` confirms active PDR/FAR rules for `12.1.1.2`.  
However, pinging from UE (`ping -I oaitun_ue1 -c 4 192.168.70.145`) or gateway `12.1.1.1` results in 100% packet loss.

On VM-4 (`oai-ran`), `cu.log` repeatedly floods with GTP-U drop messages from DU-1:
```text
[GTPU]   [81] GTP Error Indication TEID-I 0x99b867eb: no tunnel mapping, drop
[GTPU]   [81] Sent GTP Error Indication TEID-I 0x99b867eb to 127.0.0.1:2153
[GTPU]   [81] Received a incoming packet on unknown TEID (0x99b867eb) Dropping!
[GTPU]   [81] GTP Error Indication TEID-I 0x99b867eb GTP-U Peer Address 127.0.0.1 UDP-from 127.0.0.1
```

### Cause
In OAI Split-RAN (CU + DU), the user plane uses F1-U (GTP-U over local port `2153/2152`) to transport data radio bearer (DRB) packets between DU and CU.  
When an nrUE instance is aborted abruptly (e.g. via `Ctrl+C`) or when prior connection attempts failed during 5GC debugging, DU and CU retain orphaned F1-U bearer mappings. When the UE reconnects and initiates user plane traffic, DU forwards packets using a stale or out-of-sync TEID that CU no longer maps to an active N3 GTP-U session, causing CU to drop all uplink traffic.

### Solution
Restart the RAN components on **VM-4** to clear all orphaned GTP-U and F1-U context tables, then relaunch the UE:

1. On **VM-4 (`oai-ran`)**, restart the clean background daemons:
   ```bash
   sudo /opt/oran/ran/start_ran.sh
   ```
2. Verify CU and DU are running fresh:
   ```bash
   pgrep nr-softmodem
   tail -n 15 /opt/oran/ran/cu.log | grep -i "associated"
   ```
3. On **VM-5 (`ue-emulator`)**, restart UE 1:
   ```bash
   cd /opt/oran/ue/openairinterface5g/cmake_targets/ran_build/build
   sudo ./nr-uesoftmodem \
     -r 106 \
     --numerology 1 \
     --band 78 \
     -C 3619200000 \
     --rfsim \
     --rfsimulator.serveraddr 10.102.0.167 \
     --rfsimulator.serverport 4043 \
     -O /opt/oran/ue/conf/ue_slice1.conf
   ```
4. Verify user plane ping from VM-5:
   ```bash
   ping -I oaitun_ue1 -c 4 192.168.70.145
   ping -I oaitun_ue1 -c 4 12.1.1.1
   ```

---

## Case 42 — F1-U Downlink Self-Loop Drop when CU and DU Bind to `127.0.0.1` (`Sent GTP Error Indication ... to 127.0.0.1:2153: no tunnel mapping, drop`)

### Symptom
When UE on VM-5 pings an external Data Network (`192.168.70.145`) or UPF gateway (`12.1.1.1`):
- `tcpdump` on VM-3 confirms that the ICMP echo request reaches UPF-1, EXT-DN replies with ICMP echo reply, and UPF-1 encapsulates the reply into N3 GTP-U and sends it back to gNB CU (`10.102.0.167:2152`).
- However, the UE on VM-5 experiences 100% packet loss.
- On VM-4 (`oai-ran`), `cu.log` logs:
  ```text
  [GTPU]   [81] Sent GTP Error Indication TEID-I 0x... to 127.0.0.1:2153
  [GTPU]   [81] Received a incoming packet on unknown TEID (0x...) Dropping!
  [GTPU]   [81] GTP Error Indication TEID-I 0x... GTP-U Peer Address 127.0.0.1 UDP-from 127.0.0.1
  [GTPU]   [81] GTP Error Indication TEID-I 0x...: no tunnel mapping, drop
  ```

### Cause
In `cu_gnb.conf`, `local_s_address` is set to `127.0.0.1` and `local_s_portd` is `2153`. Because `remote_s_portd` is also configured as `2153`, when CU prepares to send downlink F1-U packets to DU-1, it sends them to destination `127.0.0.1:2153`.  
Because CU itself is listening on `127.0.0.1:2153`, CU receives its own downlink packet on its F1-U listening socket. It attempts to treat the packet as an uplink packet from DU, fails to find an uplink tunnel mapping for the downlink TEID, and forcefully drops it. DU-1 never receives the packet.

### Solution
Use loopback aliases within the standard Linux `127.0.0.0/8` subnet to give CU and each DU distinct IP addresses on port `2153`:
- **CU (`cu_gnb.conf`):** `local_s_address = "127.0.0.3";`
- **DU-1 (`du_gnb1.conf`):** `local_n_address = "127.0.0.4"; remote_n_address = "127.0.0.3"; local_n_portd = 2153; remote_n_portd = 2153;`
- **DU-2 (`du_gnb2.conf`):** `local_n_address = "127.0.0.5"; remote_n_address = "127.0.0.3"; local_n_portd = 2153; remote_n_portd = 2153;`

Apply the fix on VM-4:
```bash
python3 - << 'EOF'
# 1. Update cu_gnb.conf
with open("/opt/oran/ran/conf/cu_gnb.conf", "r") as f:
    cu = f.read()
cu = cu.replace('local_s_address  = "127.0.0.1";', 'local_s_address  = "127.0.0.3";')
cu = cu.replace('local_s_address = "127.0.0.1";', 'local_s_address = "127.0.0.3";')
with open("/opt/oran/ran/conf/cu_gnb.conf", "w") as f:
    f.write(cu)

# 2. Update du_gnb1.conf
with open("/opt/oran/ran/conf/du_gnb1.conf", "r") as f:
    du1 = f.read()
du1 = du1.replace('local_n_address = "127.0.0.1";', 'local_n_address = "127.0.0.4";')
du1 = du1.replace('remote_n_address = "127.0.0.1";', 'remote_n_address = "127.0.0.3";')
du1 = du1.replace('local_n_portd   = 2155;', 'local_n_portd   = 2153;')
du1 = du1.replace('local_n_portd = 2155;', 'local_n_portd = 2153;')
with open("/opt/oran/ran/conf/du_gnb1.conf", "w") as f:
    f.write(du1)

# 3. Update du_gnb2.conf
with open("/opt/oran/ran/conf/du_gnb2.conf", "r") as f:
    du2 = f.read()
du2 = du2.replace('local_n_address = "127.0.0.1";', 'local_n_address = "127.0.0.5";')
du2 = du2.replace('remote_n_address = "127.0.0.1";', 'remote_n_address = "127.0.0.3";')
du2 = du2.replace('local_n_portd   = 2154;', 'local_n_portd   = 2153;')
du2 = du2.replace('local_n_portd = 2154;', 'local_n_portd = 2153;')
with open("/opt/oran/ran/conf/du_gnb2.conf", "w") as f:
    f.write(du2)

print("Loopback aliases configured successfully.")
EOF

sudo /opt/oran/ran/start_ran.sh
```

---

## Case 46 — Stale NRF Session & Cross-VM Split-RAN Desynchronization

### Symptom
1. In `oai-smf-slice1` logs:
   ```text
   [smf_sbi] Response data {"cause":"RESOURCE_URI_STRUCTURE_NOT_FOUND"}
   [smf_sbi] NF Instance Registration, response from NRF, HTTP Code: 404
   [smf_sbi] NF Update, could not get response from NRF
   ```
2. In `oai-amf` logs:
   ```text
   [amf_sbi] Cannot get response when calling
   [amf_app] [warning] NF Instance Registration, got issue when registering to NRF, try again ...
   ```
3. In `ue1.log` on VM-5:
   ```text
   [NAS] requested PDU session ID 10 type 1 NSSAI 1.1 DNN default
   [NAS] Send NAS_UPLINK_DATA_REQ message(PduSessionEstablishRequest)
   [NAS] Received NAS_DOWNLINK_DATA_IND type FGS_PDU_SESSION_ESTABLISHMENT_REJ with length 21
   [NAS] Received PDU Session Establishment reject
   ```
4. After restarting `oai-amf`, both UE 1 and UE 2 show `Tunnel IP: DOWN` and `Ping: FAIL`.
5. Running `ip a | grep tun` on the root host of VM-5 returns nothing.

### Cause
1. **NRF SBI Expiry:** When 5GC Network Functions (`oai-amf`, `oai-smf-slice1`) run continuously across days without a coordinated restart, internal HTTP/2 SBI client handles or NRF instance registration URIs expire. AMF cannot resolve SMF endpoints, immediately returning `FGS_PDU_SESSION_ESTABLISHMENT_REJ` to the UE.
2. **Split-RAN CU N2/F1-U Orphan:** When `oai-amf` restarts, the N2 SCTP socket to gNB-CU on VM-4 drops. OAI `nr-softmodem` CU does not automatically rebind its F1-C and GTP-U TEID mappings cleanly, preventing subsequent UE registrations from completing.
3. **Network Namespace Isolation:** VM-5 uses Linux Network Namespaces (`ue1` and `ue2`). Interfaces `oaitun_ue1` exist exclusively inside their respective namespaces, never appearing on the host's root network stack.

### Solution
Follow the strict 3-VM startup sequence to achieve complete end-to-end synchronization:
1. **VM-3 (`oai-core`):** Synchronously restart the core slicing services:
   ```bash
   sudo docker restart oai-nrf-slice12 oai-nssf oai-amf oai-smf-slice1 oai-smf-slice2 oai-upf-slice1 oai-upf-slice2
   ```
2. **VM-4 (`oai-ran`):** Restart the split CU and multi-DU processes to rebind N2 and F1:
   ```bash
   sudo /opt/oran/ran/stop_ran.sh
   sleep 2
   sudo /opt/oran/ran/start_ran.sh
   sleep 4
   grep -E "associated AMF|is in service" /opt/oran/ran/cu.log | tail -n 5
   ```
3. **VM-5 (`nrue`):** Spawn the isolated multi-UE instances and verify tunnel IPs inside each netns:
   ```bash
   sudo /opt/oran/ue/scripts/stop_multi_ue.sh
   sudo /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1
   sudo ip netns exec ue1 ip addr show oaitun_ue1
   sudo ip netns exec ue2 ip addr show oaitun_ue1
   sudo /opt/oran/ue/scripts/trafgen.sh ping
   ```

---

<a id="case-49"></a>
## Case 49 — UE 2 PDU Session Establishment Rejected — MySQL S-NSSAI Subscriber Profile Mismatch

### Symptom

UE 2 (`IMSI: 208950000000002`, Slice 2 URLLC) spawned via `spawn_multi_ue.sh` fails PDU Session Establishment. In `ue2.log`:

```text
[NAS] requested PDU session ID 10 type 1 NSSAI 222.123 DNN lowlatency
[NAS] Send NAS_UPLINK_DATA_REQ message(PduSessionEstablishRequest)
[NAS] Received NAS_DOWNLINK_DATA_IND type FGS_PDU_SESSION_ESTABLISHMENT_REJ with length 21
[NAS] Received PDU Session Establishment reject
```

Meanwhile UE 1 (`IMSI: 208950000000001`, Slice 1 eMBB) connects successfully with `oaitun_ue1` UP and ping to DN (`192.168.70.145`) succeeding.

### Cause

The MySQL subscriber database (`oai_db`) had conflicting S-NSSAI provisioning for UE 2's IMSI in the `SessionManagementSubscriptionData` table. Specifically:

1. The `singleNssai` column pointed to an incorrect slice ({SST: 1, SD: "000001"} — Slice 1 eMBB) instead of UE 2's intended Slice 2 ({SST: 222, SD: "00007B" / `123` decimal}).
2. Because the subscriber's session management data did not reference the correct `defaultSingleNssais` or `dnn-configurations`, `oai-smf-slice2` could not find a matching DNN profile and rejected the session immediately with `FGS_PDU_SESSION_ESTABLISHMENT_REJ`.

### Solution

1. Connect to the `mysql` container on VM-3:
   ```bash
   sudo docker exec -it mysql mysql -u root -plinux oai_db
   ```

2. Verify the current (incorrect) subscription:
   ```sql
   SELECT * FROM SessionManagementSubscriptionData
   WHERE ueid = '208950000000002' AND sst = 222;
   ```

3. Correct the `singleNssai` JSON and `dnn-configurations` to align with Slice 2 (SST: 222, SD: "00007B"):
   ```sql
   UPDATE SessionManagementSubscriptionData
   SET singleNssai = '{"sst":222,"sd":"00007B"}'
   WHERE ueid = '208950000000002' AND sst = 222;
   ```

4. Restart the affected core services to flush stale AMF/SMF state and allow re-registration:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   sudo docker compose -f docker-compose-slicing-basic-nrf.yaml restart oai_amf oai_smf_slice1 oai_smf_slice2 oai-nwdaf-sbi
   ```

5. Re-run the UE spawner and verify UE 2 obtains `oaitun_ue1` inside namespace `ue2`:
   ```bash
   sudo ip netns exec ue2 ip -4 addr show oaitun_ue1
   ```

---

<a id="case-50"></a>
## Case 50 — OAI Telnet Server Missing (`libtelnetsrv.so`) & CLI Array Parsing Failure

### Symptom
When starting `nr-softmodem` on VM-4 with `--telnetsrv` flags, the process aborts or logs:
```text
[LOADER] library libtelnetsrv.so is not loaded: No such file or directory
[CONFIG] unknown option: --telnetsrv.listenport
```
Furthermore, passing `--rfsimulator.options chanmod` via CLI fails with:
```text
[CONFIG] unknown option: chanmod
```

### Cause
1. In the OAI CMake build configuration, `ENABLE_TELNETSRV` is marked as an optional component (`OPTIONAL_LIBRARIES`) and defaults to `OFF`. The softmodem attempts runtime `dlopen("libtelnetsrv.so")`. If not compiled, the Telnet server command-line options fail to register.
2. In `du_gnb1.conf`, `rfsimulator.options` is typed as a libconfig array of strings (e.g., `options = ("chanmod");`). The OAI CLI parser does not support appending string elements to array structures from raw scalar command-line arguments.

### Solution
1. Reconfigure CMake and compile the Telnet shared library targets:
   ```bash
   cd /opt/oran/ran/openairinterface5g/cmake_targets/ran_build/build
   cmake -DENABLE_TELNETSRV=ON .
   ninja telnetsrv
   ls -la libtelnetsrv*.so
   ```
   *Verified output confirms `libtelnetsrv.so` and `libtelnetsrv_ci.so` (Channel Impairment) are built.*

2. Configure `options = ("chanmod");` directly inside `/opt/oran/ran/conf/du_gnb1.conf`:
   ```hcl
   rfsimulator = (
     {
       serveraddr = "server";
       serverport = 4043;
       options = ("chanmod");
       modelname = "AWGN";
       IQfile = "/tmp/rfsimulator.iqs";
     }
   );
   ```

3. Launch DU-1 cleanly without CLI array overrides:
   ```bash
   ./nr-softmodem -O /opt/oran/ran/conf/du_gnb1.conf --rfsim --telnetsrv --telnetsrv.listenport 9090
   ```

---

<a id="case-51"></a>
## Case 51 — Radio Impairment Target Identification: Downlink (Model 0) vs Uplink (Model 1) in `du_gnb1.conf`

### Symptom
Executing `channelmod modify 0 ploss <dB>` via Telnet succeeds, but monitoring DU-1 scheduler logs (`ulsch`) shows that Uplink SNR, RSSI, and MCS remain unchanged.

### Cause
In this testbed's configuration (`du_gnb1.conf`), channel modeling descriptors configured under `modellist_rfsimu_1` are mapped sequentially by index:
* **`model 0: rfsimu_channel_enB0`** $\implies$ Configured as Downlink Channel (gNB TX $\to$ UE RX).
* **`model 1: rfsimu_channel_ue0`** $\implies$ Configured as Uplink Channel (UE TX $\to$ gNB RX).

Because the telemetry pipeline and `ran_adapter.py` monitor the Uplink Shared Channel (`ulsch`) scheduler logs on gNB, modifying Model 0 primarily impacts Downlink signal reception at the UE. To induce degradation on Uplink telemetry metrics, Model 1 must be targeted.
> [!NOTE]
> This channel assignment is defined by the model list in `du_gnb1.conf`, not an immutable hardcoded constant of OAI. If the configuration order or model names change, verify active models with `channelmod show current`.

### Solution
1. Target channel modifications explicitly to Channel 1 (Uplink in this testbed):
   ```bash
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py set-attenuation 10.0 --channel-id 1 --port 9090
   ```
2. The controller script `rfsim_channel_control.py` uses isolated per-channel regex extraction (`get_channel_block`) and explicitly fails if the requested channel index is not present in the softmodem response.

---

<a id="case-52"></a>
## Case 52 — OAI MAC Log String Truncation (`BLER` to `BLE`) Observed Under High HARQ Retransmissions

### Symptom
When severe channel attenuation is injected on DU-1, `ran_adapter.py` intermittently dropped telemetric readings or fell back to `N/A`, even though `du1.log` continued to update.

### Cause
In live testbed log samples under high retransmission conditions, lines matching `BLE <float>` were observed in place of the expected `BLER <float>` (e.g., `ulsch_rounds 66483/6159/210/165 ... BLE 0.80550 MCS (0) 14`). While the exact underlying formatting behavior in OAI C code remains under investigation, the strict pattern `BLER\s+` fails to match these lines whenever the trailing 'R' is missing.

### Solution
Update `RADIO_STATS_PATTERN` in `scripts/ran_adapter.py` to make the trailing 'R' optional:
```python
RADIO_STATS_PATTERN = re.compile(
    r'ulsch_errors\s+(?P<errors>\d+).*?'
    r'BLER?\s+(?P<bler>[0-9.]+).*?'
    r'MCS\s*(?:\([^)]*\))?\s*(?P<mcs>\d+).*?'
    r'NPRB\s+(?P<nprb>\d+).*?'
    r'SNR\s+(?P<snr>[-0-9.]+).*?'
    r'RSSI\s+(?P<rssi>[-0-9.]+)'
)
```
This regex accommodates both observed variants (`BLER` and `BLE`), ensuring continuous metric extraction across baseline and degraded states.

---

<a id="case-53"></a>
## Case 53 — Radio Link Failure (RLF) Breakdown Threshold & Tunnel Teardown

### Symptom
Injecting excessive attenuation causes client traffic (`iperf3`) to abort with:
```text
iperf3: error - unable to write to stream socket: Network is unreachable
iperf3: error - unable to send control message: Connection reset by peer
```
Interface `oaitun_ue1` is deleted from namespace `ue1`.

### Cause
When path loss increases substantially beyond receiver sensitivity, received signal power drops below detection threshold, `pucch0_DTX` counters rise, and OAI triggers standard 3GPP Radio Link Failure (RLF). Upon RLF and session teardown, the Linux kernel removes the PDU session tunnel `oaitun_ue1`.

### Solution
1. **Calibrated Operating Regimes (Testbed-Specific):**
   * **Degraded Channel Evaluation (Non-RLF):** Under this testbed's baseline configuration (`du_gnb1.conf`, AWGN, full-buffer 15 Mbps UDP, MCS baseline 28), attenuation values between **$5\text{ dB}$ and $16\text{ dB}$** provide controlled stress: RSSI decreases, BLER dynamically rises into the ~30–80% range, and MCS adapts without dropping the PDU session.
   * **Outage & Service Disruption Evaluation:** In this testbed, attenuation $\ge 20 - 25\text{ dB}$ consistently induced RLF and interface teardown.
   > [!NOTE]
   > Exact threshold values depend on the specific channel model, configured noise power, bandwidth, and traffic load, and should be calibrated for each experimental environment.
2. **Recovery from Outage:**
   Reset the RFsim channels on VM-4:
   ```bash
   python3 /opt/oran/ran/scripts/rfsim_channel_control.py reset --port 9090
   ```
   Respawn the UE instances on VM-5:
   ```bash
   sudo bash /opt/oran/ue/scripts/stop_multi_ue.sh
   sudo bash /opt/oran/ue/scripts/spawn_multi_ue.sh -s1 1 -s2 1
   ```

---

<a id="case-54"></a>
## Case 54 — 5G Core Docker JSON Log Growth and Rotation Configuration

### Symptom
Executing diagnostic commands on VM-3 such as `sudo docker logs oai-amf --tail 30` takes over 30 seconds or causes the SSH session to hang.

### Cause
When the 23 5GC containers run across extended testing campaigns without log rotation limits, individual container log files (`/var/lib/docker/containers/*/*-json.log`) can grow to multiple gigabytes. Reading the tail of bloated JSON files requires the Docker daemon to traverse large files on disk.

### Solution

#### Step 1: Configure Docker Daemon Log Rotation
Edit `/etc/docker/daemon.json` on VM-3 to enforce log rotation globally for newly created containers:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "50m",
    "max-file": "3"
  }
}
```
Reload and restart the Docker service:
```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
```

#### Step 2: Recreate Existing Containers to Apply Log Rotation
> [!IMPORTANT]
> **Daemon Config Does Not Retroactively Update Running Containers:**  
> According to [official Docker documentation](https://docs.docker.com/engine/logging/drivers/json-file/), changing `daemon.json` only applies to *newly created* containers. Existing containers keep the logging driver configuration they were originally started with. Merely restarting the Docker service does **not** update existing container log settings.

1. **Verify Volume Persistence First:**
   Before recreating containers, verify that stateful datastores use persistent Docker volumes so subscriber identities and metrics are preserved:
   * **MySQL (`oai-db`):** Verify named volume `db-data` or directory mount in `docker-compose-slicing-basic-nrf.yaml` (`/var/lib/mysql`).
   * **MongoDB (`mongodb`):** Verify named volume `mongodb-data` (`/data/db`).
   * *Note:* All other 5GC core network functions (AMF, SMF, UPF, NRF, AUSF, UDM, UDR, NWDAF) are stateless microservices that reconstruct session state from database/NRF registrations.

2. **Inspect and Recreate Containers:**
   Check current container logging config (typically empty before recreation):
   ```bash
   docker inspect oai-amf --format '{{json .HostConfig.LogConfig}}'
   ```
   Recreate the 5GC stack to inherit the new daemon logging limits:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   docker compose -f docker-compose-slicing-basic-nrf.yaml up -d --force-recreate
   ```
   Recreate the NWDAF stack:
   ```bash
   cd /opt/oran/5gc/oai-cn5g-fed/docker-compose
   docker compose -f docker-compose-nwdaf.yaml up -d --force-recreate
   ```

3. **Verify Active Log Limits on Running Containers:**
   Confirm that recreated containers have active rotation constraints:
   ```bash
   docker inspect oai-amf --format '{{json .HostConfig.LogConfig}}'
   # Expected output: {"Type":"json-file","Config":{"max-file":"3","max-size":"50m"}}
   ```

> [!WARNING]
> **Avoid Manual `truncate` of Container Log Files:**  
> Directly truncating active container log files (`*-json.log`) can corrupt internal logging file descriptor tracking and permanently erases diagnostic evidence across all containers. Always use Docker's native log rotation (`max-size` / `max-file`) or Docker Compose logging options as described above.
