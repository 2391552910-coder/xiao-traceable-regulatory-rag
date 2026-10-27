"""Durable, no-retry journals for development requests and multi-call units.

The caller supplies the transport; this module never opens a network connection.
``transport_entered`` is conservative: an exception after that marker means that
remote execution is unknown, even when a local transport probably failed early.
Opening an existing call never sends it again. Use a new, explicitly identified
attempt path for a separately authorised retry instead of overwriting history.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable, Mapping, Sequence


TERMINAL_STATUSES = frozenset({
    "not_dispatched", "remote_unknown", "http_failed", "output_exhausted",
    "empty_answer", "parse_failed", "completed",
})
_SECRET_FIELDS = frozenset({
    "authorization", "proxy_authorization", "api_key", "apikey", "access_token",
    "refresh_token", "password", "secret", "client_secret",
})


class JournalInUseError(RuntimeError):
    """Another worker currently owns this request or unit journal."""


class JournalMismatchError(ValueError):
    """An existing path belongs to a different redacted request."""


@dataclass(frozen=True)
class TransportResult:
    """Optional adapter for a caller's curl/SDK transport result.

    None usage means unknown, rather than zero. A returned HTTP response is not
    by itself verification of provider billing or physical HTTP attempt counts.
    """

    http_status: int | None = None
    raw_response: Any = None
    text: str | None = None
    finish_reason: str | None = None
    usage: Mapping[str, Any] | None = None
    transport_exit_code: int | None = None
    provider_receipt_confirmed: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def redact(value: Any, secrets: Sequence[str] = ()) -> Any:
    """Return a JSON-safe copy with explicit secrets and credential fields hidden."""
    needles = sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True)

    def clean_string(text: str) -> str:
        for needle in needles:
            text = text.replace(needle, "[REDACTED]")
        text = re.sub(r"(?i)\bbearer\s+[^\s,;\"'<>]+", "Bearer [REDACTED]", text)
        return re.sub(
            r"(?i)([?&](?:api_key|apikey|access_token|token)=)[^&\s]+",
            r"\1[REDACTED]", text,
        )

    def visit(item: Any) -> Any:
        if isinstance(item, Mapping):
            result = {}
            for key, val in item.items():
                key = clean_string(str(key))
                normal = key.lower().replace("-", "_")
                result[key] = "[REDACTED]" if normal in _SECRET_FIELDS and val is not None else visit(val)
            return result
        if isinstance(item, (list, tuple)):
            return [visit(x) for x in item]
        if isinstance(item, str):
            return clean_string(item)
        if item is None or isinstance(item, (bool, int, float)):
            return item
        return clean_string(str(item))

    return visit(value)


def _encoded(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def atomic_write_json(path: str | Path, value: Any, *, secrets: Sequence[str] = ()) -> None:
    """Flush a unique temporary file, then replace the JSON snapshot atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _encoded(redact(value, secrets))
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def event_path(path: str | Path) -> Path:
    return Path(path).with_suffix(".events.jsonl")


