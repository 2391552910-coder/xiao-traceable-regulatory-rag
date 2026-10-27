"""Failure injection only: these checks never use a model or network."""
import json
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from src.generation.request_journal import (
    JournalInUseError, JournalMismatchError, TransportResult, UnitJournal,
    atomic_write_json, event_path, journaled_request, recover_request, recover_unit,
)


REQUEST = {"model": "fixture", "messages": [{"role": "user", "content": "source fixture"}]}


def response(text='{"answer":1}', *, code=200, finish="stop", usage=None, curl_exit=0):
    return {"http_status": str(code), "curl_exit": curl_exit, "response": {
        "choices": [{"message": {"content": text}, "finish_reason": finish}], "usage": usage,
    }}


def events(path):
    return [json.loads(x) for x in event_path(path).read_text(encoding="utf-8").splitlines()]


def test_start_and_transport_markers_are_durable_before_callback(tmp_path):
    path = tmp_path / "call.json"
    def before(request):
        record = json.loads(path.read_bytes())
        assert record["status"] == "request_started" and not record["transport_entered"]
        assert events(path)[-1]["event"] == "request_started"
    def transport(request):
        assert request == REQUEST
        record = json.loads(path.read_bytes())
        assert record["status"] == "transport_entered" and not record["terminal"]
        assert [e["event"] for e in events(path)] == ["request_started", "transport_entered"]
        return response(usage={"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6})
    record = journaled_request(path, REQUEST, transport, before_dispatch=before, parser=json.loads)
    assert record["status"] == "completed" and record["terminal"]
    assert record["parsed"] == {"answer": 1}
    assert record["usage"]["total_tokens"] == 6
    assert record["raw_response"]["choices"][0]["message"]["content"] == '{"answer":1}'
    assert not record["provider_receipt_confirmed"] and not record["automatic_retry"]


@pytest.mark.parametrize("value,status", [
    (response(code=502), "http_failed"),
    (response(text="", finish="length"), "output_exhausted"),
    (response(text="   "), "empty_answer"),
    (response(text="not JSON"), "parse_failed"),
    (response(finish="content_filter"), "parse_failed"),
    (response(code="000", curl_exit=28), "remote_unknown"),
    (response(curl_exit=28), "remote_unknown"),
])
def test_outcomes_are_terminal_without_fabricating_usage(tmp_path, value, status):
    path = tmp_path / "call.json"
    record = journaled_request(path, REQUEST, lambda _: value, parser=json.loads)
    assert record["status"] == status and record["terminal"]
    assert record["usage"] == {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}
    assert json.loads(path.read_bytes()) == record
    assert events(path)[-1]["terminal"]


def test_zero_usage_is_preserved_and_not_confused_with_unknown(tmp_path):
    record = journaled_request(tmp_path / "call.json", REQUEST,
        lambda _: response(usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}))
    assert record["usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


@pytest.mark.parametrize("preflight,status", [(True, "not_dispatched"), (False, "remote_unknown")])
def test_exception_classifies_dispatch_conservatively(tmp_path, preflight, status):
    count = []
    def error(_):
        raise OSError("injected launch/transport failure")
    def transport(_):
        count.append(1)
        return error(_)
    record = journaled_request(tmp_path / "call.json", REQUEST, transport,
        before_dispatch=error if preflight else None)
    assert record["status"] == status and record["terminal"]
    assert len(count) == int(not preflight)


def test_http_error_exception_preserves_status_without_claiming_provider_execution(tmp_path):
    class HTTPError(Exception):
        status_code = 502
        body = {"error": "gateway fixture"}
    def transport(_):
        raise HTTPError("fixture")
    record = journaled_request(tmp_path / "call.json", REQUEST, transport)
    assert record["status"] == "http_failed" and record["http_status"] == 502
    assert record["raw_response"] == {"error": "gateway fixture"}
    assert not record["remote_execution_known"]


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_interrupt_is_saved_before_it_is_propagated(tmp_path, interrupt):
    path = tmp_path / "call.json"
    def transport(_):
        raise interrupt("simulated interruption")
    with pytest.raises(interrupt):
        journaled_request(path, REQUEST, transport)
    record = json.loads(path.read_bytes())
    assert record["status"] == "remote_unknown" and record["terminal"]
    assert record["error_type"] == interrupt.__name__
    assert events(path)[-1]["event"] == "request_interrupted"


def test_parser_or_validator_failure_is_not_an_http_failure(tmp_path):
    def invalid(_):
        raise ValueError("required field missing")
    record = journaled_request(tmp_path / "call.json", REQUEST, lambda _: response(),
        parser=json.loads, validator=invalid)
    assert record["status"] == "parse_failed" and record["http_status"] == 200
    assert record["text"] == '{"answer":1}'


def test_duplicate_path_reuses_terminal_record_but_rejects_other_request(tmp_path):
    path = tmp_path / "call.json"; calls = []
    def transport(_):
        calls.append(1)
        return response()
    first = journaled_request(path, REQUEST, transport)
    before = path.read_bytes(), event_path(path).read_bytes()
    assert journaled_request(path, REQUEST, transport) == first
    assert len(calls) == 1 and before == (path.read_bytes(), event_path(path).read_bytes())
    with pytest.raises(JournalMismatchError):
        journaled_request(path, {**REQUEST, "model": "different"}, transport)
    assert len(calls) == 1


@pytest.mark.parametrize("entered,status", [(False, "not_dispatched"), (True, "remote_unknown")])
def test_reopening_incomplete_record_closes_it_without_redispatch(tmp_path, entered, status):
    path = tmp_path / "call.json"
    record = journaled_request(path, REQUEST, lambda _: response())
    record.update(terminal=False, status="transport_entered" if entered else "request_started", transport_entered=entered)
    record.pop("response_returned_at_utc")
    atomic_write_json(path, record)
    def forbidden(_):
        pytest.fail("Recovered request must never be resent")
    recovered = journaled_request(path, REQUEST, forbidden)
    assert recovered["status"] == status and recovered["terminal"]
    assert recovered["failure_reason"] == "interrupted_journal_recovered_without_redispatch"
    assert recover_request(path) == recovered


def test_active_worker_cannot_be_recovered_or_dispatched_by_second_worker(tmp_path):
    path = tmp_path / "call.json"; entered = threading.Event(); release = threading.Event()
    def transport(_):
        entered.set()
        assert release.wait(5)
        return response()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(journaled_request, path, REQUEST, transport)
        assert entered.wait(5)
        try:
            with pytest.raises(JournalInUseError):
                recover_request(path)
            with pytest.raises(JournalInUseError):
                journaled_request(path, REQUEST, lambda _: response())
        finally:
            release.set()
        assert future.result()["status"] == "completed"


def test_request_response_metadata_and_errors_are_redacted_without_changing_transport(tmp_path):
    path = tmp_path / "call.json"; secret = 'fixture-secret-\\"-123'
    request = {**REQUEST, "headers": {"Authorization": "Bearer hidden-header", "api_key": secret},
               "note": secret, "url": "https://fixture.invalid?token=hidden-query"}
    def transport(raw):
        assert raw["headers"]["api_key"] == secret
        return TransportResult(http_status=200, text='{"note":"Bearer hidden-output"}',
            finish_reason="stop", raw_response={"echo": secret, "access_token": "hidden-body"})
    record = journaled_request(path, request, transport, metadata={"echo": secret}, secrets=[secret])
    text = path.read_text(encoding="utf-8") + event_path(path).read_text(encoding="utf-8")
    assert not any(s in text for s in [secret, "hidden-header", "hidden-query", "hidden-output", "hidden-body"])
    assert record["request"]["headers"]["api_key"] == "[REDACTED]"
    failed = journaled_request(tmp_path / "failed.json", REQUEST,
        lambda _: (_ for _ in ()).throw(OSError(secret)), secrets=[secret])
    assert secret not in failed["error"]


def test_unit_is_terminal_with_linked_call_records_and_result(tmp_path):
    path = tmp_path / "unit.json"
    with UnitJournal(path, metadata={"question_id": "fixture"}, expected_calls=2) as unit:
        for i in range(2):
            unit.run_call(tmp_path / f"call{i}.json", REQUEST, lambda _: response(), parser=json.loads)
        unit.finish(result={"answer": 1})
    record = json.loads(path.read_bytes())
    assert record["status"] == "completed" and record["terminal"]
    assert record["result"] == {"answer": 1} and len(record["calls"]) == 2
    with pytest.raises(FileExistsError):
        with UnitJournal(path):
            pytest.fail("Existing unit body must not run")


def test_unit_marks_missing_required_calls_as_failed(tmp_path):
    with UnitJournal(tmp_path / "unit.json", expected_calls=2) as unit:
        unit.run_call(tmp_path / "call.json", REQUEST, lambda _: response())
    assert unit.record["status"] == "failed" and unit.record["terminal"]


def test_unit_records_interrupted_child_and_recovery_does_not_rerun(tmp_path):
    path = tmp_path / "unit.json"
    with pytest.raises(KeyboardInterrupt):
        with UnitJournal(path, expected_calls=1) as unit:
            unit.run_call(tmp_path / "call.json", REQUEST,
                lambda _: (_ for _ in ()).throw(KeyboardInterrupt("fixture")))
    record = json.loads(path.read_bytes())
    assert record["status"] == "failed" and record["terminal"]
    assert record["calls"][0]["status"] == "remote_unknown"
    assert recover_unit(path) == record


def test_abandoned_unit_recovers_child_and_missing_call_without_inference(tmp_path):
    call = tmp_path / "call.json"
    child = journaled_request(call, REQUEST, lambda _: response())
    child.update(status="transport_entered", terminal=False, transport_entered=True)
    child.pop("response_returned_at_utc")
    atomic_write_json(call, child)
    path = tmp_path / "unit.json"
    atomic_write_json(path, {"status": "running", "terminal": False,
        "calls": [{"path": str(call)}, {"path": str(tmp_path / "never.json")}]})
    record = recover_unit(path)
    assert record["status"] == "failed" and record["terminal"]
    assert [c["status"] for c in record["calls"]] == ["remote_unknown", "not_dispatched"]


def test_response_is_saved_before_parser_interrupts(tmp_path):
    path = tmp_path / "call.json"
    def interrupted_parser(_):
        saved = json.loads(path.read_bytes())
        assert saved["status"] == "transport_returned" and not saved["terminal"]
        assert saved["usage"]["total_tokens"] == 6
        assert saved["raw_response"]["choices"]
        assert events(path)[-1]["event"] == "transport_returned"
        raise KeyboardInterrupt("local parsing interrupted after receipt")
    with pytest.raises(KeyboardInterrupt):
        journaled_request(path, REQUEST, lambda _: response(usage={"total_tokens": 6}), parser=interrupted_parser)
    saved = json.loads(path.read_bytes())
    assert saved["status"] == "parse_failed" and saved["terminal"]
    assert saved["usage"]["total_tokens"] == 6 and saved["remote_execution_known"]


def test_recovery_after_saved_response_retains_usage_and_does_not_reinfer(tmp_path):
    path = tmp_path / "call.json"
    saved = journaled_request(path, REQUEST, lambda _: response(usage={"total_tokens": 6}))
    saved.update(status="transport_returned", terminal=False)
    atomic_write_json(path, saved)
    recovered = recover_request(path)
    assert recovered["status"] == "parse_failed" and recovered["terminal"]
    assert recovered["failure_reason"] == "response_saved_but_validation_interrupted"
    assert recovered["usage"]["total_tokens"] == 6 and recovered["raw_response"] == saved["raw_response"]
