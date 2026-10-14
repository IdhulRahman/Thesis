#!/usr/bin/env python3
"""UPF Research Telemetry Collector v9 -- Python 3.9+, standard library only.

Run on the Docker host (VM-3), not inside an UPF container.
Reads Linux interface counters and ONE explicitly selected egress qdisc.
Records raw measurements, missing values, independent intervals and identities.
Does not modify traffic control, create labels, or calculate NWDAF slice load.

Official design references (see --standards):
  TS 32.401 v17.0.0, 5.4.1.5: identity, timestamp, validity, incomplete scans.
  TS 32.435 v17.0.0, 4.2.2: duration/end-time metadata (XML is not implemented).
  TS 28.552 v17.11.0, 5.4.1.3-4: GTP counters have protocol-specific semantics.
  TS 28.554 v17.17.0, 6.3.4-5: volume divided by the observation interval.
  TS 23.288 v17.5.0, 6.2.3: NWDAF collection through OAM services.

This is a research collector informed by PM principles, not certification of
3GPP compliance, an Nnwdaf service, a DCCF, or a TS 32.435 XML PM exporter.
One-second sampling and this JSON/CSV schema are research implementation choices.
"""

import argparse
import concurrent.futures
import copy
import csv
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import queue
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
import urllib.error
import urllib.request
import uuid

