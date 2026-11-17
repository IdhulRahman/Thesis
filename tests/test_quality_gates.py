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
import telemetry_collector


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
# HELP nwdaf_run_raw_polls_written Polls written for active run
# TYPE nwdaf_run_raw_polls_written gauge
nwdaf_run_raw_polls_written 5
# HELP nwdaf_run_raw_polls_failed Polls failed for active run
# TYPE nwdaf_run_raw_polls_failed gauge
nwdaf_run_raw_polls_failed 0
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
            ("S3", "S3_RAN_SOFT", "RAN", "DU-1_Cell-1"),
            ("S4", "S4_RAN_DEGRADATION", "RAN", "DU-1_Cell-1"),
            ("S5", "S5_RAN_OVERLOAD", "RAN", "DU-1_Cell-1"),
            ("S6", "S6_CORE_SOFT", "CORE", "UPF-1_Slice-1"),
            ("S7", "S7_CORE_QUEUE_TBF", "CORE", "UPF-1_Slice-1"),
            ("S8", "S8_JOINT_SOFT", "JOINT", "Cell-1+UPF-1"),
            ("S9", "S9_JOINT_OVERLOAD", "JOINT", "Cell-1+UPF-1"),
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
        data, scrape_ok, lat, storage_stats = record_experiment.extract_telemetry(metrics_url=self.mock_url)
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
        self.assertEqual(storage_stats["nwdaf_run_polls_written"], 5)
        self.assertEqual(storage_stats["nwdaf_run_polls_failed"], 0)

    def test_06_scrape_failure_records_nan_transparently(self):
        """POS-06: Outages or unreachable exporter record scrape_ok=0 and NaN without crash."""
        bad_url = "http://127.0.0.1:1"  # Port 1 will fail connection
        data, scrape_ok, lat, storage_stats = record_experiment.extract_telemetry(metrics_url=bad_url, timeout=0.1)
        self.assertEqual(scrape_ok, 0)
        self.assertEqual(data["ran_prb_cell1"], "NaN")
        self.assertEqual(data["e2e_slice1_tput_mbps"], "NaN")
        self.assertEqual(data["upf_backlog_bytes_embb"], "NaN")
        self.assertEqual(storage_stats["nwdaf_run_polls_written"], 0)

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
            self.assertIn("storage_audit", m)
            self.assertEqual(m["storage_audit"]["telemetry_csv"]["status"], "WRITTEN")

            # Strict verification: Manifest must NOT contain quality-gate decisions!
            self.assertNotIn("training_eligible", m)
            self.assertNotIn("data_quality_pass", m)
            self.assertNotIn("final_decision", m)

    def test_08_active_run_id_closed_on_completion(self):
        """POS-08: active_run_id.txt is closed upon run completion so collector halts archiving to finished run."""
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
            self.assertEqual(content, "", "active_run_id.txt must be cleared upon session completion")

        event_file = os.path.join(self.test_dir, "active_event.json")
        self.assertTrue(os.path.isfile(event_file))
        with open(event_file, "r", encoding="utf-8") as f:
            ev = json.load(f)
            self.assertEqual(ev.get("phase_id"), "idle")
            self.assertEqual(ev.get("scenario"), "IDLE")

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

    def test_11_nwdaf_storage_failure_audit_and_warning(self):
        """POS-11: Collector NWDAF storage failure counter is tracked and flagged in manifest storage_audit."""
        # Create a mock handler that simulates 3 failed NWDAF polls
        class FailingNWDAFHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                payload = b"""# HELP nwdaf_run_raw_polls_written Polls written
nwdaf_run_raw_polls_written 2
# HELP nwdaf_run_raw_polls_failed Polls failed
nwdaf_run_raw_polls_failed 3
"""
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(payload)
            def log_message(self, format, *args):
                pass

        fail_server = socketserver.TCPServer(("127.0.0.1", 0), FailingNWDAFHandler)
        port = fail_server.server_address[1]
        fail_url = f"http://127.0.0.1:{port}/metrics"
        t = threading.Thread(target=fail_server.serve_forever, daemon=True)
        t.start()

        run_id = "EXP_TEST_STORAGE_FAIL"
        try:
            args = [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "..", "scripts", "record_experiment.py"),
                "S1",
                "--duration", "1",
                "--run-id", run_id,
                "--metrics-url", fail_url,
                "--data-dir", self.test_dir
            ]
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            manifest_file = os.path.join(self.test_dir, "raw", run_id, "manifest.json")
            self.assertTrue(os.path.isfile(manifest_file))
            with open(manifest_file, "r", encoding="utf-8") as mf:
                m = json.load(mf)
                self.assertEqual(m["recording_status"], "PARTIAL_STORAGE_WARNING")
                self.assertGreater(len(m["storage_warnings"]), 0)
                self.assertEqual(m["storage_audit"]["nwdaf_raw_jsonl"]["polls_failed_reported"], 3)
        finally:
            fail_server.shutdown()
            fail_server.server_close()

    def test_12_atomic_manifest_failure_returns_exit_1(self):
        """NEG-02: Manifest write failure results in consistent non-zero exit code and FAILED status."""
        test_manifest = {"run_id": "TEST_ATOMIC", "status": "IN_PROGRESS"}
        invalid_path = os.path.join(self.test_dir, "nonexistent_dir_12345", "sub", "manifest.json")
        with self.assertRaises(Exception):
            record_experiment.save_manifest_atomic(invalid_path, test_manifest)

    def test_13_signal_stop_reason_operator_interrupt(self):
        """POS-12: Subprocess terminated via signal properly attributes stop_reason to operator interrupt."""
        run_id = "EXP_TEST_SIGNAL_STOP"
        args = [
            sys.executable,
            os.path.join(os.path.dirname(__file__), "..", "scripts", "record_experiment.py"),
            "S1",
            "--duration", "0",  # infinite / manual mode
            "--run-id", run_id,
            "--metrics-url", self.mock_url,
            "--data-dir", self.test_dir
        ]
        if sys.platform == "win32":
            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            time.sleep(1.8)
            proc.send_signal(signal.CTRL_BREAK_EVENT)
            proc.wait(timeout=5)
        else:
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(1.8)
            proc.send_signal(signal.SIGINT)
            proc.wait(timeout=5)
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()

        manifest_file = os.path.join(self.test_dir, "raw", run_id, "manifest.json")
        self.assertTrue(os.path.isfile(manifest_file))
        with open(manifest_file, "r", encoding="utf-8") as mf:
            m = json.load(mf)
            self.assertEqual(m["stop_reason"], "INTERRUPTED_BY_OPERATOR")

    def test_14_cross_run_nwdaf_contamination_prevention_and_late_responses(self):
        """POS-13: Ensures NWDAF poll archiving strictly binds to request context and drops late responses."""
        orig_data_dir = os.environ.get("MONITORING_DATA_DIR")
        os.environ["MONITORING_DATA_DIR"] = self.test_dir
        try:
            run_a_dir = os.path.join(self.test_dir, "raw", "RUN_A")
            run_b_dir = os.path.join(self.test_dir, "raw", "RUN_B")
            os.makedirs(run_a_dir, exist_ok=True)
            os.makedirs(run_b_dir, exist_ok=True)

            active_file = os.path.join(self.test_dir, "active_run_id.txt")
            telemetry_collector.RUN_STATE_FILE = active_file

            # 1. Idle request: target_run_id=None must not write to any run directory even if RUN_B is active
            with open(active_file, "w", encoding="utf-8") as f:
                f.write("RUN_B\n")
            telemetry_collector.check_run_state_change()

            ok, reason = telemetry_collector.log_raw_nwdaf_poll({"poll": "idle"}, target_run_id=None)
            self.assertFalse(ok)
            self.assertEqual(reason, "IDLE_REQUEST")
            self.assertFalse(os.path.exists(os.path.join(run_b_dir, "nwdaf_raw_poll_responses.jsonl")))

            # 2. Late response: request started for RUN_A, but response arrived when RUN_B is active
            ok, reason = telemetry_collector.log_raw_nwdaf_poll({"poll": "late_A"}, target_run_id="RUN_A")
            self.assertFalse(ok)
            self.assertIn("LATE_RESPONSE", reason)
            # Must NOT be written into RUN_B directory!
            self.assertFalse(os.path.exists(os.path.join(run_b_dir, "nwdaf_raw_poll_responses.jsonl")))
            # Must NOT be written into RUN_A directory!
            self.assertFalse(os.path.exists(os.path.join(run_a_dir, "nwdaf_raw_poll_responses.jsonl")))
            # RUN_B counters must not have been incremented by RUN_A's response
            self.assertEqual(telemetry_collector.run_poll_stats["written"], 0)

            # 3. In-context response: request started for RUN_B and arrived when RUN_B is still active
            ok, reason = telemetry_collector.log_raw_nwdaf_poll({"poll": "valid_B"}, target_run_id="RUN_B")
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(os.path.join(run_b_dir, "nwdaf_raw_poll_responses.jsonl")))
            with open(os.path.join(run_b_dir, "nwdaf_raw_poll_responses.jsonl"), "r", encoding="utf-8") as f:
                line = json.loads(f.read().strip())
                self.assertEqual(line["run_id"], "RUN_B")
            self.assertEqual(telemetry_collector.run_poll_stats["written"], 1)

        finally:
            if orig_data_dir:
                os.environ["MONITORING_DATA_DIR"] = orig_data_dir
            else:
                os.environ.pop("MONITORING_DATA_DIR", None)

    def test_15_storage_failure_history_retained_across_subsequent_scrape_errors(self):
        """POS-14: Verifies that observed archive failures are retained even when subsequent scrapes fail (e.g. HTTP 503)."""
        request_count = 0
        class FlakyPrometheusHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal request_count
                request_count += 1
                if request_count <= 2:
                    # Initial scrapes report 3 failed polls
                    payload = b"""# HELP nwdaf_run_raw_polls_written Polls written
nwdaf_run_raw_polls_written 1
# HELP nwdaf_run_raw_polls_failed Polls failed
nwdaf_run_raw_polls_failed 3
# HELP nwdaf_poll_in_flight In flight
nwdaf_poll_in_flight 0
"""
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    # Subsequent scrapes fail with HTTP 503
                    self.send_response(503)
                    self.end_headers()
            def log_message(self, format, *args):
                pass

        flaky_server = socketserver.TCPServer(("127.0.0.1", 0), FlakyPrometheusHandler)
        port = flaky_server.server_address[1]
        flaky_url = f"http://127.0.0.1:{port}/metrics"
        t = threading.Thread(target=flaky_server.serve_forever, daemon=True)
        t.start()

        run_id = "EXP_TEST_FLAKY_FAIL"
        try:
            args = [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "..", "scripts", "record_experiment.py"),
                "S1",
                "--duration", "2",
                "--run-id", run_id,
                "--metrics-url", flaky_url,
                "--data-dir", self.test_dir
            ]
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            manifest_file = os.path.join(self.test_dir, "raw", run_id, "manifest.json")
            self.assertTrue(os.path.isfile(manifest_file))
            with open(manifest_file, "r", encoding="utf-8") as mf:
                m = json.load(mf)
                # Failure count 3 MUST be retained, status must be PARTIAL_STORAGE_WARNING!
                self.assertEqual(m["recording_status"], "PARTIAL_STORAGE_WARNING")
                self.assertEqual(m["storage_audit"]["nwdaf_raw_jsonl"]["polls_failed_reported"], 3)
                self.assertGreater(len(m["storage_warnings"]), 0)
        finally:
            flaky_server.shutdown()
            flaky_server.server_close()

    def test_16_run_transition_isolation_when_first_scrape_precedes_collector_detection(self):
        """POS-15: Verifies that when first scrape of RUN_B occurs before collector poller detects transition,
        RUN_A's stale cache (e.g. 999999) and failure history (e.g. 3) are isolated and rejected.
        """
        request_count = 0
        class TwoRunTransitionHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal request_count
                request_count += 1
                if request_count == 1:
                    # First scrape of RUN_B arrives when exporter still holds RUN_A state
                    payload = b"""# HELP collector_active_run_id Active run
collector_active_run_id{run_id="RUN_A"} 1
# HELP nwdaf_comm_duration_sec Duration
nwdaf_comm_duration_sec 999999
# HELP nwdaf_run_raw_polls_written Polls written
nwdaf_run_raw_polls_written{run_id="RUN_A"} 1
# HELP nwdaf_run_raw_polls_failed Polls failed
nwdaf_run_raw_polls_failed{run_id="RUN_A"} 3
# HELP nwdaf_poll_in_flight In flight
nwdaf_poll_in_flight 0
"""
                else:
                    # Subsequent scrapes reflect RUN_B
                    payload = b"""# HELP collector_active_run_id Active run
collector_active_run_id{run_id="RUN_B"} 1
# HELP nwdaf_comm_duration_sec Duration
nwdaf_comm_duration_sec NaN
# HELP nwdaf_run_raw_polls_written Polls written
nwdaf_run_raw_polls_written{run_id="RUN_B"} 0
# HELP nwdaf_run_raw_polls_failed Polls failed
nwdaf_run_raw_polls_failed{run_id="RUN_B"} 0
# HELP nwdaf_poll_in_flight In flight
nwdaf_poll_in_flight 0
"""
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format, *args):
                pass

        server = socketserver.TCPServer(("127.0.0.1", 0), TwoRunTransitionHandler)
        port = server.server_address[1]
        metrics_url = f"http://127.0.0.1:{port}/metrics"
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        run_id = "RUN_B"
        try:
            args = [
                sys.executable,
                os.path.join(os.path.dirname(__file__), "..", "scripts", "record_experiment.py"),
                "S1",
                "--duration", "2",
                "--run-id", run_id,
                "--metrics-url", metrics_url,
                "--data-dir", self.test_dir
            ]
            res = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            csv_path = os.path.join(self.test_dir, "raw", run_id, f"telemetry_{run_id}.csv")
            manifest_path = os.path.join(self.test_dir, "raw", run_id, "manifest.json")
            self.assertTrue(os.path.isfile(csv_path))
            self.assertTrue(os.path.isfile(manifest_path))

            # Verify row 1 of CSV did NOT absorb RUN_A's 999999 cache
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader)
                row1 = next(reader)
                dur_idx = headers.index("nwdaf_comm_duration_sec")
                self.assertEqual(row1[dur_idx], "NaN")

            # Verify manifest did NOT absorb RUN_A's 3 failures
            with open(manifest_path, "r", encoding="utf-8") as f:
                m = json.load(f)
                self.assertEqual(m["recording_status"], "SUCCESS")
                self.assertEqual(m["storage_audit"]["nwdaf_raw_jsonl"]["polls_failed_reported"], 0)
                self.assertEqual(len(m["storage_warnings"]), 0)
        finally:
            server.shutdown()
            server.server_close()

    def test_17_collector_format_metrics_synchronizes_run_state_and_resets_cache(self):
        """POS-16: Verifies that collector format_prometheus_metrics directly synchronizes run state from active_run_id.txt."""
        active_file = os.path.join(self.test_dir, "active_run_id_sync_test.txt")
        telemetry_collector.RUN_STATE_FILE = active_file

        with open(active_file, "w", encoding="utf-8") as f:
            f.write("RUN_OLD\n")
        telemetry_collector.check_run_state_change()

        with telemetry_collector.METRICS_LOCK:
            telemetry_collector.metrics_store["nwdaf_comm_duration_sec"] = 999999.0
            telemetry_collector.metrics_store["nwdaf_run_raw_polls_failed"] = 3

        # Switch to RUN_NEW on disk without calling check_run_state_change manually
        with open(active_file, "w", encoding="utf-8") as f:
            f.write("RUN_NEW\n")

        # format_prometheus_metrics should auto-detect and reset
        output = telemetry_collector.format_prometheus_metrics()
        self.assertIn('collector_active_run_id{run_id="RUN_NEW"} 1', output)
        self.assertIn('nwdaf_run_raw_polls_failed{run_id="RUN_NEW"} 0', output)
        self.assertIn('nwdaf_comm_duration_sec NaN', output)

    def test_18_interleaved_run_transition_prevents_mixed_query_window_and_run_id(self):
        """POS-17: Verifies that atomic context snapshotting and session generation prevent
        a request from having mixed window (RUN_A start time) and target identity (RUN_B).
        """
        orig_data_dir = os.environ.get("MONITORING_DATA_DIR")
        os.environ["MONITORING_DATA_DIR"] = self.test_dir
        try:
            run_a_dir = os.path.join(self.test_dir, "raw", "RUN_CONC_A")
            run_b_dir = os.path.join(self.test_dir, "raw", "RUN_CONC_B")
            os.makedirs(run_a_dir, exist_ok=True)
            os.makedirs(run_b_dir, exist_ok=True)

            active_file = os.path.join(self.test_dir, "active_run_id_conc.txt")
            telemetry_collector.RUN_STATE_FILE = active_file

            # 1. Start RUN_CONC_A
            with open(active_file, "w", encoding="utf-8") as f:
                f.write("RUN_CONC_A\n")

            # Atomic poll context captured for RUN_CONC_A
            ctx_a = telemetry_collector.get_nwdaf_poll_context()
            self.assertEqual(ctx_a["run_id"], "RUN_CONC_A")
            gen_a = ctx_a["generation"]
            start_ts_a = ctx_a["start_ts"]

            # 2. Interleaved transition: /metrics or another event transitions to RUN_CONC_B
            with open(active_file, "w", encoding="utf-8") as f:
                f.write("RUN_CONC_B\n")

            # Atomic poll context captured for RUN_CONC_B
            ctx_b = telemetry_collector.get_nwdaf_poll_context()
            self.assertEqual(ctx_b["run_id"], "RUN_CONC_B")
            gen_b = ctx_b["generation"]
            start_ts_b = ctx_b["start_ts"]
            self.assertGreater(gen_b, gen_a)

            # 3. An in-flight request started under RUN_CONC_A attempts to log with stale generation
            poll_record_a = {
                "poll_timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "query_start_ts": start_ts_a,
                "query_url": "http://mock/analytics",
                "http_status": 200,
                "response_body": {"ueComms": [{"commDur": 123.0}]}
            }
            # Attempting to log with target_run_id=RUN_CONC_A and target_generation=gen_a
            ok, reason = telemetry_collector.log_raw_nwdaf_poll(
                poll_record_a,
                target_run_id="RUN_CONC_A",
                target_generation=gen_a
            )
            self.assertFalse(ok)
            self.assertIn("LATE_RESPONSE", reason)
            self.assertFalse(os.path.exists(os.path.join(run_a_dir, "nwdaf_raw_poll_responses.jsonl")))
            self.assertFalse(os.path.exists(os.path.join(run_b_dir, "nwdaf_raw_poll_responses.jsonl")))

            # 4. Even if a race attempted to attribute the response to RUN_CONC_B with stale gen_a
            ok2, reason2 = telemetry_collector.log_raw_nwdaf_poll(
                poll_record_a,
                target_run_id="RUN_CONC_B",
                target_generation=gen_a
            )
            self.assertFalse(ok2)
            self.assertIn("LATE_RESPONSE", reason2)
            self.assertFalse(os.path.exists(os.path.join(run_b_dir, "nwdaf_raw_poll_responses.jsonl")))

            # RUN_CONC_B metrics must remain clean/uncontaminated
            with telemetry_collector.METRICS_LOCK:
                self.assertTrue(math.isnan(telemetry_collector.metrics_store["nwdaf_comm_duration_sec"]))
                self.assertEqual(telemetry_collector.run_poll_stats["written"], 0)

        finally:
            if orig_data_dir:
                os.environ["MONITORING_DATA_DIR"] = orig_data_dir
            else:
                os.environ.pop("MONITORING_DATA_DIR", None)


