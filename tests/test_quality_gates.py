#!/usr/bin/env python3
"""
Automated Quality Gate & Falsification Test Suite for 5G O-RAN Thesis Runner
Location: tests/test_quality_gates.py
Pure Python 3 Standard Library - Zero External Dependencies

Validates the 3-status research contract:
- execution_complete
- data_quality_pass
- training_eligible
under both clean positive conditions and rigorous adversarial/falsification test fixtures.
"""

import csv
import datetime
import json
import math
import os
import shutil
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import run_pilot_experiment
from run_pilot_experiment import evaluate_run_dataset, REQUIRED_COLUMNS


def create_fixture_telemetry(path, run_id, rows_data):
    """Creates a telemetry CSV file with REQUIRED_COLUMNS and supplied row mappings."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(REQUIRED_COLUMNS)
        for r_dict in rows_data:
            row = []
            for col in REQUIRED_COLUMNS:
                if col == "run_id":
                    val = r_dict.get(col, run_id)
                elif col in r_dict:
                    val = r_dict[col]
                else:
                    val = "NaN"
                row.append(str(val))
            writer.writerow(row)


def create_fixture_events(path, run_id, events_data):
    """Creates an experiment_events CSV file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    headers = ["timestamp_utc", "run_id", "phase_id", "event_type", "scenario_id", "target_domain", "target_component", "mechanism", "parameters", "notes"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for ev in events_data:
            writer.writerow([
                ev.get("timestamp_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()),
                ev.get("run_id", run_id),
                ev.get("phase_id", "phase_1_S1"),
                ev.get("event_type", "START_SCENARIO"),
                ev.get("scenario_id", "S1"),
                ev.get("target_domain", "BASELINE"),
                ev.get("target_component", "NONE"),
                ev.get("mechanism", "NONE"),
                ev.get("parameters", "load=10M"),
                ev.get("notes", "fixture event")
            ])


def create_fixture_jsonl(path, run_id, poll_records):
    """Creates an nwdaf_raw_poll_responses.jsonl file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in poll_records:
            if "run_id" not in rec:
                rec["run_id"] = run_id
            f.write(json.dumps(rec) + "\n")


class TestResearchContractQualityGates(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_pilot_gate_")
        os.environ["MONITORING_DATA_DIR"] = self.test_dir
        self.run_id = "TEST_RUN_01"
        self.run_dir = os.path.join(self.test_dir, "raw", self.run_id)
        os.makedirs(self.run_dir, exist_ok=True)
        self.planned_scenarios = ["S1", "S3", "S6"]
        self.config_params = {
            "min_total_rows": 30,
            "min_phase_rows": 10,
            "min_ran_coverage": 0.70
        }

    def tearDown(self):
        os.environ.pop("MONITORING_DATA_DIR", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_pos_01_clean_healthy_run(self):
        """POS-01: Clean, valid dataset with full coverage and verified recovery must pass all gates."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        rows = []
        for i in range(40):
            if i < 15:
                phase, scen, prb, vol = "phase_1_S1", "S1_NORMAL_LIGHT", 35.0, 100000.0 + i*1000
            elif i < 30:
                phase, scen, prb, vol = "phase_2_S3", "S3_RAN_OVERLOAD", 99.5, 200000.0 + i*1000
            else:
                phase, scen, prb, vol = "phase_3_S6", "S6_CORE_QUEUE_TBF", 40.0, 300000.0 + i*1000
            rows.append({
                "timestamp_utc": f"2026-10-16T10:00:{i:02d}Z",
                "elapsed_sec": f"{i}.000",
                "run_id": self.run_id,
                "event_phase_id": phase,
                "event_scenario": scen,
                "ran_prb_cell1": prb,
                "nwdaf_comm_ul_bytes": vol,
                "upf_backlog_bytes_embb": 0.0
            })
        create_fixture_telemetry(csv_path, self.run_id, rows)

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [
            {"timestamp_utc": "2026-10-16T10:00:00Z", "phase_id": "phase_1_S1", "scenario_id": "S1"},
            {"timestamp_utc": "2026-10-16T10:00:15Z", "phase_id": "phase_2_S3", "scenario_id": "S3"},
            {"timestamp_utc": "2026-10-16T10:00:30Z", "phase_id": "phase_3_S6", "scenario_id": "S6"},
            {"timestamp_utc": "2026-10-16T10:00:40Z", "phase_id": "phase_clear", "scenario_id": "CLEAR"}
        ])

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "http_status": 200, "response_body": {"ueComms": [{"commDur": 10}]}}
        ])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=self.planned_scenarios,
            recovery_verified=True,
            recovery_evidence={"final_backlog": 0.0, "final_prb": 35.0},
            config_params=self.config_params
        )

        self.assertTrue(dq_pass, f"Data quality should pass: {dq_reasons}")
        self.assertTrue(tr_elig, f"Training eligible should pass: {tr_reasons}")
        self.assertEqual(len(dq_reasons), 0)
        self.assertEqual(len(tr_reasons), 0)

    def test_pos_02_constant_nwdaf_with_new_source_reports(self):
        """POS-02: Constant NWDAF volume with verified poll responses must NOT be rejected."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        rows = []
        for i in range(35):
            phase, scen = ("phase_1_S1", "S1") if i < 18 else ("phase_2_S3", "S3")
            rows.append({
                "timestamp_utc": f"2026-10-16T10:00:{i:02d}Z",
                "elapsed_sec": f"{i}.000",
                "run_id": self.run_id,
                "event_phase_id": phase,
                "event_scenario": scen,
                "ran_prb_cell1": 35.0,
                # Volume is completely constant (e.g. steady traffic report)
                "nwdaf_comm_ul_bytes": 5000000.0,
                "upf_backlog_bytes_embb": 0.0
            })
        create_fixture_telemetry(csv_path, self.run_id, rows)

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [
            {"timestamp_utc": "2026-10-16T10:00:00Z", "phase_id": "phase_1_S1", "scenario_id": "S1"},
            {"timestamp_utc": "2026-10-16T10:00:18Z", "phase_id": "phase_2_S3", "scenario_id": "S3"},
        ])

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "http_status": 200, "response_body": {"ueComms": [{"commDur": 10}]}},
            {"poll_timestamp_utc": "2026-10-16T10:00:20Z", "http_status": 200, "response_body": {"ueComms": [{"commDur": 20}]}}
        ])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1", "S3"],
            recovery_verified=True,
            config_params=self.config_params
        )

        self.assertTrue(dq_pass)
        self.assertTrue(tr_elig, f"Constant NWDAF with source reports should be training eligible: {tr_reasons}")

    def test_pos_03_real_log_event_writer_canonical_scenario(self):
        """POS-03: Real log_event.py writer producing canonical IDs (e.g. S1_NORMAL_LIGHT) must be accepted by validator."""
        from run_pilot_experiment import is_scenario_matching

        # Unit verification of scenario matcher
        self.assertTrue(is_scenario_matching("S1_NORMAL_LIGHT", "S1"))
        self.assertTrue(is_scenario_matching("S1", "S1_NORMAL_LIGHT"))
        self.assertTrue(is_scenario_matching("S3_RAN_OVERLOAD", "S3"))
        self.assertTrue(is_scenario_matching("S6_CORE_QUEUE_TBF", "S6"))
        self.assertFalse(is_scenario_matching("S1_NORMAL_LIGHT", "S3"))
        self.assertFalse(is_scenario_matching("S6_CORE_QUEUE_TBF", "S1"))

        # Integration test using authentic scripts/log_event.py
        log_event_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "log_event.py"))
        env = os.environ.copy()
        env["MONITORING_DATA_DIR"] = self.run_dir

        active_run_file = os.path.join(self.run_dir, "active_run_id.txt")
        with open(active_run_file, "w") as f:
            f.write(self.run_id + "\n")

        import subprocess
        # Run real log_event.py writer for phase 1 and phase 2
        res1 = subprocess.run([sys.executable, log_event_script, "S1", "Normal baseline", "--phase-id", "phase_1_S1"], env=env, capture_output=True, text=True)
        self.assertEqual(res1.returncode, 0, f"log_event failed: {res1.stderr}")

        res2 = subprocess.run([sys.executable, log_event_script, "S3", "RAN overload fault", "--phase-id", "phase_2_S3"], env=env, capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0, f"log_event failed: {res2.stderr}")

        # Verify real log_event.py wrote canonical scenario IDs
        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        self.assertTrue(os.path.exists(events_path))
        with open(events_path, "r", encoding="utf-8") as ef:
            rows = list(csv.DictReader(ef))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["scenario_id"], "S1_NORMAL_LIGHT")
        self.assertEqual(rows[1]["scenario_id"], "S3_RAN_OVERLOAD")

        # Create matching telemetry and JSONL
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        telemetry_rows = []
        for i in range(35):
            phase, scen = ("phase_1_S1", "S1_NORMAL_LIGHT") if i < 18 else ("phase_2_S3", "S3_RAN_OVERLOAD")
            telemetry_rows.append({
                "timestamp_utc": f"2026-10-16T10:00:{i:02d}Z",
                "elapsed_sec": f"{i}.000",
                "run_id": self.run_id,
                "event_phase_id": phase,
                "event_scenario": scen,
                "ran_prb_cell1": 35.0,
                "nwdaf_comm_ul_bytes": 100000.0 + i * 500,
                "upf_backlog_bytes_embb": 0.0
            })
        create_fixture_telemetry(csv_path, self.run_id, telemetry_rows)

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "http_status": 200, "response_body": {"ueComms": [{"commDur": 10}]}}
        ])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1", "S3"],
            recovery_verified=True,
            config_params=self.config_params
        )

        self.assertTrue(dq_pass, f"Authentic log_event canonical IDs must pass data_quality_pass: {dq_reasons}")
        self.assertTrue(tr_elig, f"Authentic log_event canonical IDs must pass training_eligible: {tr_reasons}")
        self.assertEqual(len(dq_reasons), 0)

    def test_pos_04_receiver_parser_json_stream_and_strict_validation(self):
        """POS-04: Receiver parser must correctly extract goodput/loss from ESnet json-stream and exit nonzero on errors."""
        import subprocess
        receiver_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "receiver_iperf.sh"))
        with open(receiver_script, "r", encoding="utf-8") as f:
            sh_content = f.read()
        py_parser_code = sh_content.split("python3 - \"$TARGET_FILE\" \"$SUMMARY_FILE\" << 'EOF'")[1].split("EOF")[0]

        cases = [
            # 1. Standard single JSON
            ("standard", json.dumps({"end": {"sum_received": {"bytes": 12500000, "bits_per_second": 10000000.0, "lost_packets": 10, "packets": 100, "lost_percent": 10.0, "jitter_ms": 1.2}}}), 0, 10.0, 10.0, True),
            # 2. ESnet JSON-stream with final end event
            ("stream", '{"event": "start", "data": {}}\n{"event": "end", "data": {"sum_received": {"bytes": 12500000, "bits_per_second": 10000000.0, "lost_packets": 10, "packets": 100, "lost_percent": 10.0, "jitter_ms": 1.2}}}', 0, 10.0, 10.0, True),
            # 3. ESnet JSON-stream with ONLY interval (session incomplete, must fail export with code 1)
            ("partial_stream", '{"event": "start", "data": {}}\n{"event": "interval", "data": {"sum": {"bytes": 1250000, "bits_per_second": 10000000.0, "lost_packets": 0, "packets": 10, "lost_percent": 0.0, "jitter_ms": 1.0}}}', 1, 10.0, 0.0, False),
            # 4. Corrupt JSON stream (must fail, not silent 0)
            ("corrupt", '{"event": "start"}\n{"event": "broken json line', 1, None, None, None),
            # 5. Incomplete JSON without mandatory bytes (must fail)
            ("incomplete", json.dumps({"end": {"sum_received": {"jitter_ms": 1.2}}}), 1, None, None, None),
            # 6. Empty JSON (must fail)
            ("empty", "   ", 1, None, None, None)
        ]

        for label, raw_input, exp_exit, exp_mbps, exp_loss, exp_complete in cases:
            tf = os.path.join(self.test_dir, f"test_{label}_input.json")
            sf = os.path.join(self.test_dir, f"test_{label}_summary.json")
            with open(tf, "w", encoding="utf-8") as f:
                f.write(raw_input)

            proc = subprocess.run([sys.executable, "-c", py_parser_code, tf, sf], capture_output=True, text=True)
            self.assertEqual(proc.returncode, exp_exit, f"Case {label} unexpected exit code {proc.returncode} (stderr: {proc.stderr})")

            if exp_complete is not None and os.path.exists(sf):
                with open(sf, "r", encoding="utf-8") as f:
                    res = json.load(f)
                self.assertEqual(res.get("session_complete"), exp_complete, f"Case {label} session_complete mismatch")
                if exp_exit == 0:
                    self.assertEqual(res["goodput_mbps"], exp_mbps)
                    self.assertEqual(res["packet_loss_pct"], exp_loss)

    def test_pos_05_analyze_dataset_both_slices_output(self):
        """POS-05: analyze_dataset.py must report both Slice 1 (eMBB) and Slice 2 (URLLC) explicitly."""
        import subprocess
        analyze_script = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "analyze_dataset.py"))

        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        rows = []
        for i in range(20):
            rows.append({
                "timestamp_utc": f"2026-10-16T10:00:{i:02d}Z",
                "elapsed_sec": f"{i}.000",
                "run_id": self.run_id,
                "event_phase_id": "phase_1_S1",
                "event_scenario": "S1_NORMAL_LIGHT",
                "e2e_slice1_tput_mbps": 10.5,
                "e2e_slice1_rtt_ms": 12.4,
                "e2e_slice1_loss_pct": 0.0,
                "e2e_slice2_rtt_ms": 8.5,
                "e2e_slice2_loss_pct": 0.0,
                "ran_prb_cell1": 35.0,
                "upf_backlog_bytes_embb": 0.0
            })
        create_fixture_telemetry(csv_path, self.run_id, rows)

        res = subprocess.run([sys.executable, analyze_script, csv_path], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"analyze_dataset failed: {res.stderr}")
        self.assertIn("SLICE 1: eMBB", res.stdout)
        self.assertIn("SLICE 2: URLLC", res.stdout)
        self.assertIn("TELEMETRI INFRASTRUKTUR", res.stdout)
        self.assertIn("10.50 M", res.stdout)
        self.assertIn("12.40 ms", res.stdout)
        self.assertIn("8.50 ms", res.stdout)

    def test_pos_06_consecutive_runs_archive_counter_isolation(self):
        """POS-06: Consecutive runs sharing the same long-running collector daemon must isolate archive counters."""
        run_a_id = "TEST_RUN_A"
        run_b_id = "TEST_RUN_B"
        run_a_dir = os.path.join(self.test_dir, "raw", run_a_id)
        run_b_dir = os.path.join(self.test_dir, "raw", run_b_id)
        os.makedirs(run_a_dir, exist_ok=True)
        os.makedirs(run_b_dir, exist_ok=True)

        # 1. Setup RUN_A: 1 jsonl line
        jsonl_a = os.path.join(run_a_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_a, run_a_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "http_status": 200, "response_body": {"ueComms": [{"commDur": 10}]}}
        ])
        csv_a = os.path.join(run_a_dir, f"telemetry_{run_a_id}.csv")
        create_fixture_telemetry(csv_a, run_a_id, [{
            "elapsed_sec": str(i),
            "ran_prb_cell1": 35.0,
            "nwdaf_comm_ul_bytes": 1000.0,
            "event_phase_id": "phase_1_S1",
            "event_scenario": "S1"
        } for i in range(35)])
        events_a = os.path.join(run_a_dir, f"experiment_events_{run_a_id}.csv")
        create_fixture_events(events_a, run_a_id, [{"phase_id": "phase_1_S1", "scenario_id": "S1"}])

        # 2. Setup RUN_B: 1 jsonl line
        jsonl_b = os.path.join(run_b_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_b, run_b_id, [
            {"poll_timestamp_utc": "2026-10-16T10:01:05Z", "http_status": 200, "response_body": {"ueComms": [{"commDur": 20}]}}
        ])
        csv_b = os.path.join(run_b_dir, f"telemetry_{run_b_id}.csv")
        create_fixture_telemetry(csv_b, run_b_id, [{
            "elapsed_sec": str(i),
            "ran_prb_cell1": 35.0,
            "nwdaf_comm_ul_bytes": 2000.0,
            "event_phase_id": "phase_1_S1",
            "event_scenario": "S1"
        } for i in range(35)])
        events_b = os.path.join(run_b_dir, f"experiment_events_{run_b_id}.csv")
        create_fixture_events(events_b, run_b_id, [{"phase_id": "phase_1_S1", "scenario_id": "S1"}])

        # Test Scenario 1: Using explicit per-run metrics from updated collector
        collector_metrics_b = {
            "nwdaf_raw_polls_total": 3,
            "nwdaf_raw_polls_written": 2,
            "nwdaf_raw_polls_failed": 1,
            "nwdaf_run_raw_polls_written": 1,
            "nwdaf_run_raw_polls_failed": 0
        }
        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=run_b_dir,
            run_id=run_b_id,
            planned_scenarios=["S1"],
            recovery_verified=True,
            config_params=self.config_params,
            collector_metrics=collector_metrics_b
        )
        self.assertTrue(dq_pass, f"RUN_B must pass when using per-run metrics: {dq_reasons}")
        self.assertEqual(len(dq_reasons), 0)

        # Test Scenario 2: Using initial/final delta without per-run keys (fallback for older exporter)
        initial_metrics_b = {
            "nwdaf_raw_polls_written": 1,
            "nwdaf_raw_polls_failed": 1
        }
        final_metrics_b = {
            "nwdaf_raw_polls_written": 2,
            "nwdaf_raw_polls_failed": 1
        }
        dq_pass2, tr_elig2, summary2, dq_reasons2, tr_reasons2 = evaluate_run_dataset(
            run_dir=run_b_dir,
            run_id=run_b_id,
            planned_scenarios=["S1"],
            recovery_verified=True,
            config_params=self.config_params,
            collector_metrics=final_metrics_b,
            initial_collector_metrics=initial_metrics_b
        )
        self.assertTrue(dq_pass2, f"RUN_B must pass using delta between initial and final metrics: {dq_reasons2}")
        self.assertEqual(len(dq_reasons2), 0)

    def test_neg_01_single_valid_row_coverage_failure(self):
        """NEG-01: 30 rows but only 1 row valid float -> passes data_quality_pass (syntax ok), fails training_eligible."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        rows = []
        for i in range(30):
            # Only row 0 has valid PRB, rest are NaN
            prb_val = 35.0 if i == 0 else "NaN"
            rows.append({
                "timestamp_utc": f"2026-10-16T10:00:{i:02d}Z",
                "elapsed_sec": f"{i}.000",
                "run_id": self.run_id,
                "event_phase_id": "phase_1_S1",
                "event_scenario": "S1_NORMAL_LIGHT",
                "ran_prb_cell1": prb_val,
                "nwdaf_comm_ul_bytes": "NaN"
            })
        create_fixture_telemetry(csv_path, self.run_id, rows)

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [
            {"timestamp_utc": "2026-10-16T10:00:00Z", "phase_id": "phase_1_S1", "scenario_id": "S1"}
        ])

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "http_status": 200, "response_body": {}}
        ])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            recovery_verified=True,
            config_params=self.config_params
        )

        self.assertTrue(dq_pass, "Syntactic structure should pass data_quality_pass")
        self.assertFalse(tr_elig, "Dataset with only 1 valid row must be rejected from training_eligible")
        self.assertTrue(any("cakupan telemetri RAN di bawah ambang batas" in r for r in tr_reasons))

    def test_neg_02_header_only_event_file(self):
        """NEG-02: Event CSV contains only header with zero event records -> must fail data_quality_pass."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        create_fixture_telemetry(csv_path, self.run_id, [{"elapsed_sec": str(i)} for i in range(35)])

        # Create header-only event file
        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        with open(events_path, "w", newline="", encoding="utf-8") as f:
            f.write("timestamp_utc,run_id,phase_id,event_type,scenario_id,target_domain,target_component,mechanism,parameters,notes\n")

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [{"http_status": 200}])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            config_params=self.config_params
        )

        self.assertFalse(dq_pass)
        self.assertFalse(tr_elig)
        self.assertTrue(any("hanya berisi header" in r for r in dq_reasons))

    def test_neg_03_telemetry_contains_inf(self):
        """NEG-03: Telemetry contains 'inf' or '-inf' -> must fail data_quality_pass."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        rows = [{"elapsed_sec": str(i), "ran_prb_cell1": 35.0} for i in range(35)]
        rows[10]["ran_prb_cell1"] = "inf"
        create_fixture_telemetry(csv_path, self.run_id, rows)

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [{"phase_id": "phase_1_S1", "scenario_id": "S1"}])

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [{"http_status": 200}])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            config_params=self.config_params
        )

        self.assertFalse(dq_pass)
        self.assertTrue(any("inf" in r for r in dq_reasons))

    def test_neg_04_uninitialized_label_leakage(self):
        """NEG-04: Active testing phase labeled as UNINITIALIZED -> passes data_quality_pass, fails training_eligible."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        rows = []
        for i in range(35):
            # i >= 10 has UNINITIALIZED during active phase
            scen = "UNINITIALIZED" if i >= 10 else "S1_NORMAL_LIGHT"
            rows.append({
                "timestamp_utc": f"2026-10-16T10:00:{i:02d}Z",
                "elapsed_sec": f"{i}.000",
                "run_id": self.run_id,
                "event_phase_id": "phase_1_S1",
                "event_scenario": scen,
                "ran_prb_cell1": 35.0,
                "nwdaf_comm_ul_bytes": 1000.0
            })
        create_fixture_telemetry(csv_path, self.run_id, rows)

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [{"phase_id": "phase_1_S1", "scenario_id": "S1"}])

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [{"http_status": 200}])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            recovery_verified=True,
            config_params=self.config_params
        )

        self.assertTrue(dq_pass)
        self.assertFalse(tr_elig)
        self.assertTrue(any("UNINITIALIZED" in r for r in tr_reasons))

    def test_neg_05_nwdaf_start_time_does_not_break_run_id(self):
        """NEG-05: Collector check_run_state_change with NWDAF_START_TIME must still resolve active_run_id."""
        import telemetry_collector

        # Create temporary active_run_id.txt
        state_file = os.path.join(self.test_dir, "active_run_id.txt")
        with open(state_file, "w") as f:
            f.write("EXPERIMENT_RUN_XYZ\n")

        orig_state_file = telemetry_collector.RUN_STATE_FILE
        telemetry_collector.RUN_STATE_FILE = state_file

        os.environ["NWDAF_START_TIME"] = "2026-10-16T00:00:00Z"
        try:
            window_start = telemetry_collector.check_run_state_change()
            self.assertEqual(window_start, "2026-10-16T00:00:00Z")
            # CRUCIAL: active_run_id must NOT be None!
            self.assertEqual(telemetry_collector.active_run_id, "EXPERIMENT_RUN_XYZ")
        finally:
            telemetry_collector.RUN_STATE_FILE = orig_state_file
            os.environ.pop("NWDAF_START_TIME", None)

    def test_neg_06_raw_jsonl_missing_or_corrupt(self):
        """NEG-06: Raw JSONL archive missing or malformed -> must fail data_quality_pass."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        create_fixture_telemetry(csv_path, self.run_id, [{"elapsed_sec": str(i), "ran_prb_cell1": 35.0} for i in range(35)])

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [{"phase_id": "phase_1_S1", "scenario_id": "S1"}])

        # Write corrupt line in JSONL
        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        with open(jsonl_path, "w") as f:
            f.write("{corrupt_json_line\n")

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            config_params=self.config_params
        )

        self.assertFalse(dq_pass)
        self.assertTrue(any("korup" in r or "gagal" in r for r in dq_reasons))

    def test_neg_07_recovery_timeout_unverified(self):
        """NEG-07: Recovery unverified (recovery_verified=False) -> passes data_quality_pass, fails training_eligible."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        create_fixture_telemetry(csv_path, self.run_id, [{
            "elapsed_sec": str(i),
            "ran_prb_cell1": 35.0,
            "nwdaf_comm_ul_bytes": 1000.0,
            "event_phase_id": "phase_1_S1",
            "event_scenario": "S1"
        } for i in range(35)])

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [{"phase_id": "phase_1_S1", "scenario_id": "S1"}])

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [{"http_status": 200}])

        # recovery_verified is False
        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            recovery_verified=False,
            config_params=self.config_params
        )

        self.assertTrue(dq_pass)
        self.assertFalse(tr_elig)
        self.assertTrue(any("Pemulihan tidak terverifikasi" in r for r in tr_reasons))

    def test_neg_08_recovery_with_stale_or_missing_metrics(self):
        """NEG-08: Recovery with stale or missing live telemetri (NaN/unavailable) must timeout and fail."""
        from unittest.mock import patch

        stale_metrics = {
            "upf_backlog_embb": float("nan"),
            "ran_prb_cell1": float("nan"),
            "nwdaf_comm_freshness": 0,
            "available": False
        }

        with patch("run_pilot_experiment.fetch_live_metrics", return_value=stale_metrics):
            verified, evidence, reason = run_pilot_experiment.verify_recovery(
                unattended=True,
                timeout_sec=1.5,
                stability_sec=1.0,
                target_backlog=0.0,
                target_prb=40.0
            )
            self.assertFalse(verified, "Stale or missing metrics must not be verified as recovered")
            self.assertIn("Recovery timeout", reason)
            self.assertFalse(any(s["healthy"] for s in evidence["samples"]))

    def test_neg_09_archive_failure_after_initial_success(self):
        """NEG-09: Archive failure occurring after initial successful writes must increment failure counter."""
        import telemetry_collector

        state_file = os.path.join(self.test_dir, "active_run_id.txt")
        with open(state_file, "w") as f:
            f.write(f"{self.run_id}\n")

        orig_state_file = telemetry_collector.RUN_STATE_FILE
        telemetry_collector.RUN_STATE_FILE = state_file
        telemetry_collector.active_run_id = self.run_id
        telemetry_collector.raw_poll_stats = {"total": 0, "written": 0, "failed": 0, "last_error": ""}

        try:
            # Poll 1: Writes successfully to run_dir
            telemetry_collector.log_raw_nwdaf_poll({"poll_idx": 1, "http_status": 200})
            self.assertEqual(telemetry_collector.raw_poll_stats["written"], 1)
            self.assertEqual(telemetry_collector.raw_poll_stats["failed"], 0)

            # Poll 2: Force failure by making run_dir inaccessible or mocking open to raise PermissionError
            from unittest.mock import patch
            with patch("builtins.open", side_effect=PermissionError("Mock Permission Denied")):
                telemetry_collector.log_raw_nwdaf_poll({"poll_idx": 2, "http_status": 200})

            # Failure counter must increment; failure must NOT be silently swallowed!
            self.assertEqual(telemetry_collector.raw_poll_stats["total"], 2)
            self.assertEqual(telemetry_collector.raw_poll_stats["failed"], 1)
            self.assertIn("Permission Denied", telemetry_collector.raw_poll_stats["last_error"])
        finally:
            telemetry_collector.RUN_STATE_FILE = orig_state_file

    def test_neg_10_empty_nwdaf_body_with_all_nan_volume_must_fail_training_eligible(self):
        """NEG-10: All NWDAF volume NaN in CSV and JSONL has HTTP 200 with empty body -> must fail training_eligible."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        rows = []
        for i in range(35):
            phase, scen = ("phase_1_S1", "S1") if i < 18 else ("phase_2_S3", "S3")
            rows.append({
                "timestamp_utc": f"2026-10-16T10:00:{i:02d}Z",
                "elapsed_sec": f"{i}.000",
                "run_id": self.run_id,
                "event_phase_id": phase,
                "event_scenario": scen,
                "ran_prb_cell1": 35.0,
                "nwdaf_comm_ul_bytes": "NaN",  # Entire volume NaN!
                "upf_backlog_bytes_embb": 0.0
            })
        create_fixture_telemetry(csv_path, self.run_id, rows)

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [
            {"timestamp_utc": "2026-10-16T10:00:00Z", "phase_id": "phase_1_S1", "scenario_id": "S1"},
            {"timestamp_utc": "2026-10-16T10:00:18Z", "phase_id": "phase_2_S3", "scenario_id": "S3"},
        ])

        # JSONL has HTTP 200 with empty body {} (no AnLF analytic payload)
        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "http_status": 200, "response_body": {}}
        ])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1", "S3"],
            recovery_verified=True,
            config_params=self.config_params
        )

        self.assertTrue(dq_pass, f"Syntax is valid so data_quality should pass: {dq_reasons}")
        self.assertFalse(tr_elig, "Empty NWDAF body and NaN volume must NOT be training eligible")
        self.assertTrue(any("payload analitik NWDAF" in r or "kelayakan NWDAF" in r for r in tr_reasons))

    def test_neg_11_invalid_event_timestamp_and_phase_mismatch_must_fail_data_quality(self):
        """NEG-11: Event contains unparseable timestamp or scenario mismatch -> must fail data_quality_pass."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        create_fixture_telemetry(csv_path, self.run_id, [{
            "elapsed_sec": str(i),
            "ran_prb_cell1": 35.0,
            "nwdaf_comm_ul_bytes": 1000.0,
            "event_phase_id": "phase_1_S1",
            "event_scenario": "S1"
        } for i in range(35)])

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        # Record event with malformed timestamp
        create_fixture_events(events_path, self.run_id, [
            {"timestamp_utc": "NOT_AN_ISO_TIMESTAMP", "phase_id": "phase_1_S1", "scenario_id": "S1"}
        ])

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "http_status": 200, "response_body": {"ueComms": [{"commDur": 10}]}}
        ])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            recovery_verified=True,
            config_params=self.config_params
        )

        self.assertFalse(dq_pass, "Unparseable event timestamp must fail data_quality_pass")
        self.assertTrue(any("timestamp event tidak valid" in r for r in dq_reasons))

    def test_neg_12_foreign_run_id_in_raw_polling_must_fail_data_quality(self):
        """NEG-12: Raw polling listing a foreign run_id from another experiment -> must fail data_quality_pass."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        create_fixture_telemetry(csv_path, self.run_id, [{
            "elapsed_sec": str(i),
            "ran_prb_cell1": 35.0,
            "nwdaf_comm_ul_bytes": 1000.0,
            "event_phase_id": "phase_1_S1",
            "event_scenario": "S1"
        } for i in range(35)])

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [{"phase_id": "phase_1_S1", "scenario_id": "S1"}])

        # JSONL contains record stamped with foreign run_id
        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "run_id": "FOREIGN_EXPERIMENT_999", "http_status": 200, "response_body": {"ueComms": [{"commDur": 10}]}}
        ])

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            recovery_verified=True,
            config_params=self.config_params
        )

        self.assertFalse(dq_pass, "Raw poll with foreign run_id must fail data_quality_pass")
        self.assertTrue(any("eksperimen lain" in r for r in dq_reasons))

    def test_neg_13_recovery_with_available_false_must_fail(self):
        """NEG-13: Recovery receiving partial parsing with available=False must not be verified as recovered."""
        from unittest.mock import patch
        partial_metrics = {
            "upf_backlog_embb": 0.0,
            "ran_prb_cell1": 35.0,
            "nwdaf_comm_freshness": 1,
            "available": False
        }
        with patch("run_pilot_experiment.fetch_live_metrics", return_value=partial_metrics):
            verified, evidence, reason = run_pilot_experiment.verify_recovery(
                unattended=True,
                timeout_sec=1.5,
                stability_sec=1.0,
                target_backlog=0.0,
                target_prb=40.0
            )
            self.assertFalse(verified, "available=False must not be verified even if values look nominal")
            self.assertIn("Recovery timeout", reason)

    def test_neg_14_interactive_recovery_rejects_negative_and_inf_inputs(self):
        """NEG-14: Interactive recovery inputs with -inf, inf, or negative values must be rejected."""
        from unittest.mock import patch
        
        # Test 1: -inf backlog input
        with patch("builtins.input", side_effect=["-inf", "35.0", "Grafana Panel 4", "5.0"]):
            verified, evidence, reason = run_pilot_experiment.verify_recovery(
                unattended=False,
                target_backlog=0.0,
                target_prb=40.0
            )
            self.assertFalse(verified, "Negative infinity input must be rejected")
            self.assertIn("tidak memenuhi syarat", reason)

        # Test 2: negative PRB input
        with patch("builtins.input", side_effect=["0.0", "-10.0", "Grafana Panel 4", "5.0"]):
            verified, evidence, reason = run_pilot_experiment.verify_recovery(
                unattended=False,
                target_backlog=0.0,
                target_prb=40.0
            )
            self.assertFalse(verified, "Negative PRB input must be rejected")
            self.assertIn("tidak memenuhi syarat", reason)

    def test_neg_15_archive_failure_counter_fails_quality_gate(self):
        """NEG-15: nwdaf_raw_polls_failed > 0 during run must fail data_quality_pass."""
        csv_path = os.path.join(self.run_dir, f"telemetry_{self.run_id}.csv")
        create_fixture_telemetry(csv_path, self.run_id, [{
            "elapsed_sec": str(i),
            "ran_prb_cell1": 35.0,
            "nwdaf_comm_ul_bytes": 1000.0,
            "event_phase_id": "phase_1_S1",
            "event_scenario": "S1"
        } for i in range(35)])

        events_path = os.path.join(self.run_dir, f"experiment_events_{self.run_id}.csv")
        create_fixture_events(events_path, self.run_id, [{"phase_id": "phase_1_S1", "scenario_id": "S1"}])

        jsonl_path = os.path.join(self.run_dir, "nwdaf_raw_poll_responses.jsonl")
        create_fixture_jsonl(jsonl_path, self.run_id, [
            {"poll_timestamp_utc": "2026-10-16T10:00:05Z", "http_status": 200, "response_body": {"ueComms": [{"commDur": 10}]}}
        ])

        # Exporter reports failure in archiving
        collector_metrics = {
            "nwdaf_raw_polls_total": 2,
            "nwdaf_raw_polls_written": 1,
            "nwdaf_raw_polls_failed": 1
        }

        dq_pass, tr_elig, summary, dq_reasons, tr_reasons = evaluate_run_dataset(
            run_dir=self.run_dir,
            run_id=self.run_id,
            planned_scenarios=["S1"],
            recovery_verified=True,
            config_params=self.config_params,
            collector_metrics=collector_metrics
        )

        self.assertFalse(dq_pass, "Collector failure counter > 0 must fail data_quality_pass")
        self.assertTrue(any("kegagalan penulisan arsip" in r for r in dq_reasons))


if __name__ == "__main__":
    unittest.main()
