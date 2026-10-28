"""Offline protocol checks for concurrent generation continuations."""
import copy
import json
import random
import threading

import pytest

from src.generation.comparison import canonical_sha256, text_sha256
from src.generation.concurrent_execution_v2 import execute_concurrent, remaining_after_concurrent


def fixture(n=8):
    bundles = []
    for i in range(n):
        prompt = f"synthetic-{i}"
        bundles.append({
            "question": {"question_id": f"Q{i}"},
            "modes": {"fixture": {
                "prompt": prompt,
                "prompt_sha256": text_sha256(prompt),
                "prompt_reference_tokens": 1,
                "context_key": "dual",
            }},
            "contexts": {"dual": {
                "context_sha256": text_sha256(""),
                "source_records_sha256": canonical_sha256([]),
                "reference_tokens": 0,
                "source_records": [],
            }},
        })
    plan = {
        "methods": ["fixture"], "repeats": 1, "randomization_seed": 42,
        "maximum_client_calls": n, "max_consecutive_failures": 3,
        "max_output_tokens": 16384, "temperature": 1,
        "request_timeout_seconds": 600,
    }
    schedule = [
        {"question_id": f"Q{i}", "mode": "fixture", "repeat_id": 1}
        for i in range(n)
    ]
    random.Random(42).shuffle(schedule)
    return bundles, plan, schedule


class Clients:
    def __init__(self, start_barrier=None):
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.created = 0
        self.calls = []
        self.start_barrier = start_barrier

    def factory(self):
        owner = self
        with owner.lock:
            owner.created += 1

        class Client:
            mock = False

            def chat(self, prompt):
                with owner.lock:
                    owner.active += 1
                    owner.peak = max(owner.peak, owner.active)
                    owner.calls.append(prompt)
                if owner.start_barrier is not None:
                    owner.start_barrier.wait(timeout=5)
                result = json.dumps({
                    "evaluation": prompt,
                    "claims": [],
                    "citations": [],
                    "overall_evidence_status": "insufficient",
                })
                self.last_request = {"prompt": prompt}
                self.last_raw_response = {"content": result}
                self.last_response_metadata = {
                    "mock": False, "finish_reason": "stop", "total_tokens": 3,
                }
                self.last_response_text = result
                with owner.lock:
                    owner.active -= 1
                return result

        return Client()


def test_twenty_workers_overlap_and_do_not_duplicate_units(tmp_path):
    bundles, plan, schedule = fixture(32)
    clients = Clients(start_barrier=threading.Barrier(8))
    result = execute_concurrent(
        bundles, schedule, tmp_path / "run", client_factory=clients.factory,
        validate=lambda *args: None, plan=plan, inherited_units=[], concurrency=20,
    )
    assert result["status"] == "completed"
    assert result["client_calls_returned"] == 32
    assert 8 <= clients.peak <= 20
    assert clients.created >= 8
    assert len(clients.calls) == len(set(clients.calls)) == 32


def test_chained_resume_accepts_reordering_but_rejects_unknown_requests():
    bundles, plan, schedule = fixture(12)
    serial = {
        "active_request": None, "client_calls_attempted": 3,
        "client_calls_returned": 3, "schedule": schedule, "units": schedule[:3],
    }
    concurrent = {
        "status": "stopped_by_control", "active_requests": [],
        "client_calls_attempted": 4, "client_calls_returned": 4,
        "schedule": schedule[3:], "units": list(reversed(schedule[3:7])),
    }
    assert remaining_after_concurrent(serial, concurrent, bundles, plan) == schedule[7:]

    altered = copy.deepcopy(concurrent)
    altered["active_requests"] = [{"unknown": True}]
    with pytest.raises(ValueError):
        remaining_after_concurrent(serial, altered, bundles, plan)

    altered = copy.deepcopy(concurrent)
    altered["units"][0] = schedule[9]
    with pytest.raises(ValueError):
        remaining_after_concurrent(serial, altered, bundles, plan)


def test_registered_drain_before_dispatch_makes_no_calls(tmp_path):
    bundles, plan, schedule = fixture(8)
    clients = Clients()
    control = tmp_path / "control.json"
    control.write_text(json.dumps({"action": "drain"}), encoding="utf-8")
    result = execute_concurrent(
        bundles, schedule, tmp_path / "run", client_factory=clients.factory,
        validate=lambda *args: None, plan=plan, inherited_units=[], concurrency=20,
        control_file=control,
    )
    assert result["status"] == "stopped_by_control"
    assert result["client_calls_attempted"] == 0
    assert clients.created == 0
    assert result["unattempted_units"] == 8


def test_rate_limits_reduce_concurrency_without_automatic_retry(tmp_path):
    bundles, plan, schedule = fixture(8)

    class Limit(Exception):
        status_code = 429

    class Client:
        mock = False

        def chat(self, prompt):
            raise Limit("synthetic quota")

    result = execute_concurrent(
        bundles, schedule, tmp_path / "run", client_factory=Client,
        validate=lambda *args: None, plan=plan, inherited_units=[], concurrency=20,
    )
    assert result["client_calls_returned"] == 8
    assert result["rate_limit_events"] == 8
    assert result["effective_concurrency"] == 1
    assert result["retries_in_this_run"] == 0
    assert result["status"] == "completed_with_failures"