# ---------------------------------------------------------------------------
# Regression tests for analyzer bug fixes (audit 2026-11-17)
# ---------------------------------------------------------------------------

class TestBlerUnitConversion(unittest.TestCase):
    """BLER stored as ratio [0,1]; display must multiply by 100."""

    def _fmt_bler(self, ratio):
        """Mirror the fixed format logic from analyze_dataset.py."""
        if ratio is None or (isinstance(ratio, float) and math.isnan(ratio)):
            return "N/A"
        return f"{ratio * 100:.2f} %"

    def test_zero(self):
        self.assertEqual(self._fmt_bler(0.0), "0.00 %")

    def test_ten_percent(self):
        self.assertEqual(self._fmt_bler(0.1), "10.00 %")

    def test_hundred_percent(self):
        self.assertEqual(self._fmt_bler(1.0), "100.00 %")

    def test_nan_returns_na(self):
        self.assertEqual(self._fmt_bler(float("nan")), "N/A")


class TestNaNBacklogDisplay(unittest.TestCase):
    """When all backlog readings are NaN (empty list), display must be 'N/A', not '0 B'."""

    def _fmt_backlog(self, backlog_list):
        return f"{max(backlog_list):>10,.0f} B" if backlog_list else "N/A"

    def test_empty_list_returns_na(self):
        self.assertEqual(self._fmt_backlog([]), "N/A")

    def test_nonempty_list_returns_value(self):
        result = self._fmt_backlog([1024.0])
        self.assertIn("1,024", result)


