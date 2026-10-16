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


if __name__ == "__main__":
    unittest.main()
