#!/usr/bin/env python3
"""
Test Suite for Simplified Telemetry Recording System (VM-6)
Location: tests/test_quality_gates.py
Pure Python 3 Standard Library - Zero External Dependencies

Validates that:
1. record_experiment.py records single scenarios without gate decisions.
2. 40-column schema integrity is strictly maintained.
3. Metric parsing, Prometheus scraping, and transparent NaN handling work properly.
4. Non-overwriting run directory creation and safe file closing on duration or Ctrl+C.
5. Manifest metadata is saved consistently without training_eligible or data_quality_pass.
6. Zero dependencies on deleted run_pilot_experiment.py and log_event.py.
7. Output CSV is fully compatible with analyze_dataset.py.
"""

import csv
import datetime
import http.server
import json
import math
import os
import shutil
import signal
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import record_experiment
import analyze_dataset


class MockPrometheusHandler(http.server.BaseHTTPRequestHandler):
    """Mock HTTP server simulating Prometheus :9100 exporter."""
    metrics_payload = b"""# HELP ran_cell_prb_utilization PRB utilization
# TYPE ran_cell_prb_utilization gauge
ran_cell_prb_utilization{cell_id="1"} 12.26
ran_cell_prb_utilization{cell_id="2"} 4.72
# HELP ran_cell_mcs MCS index
# TYPE ran_cell_mcs gauge
ran_cell_mcs{cell_id="1"} 28
ran_cell_mcs{cell_id="2"} 14
# HELP ran_cell_bler Block error rate
# TYPE ran_cell_bler gauge
ran_cell_bler{cell_id="1"} 0.0000
ran_cell_bler{cell_id="2"} 0.0000
# HELP ran_cell_snr_db SNR in dB
# TYPE ran_cell_snr_db gauge
ran_cell_snr_db{cell_id="1"} 25.5
ran_cell_snr_db{cell_id="2"} 22.0
# HELP upf_queue_backlog_bytes UPF queue backlog
# TYPE upf_queue_backlog_bytes gauge
upf_queue_backlog_bytes{snssai="01000001"} 0
upf_queue_backlog_bytes{snssai="de00007b"} 0
# HELP upf_packet_drops UPF packet drops
# TYPE upf_packet_drops counter
upf_packet_drops{snssai="01000001"} 0
upf_packet_drops{snssai="de00007b"} 0
# HELP e2e_slice1_throughput_mbps Throughput
# TYPE e2e_slice1_throughput_mbps gauge
e2e_slice1_throughput_mbps 9.85
# HELP e2e_slice1_latency_rtt_ms RTT
# TYPE e2e_slice1_latency_rtt_ms gauge
e2e_slice1_latency_rtt_ms 26.50
# HELP e2e_slice1_packet_loss_pct Loss
# TYPE e2e_slice1_packet_loss_pct gauge
e2e_slice1_packet_loss_pct 0.00
# HELP e2e_slice1_jitter_ms Jitter
# TYPE e2e_slice1_jitter_ms gauge
e2e_slice1_jitter_ms 1.20
# HELP e2e_slice2_latency_rtt_ms URLLC RTT
# TYPE e2e_slice2_latency_rtt_ms gauge
e2e_slice2_latency_rtt_ms 14.10
# HELP e2e_slice2_packet_loss_pct URLLC Loss
# TYPE e2e_slice2_packet_loss_pct gauge
e2e_slice2_packet_loss_pct 0.00
# HELP e2e_probe_freshness Probe Freshness
# TYPE e2e_probe_freshness gauge
e2e_probe_freshness 1
# HELP nwdaf_slice_load_level NWDAF Load
# TYPE nwdaf_slice_load_level gauge
nwdaf_slice_load_level{snssai="01000001"} 35.0
nwdaf_slice_load_level{snssai="de00007b"} 10.0
# HELP nwdaf_comm_ul_bytes NWDAF UL Bytes
# TYPE nwdaf_comm_ul_bytes gauge
nwdaf_comm_ul_bytes 10485760
# HELP nwdaf_comm_dl_bytes NWDAF DL Bytes
# TYPE nwdaf_comm_dl_bytes gauge
nwdaf_comm_dl_bytes 5242880
# HELP nwdaf_comm_duration_sec NWDAF Duration
# TYPE nwdaf_comm_duration_sec gauge
nwdaf_comm_duration_sec 60.0
# HELP nwdaf_comm_vol_std_bytes NWDAF Vol Std
# TYPE nwdaf_comm_vol_std_bytes gauge
nwdaf_comm_vol_std_bytes 1024.0
# HELP nwdaf_comm_freshness NWDAF Freshness
# TYPE nwdaf_comm_freshness gauge
nwdaf_comm_freshness 1
# HELP nwdaf_api_status NWDAF API Status
# TYPE nwdaf_api_status gauge
nwdaf_api_status 200
"""

    def do_GET(self):
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(self.metrics_payload)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress HTTP server output in test logs