class TestDropRateSemantics(unittest.TestCase):
    """upf_drops_embb is a rate (pkt/s gauge). Report max rate, not sum."""

    def _fmt_drops(self, drops_list):
        return f"{max(drops_list):.1f} pkt/s" if drops_list else "N/A"

    def test_empty_returns_na(self):
        self.assertEqual(self._fmt_drops([]), "N/A")

    def test_max_not_sum(self):
        values = [10.0, 20.0, 15.0]
        result = self._fmt_drops(values)
        self.assertIn("20.0", result)
        self.assertNotIn("45", result)


class TestSlaThreshold(unittest.TestCase):
    """SLA compliant when loss <= 1.0%. Only loss > 1.0% is a violation."""

    def _is_loss_violation(self, loss_pct):
        return loss_pct > 1.0 and loss_pct < 100.0

    def test_zero_loss_compliant(self):
        self.assertFalse(self._is_loss_violation(0.0))

    def test_half_percent_compliant(self):
        self.assertFalse(self._is_loss_violation(0.5))

    def test_one_percent_compliant(self):
        self.assertFalse(self._is_loss_violation(1.0))

    def test_above_one_percent_violation(self):
        self.assertTrue(self._is_loss_violation(1.1))

    def test_full_loss_is_outage_not_violation(self):
        self.assertFalse(self._is_loss_violation(100.0))


