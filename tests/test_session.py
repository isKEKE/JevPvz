"""Fixed-input regression for the target session guard and reverification cycles."""

import unittest
from unittest.mock import patch

import runtime.session as session_module
from configs.pvz_1051 import TARGET_IDENTITY
from runtime.memory import MemoryAccessError, ProcessExitedError
from runtime.process import (
    AmbiguousTargetError,
    IdentityMismatchError,
    ProcessDiscoveryError,
    ProcessInfo,
    ProcessIdentity,
    TargetNotRunningError,
)
from runtime.session import TargetSession


PATH = str(TARGET_IDENTITY["path"])


def _process(pid: int) -> ProcessInfo:
    return ProcessInfo(pid=pid, executable_path=PATH)


def _identity(pid: int) -> ProcessIdentity:
    return ProcessIdentity(
        pid=pid,
        executable_path=PATH,
        file_version="1.0.0.1051",
        pe_machine=0x014C,
        sha256="B" * 64,
    )


class FakeClock:
    def __init__(self, start: float = 0.0):
        self.now = start

    def __call__(self) -> float:
        return self.now


class FakeMemory:
    def __init__(self, pid: int):
        self.pid = int(pid)
        self.closed = 0

    def close(self) -> None:
        self.closed += 1


class FakeMemoryFactory:
    def __init__(self):
        self.calls = 0
        self.instances: list[FakeMemory] = []

    def __call__(self, pid: int) -> FakeMemory:
        self.calls += 1
        memory = FakeMemory(pid)
        self.instances.append(memory)
        return memory


class UtcStub:
    def __init__(self):
        self.count = 0

    def __call__(self) -> str:
        self.count += 1
        return f"2026-01-01T00:00:00.{self.count:03d}Z"


class Harness:
    """Injectable collaborators that count calls and can raise on demand."""

    def __init__(self, pid: int = 4242):
        self.clock = FakeClock()
        self.pid = pid
        self.resolver_calls = 0
        self.verifier_calls = 0
        self.module_base_calls = 0
        self.snapshot_calls = 0
        self.resolver_pid = pid
        self.resolver_error: type[Exception] | None = None
        self.verifier_error: type[Exception] | None = None
        self.module_base_error: type[Exception] | None = None
        self.snapshot_error: type[Exception] | None = None
        self.memory_factory = FakeMemoryFactory()
        self.raw = {"captured_at_utc": "raw"}
        self.session = TargetSession(
            clock=self.clock,
            resolver=self._resolver,
            verifier=self._verifier,
            module_base_reader=self._module_base,
            memory_factory=self.memory_factory,
            snapshot_reader=self._snapshot,
        )

    def _resolver(self, path):
        self.resolver_calls += 1
        if self.resolver_error is not None:
            raise self.resolver_error("resolver failed")
        return _process(self.resolver_pid)

    def _verifier(self, process, identity):
        self.verifier_calls += 1
        if self.verifier_error is not None:
            raise self.verifier_error("verifier failed")
        return _identity(process.pid)

    def _module_base(self, pid, path):
        self.module_base_calls += 1
        if self.module_base_error is not None:
            raise self.module_base_error("guard failed")
        return 0x400000

    def _snapshot(self, memory, module_base):
        self.snapshot_calls += 1
        if self.snapshot_error is not None:
            raise self.snapshot_error("read failed")
        return dict(self.raw)


class TargetSessionGuardTests(unittest.TestCase):
    def test_construction_does_not_resolve(self):
        harness = Harness()
        self.assertEqual(harness.resolver_calls, 0)
        self.assertEqual(harness.verifier_calls, 0)
        self.assertEqual(harness.memory_factory.calls, 0)
        self.assertIsNone(harness.session.identity_verified_at_utc)

    def test_call_count_matrix_over_fixed_sample_series(self):
        harness = Harness()
        harness.session.read()  # establish at t=0
        self.assertEqual(
            (harness.resolver_calls, harness.verifier_calls, harness.module_base_calls, harness.snapshot_calls),
            (1, 1, 1, 1),
        )

        for now in (0.25, 0.5, 0.75):  # steady state: no enumeration or disk verification
            harness.clock.now = now
            harness.session.read()
        self.assertEqual(
            (harness.resolver_calls, harness.verifier_calls, harness.module_base_calls, harness.snapshot_calls),
            (1, 1, 4, 4),
        )

        harness.clock.now = 1.0  # crosses exactly one 1 s identity boundary
        harness.session.read()
        self.assertEqual(
            (harness.resolver_calls, harness.verifier_calls, harness.module_base_calls, harness.snapshot_calls),
            (1, 2, 5, 5),
        )

        for now in (1.25, 1.5):
            harness.clock.now = now
            harness.session.read()
        self.assertEqual(
            (harness.resolver_calls, harness.verifier_calls, harness.module_base_calls, harness.snapshot_calls),
            (1, 2, 7, 7),
        )

        harness.clock.now = 30.0  # crosses exactly one 30 s uniqueness boundary
        harness.session.read()
        self.assertEqual(
            (harness.resolver_calls, harness.verifier_calls, harness.module_base_calls, harness.snapshot_calls),
            (2, 3, 8, 8),
        )

    def test_source_keys_and_verified_timestamp(self):
        harness = Harness()
        _, source = harness.session.read()
        expected = set(_identity(harness.pid).as_dict())
        expected.update({"profile", "exe_sha256", "identity_verified_at_utc"})
        self.assertEqual(set(source), expected)
        self.assertEqual(source["exe_sha256"], "B" * 64)
        self.assertEqual(source["identity_verified_at_utc"], harness.session.identity_verified_at_utc)

    def test_identity_verified_at_utc_tracks_latest_successful_verification(self):
        harness = Harness()
        with patch.object(session_module, "utc_now", UtcStub()):
            _, first = harness.session.read()
            self.assertEqual(first["identity_verified_at_utc"], "2026-01-01T00:00:00.001Z")

            harness.clock.now = 1.0
            _, second = harness.session.read()
            self.assertEqual(second["identity_verified_at_utc"], "2026-01-01T00:00:00.002Z")

            harness.clock.now = 1.5
            _, third = harness.session.read()
            self.assertEqual(third["identity_verified_at_utc"], "2026-01-01T00:00:00.002Z")