def append_event(path: str | Path, event: Mapping[str, Any], *, secrets: Sequence[str] = ()) -> None:
    """Append and fsync one event. Existing events are never rewritten."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(redact(event, secrets), ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    with path.open("ab+") as stream:
        # Preserve a killed writer's partial line as a separate line, never join
        # the next event to it. The snapshot remains the recovery authority.
        stream.seek(0, os.SEEK_END)
        if stream.tell():
            stream.seek(-1, os.SEEK_END)
            if stream.read(1) != b"\n":
                stream.write(b"\n")
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def _locked(path: Path):
    """OS-owned lock: a killed process releases it without deleting history."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if not stream.tell():
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise JournalInUseError(f"Journal is owned by another worker: {path.name}") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _persist(path: Path, record: dict, event: str, secrets: Sequence[str]) -> dict:
    record["updated_at_utc"] = _now()
    record = redact(record, secrets)
    atomic_write_json(path, record)
    append_event(event_path(path), {
        "event": event, "at_utc": record["updated_at_utc"],
        "status": record["status"], "terminal": record["terminal"],
        "snapshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    })
    return record


def _load(path: Path) -> dict:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("Journal snapshot must be a JSON object")
    return value


def _recover_locked(path: Path, secrets: Sequence[str]) -> dict:
    record = _load(path)
    if record.get("terminal"):
        return record
    entered = bool(record.get("transport_entered")) or record.get("status") == "transport_entered"
    returned = bool(record.get("response_returned_at_utc"))
    status = (_response_failure(record) or "parse_failed") if returned else "remote_unknown" if entered else "not_dispatched"
    record.update(status=status, terminal=True,
                  failure_reason="response_saved_but_validation_interrupted" if returned else "interrupted_journal_recovered_without_redispatch",
                  remote_execution_known=status not in {"remote_unknown", "http_failed"},
                  automatic_retry=False, finished_at_utc=_now())
    return _persist(path, record, "request_recovered", secrets)


def recover_request(path: str | Path, *, secrets: Sequence[str] = ()) -> dict:
    """Close an abandoned request conservatively; never invoke a transport."""
    path = Path(path)
    with _locked(path):
        return _recover_locked(path, secrets)


def _normalise_transport(value: TransportResult | Mapping[str, Any]) -> TransportResult:
    if isinstance(value, TransportResult):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("Transport must return TransportResult or a mapping")
    raw = value.get("raw_response", value.get("response"))
    text, finish, usage = value.get("text"), value.get("finish_reason"), value.get("usage")
    if isinstance(raw, Mapping):
        usage = raw.get("usage") if usage is None else usage
        choices = raw.get("choices") or []
        if choices and isinstance(choices[0], Mapping):
            finish = choices[0].get("finish_reason") if finish is None else finish
            message = choices[0].get("message") or {}
            if text is None and isinstance(message, Mapping):
                text = message.get("content")
    status = value.get("http_status")
    status = int(status) if isinstance(status, (int, str)) and not isinstance(status, bool) and str(status).isdigit() else None
    if status == 0:
        status = None
    return TransportResult(
        http_status=status, raw_response=raw, text=text, finish_reason=finish,
        usage=usage if isinstance(usage, Mapping) else None,
        transport_exit_code=value.get("transport_exit_code", value.get("curl_exit")),
        provider_receipt_confirmed=value.get("provider_receipt_confirmed") is True,
    )


def _response_failure(record: Mapping[str, Any]) -> str | None:
    status = record.get("http_status")
    if status is not None and not 200 <= status < 300:
        return "http_failed"
    if record.get("transport_exit_code") not in (None, 0) or status is None:
        return "remote_unknown"
    if record.get("finish_reason") in {"length", "max_tokens", "max_output_tokens"}:
        return "output_exhausted"
    if not isinstance(record.get("text"), str) or not record["text"].strip():
        return "empty_answer"
    return None


def journaled_request(
    path: str | Path,
    request: Mapping[str, Any],
    transport: Callable[[Mapping[str, Any]], TransportResult | Mapping[str, Any]],
    *, parser: Callable[[str], Any] | None = None,
    validator: Callable[[Any], Any] | None = None,
    before_dispatch: Callable[[Mapping[str, Any]], Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    secrets: Sequence[str] = (),
) -> dict:
    """Execute once, durably classify the outcome, and preserve failures.

    Ordinary transport/parser exceptions return terminal records. Interrupts and
    SystemExit are journaled before propagating. Reopening any existing record
    reads or recovers it and never calls ``transport`` again.
    """
    path = Path(path)
    safe_request = redact(dict(request), secrets)
    digest = hashlib.sha256(_encoded(safe_request)).hexdigest()
    with _locked(path):
        if path.exists():
            existing = _load(path)
            if existing.get("request_sha256") != digest:
                raise JournalMismatchError("Existing journal has a different request")
            return _recover_locked(path, secrets)
        started = time.perf_counter()
        record = {
            "schema_version": "development-request-journal-v1",
            "record_kind": "request", "status": "request_started", "terminal": False,
            "request": safe_request, "request_sha256": digest,
            "metadata": dict(metadata or {}), "started_at_utc": _now(),
            "transport_entered": False, "provider_receipt_confirmed": False,
            "physical_http_request_count_verified": False, "automatic_retry": False,
            "usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None},
        }
        record = _persist(path, record, "request_started", secrets)
        try:
            if before_dispatch is not None:
                before_dispatch(request)
            record.update(status="transport_entered", transport_entered=True, transport_entered_at_utc=_now())
            record = _persist(path, record, "transport_entered", secrets)
            value = transport(request)
            response = _normalise_transport(value)
            record.update(
                status="transport_returned",
                http_status=response.http_status, raw_response=response.raw_response,
                text=response.text, finish_reason=response.finish_reason,
                transport_exit_code=response.transport_exit_code,
                provider_receipt_confirmed=response.provider_receipt_confirmed,
                response_returned_at_utc=_now(),
                http_response_received=response.http_status is not None,
                usage={**record["usage"], **dict(response.usage or {})},
            )
            # Preserve raw response and reported usage before potentially slow
            # parsing/validation; a killed validator must not lose this receipt.
            record = _persist(path, record, "transport_returned", secrets)
            failure = _response_failure(record)
            if failure:
                record["status"] = failure
            elif response.finish_reason not in {"stop", "eos"}:
                record.update(status="parse_failed", error_type="UnexpectedFinishReason",
                              error="No completed answer finish reason was reported")
            else:
                try:
                    parsed = parser(response.text) if parser is not None else response.text
                    if validator is not None:
                        validator(parsed)
                    record.update(status="completed", parsed=parsed)
                except Exception as exc:
                    record.update(status="parse_failed", error_type=type(exc).__name__, error=str(exc))
            record["remote_execution_known"] = record["status"] not in {"remote_unknown", "http_failed"}
        except BaseException as exc:
            exception_status = getattr(exc, "status_code", None)
            exception_response = getattr(exc, "response", None)
            if exception_status is None:
                exception_status = getattr(exception_response, "status_code", None)
            has_http_error = type(exception_status) is int and 100 <= exception_status <= 599
            returned = bool(record.get("response_returned_at_utc"))
            status = (_response_failure(record) or "parse_failed") if returned else ("http_failed" if has_http_error else "remote_unknown") if record["transport_entered"] else "not_dispatched"
            record.update(
                status=status,
                error_type=type(exc).__name__, error=str(exc),
                remote_execution_known=status not in {"remote_unknown", "http_failed"},
            )
            if record["transport_entered"] and has_http_error:
                record.update(http_status=exception_status, http_response_received=True,
                              raw_response=exception_response if isinstance(exception_response, Mapping) else getattr(exc, "body", getattr(exception_response, "text", None)))
            record.update(terminal=True, elapsed_seconds=time.perf_counter() - started, finished_at_utc=_now())
            record = _persist(path, record, "request_interrupted" if not isinstance(exc, Exception) else "request_failed", secrets)
            if not isinstance(exc, Exception):
                raise
            return record
        record.update(terminal=True, elapsed_seconds=time.perf_counter() - started, finished_at_utc=_now())
        return _persist(path, record, "request_returned", secrets)


class UnitJournal:
    """Small multi-call unit context manager; failures also become terminal.

    ``run_call`` registers each child path before dispatch. Existing unit paths
    are rejected rather than executed again; use ``recover_unit`` after a crash.
    Unit status retains the established completed/failed convention, while each
    request keeps its more precise failure classification.
    """

    def __init__(self, path: str | Path, *, metadata: Mapping[str, Any] | None = None,
                 secrets: Sequence[str] = (), expected_calls: int | None = None):
        if expected_calls is not None and (type(expected_calls) is not int or expected_calls < 1):
            raise ValueError("expected_calls must be a positive integer")
        self.path, self.metadata, self.secrets = Path(path), dict(metadata or {}), secrets
        self.expected_calls = expected_calls
        self.record: dict = {}
        self._lock = None

    def __enter__(self):
        self._lock = _locked(self.path)
        self._lock.__enter__()
        try:
            if self.path.exists():
                raise FileExistsError("Never overwrite or automatically rerun an existing unit")
            self.record = dict(schema_version="development-unit-journal-v1", record_kind="unit",
                               metadata=self.metadata, status="running", terminal=False,
                               started_at_utc=_now(), calls=[], expected_calls=self.expected_calls,
                               automatic_retry=False)
            self.record = _persist(self.path, self.record, "unit_started", self.secrets)
        except BaseException:
            self._lock.__exit__(None, None, None)
            raise
        return self

    def run_call(self, path: str | Path, request: Mapping[str, Any], transport: Callable, **kwargs) -> dict:
        if self.record.get("terminal"):
            raise RuntimeError("Unit is already terminal")
        path = Path(path).resolve()
        if any(c["path"] == str(path) for c in self.record["calls"]):
            raise ValueError("Duplicate request path within a unit")
        self.record["calls"].append(dict(path=str(path), status="registered"))
        self.record = _persist(self.path, self.record, "unit_call_registered", self.secrets)
        record = journaled_request(path, request, transport, secrets=self.secrets, **kwargs)
        self.record["calls"][-1].update(status=record["status"], sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.record = _persist(self.path, self.record, "unit_call_returned", self.secrets)
        return record

    def finish(self, result: Any = None) -> dict:
        if self.record.get("terminal"):
            return self.record
        calls = self.record["calls"]
        complete = bool(calls) and all(c["status"] == "completed" for c in calls)
        if self.expected_calls is not None:
            complete = complete and len(calls) == self.expected_calls
        self.record.update(status="completed" if complete else "failed", terminal=True,
                           result=result, finished_at_utc=_now())
        if not complete:
            self.record["failure_reason"] = "failed_or_missing_required_request"
        self.record = _persist(self.path, self.record, "unit_finished", self.secrets)
        return self.record

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc is None:
                self.finish()
            elif not self.record.get("terminal"):
                self.record.update(status="failed", terminal=True, error_type=type(exc).__name__,
                                   error=str(exc), failure_reason="unit_operation_interrupted",
                                   finished_at_utc=_now())
                for call in self.record["calls"]:
                    path = Path(call["path"])
                    if path.exists():
                        child = recover_request(path, secrets=self.secrets)
                        call["status"] = child["status"]
                        call["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    else:
                        call["status"] = "not_dispatched"
                self.record = _persist(self.path, self.record, "unit_failed", self.secrets)
        finally:
            self._lock.__exit__(exc_type, exc, tb)
        return False


def recover_unit(path: str | Path, *, secrets: Sequence[str] = ()) -> dict:
    """Finalize an interrupted unit and its saved requests without rerunning it."""
    path = Path(path)
    with _locked(path):
        record = _load(path)
        if record.get("terminal"):
            return record
        for call in record.get("calls", []):
            child_path = Path(call["path"])
            if child_path.exists():
                child = recover_request(child_path, secrets=secrets)
                call.update(status=child["status"], sha256=hashlib.sha256(child_path.read_bytes()).hexdigest())
            else:
                call["status"] = "not_dispatched"
        record.update(status="failed", terminal=True, automatic_retry=False,
                      failure_reason="interrupted_unit_recovered_without_redispatch",
                      finished_at_utc=_now())
        return _persist(path, record, "unit_recovered", secrets)