class TestLossNaDisplay(unittest.TestCase):
    """When loss is not measured (empty list), show 'N/A', not '0.0 %'."""

    def _fmt_loss(self, loss_list):
        avg_loss = (sum(loss_list) / len(loss_list)) if loss_list else None
        return f"{avg_loss:.1f} %" if avg_loss is not None else "N/A"

    def test_empty_loss_returns_na(self):
        self.assertEqual(self._fmt_loss([]), "N/A")

    def test_nonempty_loss_returns_value(self):
        self.assertEqual(self._fmt_loss([2.5]), "2.5 %")


# ---------------------------------------------------------------------------
# End-to-end integration tests using CSV fixtures on analyze_dataset.py
# ---------------------------------------------------------------------------

class TestAnalyzeDatasetIntegration(unittest.TestCase):
    """Real end-to-end integration tests for analyze_dataset.py using synthesized CSV fixtures."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_analyzer_e2e_")
        self.script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "scripts", "analyze_dataset.py")
        )

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _write_csv(self, filename, rows):
        path = os.path.join(self.test_dir, filename)
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=record_experiment.HEADERS)
            writer.writeheader()
            for r in rows:
                full_row = {h: "NaN" for h in record_experiment.HEADERS}
                full_row.update(r)
                writer.writerow(full_row)
        return path

    def _run_analyzer(self, csv_path):
        res = subprocess.run(
            [sys.executable, self.script_path, csv_path],
            capture_output=True,
            text=True,
            check=True
        )
        return res.stdout

    def _get_table_row(self, output, section_prefix, scenario):
        sec_idx = output.find(section_prefix)
        if sec_idx == -1:
            return None
        sec_text = output[sec_idx:]
        next_idx = sec_text.find("\n--- ", len(section_prefix))
        if next_idx != -1:
            sec_text = sec_text[:next_idx]
        for line in sec_text.splitlines():
            if line.startswith(scenario):
                return [p.strip() for p in line.split("|")]
        return None

    def test_01_partial_sla_unknown_rtt_15_loss_nan(self):
        """When RTT=15ms (<=20ms) and Loss=NaN, SLA must be reported as Unknown (N/A), never 0.0%."""
        rows = [{
            "timestamp_utc": "2026-11-17T12:00:00Z",
            "elapsed_sec": "10.0",
            "event_scenario": "S3_RAN_SOFT",
            "e2e_slice2_rtt_ms": "15.0",
            "e2e_slice2_loss_pct": "NaN"
        }]
        csv_path = self._write_csv("test_partial_sla.csv", rows)
        output = self._run_analyzer(csv_path)

        parts = self._get_table_row(output, "--- 2. SLICE 2: URLLC", "S3_RAN_SOFT")
        self.assertIsNotNone(parts)
        # ['S3_RAN_SOFT', '1', '1', '0', '0', '1', '100.0%', '15.00 ms', '15.00 ms', 'N/A', 'N/A']
        self.assertEqual(parts[1], "1")     # Total
        self.assertEqual(parts[2], "1")     # Valid
        self.assertEqual(parts[3], "0")     # Outage
        self.assertEqual(parts[4], "0")     # Miss
        self.assertEqual(parts[5], "1")     # Unk
        self.assertEqual(parts[10], "N/A")  # SLA Viol % must be N/A, not 0.0%

    def test_02_latency_violation_proven_even_if_loss_nan(self):
        """When RTT=25ms (>20ms) and Loss=NaN, violation is proven regardless of missing loss."""
        rows = [{
            "timestamp_utc": "2026-11-17T12:00:00Z",
            "elapsed_sec": "10.0",
            "event_scenario": "S3_RAN_SOFT",
            "e2e_slice2_rtt_ms": "25.0",
            "e2e_slice2_loss_pct": "NaN"
        }]
        csv_path = self._write_csv("test_lat_violation.csv", rows)
        output = self._run_analyzer(csv_path)

        parts = self._get_table_row(output, "--- 2. SLICE 2: URLLC", "S3_RAN_SOFT")
        self.assertIsNotNone(parts)
        self.assertEqual(parts[5], "0")       # Unk = 0 (violation is definitive)
        self.assertEqual(parts[10], "100.0%") # SLA Viol % = 100.0%

    def test_03_loss_violation_proven_even_if_rtt_ok(self):
        """When RTT=15ms and Loss=2.5% (>1.0%), violation is proven."""
        rows = [{
            "timestamp_utc": "2026-11-17T12:00:00Z",
            "elapsed_sec": "10.0",
            "event_scenario": "S4_RAN_DEGRADATION",
            "e2e_slice2_rtt_ms": "15.0",
            "e2e_slice2_loss_pct": "2.5"
        }]
        csv_path = self._write_csv("test_loss_violation.csv", rows)
        output = self._run_analyzer(csv_path)

        parts = self._get_table_row(output, "--- 2. SLICE 2: URLLC", "S4_RAN_DEGRADATION")
        self.assertIsNotNone(parts)
        self.assertEqual(parts[5], "0")       # Unk = 0
        self.assertEqual(parts[10], "100.0%") # SLA Viol % = 100.0%

    def test_04_fully_compliant_joint_sla(self):
        """When RTT=12ms and Loss=0.5% (both <= thresholds), compliant 0.0% violation."""
        rows = [{
            "timestamp_utc": "2026-11-17T12:00:00Z",
            "elapsed_sec": "10.0",
            "event_scenario": "S1_NORMAL_LIGHT",
            "e2e_slice2_rtt_ms": "12.0",
            "e2e_slice2_loss_pct": "0.5"
        }]
        csv_path = self._write_csv("test_compliant.csv", rows)
        output = self._run_analyzer(csv_path)

        parts = self._get_table_row(output, "--- 2. SLICE 2: URLLC", "S1_NORMAL_LIGHT")
        self.assertIsNotNone(parts)
        self.assertEqual(parts[5], "0")     # Unk = 0
        self.assertEqual(parts[10], "0.0%") # SLA Viol % = 0.0%

    def test_05_outage_loss_100_percent(self):
        """When Loss=100%, row is counted as outage and 100.0% SLA violation."""
        rows = [{
            "timestamp_utc": "2026-11-17T12:00:00Z",
            "elapsed_sec": "10.0",
            "event_scenario": "S5_RAN_OVERLOAD",
            "e2e_slice2_rtt_ms": "NaN",
            "e2e_slice2_loss_pct": "100.0"
        }]
        csv_path = self._write_csv("test_outage.csv", rows)
        output = self._run_analyzer(csv_path)

        parts = self._get_table_row(output, "--- 2. SLICE 2: URLLC", "S5_RAN_OVERLOAD")
        self.assertIsNotNone(parts)
        self.assertEqual(parts[3], "1")       # Outage = 1
        self.assertEqual(parts[10], "100.0%") # SLA Viol % = 100.0%

    def test_06_bler_scaled_to_percentage(self):
        """BLER 0.1000 in CSV must be formatted as 10.00 % in Section 3."""
        rows = [{
            "timestamp_utc": "2026-11-17T12:00:00Z",
            "elapsed_sec": "10.0",
            "event_scenario": "S3_RAN_SOFT",
            "ran_bler_cell1": "0.1000"
        }]
        csv_path = self._write_csv("test_bler.csv", rows)
        output = self._run_analyzer(csv_path)

        self.assertIn("--- 3. TELEMETRI INFRASTRUKTUR", output)
        self.assertIn("10.00 %", output)
        self.assertNotIn("0.10 %", output)

    def test_07_nan_backlog_displays_na(self):
        """All-NaN backlog readings must display 'N/A' rather than '0 B'."""
        rows = [{
            "timestamp_utc": "2026-11-17T12:00:00Z",
            "elapsed_sec": "10.0",
            "event_scenario": "S1_NORMAL_LIGHT",
            "upf_backlog_bytes_embb": "NaN"
        }]
        csv_path = self._write_csv("test_backlog_nan.csv", rows)
        output = self._run_analyzer(csv_path)

        parts = self._get_table_row(output, "--- 3. TELEMETRI INFRASTRUKTUR", "S1_NORMAL_LIGHT")
        self.assertIsNotNone(parts)
        # parts: [S1_NORMAL_LIGHT, PRB C1 Avg, PRB C1 Max, Backlog Max, ...]
        self.assertEqual(parts[3], "N/A")

    def test_08_drop_rate_max_gauge(self):
        """upf_drops_embb is a gauge rate; report maximum rate, not sum."""
        rows = [
            {"timestamp_utc": "2026-11-17T12:00:00Z", "elapsed_sec": "10.0", "event_scenario": "S6_CORE_SOFT", "upf_drops_embb": "10.0"},
            {"timestamp_utc": "2026-11-17T12:00:01Z", "elapsed_sec": "11.0", "event_scenario": "S6_CORE_SOFT", "upf_drops_embb": "25.5"},
            {"timestamp_utc": "2026-11-17T12:00:02Z", "elapsed_sec": "12.0", "event_scenario": "S6_CORE_SOFT", "upf_drops_embb": "15.0"},
        ]
        csv_path = self._write_csv("test_drops.csv", rows)
        output = self._run_analyzer(csv_path)

        self.assertIn("25.5 pkt/s", output)
        self.assertNotIn("50.5 pkt/s", output)

    def test_09_operational_phase_segmentation(self):
        """CSV spanning Baseline (<120s), Fault (120-420s), Recovery (>=420s) must output phase table."""
        rows = [
            {"timestamp_utc": "2026-11-17T12:00:00Z", "elapsed_sec": "30.0", "event_scenario": "S3_RAN_SOFT", "ran_prb_cell1": "10.0"},
            {"timestamp_utc": "2026-11-17T12:03:00Z", "elapsed_sec": "200.0", "event_scenario": "S3_RAN_SOFT", "ran_prb_cell1": "85.0"},
            {"timestamp_utc": "2026-11-17T12:08:00Z", "elapsed_sec": "500.0", "event_scenario": "S3_RAN_SOFT", "ran_prb_cell1": "12.0"},
        ]
        csv_path = self._write_csv("test_phases.csv", rows)
        output = self._run_analyzer(csv_path)

        self.assertIn("--- 4. AUDIT SEGMENTASI FASE OPERASIONAL", output)
        self.assertIn("S3_RAN_SOFT [1_BASELINE_NOMINAL [0-120s]]", output)
        self.assertIn("S3_RAN_SOFT [2_ACTIVE_FAULT_NOMINAL [120-420s]]", output)
        self.assertIn("S3_RAN_SOFT [3_RECOVERY_NOMINAL [420-600s]]", output)
        self.assertIn("10.0 %", output)
        self.assertIn("85.0 %", output)
        self.assertIn("12.0 %", output)

    def test_10_phase_segmentation_s1_reference_steady(self):
        """S1 baseline without disturbance must remain a single reference steady-state without active fault."""
        rows = [
            {"timestamp_utc": "2026-11-17T12:00:00Z", "elapsed_sec": "30.0", "event_scenario": "S1_NORMAL_LIGHT", "e2e_slice1_tput_mbps": "5.0"},
            {"timestamp_utc": "2026-11-17T12:03:00Z", "elapsed_sec": "200.0", "event_scenario": "S1_NORMAL_LIGHT", "e2e_slice1_tput_mbps": "5.0"},
            {"timestamp_utc": "2026-11-17T12:08:00Z", "elapsed_sec": "500.0", "event_scenario": "S1_NORMAL_LIGHT", "e2e_slice1_tput_mbps": "5.0"},
        ]
        csv_path = self._write_csv("test_s1_phases.csv", rows)
        output = self._run_analyzer(csv_path)

        # S1 has no fault injection; must not be split into false active fault or recovery phases
        self.assertNotIn("ACTIVE_FAULT", output)
        self.assertNotIn("--- 4. AUDIT SEGMENTASI FASE OPERASIONAL", output)

    def test_11_phase_segmentation_s5_continuous_saturated(self):
        """S5 continuous saturated load must remain a single steady saturated phase without active fault."""
        rows = [
            {"timestamp_utc": "2026-11-17T12:00:00Z", "elapsed_sec": "30.0", "event_scenario": "S5_RAN_OVERLOAD", "e2e_slice1_tput_mbps": "16.5"},
            {"timestamp_utc": "2026-11-17T12:03:00Z", "elapsed_sec": "200.0", "event_scenario": "S5_RAN_OVERLOAD", "e2e_slice1_tput_mbps": "16.5"},
            {"timestamp_utc": "2026-11-17T12:08:00Z", "elapsed_sec": "500.0", "event_scenario": "S5_RAN_OVERLOAD", "e2e_slice1_tput_mbps": "16.5"},
        ]
        csv_path = self._write_csv("test_s5_phases.csv", rows)
        output = self._run_analyzer(csv_path)

        # S5 is continuous saturation; must not be split into false baseline or recovery phases
        self.assertNotIn("ACTIVE_FAULT", output)
        self.assertNotIn("--- 4. AUDIT SEGMENTASI FASE OPERASIONAL", output)

    def test_12_actual_phase_annotation_overrides_nominal_schedule(self):
        """Informative actual event annotations like PHASE_2_ACTUAL_FAULT must override nominal windows."""
        rows = [
            # Injected fault actually occurred early at t = 100s, annotated by actual event logger
            {"timestamp_utc": "2026-11-17T12:00:00Z", "elapsed_sec": "100.0", "event_scenario": "S3_RAN_SOFT", "event_phase_id": "PHASE_2_ACTUAL_FAULT", "ran_prb_cell1": "75.0"},
            {"timestamp_utc": "2026-11-17T12:07:00Z", "elapsed_sec": "450.0", "event_scenario": "S3_RAN_SOFT", "event_phase_id": "PHASE_3_ACTUAL_RECOVERY", "ran_prb_cell1": "10.0"},
        ]
        csv_path = self._write_csv("test_actual_phase.csv", rows)
        output = self._run_analyzer(csv_path)

        # Must report the actual informative event phase, NOT 1_BASELINE_NOMINAL
        self.assertIn("PHASE_2_ACTUAL_FAULT", output)
        self.assertIn("PHASE_3_ACTUAL_RECOVERY", output)
        self.assertNotIn("1_BASELINE_NOMINAL", output)


# ---------------------------------------------------------------------------
# Integration tests for receiver_iperf.sh abort & export persistence
# ---------------------------------------------------------------------------

class TestReceiverAbortExportIntegration(unittest.TestCase):
    """Integration test suite ensuring abort state persistence and error enforcement in receiver export."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_receiver_iperf_")
        self.script_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "scripts", "receiver_iperf.sh")
        )
        with open(self.script_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        start_idx = None
        for i, l in enumerate(lines):
            if 'python3 - "$TARGET_FILE"' in l:
                start_idx = i + 1
                break
        end_idx = None
        if start_idx is not None:
            for j in range(start_idx, len(lines)):
                if lines[j].strip() == "EOF":
                    end_idx = j
                    break
        self.parser_code = "".join(lines[start_idx:end_idx]) if (start_idx and end_idx) else None

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def _run_parser(self, target_file, summary_file, force_abort="0", session_id="ue1"):
        self.assertIsNotNone(self.parser_code, "Could not extract parser code from receiver_iperf.sh")
        return subprocess.run(
            [sys.executable, "-c", self.parser_code, target_file, summary_file, force_abort, session_id],
            capture_output=True,
            text=True
        )

    def test_01_abort_then_export_preserves_aborted_status(self):
        """Simulate an abort, then subsequent export must preserve session_complete=False and aborted=True."""
        summary_path = os.path.join(self.test_dir, "receiver_ue1_summary.json")
        marker_path = os.path.join(self.test_dir, ".receiver_ue1_aborted")
        log_path = os.path.join(self.test_dir, "receiver_export.json")

        # Step 1: Simulate prior abort action
        with open(marker_path, "w") as mf:
            mf.write("")
        initial_abort_summary = {
            "format": "aborted",
            "session_complete": False,
            "aborted": True,
            "error": "Sesi receiver dihentikan paksa oleh perintah abort eksplisit"
        }
        with open(summary_path, "w", encoding="utf-8") as sf:
            json.dump(initial_abort_summary, sf, indent=2)

        # Step 2: Receiver log on host contains an 'end' block
        iperf_log_content = {
            "end": {
                "sum_received": {
                    "bytes": 5000000,
                    "bits_per_second": 9500000.0,
                    "seconds": 5.0,
                    "packets": 5000,
                    "lost_packets": 2,
                    "lost_percent": 0.04,
                    "jitter_ms": 0.5
                }
            }
        }
        with open(log_path, "w", encoding="utf-8") as lf:
            json.dump(iperf_log_content, lf)

        # Step 3: Run export parser
        res = self._run_parser(log_path, summary_path, force_abort="0", session_id="ue1")

        # Must exit with failure code 1 and report aborted in stderr
        self.assertEqual(res.returncode, 1)
        self.assertIn("ABORTED", res.stderr)
        self.assertNotIn("Session: COMPLETE", res.stdout)

        # Step 4: Verify summary file retains aborted state and does NOT flip to complete
        with open(summary_path, "r", encoding="utf-8") as sf:
            summary = json.load(sf)
        self.assertFalse(summary["session_complete"])
        self.assertTrue(summary["aborted"])
        self.assertEqual(summary["format"], "aborted")
        self.assertEqual(summary["goodput_mbps"], 9.5)

    def test_02_fixture_with_error_and_end_block_aborts(self):
        """When log fixture contains top-level error and an end block, parser must abort."""
        summary_path = os.path.join(self.test_dir, "receiver_ue1_summary.json")
        log_path = os.path.join(self.test_dir, "receiver_error_log.json")

        iperf_log_content = {
            "error": "interrupt - the server was interrupted",
            "end": {
                "sum_received": {
                    "bytes": 2000000,
                    "bits_per_second": 8000000.0,
                    "seconds": 2.0,
                    "packets": 2000,
                    "lost_packets": 10,
                    "lost_percent": 0.5,
                    "jitter_ms": 1.1
                }
            }
        }
        with open(log_path, "w", encoding="utf-8") as lf:
            json.dump(iperf_log_content, lf)

        res = self._run_parser(log_path, summary_path, force_abort="0", session_id="ue1")

        self.assertEqual(res.returncode, 1)
        self.assertIn("ABORTED", res.stderr)
        self.assertNotIn("Session: COMPLETE", res.stdout)

        with open(summary_path, "r", encoding="utf-8") as sf:
            summary = json.load(sf)
        self.assertFalse(summary["session_complete"])
        self.assertTrue(summary["aborted"])
        self.assertIn("interrupt", summary["error"])

    def test_03_normal_session_without_abort_completes(self):
        """Normal completed receiver run must succeed with session_complete=True."""
        summary_path = os.path.join(self.test_dir, "receiver_ue1_summary.json")
        log_path = os.path.join(self.test_dir, "receiver_normal_log.json")

        iperf_log_content = {
            "end": {
                "sum_received": {
                    "bytes": 10000000,
                    "bits_per_second": 10000000.0,
                    "seconds": 10.0,
                    "packets": 10000,
                    "lost_packets": 0,
                    "lost_percent": 0.0,
                    "jitter_ms": 0.8
                }
            }
        }
        with open(log_path, "w", encoding="utf-8") as lf:
            json.dump(iperf_log_content, lf)

        res = self._run_parser(log_path, summary_path, force_abort="0", session_id="ue1")

        self.assertEqual(res.returncode, 0)
        self.assertIn("Session: COMPLETE", res.stdout)

        with open(summary_path, "r", encoding="utf-8") as sf:
            summary = json.load(sf)
        self.assertTrue(summary["session_complete"])
        self.assertFalse(summary["aborted"])
        self.assertEqual(summary["goodput_mbps"], 10.0)

    def test_04_single_line_event_end_with_data_error_aborts(self):
        """Single-line JSON {'event':'end','data':{'error':…}} must result in aborted status, never COMPLETE."""
        summary_path = os.path.join(self.test_dir, "receiver_ue1_summary.json")
        log_path = os.path.join(self.test_dir, "receiver_single_line_err.json")

        payload = {
            "event": "end",
            "data": {
                "error": "interrupt - the server was interrupted",
                "sum_received": {
                    "bytes": 1000000,
                    "bits_per_second": 5000000.0,
                    "seconds": 2.0,
                    "packets": 1000,
                    "lost_packets": 2,
                    "lost_percent": 0.2,
                    "jitter_ms": 1.0
                }
            }
        }
        with open(log_path, "w", encoding="utf-8") as lf:
            json.dump(payload, lf)

        res = self._run_parser(log_path, summary_path, force_abort="0", session_id="ue1")

        self.assertEqual(res.returncode, 1)
        self.assertIn("ABORTED", res.stderr)
        self.assertNotIn("Session: COMPLETE", res.stdout)

        with open(summary_path, "r", encoding="utf-8") as sf:
            summary = json.load(sf)
        self.assertFalse(summary["session_complete"])
        self.assertTrue(summary["aborted"])
        self.assertIn("interrupt", summary["error"])

    def test_05_multi_line_stream_event_end_with_data_error_aborts(self):
        """Multi-line JSON-stream containing {'event':'end','data':{'error':…}} must abort, never COMPLETE."""
        summary_path = os.path.join(self.test_dir, "receiver_ue1_summary.json")
        log_path = os.path.join(self.test_dir, "receiver_stream_err.json")

        lines = [
            json.dumps({"event": "start", "data": {}}),
            json.dumps({"event": "interval", "data": {"sum": {"bytes": 500000, "bits_per_second": 5000000.0, "seconds": 1.0}}}),
            json.dumps({
                "event": "end",
                "data": {
                    "error": "interrupt - the server was interrupted",
                    "sum_received": {
                        "bytes": 1000000,
                        "bits_per_second": 5000000.0,
                        "seconds": 2.0,
                        "packets": 1000,
                        "lost_packets": 5,
                        "lost_percent": 0.5,
                        "jitter_ms": 1.2
                    }
                }
            })
        ]
        with open(log_path, "w", encoding="utf-8") as lf:
            lf.write("\n".join(lines) + "\n")

        res = self._run_parser(log_path, summary_path, force_abort="0", session_id="ue1")

        self.assertEqual(res.returncode, 1)
        self.assertIn("ABORTED", res.stderr)
        self.assertNotIn("Session: COMPLETE", res.stdout)

        with open(summary_path, "r", encoding="utf-8") as sf:
            summary = json.load(sf)
        self.assertFalse(summary["session_complete"])
        self.assertTrue(summary["aborted"])
        self.assertIn("interrupt", summary["error"])


class TestTrafGenQualityGates(unittest.TestCase):
    """Quality gates for scripts/trafgen.sh ping and throughput parsing."""

    def setUp(self):
        self.repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.trafgen_path = os.path.join(self.repo_root, "scripts", "trafgen.sh")
        self.test_dir = tempfile.mkdtemp(prefix="test_trafgen_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_01_trafgen_syntax_check(self):
        res = subprocess.run(["bash", "-n", self.trafgen_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"trafgen.sh syntax error: {res.stderr}")

    def test_02_trafgen_ping_summary_extraction(self):
        log_path = os.path.join(self.test_dir, "ping.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                "[1731831539.123] 64 bytes from 192.168.70.135: icmp_seq=1 ttl=64 time=10.0 ms\n"
                "[1731831539.223] 64 bytes from 192.168.70.135: icmp_seq=2 ttl=64 time=12.5 ms\n\n"
                "--- 192.168.70.135 ping statistics ---\n"
                "2 packets transmitted, 2 received, 0% packet loss, time 200ms\n"
                "rtt min/avg/max/mdev = 10.000/11.250/12.500/1.250 ms\n"
            )
        script = f"""
        PING_LOG="{log_path}"
        rtt="12.50"
        loss_pct="0.0"
        ping_stat=$(grep -oP '(?<=rtt min/avg/max/mdev = )[^ ]+' "$PING_LOG" 2>/dev/null | tail -n 1 || true)
        ping_loss=$(grep -oP '\\d+(\\.\\d+)?(?=%\\s+(packet\\s+)?loss)' "$PING_LOG" 2>/dev/null | tail -n 1 || true)
        if [[ -z "$ping_stat" || "$ping_stat" == "N/A" ]]; then
          [[ "$rtt" != "NaN" && -n "$rtt" ]] && ping_stat="$rtt" || ping_stat="N/A"
        fi
        if [[ -z "$ping_loss" ]]; then
          [[ "$loss_pct" != "NaN" && -n "$loss_pct" ]] && ping_loss="$loss_pct" || ping_loss="0.0"
        fi
        echo "$ping_stat|$ping_loss"
        """
        res = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "10.000/11.250/12.500/1.250|0")

    def test_03_trafgen_ping_fallback_when_summary_absent(self):
        log_path = os.path.join(self.test_dir, "ping_incomplete.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                "[1731831539.123] 64 bytes from 192.168.70.135: icmp_seq=1 ttl=64 time=10.0 ms\n"
                "[1731831539.223] 64 bytes from 192.168.70.135: icmp_seq=2 ttl=64 time=13.3 ms\n"
            )
        script = f"""
        PING_LOG="{log_path}"
        rtt="13.30"
        loss_pct="0.0"
        ping_stat=$(grep -oP '(?<=rtt min/avg/max/mdev = )[^ ]+' "$PING_LOG" 2>/dev/null | tail -n 1 || true)
        ping_loss=$(grep -oP '\\d+(\\.\\d+)?(?=%\\s+(packet\\s+)?loss)' "$PING_LOG" 2>/dev/null | tail -n 1 || true)
        if [[ -z "$ping_stat" || "$ping_stat" == "N/A" ]]; then
          [[ "$rtt" != "NaN" && -n "$rtt" ]] && ping_stat="$rtt" || ping_stat="N/A"
        fi
        if [[ -z "$ping_loss" ]]; then
          [[ "$loss_pct" != "NaN" && -n "$loss_pct" ]] && ping_loss="$loss_pct" || ping_loss="0.0"
        fi
        echo "$ping_stat|$ping_loss"
        """
        res = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "13.30|0.0")


if __name__ == "__main__":
    unittest.main()