class TargetSessionFailureTests(unittest.TestCase):
    def test_guard_failure_invalidates_and_reestablishes(self):
        harness = Harness()
        harness.session.read()
        harness.module_base_error = ProcessDiscoveryError
        with self.assertRaises(ProcessDiscoveryError):
            harness.session.read()
        self.assertEqual(harness.memory_factory.instances[0].closed, 1)

        harness.module_base_error = None
        resolver_before = harness.resolver_calls
        verifier_before = harness.verifier_calls
        harness.session.read()
        self.assertEqual(harness.resolver_calls, resolver_before + 1)
        self.assertEqual(harness.verifier_calls, verifier_before + 1)
        self.assertEqual(len(harness.memory_factory.instances), 2)

    def test_guard_process_exit_invalidates(self):
        harness = Harness()
        harness.session.read()
        harness.module_base_error = ProcessExitedError
        with self.assertRaises(ProcessExitedError):
            harness.session.read()
        self.assertEqual(harness.memory_factory.instances[0].closed, 1)

    def test_reverification_failure_invalidates_and_reestablishes(self):
        harness = Harness()
        harness.session.read()
        harness.verifier_error = IdentityMismatchError
        harness.clock.now = 1.0
        with self.assertRaises(IdentityMismatchError):
            harness.session.read()
        self.assertEqual(harness.memory_factory.instances[0].closed, 1)

        harness.verifier_error = None
        resolver_before = harness.resolver_calls
        verifier_before = harness.verifier_calls
        harness.session.read()
        self.assertEqual(harness.resolver_calls, resolver_before + 1)
        self.assertEqual(harness.verifier_calls, verifier_before + 1)

    def test_uniqueness_resolution_failure_invalidates_and_reestablishes(self):
        harness = Harness()
        harness.session.read()
        harness.resolver_error = AmbiguousTargetError
        harness.clock.now = 30.0
        with self.assertRaises(AmbiguousTargetError):
            harness.session.read()
        self.assertEqual(harness.memory_factory.instances[0].closed, 1)

        harness.resolver_error = None
        resolver_before = harness.resolver_calls
        verifier_before = harness.verifier_calls
        harness.session.read()
        self.assertEqual(harness.resolver_calls, resolver_before + 1)
        self.assertEqual(harness.verifier_calls, verifier_before + 1)

    def test_data_read_failure_does_not_invalidate(self):
        harness = Harness()
        harness.session.read()
        harness.snapshot_error = MemoryAccessError
        with self.assertRaises(MemoryAccessError):
            harness.session.read()
        self.assertEqual(harness.memory_factory.instances[0].closed, 0)

        harness.snapshot_error = None
        resolver_before = harness.resolver_calls
        verifier_before = harness.verifier_calls
        harness.session.read()
        self.assertEqual(harness.resolver_calls, resolver_before)
        self.assertEqual(harness.verifier_calls, verifier_before)
        self.assertEqual(harness.memory_factory.calls, 1)


class TargetSessionFailClosedTests(unittest.TestCase):
    def test_second_resolution_with_a_different_pid_fails_closed(self):
        harness = Harness()
        harness.session.read()
        harness.resolver_pid = 9999
        harness.clock.now = 30.0
        with self.assertRaises(IdentityMismatchError):
            harness.session.read()
        self.assertEqual(harness.snapshot_calls, 1)

    def test_ambiguous_and_missing_targets_fail_closed(self):
        for error in (AmbiguousTargetError, TargetNotRunningError):
            harness = Harness()
            harness.resolver_error = error
            with self.assertRaises(error):
                harness.session.read()
            self.assertEqual(harness.snapshot_calls, 0)
            self.assertEqual(harness.memory_factory.calls, 0)

    def test_guard_main_module_path_change_fails_closed(self):
        harness = Harness()
        harness.module_base_error = IdentityMismatchError
        with self.assertRaises(IdentityMismatchError):
            harness.session.read()
        self.assertEqual(harness.snapshot_calls, 0)

    def test_verifier_digest_mismatch_fails_closed(self):
        harness = Harness()
        harness.verifier_error = IdentityMismatchError
        with self.assertRaises(IdentityMismatchError):
            harness.session.read()
        self.assertEqual(harness.snapshot_calls, 0)
        self.assertEqual(harness.memory_factory.calls, 0)


if __name__ == "__main__":
    unittest.main()