VERSION = "9.0.0"
SCHEMA = "upf-research-telemetry/v9"
LOG = logging.getLogger("upf-collector")
DEFAULT_CONFIG = {
    "resources": {
        "01000001": {
            "container": "oai-upf-slice1", "interface": "eth0",
            "snssai": {"sst": 1, "sd": "000001"},
            "qdisc_selector": {"root": True},
        },
        "de00007b": {
            "container": "oai-upf-slice2", "interface": "eth0",
            "snssai": {"sst": 222, "sd": "00007B"},
            "qdisc_selector": {"root": True},
        },
    }
}
STANDARDS = [
    {"document": "3GPP TS 32.401 v17.0.0", "clauses": "5.4.1.4-5",
     "url": "https://www.etsi.org/deliver/etsi_ts/132400_132499/132401/17.00.00_60/ts_132401v170000p.pdf"},
    {"document": "3GPP TS 32.435 v17.0.0", "clauses": "4.2.2",
     "url": "https://www.etsi.org/deliver/etsi_ts/132400_132499/132435/17.00.00_60/ts_132435v170000p.pdf"},
    {"document": "3GPP TS 28.552 v17.11.0", "clauses": "5.4.1.3-4",
     "url": "https://www.etsi.org/deliver/etsi_ts/128500_128599/128552/17.11.00_60/ts_128552v171100p.pdf"},
    {"document": "3GPP TS 28.554 v17.17.0", "clauses": "6.3.4-5",
     "url": "https://www.etsi.org/deliver/etsi_ts/128500_128599/128554/17.17.00_60/ts_128554v171700p.pdf"},
    {"document": "3GPP TS 23.288 v17.5.0", "clauses": "6.2.3",
     "url": "https://www.etsi.org/deliver/etsi_ts/123200_123299/123288/17.05.00_60/ts_123288v170500p.pdf"},
    {"document": "Linux kernel: Interface statistics",
     "url": "https://www.kernel.org/doc/html/latest/networking/statistics.html"},
]
NET_FIELDS = (
    "rx_bytes", "rx_packets", "rx_errors", "rx_dropped", "rx_fifo_errors",
    "rx_frame_errors", "rx_compressed", "rx_multicast", "tx_bytes", "tx_packets",
    "tx_errors", "tx_dropped", "tx_fifo_errors", "tx_collisions",
    "tx_carrier_errors", "tx_compressed",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def nonnegative_integer(value):
    """JSON bool, strings, fractional/negative values are not counter values."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def run_command(argv, timeout):
    """Bracket each read; midpoint is an estimate, not a packet timestamp."""
    start_mono = time.monotonic()
    start_utc = utc_now()
    output, error = None, None
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                   check=False, encoding="utf-8", errors="replace")
        if completed.returncode:
            error = "EXIT_{}: {}".format(completed.returncode, completed.stderr.strip()[:300])
        else:
            output = completed.stdout
    except subprocess.TimeoutExpired:
        error = "COMMAND_TIMEOUT"
    except OSError as exc:
        error = "COMMAND_ERROR: {}".format(str(exc)[:300])
    end_mono = time.monotonic()
    end_utc = utc_now()
    wall_duration = datetime.fromisoformat(end_utc) - datetime.fromisoformat(start_utc)
    midpoint_utc = datetime.fromisoformat(start_utc) + wall_duration / 2
    return {
        "output": output, "error": error,
        "mono": (start_mono + end_mono) / 2.0,
        "stamp": {
            "read_started_utc": start_utc, "read_finished_utc": end_utc,
            "sample_time_estimate_utc": midpoint_utc.isoformat(timespec="microseconds"),
            "read_duration_sec": end_mono - start_mono,
            "time_estimate_method": "host_command_midpoint_with_read_bounds",
            # 50 ms tolerance is an audit choice, not a standardized threshold.
            "utc_clock_step_suspected": abs(wall_duration.total_seconds() - (end_mono - start_mono)) > 0.05,
        },
    }


def inspect_container(name, timeout):
    """Pin exec to container ID; record restart epoch and image, not environment."""
    result = run_command(["docker", "inspect", "--type", "container", name], timeout)
    if result["error"]:
        raise ValueError(result["error"])
    try:
        obj = json.loads(result["output"])[0]
        st = obj["State"]
        if st.get("Running") is not True or st.get("Restarting") is True:
            raise ValueError("CONTAINER_NOT_RUNNING")
        identity = {"container_id": obj["Id"], "started_at": st["StartedAt"],
                    "pid": st["Pid"], "image_id": obj["Image"]}
        if not identity["started_at"] or not isinstance(identity["pid"], int) or identity["pid"] <= 0:
            raise ValueError("CONTAINER_IDENTITY_INCOMPLETE")
        return identity
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("INSPECT_PARSE_ERROR") from exc


def read_source(container_id, iface, source, timeout):
    # Fixed shell program; interface is a separate quoted positional argument.
    prefix = 'cat "/sys/class/net/$1/ifindex" && '
    script = prefix + ("cat /proc/net/dev" if source == "net" else 'exec tc -j -s qdisc show dev "$1"')
    return run_command(["docker", "exec", container_id, "sh", "-c", script, "collector", iface], timeout)


def parse_source_prefix(output):
    index_text, separator, body = output.partition("\n")
    if not separator or not index_text.strip().isdigit() or int(index_text.strip()) <= 0:
        raise ValueError("IFINDEX_MISSING_OR_INVALID")
    return int(index_text.strip()), body


def parse_net(output, iface):
    ifindex, body = parse_source_prefix(output)
    rows = []
    for line in body.splitlines():
        if ":" in line:
            name, fields = line.rsplit(":", 1)
            if name.strip() == iface:
                rows.append(fields.split())
    if len(rows) != 1 or len(rows[0]) != len(NET_FIELDS):
        raise ValueError("NET_INTERFACE_MISSING_OR_MALFORMED")
    if any(not field.isdigit() for field in rows[0]):
        raise ValueError("NET_COUNTER_NOT_NONNEGATIVE_INTEGER")
    return ifindex, dict(zip(NET_FIELDS, map(int, rows[0])))


def parse_qdiscs(output):
    ifindex, body = parse_source_prefix(output)
    try:
        values = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("QDISC_JSON_INVALID_OR_UNSUPPORTED") from exc
    if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
        raise ValueError("QDISC_JSON_NOT_LIST_OF_OBJECTS")
    return ifindex, values


def select_qdisc(values, selector):
    """Never sum parent and child stats; select exactly one egress qdisc."""
    candidates = []
    for item in values:
        if item.get("kind") in ("ingress", "clsact"):
            continue
        match = True
        for key, wanted in selector.items():
            actual = (item.get("root") is True or item.get("parent") == "root") if key == "root" else item.get(key)
            if actual != wanted:
                match = False
        if match:
            candidates.append(item)
    if len(candidates) != 1:
        raise ValueError("QDISC_SELECTION_{}_MATCHES".format(len(candidates)))
    selected = candidates[0]
    if not isinstance(selected.get("kind"), str) or not isinstance(selected.get("handle"), str):
        raise ValueError("QDISC_IDENTITY_INCOMPLETE")
    return selected


def qdisc_drop_value(selected):
    """iproute2 STATS2 uses 'drops'; legacy STATS can use 'dropped'."""
    present = [key for key in ("drops", "dropped") if key in selected]
    if not present:
        return None, None
    values = [nonnegative_integer(selected[key]) for key in present]
    if any(value is None for value in values) or len(set(values)) != 1:
        return None, "+".join(present)
    return values[0], "+".join(present)


class CounterTracker:
    """An independent baseline per counter, advanced only on a valid read."""

    def __init__(self, max_gap):
        self.max_gap = max_gap
        self.previous = None
        self.missing_reads = 0

    def observe(self, value, mono, utc, epoch):
        result = {"delta": None, "rate_per_sec": None, "valid": False,
                  "interval_sec": None, "interval_start_utc": None,
                  "interval_end_utc": utc, "missing_reads_in_interval": self.missing_reads,
                  "reason": "SOURCE_INVALID"}
        if nonnegative_integer(value) is None:
            self.missing_reads += 1
            return result
        current = (value, mono, utc, epoch)
        prev = self.previous
        self.previous = current
        missing = self.missing_reads
        self.missing_reads = 0
        if prev is None:
            result["reason"] = "INITIAL_BASELINE"
            return result
        dt = mono - prev[1]
        result.update(interval_sec=dt, interval_start_utc=prev[2], missing_reads_in_interval=missing)
        if epoch != prev[3]:
            result["reason"] = "RESOURCE_OR_QDISC_CHANGED_REBASELINED"
        elif dt <= 0:
            result["reason"] = "NONPOSITIVE_INTERVAL_REBASELINED"
        elif dt > self.max_gap:
            result["reason"] = "STALE_BASELINE_REINITIALIZED"
        elif value < prev[0]:
            result["reason"] = "COUNTER_DECREASE_REBASELINED"
        else:
            delta = value - prev[0]
            result.update(delta=delta, rate_per_sec=delta / dt, valid=True,
                          reason="OK_SPANS_MISSING_READS" if missing else "OK")
        return result


class ResourceSampler:
    def __init__(self, key, config, timeout, max_gap):
        self.key, self.config, self.timeout = key, config, timeout
        self.trackers = {name: CounterTracker(max_gap) for name in ("tx_bytes", "rx_bytes", "drops")}

    def sample(self):
        cfg = self.config
        metrics = {"interface_tx_bytes_total": None, "interface_rx_bytes_total": None,
                   "interface_tx_mbps": None, "interface_rx_mbps": None,
                   "qdisc_backlog_bytes": None, "qdisc_qlen_packets": None,
                   "qdisc_drops_total": None, "qdisc_drops_delta": None, "qdisc_drops_per_sec": None}
        valid = {name: False for name in metrics}
        raw_net, raw_qdiscs, selected, identity, net_index, q_index = None, None, None, None, None, None
        errors = {}
        results = {}
        try:
            identity = inspect_container(cfg["container"], self.timeout)
            for source in ("net", "qdisc"):
                results[source] = read_source(identity["container_id"], cfg["interface"], source, self.timeout)
                if results[source]["error"]:
                    errors[source] = results[source]["error"]
            if "net" not in errors:
                try:
                    net_index, raw_net = parse_net(results["net"]["output"], cfg["interface"])
                except ValueError as exc:
                    errors["net"] = str(exc)
            if "qdisc" not in errors:
                try:
                    q_index, raw_qdiscs = parse_qdiscs(results["qdisc"]["output"])
                    selected = select_qdisc(raw_qdiscs, cfg["qdisc_selector"])
                except ValueError as exc:
                    errors["qdisc"] = str(exc)
            after = inspect_container(identity["container_id"], self.timeout)
            if after != identity or (net_index is not None and q_index is not None and net_index != q_index):
                errors["identity"] = "RESOURCE_CHANGED_DURING_READ"
        except ValueError as exc:
            errors["identity"] = str(exc)
        stable = "identity" not in errors
        epoch = encode(identity) if identity else None
        intervals = {}
        for direction in ("tx", "rx"):
            name = direction + "_bytes"
            source_ok = stable and raw_net is not None and "net" not in errors
            counter = raw_net[name] if source_ok else None
            read = results.get("net")
            interval = self.trackers[name].observe(counter, read["mono"] if read else time.monotonic(),
                                                   read["stamp"]["sample_time_estimate_utc"] if read else utc_now(),
                                                   (epoch, net_index))
            intervals[direction] = interval
            metrics["interface_" + direction + "_bytes_total"] = counter
            valid["interface_" + direction + "_bytes_total"] = counter is not None
            if interval["valid"]:
                metrics["interface_" + direction + "_mbps"] = interval["rate_per_sec"] * 8.0 / 1_000_000.0
                valid["interface_" + direction + "_mbps"] = True
        qdisc_ok = stable and selected is not None and "qdisc" not in errors
        q_identity = None
        if qdisc_ok:
            q_identity = {key: selected.get(key) for key in ("kind", "handle", "parent", "root")}
            # Config changes conservatively start a new drop-counter epoch.
            options_hash = hashlib.sha256(encode(selected.get("options")).encode()).hexdigest()
            q_identity["options_sha256"] = options_hash
            drop_value, drop_field = qdisc_drop_value(selected)
            q_identity["drops_counter_field"] = drop_field
            for field, metric in (("backlog", "qdisc_backlog_bytes"), ("qlen", "qdisc_qlen_packets"),
                                  ("drops", "qdisc_drops_total")):
                value = drop_value if field == "drops" else nonnegative_integer(selected.get(field))
                metrics[metric], valid[metric] = value, value is not None
                if value is None:
                    errors[metric] = "FIELD_MISSING_OR_INVALID"
        read = results.get("qdisc")
        intervals["drops"] = self.trackers["drops"].observe(
            metrics["qdisc_drops_total"], read["mono"] if read else time.monotonic(),
            read["stamp"]["sample_time_estimate_utc"] if read else utc_now(),
            (epoch, q_index, encode(q_identity)))
        if intervals["drops"]["valid"]:
            metrics["qdisc_drops_delta"] = intervals["drops"]["delta"]
            metrics["qdisc_drops_per_sec"] = intervals["drops"]["rate_per_sec"]
            valid["qdisc_drops_delta"] = valid["qdisc_drops_per_sec"] = True
        return {
            "resource_key": self.key, "resource_id": cfg["container"] + ":" + cfg["interface"],
            "container": cfg["container"], "interface": cfg["interface"],
            "configured_snssai": cfg["snssai"],
            "slice_attribution": "configured_upf_association_not_packet_classification",
            "measurement_scope": "linux_interface_all_traffic_and_selected_egress_qdisc",
            "container_identity": identity, "net_ifindex": net_index, "qdisc_ifindex": q_index,
            "qdisc_selector": cfg["qdisc_selector"], "selected_qdisc_identity": q_identity,
            "metrics": metrics, "validity": valid, "intervals": intervals,
            "read_windows": {k: v["stamp"] for k, v in results.items()},
            "errors": errors, "scan_complete": not errors,
            "raw": {"proc_net_dev_counters": raw_net, "tc_qdisc_json": raw_qdiscs},
        }


def load_config(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8")) if path else copy.deepcopy(DEFAULT_CONFIG)
    if not isinstance(cfg, dict):
        raise ValueError("configuration must be a JSON object")
    resources = cfg.get("resources")
    if not isinstance(resources, dict) or not resources:
        raise ValueError("config.resources must be a nonempty object")
    for key, resource in resources.items():
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", key) or not isinstance(resource, dict):
            raise ValueError("Invalid resource key/configuration")
        if not isinstance(resource.get("container"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", resource["container"]):
            raise ValueError("Invalid container name")
        if not isinstance(resource.get("interface"), str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", resource["interface"]):
            raise ValueError("Invalid Linux interface name")
        snssai = resource.get("snssai", {})
        if not isinstance(snssai, dict):
            raise ValueError("snssai must be an object")
        sst = snssai.get("sst")
        if nonnegative_integer(sst) is None or sst > 255 or not re.fullmatch(r"[0-9A-Fa-f]{6}", str(snssai.get("sd", ""))):
            raise ValueError("snssai needs integer SST 0..255 and six hexadecimal SD characters")
        selector = resource.get("qdisc_selector")
        if not isinstance(selector, dict) or not selector or not set(selector).issubset({"root", "handle", "kind", "parent"}):
            raise ValueError("Specify qdisc_selector using root/handle/kind/parent")
        if "root" in selector and not isinstance(selector["root"], bool):
            raise ValueError("qdisc_selector.root must be boolean")
        if any(not isinstance(v, str) or not v for k, v in selector.items() if k != "root"):
            raise ValueError("qdisc selector strings must be nonempty")
    return cfg


def payload_from_samples(samples, run_id, collection_id, sequence, schedule):
    names = {
        "upf_interface_tx_mbps": "interface_tx_mbps", "upf_interface_rx_mbps": "interface_rx_mbps",
        "upf_tx_bytes_total": "interface_tx_bytes_total", "upf_rx_bytes_total": "interface_rx_bytes_total",
        "upf_qdisc_backlog_bytes": "qdisc_backlog_bytes", "upf_qdisc_qlen_packets": "qdisc_qlen_packets",
        "upf_qdisc_drops_total": "qdisc_drops_total", "upf_qdisc_drops_delta": "qdisc_drops_delta",
        "upf_qdisc_drops_per_sec": "qdisc_drops_per_sec",
    }
    result = {"schema_version": SCHEMA, "collector_version": VERSION, "run_id": run_id,
              "collection_id": collection_id, "sequence": sequence,
              "report_id": collection_id + ":" + str(sequence), "source_host": socket.gethostname(),
              "collection_completed_utc": utc_now(), "schedule": schedule, "measurements": samples}
    for name, field in names.items():
        result[name] = {sample["resource_key"]: sample["metrics"][field] for sample in samples}
    return result


CSV_FIELDS = ["run_id", "collection_id", "sequence", "resource_key", "resource_id", "sst", "sd",
              "net_time_estimate_utc", "qdisc_time_estimate_utc", "tx_interval_sec", "rx_interval_sec",
              "drops_interval_sec", "container_id", "container_started_at", "net_ifindex", "qdisc_ifindex",
              "qdisc_kind", "qdisc_handle", "scan_complete", "schedule_lateness_sec", "skipped_slots_before"]
METRIC_FIELDS = ["interface_tx_bytes_total", "interface_rx_bytes_total", "interface_tx_mbps", "interface_rx_mbps",
                 "qdisc_backlog_bytes", "qdisc_qlen_packets", "qdisc_drops_total", "qdisc_drops_delta", "qdisc_drops_per_sec"]
CSV_FIELDS += METRIC_FIELDS + [name + "_valid" for name in METRIC_FIELDS]
CSV_FIELDS += ["tx_reason", "rx_reason", "drops_reason", "tx_missing_reads", "drops_missing_reads", "errors_json", "net_counters_json"]


def csv_row(payload, sample):
    identity, qdisc = sample["container_identity"] or {}, sample["selected_qdisc_identity"] or {}
    row = {key: payload[key] for key in ("run_id", "collection_id", "sequence")}
    row.update(resource_key=sample["resource_key"], resource_id=sample["resource_id"],
               sst=sample["configured_snssai"]["sst"], sd=sample["configured_snssai"]["sd"],
               container_id=identity.get("container_id"), container_started_at=identity.get("started_at"),
               net_ifindex=sample["net_ifindex"], qdisc_ifindex=sample["qdisc_ifindex"],
               qdisc_kind=qdisc.get("kind"), qdisc_handle=qdisc.get("handle"), scan_complete=sample["scan_complete"],
               schedule_lateness_sec=payload["schedule"]["lateness_sec"],
               skipped_slots_before=payload["schedule"]["skipped_slots_before"],
               errors_json=encode(sample["errors"]), net_counters_json=encode(sample["raw"]["proc_net_dev_counters"]))
    for source in ("net", "qdisc"):
        row[source + "_time_estimate_utc"] = sample["read_windows"].get(source, {}).get("sample_time_estimate_utc")
    for source in ("tx", "rx", "drops"):
        row[source + "_interval_sec"] = sample["intervals"][source]["interval_sec"]
        row[source + "_reason"] = sample["intervals"][source]["reason"]
    row["tx_missing_reads"] = sample["intervals"]["tx"]["missing_reads_in_interval"]
    row["drops_missing_reads"] = sample["intervals"]["drops"]["missing_reads_in_interval"]
    row.update(sample["metrics"])
    row.update({key + "_valid": value for key, value in sample["validity"].items()})
    # CSV empty cells represent missing values. JSONL retains explicit JSON null.
    return row


class LocalArchive:
    def __init__(self, directory, metadata):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        self.raw = (directory / "telemetry.jsonl").open("x", encoding="utf-8")
        self.csv = (directory / "telemetry.csv").open("x", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.csv, fieldnames=CSV_FIELDS)
        self.writer.writeheader()

    def append(self, payload):
        self.raw.write(encode(payload) + "\n")
        self.raw.flush()
        os.fsync(self.raw.fileno())  # Archive before network delivery; disk errors stop collection.
        for sample in payload["measurements"]:
            self.writer.writerow(csv_row(payload, sample))
        self.csv.flush()

    def close(self):
        self.raw.close()
        self.csv.close()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post_report(url, payload, timeout):
    # Ignore environment HTTP proxies for the explicitly configured local endpoint.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    req = urllib.request.Request(url, data=encode(payload).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "X-Report-ID": payload["report_id"]})
    with opener.open(req, timeout=timeout) as resp:
        status = resp.status
        if not 200 <= status < 300:
            raise ValueError("HTTP_{}".format(status))
        # HTTP acceptance alone does not prove downstream storage/metric consumption.
        return status


class Publisher:
    """Best-effort asynchronous push. Full authoritative data remain in JSONL."""

    def __init__(self, url, timeout, audit_path):
        self.url, self.timeout, self.audit_path = url, timeout, audit_path
        self.pending = queue.Queue(maxsize=2)
        self.stop = threading.Event()
        self.audit_lock = threading.Lock()
        self.thread = threading.Thread(target=self.worker, name="http-publisher", daemon=True)
        self.thread.start()

    def submit(self, payload):
        try:
            self.pending.put_nowait(payload)
        except queue.Full:
            LOG.warning("PUSH_SKIPPED_BACKPRESSURE report=%s; local archive retained", payload["report_id"])
            self.audit({"report_id": payload["report_id"], "status": "SKIPPED_BACKPRESSURE"})

    def audit(self, value):
        value["recorded_at_utc"] = utc_now()
        # Short independent append; publisher failure cannot corrupt raw measurement records.
        with self.audit_lock:
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(encode(value) + "\n")

    def worker(self):
        while not self.stop.is_set() or not self.pending.empty():
            try:
                payload = self.pending.get(timeout=0.2)
            except queue.Empty:
                continue
            result = {"report_id": payload["report_id"]}
            try:
                result.update(status="HTTP_ACCEPTED", http_status=post_report(self.url, payload, self.timeout))
            except (OSError, ValueError, urllib.error.URLError) as exc:
                result.update(status="PUSH_FAILED", error=str(exc)[:300])
                LOG.warning("PUSH_FAILED report=%s error=%s; local archive retained", payload["report_id"], result["error"])
            try:
                self.audit(result)
            except OSError as exc:
                LOG.error("Delivery audit write failed: %s", exc)
            self.pending.task_done()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=self.timeout * 4 + 2)
        if self.thread.is_alive():
            LOG.warning("Publisher still closing; any undelivered report remains in local JSONL")


def next_slot(deadline, finished, interval):
    next_deadline = deadline + interval
    skipped = 0
    if finished > next_deadline:
        skipped = int(math.ceil((finished - next_deadline) / interval))
        next_deadline += skipped * interval
    return next_deadline, skipped


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", help="JSON resource configuration; default: the two UPFs in VM-3")
    parser.add_argument("--run-id", default="PILOT_RUN", help="Independent experiment/run ID, e.g. PILOT_001")
    parser.add_argument("--output-dir", default="./upf-telemetry", help="Parent directory of timestamped run archives")
    parser.add_argument("--interval", type=positive, default=1.0, help="Target sampling period in seconds, research choice")
    parser.add_argument("--command-timeout", type=positive, default=2.5)
    parser.add_argument("--http-timeout", type=positive, default=1.0)
    parser.add_argument("--max-gap", type=positive, help="Rebaseline after this many seconds without a valid read (default: 5 x interval)")
    parser.add_argument("--url", default="http://10.102.0.67:9100/report", help="Custom VM-6 report endpoint; not an NWDAF API")
    parser.add_argument("--local-only", action="store_true", help="Archive measurements without HTTP publishing")
    parser.add_argument("--once", action="store_true", help="Collect one baseline report for checking fields; rates will be missing")
    parser.add_argument("--samples", type=int, help="Stop after N reports, including the initial baseline")
    parser.add_argument("--dump-config", action="store_true", help="Print editable default JSON config and exit")
    parser.add_argument("--inspect-qdiscs", action="store_true", help="Show qdisc JSON and selected identity; read only")
    parser.add_argument("--standards", action="store_true", help="Print official design references and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.dump_config:
        print(json.dumps(DEFAULT_CONFIG, indent=2))
        return 0
    if args.standards:
        print(json.dumps(STANDARDS, indent=2))
        return 0
    try:
        cfg = load_config(args.config)
    except (ValueError, OSError, TypeError) as exc:
        parser.error(str(exc))
    if args.samples is not None and args.samples <= 0:
        parser.error("--samples must be positive")
    if args.inspect_qdiscs:
        exit_status = 0
        for key, item in cfg["resources"].items():
            sampler = ResourceSampler(key, item, args.command_timeout, args.max_gap or args.interval * 5)
            sample = sampler.sample()
            print(json.dumps({"resource": sample["resource_id"], "selector": sample["qdisc_selector"],
                              "selected": sample["selected_qdisc_identity"], "errors": sample["errors"],
                              "qdiscs": sample["raw"]["tc_qdisc_json"]}, indent=2))
            exit_status = max(exit_status, int(bool(sample["errors"])))
        return exit_status
    if not args.run_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", args.run_id):
        parser.error("provide --run-id with 1-64 letters/digits/dot/underscore/hyphen")
    if not args.local_only:
        parsed = urlparse(args.url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            parser.error("--url must be an HTTP(S) endpoint without embedded credentials")
    collection_id = uuid.uuid4().hex
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    max_gap = args.max_gap or args.interval * 5
    directory = Path(args.output_dir).resolve() / (args.run_id + "-" + collection_id[:12])
    metadata = {"schema_version": SCHEMA, "collector_version": VERSION, "run_id": args.run_id,
                "collection_id": collection_id, "started_at_utc": utc_now(), "source_host": socket.gethostname(),
                "resources": cfg["resources"], "target_interval_sec": args.interval, "max_gap_sec": max_gap,
                "command_timeout_sec": args.command_timeout, "local_only": args.local_only,
                "custom_report_endpoint": None if args.local_only else args.url, "standards_references": STANDARDS,
                "limits": ["Interface counters are not GTP/application-only counters or UE goodput.",
                           "S-NSSAI is a configured resource association, not packet-level attribution.",
                           "qdisc drops per second are not end-to-end packet loss percent.",
                           "No synthetic load score, ground-truth label, NWDAF API or DCCF is implemented.",
                           "Read times are host estimates; synchronize all VM clocks for cross-domain alignment.",
                           "No claim of TS 32.435 XML conformance or standard 1-second PM granularity.",
                           "In-place qdisc recreation with unchanged identity/options can require external event logs."]}
    archive = LocalArchive(directory, metadata)
    publisher = None if args.local_only else Publisher(args.url, args.http_timeout, directory / "delivery.jsonl")
    samplers = [ResourceSampler(key, item, args.command_timeout, max_gap) for key, item in cfg["resources"].items()]
    LOG.info("Collector v%s: archive=%s; sampling target=%.3fs", VERSION, directory, args.interval)
    sequence, deadline, skipped = 0, time.monotonic(), 0
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(samplers))) as executor:
            while not stop.is_set():
                if stop.wait(max(0.0, deadline - time.monotonic())):
                    break
                cycle_start = time.monotonic()
                futures = [executor.submit(sampler.sample) for sampler in samplers]
                samples = [future.result() for future in futures]
                schedule = {"target_interval_sec": args.interval, "lateness_sec": max(0.0, cycle_start - deadline),
                            "skipped_slots_before": skipped, "sampling_duration_sec": time.monotonic() - cycle_start}
                payload = payload_from_samples(samples, args.run_id, collection_id, sequence, schedule)
                archive.append(payload)
                if publisher:
                    publisher.submit(payload)
                for sample in samples:
                    m = sample["metrics"]
                    LOG.info("run=%s seq=%s resource=%s tx_mbps=%s backlog_B=%s drops_pps=%s errors=%s",
                             args.run_id, sequence, sample["resource_id"], m["interface_tx_mbps"],
                             m["qdisc_backlog_bytes"], m["qdisc_drops_per_sec"], encode(sample["errors"]))
                sequence += 1
                if args.once or (args.samples is not None and sequence >= args.samples):
                    break
                deadline, skipped = next_slot(deadline, time.monotonic(), args.interval)
                if skipped:
                    LOG.warning("Sampling overrun: skipped %s scheduled slots; no fabricated rows", skipped)
    finally:
        if publisher:
            publisher.close()
        archive.close()
    LOG.info("Stopped: %s reports archived at %s", sequence, directory)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        LOG.error("Collector stopped: %s", exc)
        sys.exit(1)