class TestSimplifiedTelemetryRecorder(unittest.TestCase):
    """Comprehensive test suite for the simplified record_experiment.py workflow."""

    @classmethod
    def setUpClass(cls):
        # Start local mock HTTP server on an ephemeral port
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), MockPrometheusHandler)
        cls.server_port = cls.server.server_address[1]
        cls.mock_url = f"http://127.0.0.1:{cls.server_port}/metrics"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_thesis_recorder_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_schema_column_count_and_order(self):
        """POS-01: Exactly 40 columns defined and matching thesis specification."""
        self.assertEqual(len(record_experiment.HEADERS), 40)
        self.assertEqual(record_experiment.HEADERS[0], "timestamp_utc")
        self.assertEqual(record_experiment.HEADERS[1], "elapsed_sec")
        self.assertEqual(record_experiment.HEADERS[2], "run_id")
        self.assertEqual(record_experiment.HEADERS[3], "scrape_ok")
        self.assertEqual(record_experiment.HEADERS[4], "scrape_latency_ms")
        self.assertEqual(record_experiment.HEADERS[-4], "event_phase_id")
        self.assertEqual(record_experiment.HEADERS[-3], "event_scenario")
        self.assertEqual(record_experiment.HEADERS[-2], "event_domain")
        self.assertEqual(record_experiment.HEADERS[-1], "event_component")

    def test_02_scenario_metadata_resolution(self):
        """POS-02: Canonical presets map cleanly to expected domains and components."""
        cases = [
            ("S1", "S1_NORMAL_LIGHT", "BASELINE", "NONE"),
            ("s1", "S1_NORMAL_LIGHT", "BASELINE", "NONE"),
            ("S2", "S2_NORMAL_HIGH", "BASELINE", "NONE"),
            ("S3", "S3_RAN_OVERLOAD", "RAN", "DU-1_Cell-1"),
            ("S6", "S6_CORE_QUEUE_TBF", "CORE", "UPF-1_Slice-1"),
            ("S9", "S9_JOINT_OVERLOAD", "JOINT", "Cell-1+UPF-1"),
            ("S10_A", "S10_A_RELEASE_RAN", "CORE", "UPF-1_Slice-1"),
            ("S10_B", "S10_B_RELEASE_CORE", "BASELINE", "NONE"),
            ("CUSTOM_EXP", "CUSTOM_EXP", "CUSTOM", "NONE"),
        ]
        for inp, exp_canon, exp_dom, exp_comp in cases:
            raw, canon, dom, comp = record_experiment.resolve_scenario_metadata(inp)
            self.assertEqual(canon, exp_canon)
            self.assertEqual(dom, exp_dom)
            self.assertEqual(comp, exp_comp)

    def test_03_unique_run_dir_generation_and_no_overwrite(self):
        """POS-03: Run directory is created uniquely and never overwrites existing runs."""
        base_id = "EXP_S1_20261017_120000"
        id1, dir1 = record_experiment.get_unique_run_dir(self.test_dir, base_id)
        self.assertEqual(id1, base_id)
        os.makedirs(dir1, exist_ok=True)

        # Subsequent call with the same base ID must return a collision-free increment
        id2, dir2 = record_experiment.get_unique_run_dir(self.test_dir, base_id)
        self.assertEqual(id2, f"{base_id}_1")
        self.assertNotEqual(dir1, dir2)

        os.makedirs(dir2, exist_ok=True)
        id3, dir3 = record_experiment.get_unique_run_dir(self.test_dir, base_id)
        self.assertEqual(id3, f"{base_id}_2")

    def test_04_prometheus_text_parsing(self):
        """POS-04: Prometheus parser correctly extracts names, labels, and values."""
        text = """
# A comment
metric_one 42.5
metric_two{cell_id="1",snssai="01000001"} 100.0
metric_three{empty=""} 0.0
"""
        parsed = record_experiment.parse_prometheus_text(text)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0], ("metric_one", {}, "42.5"))
        self.assertEqual(parsed[1], ("metric_two", {"cell_id": "1", "snssai": "01000001"}, "100.0"))
        self.assertEqual(parsed[2], ("metric_three", {"empty": ""}, "0.0"))

    def test_05_telemetry_extraction_against_mock_server(self):
        """POS-05: Real HTTP scrape extracts all expected metrics from Prometheus payload."""
        data, scrape_ok, lat = record_experiment.extract_telemetry(metrics_url=self.mock_url)
        self.assertEqual(scrape_ok, 1)
        self.assertGreater(lat, 0.0)
        self.assertEqual(data["ran_prb_cell1"], "12.26")
        self.assertEqual(data["ran_prb_cell2"], "4.72")
        self.assertEqual(data["e2e_slice1_tput_mbps"], "9.85")
        self.assertEqual(data["e2e_slice1_rtt_ms"], "26.50")
        self.assertEqual(data["e2e_slice1_loss_pct"], "0.00")
        self.assertEqual(data["upf_backlog_bytes_embb"], "0")
        self.assertEqual(data["nwdaf_comm_ul_bytes"], "10485760")
        self.assertEqual(data["nwdaf_api_status"], "200")

    def test_06_scrape_failure_records_nan_transparently(self):
        """POS-06: Outages or unreachable exporter record scrape_ok=0 and NaN without crash."""
        bad_url = "http://127.0.0.1:1"  # Port 1 will fail connection
        data, scrape_ok, lat = record_experiment.extract_telemetry(metrics_url=bad_url, timeout=0.1)
        self.assertEqual(scrape_ok, 0)
        self.assertEqual(data["ran_prb_cell1"], "NaN")
        self.assertEqual(data["e2e_slice1_tput_mbps"], "NaN")
        self.assertEqual(data["upf_backlog_bytes_embb"], "NaN")

    def test_07_recording_session_completes_and_generates_manifest(self):
        """POS-07: Full execution of record_experiment records telemetry and valid manifest."""
        run_id = "EXP_TEST_S1"
        args = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "..", "scripts", "record_experiment.py"),
            "S1",
            "--duration", "2",
            "--notes", "Unit test recording",
            "--run-id", run_id,
            "--metrics-url", self.mock_url,
            "--data-dir", self.test_dir
        ]
        res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"Recorder failed: {res.stderr}\n{res.stdout}")

        run_dir = os.path.join(self.test_dir, "raw", run_id)
        self.assertTrue(os.path.isdir(run_dir))

        csv_file = os.path.join(run_dir, f"telemetry_{run_id}.csv")
        self.assertTrue(os.path.isfile(csv_file))

        # Check CSV content
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = list(csv.reader(f))
            self.assertGreaterEqual(len(reader), 3)  # Header + at least 2 samples
            self.assertEqual(reader[0], record_experiment.HEADERS)
            # Check row values
            row1 = reader[1]
            self.assertEqual(row1[2], run_id)
            self.assertEqual(row1[3], "1")  # scrape_ok
            self.assertEqual(row1[36], "phase_1_S1")
            self.assertEqual(row1[37], "S1_NORMAL_LIGHT")
            self.assertEqual(row1[38], "BASELINE")
            self.assertEqual(row1[39], "NONE")

        # Check manifest.json content
        manifest_file = os.path.join(run_dir, "manifest.json")
        self.assertTrue(os.path.isfile(manifest_file))
        with open(manifest_file, "r", encoding="utf-8") as mf:
            m = json.load(mf)
            self.assertEqual(m["run_id"], run_id)
            self.assertEqual(m["scenario"], "S1")
            self.assertEqual(m["canonical_scenario"], "S1_NORMAL_LIGHT")
            self.assertEqual(m["operator_notes"], "Unit test recording")
            self.assertEqual(m["recording_status"], "SUCCESS")
            self.assertEqual(m["stop_reason"], "DURATION_REACHED")
            self.assertGreaterEqual(m["total_samples"], 2)

            # Strict verification: Manifest must NOT contain quality-gate decisions!
            self.assertNotIn("training_eligible", m)
            self.assertNotIn("data_quality_pass", m)
            self.assertNotIn("final_decision", m)

    def test_08_active_run_id_file_synchronized(self):
        """POS-08: active_run_id.txt is updated so telemetry_collector can route raw NWDAF polls."""
        run_id = "EXP_TEST_ACTIVE_SYNC"
        args = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "..", "scripts", "record_experiment.py"),
            "S3",
            "--duration", "1",
            "--run-id", run_id,
            "--metrics-url", self.mock_url,
            "--data-dir", self.test_dir
        ]
        res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0)

        active_file = os.path.join(self.test_dir, "active_run_id.txt")
        self.assertTrue(os.path.isfile(active_file))
        with open(active_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            self.assertEqual(content, run_id)

    def test_09_compatibility_with_analyze_dataset(self):
        """POS-09: Recorded CSV can be directly parsed and analyzed by analyze_dataset.py."""
        run_id = "EXP_TEST_ANALYZE_COMPAT"
        args = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "..", "scripts", "record_experiment.py"),
            "S1",
            "--duration", "2",
            "--run-id", run_id,
            "--metrics-url", self.mock_url,
            "--data-dir", self.test_dir
        ]
        res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0)

        csv_file = os.path.join(self.test_dir, "raw", run_id, f"telemetry_{run_id}.csv")
        analyze_script = os.path.join(os.path.dirname(__file__), "..", "scripts", "analyze_dataset.py")
        res_an = subprocess.run([sys.executable, analyze_script, csv_file], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res_an.returncode, 0)
        self.assertIn("ANALISIS TELEMETRI DATASET", res_an.stdout)
        self.assertIn("S1_NORMAL_LIGHT", res_an.stdout)

    def test_10_deleted_scripts_are_absent(self):
        """NEG-01: Verifies that run_pilot_experiment.py, log_event.py, and record_dual_stream.py are strictly removed."""
        scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
        pilot_path = os.path.join(scripts_dir, "run_pilot_experiment.py")
        log_event_path = os.path.join(scripts_dir, "log_event.py")
        dual_stream_path = os.path.join(scripts_dir, "record_dual_stream.py")
        self.assertFalse(os.path.exists(pilot_path), "run_pilot_experiment.py must be deleted")
        self.assertFalse(os.path.exists(log_event_path), "log_event.py must be deleted")
        self.assertFalse(os.path.exists(dual_stream_path), "record_dual_stream.py must be deleted")


if __name__ == "__main__":
    unittest.main()
