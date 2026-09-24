import struct
import unittest
from pathlib import Path

from runtime.memory import (
    ClosedMemoryError,
    NullPointerError,
    ProcessExitedError,
    ReadOnlyMemory,
    ShortReadError,
    ensure_process_active,
    follow_ptr32,
    read_f32,
    read_i32,
    read_ptr32,
    read_u32,
)
from runtime.process import IdentityMismatchError, ProcessInfo, verify_target_identity


class FakeMemory:
    def __init__(self):
        self.bytes = {}

    def put(self, address, value):
        for offset, byte in enumerate(value):
            self.bytes[address + offset] = byte

    def read_bytes(self, address, size):
        try:
            return bytes(self.bytes[address + offset] for offset in range(size))
        except KeyError as exc:
            received = sum(address + offset in self.bytes for offset in range(size))
            raise ShortReadError(address, size, received) from exc

    def read_u32(self, address):
        return read_u32(self, address)


class MemoryPrimitiveTests(unittest.TestCase):
    def setUp(self):
        self.memory = FakeMemory()

    def test_reads_little_endian_scalars_and_32_bit_pointers(self):
        self.memory.put(0x1000, struct.pack("<I", 0x89ABCDEF))
        self.memory.put(0x1004, struct.pack("<i", -42))
        self.memory.put(0x1008, struct.pack("<f", 13.25))

        self.assertEqual(read_u32(self.memory, 0x1000), 0x89ABCDEF)
        self.assertEqual(read_ptr32(self.memory, 0x1000), 0x89ABCDEF)
        self.assertEqual(read_i32(self.memory, 0x1004), -42)
        self.assertEqual(read_f32(self.memory, 0x1008), 13.25)

    def test_follows_pointer_chain_with_four_byte_remote_pointers(self):
        self.memory.put(0x2000, struct.pack("<I", 0x12340000))
        self.memory.put(0x12340010, struct.pack("<I", 0x76540000))

        self.assertEqual(follow_ptr32(self.memory, 0x2000, (0x10,)), 0x76540000)

    def test_null_pointer_and_short_read_are_distinct_failures(self):
        self.memory.put(0x3000, struct.pack("<I", 0))
        with self.assertRaises(NullPointerError):
            follow_ptr32(self.memory, 0x3000)
        with self.assertRaises(ShortReadError):
            read_u32(self.memory, 0x4000)

    def test_closed_handle_and_exited_process_have_distinct_errors(self):
        closed = object.__new__(ReadOnlyMemory)
        closed._handle = None
        with self.assertRaises(ClosedMemoryError):
            closed.read_bytes(0x5000, 1)
        with self.assertRaises(ProcessExitedError):
            ensure_process_active(123, 0)
        ensure_process_active(123, 259)

    def test_rejects_a_process_path_that_does_not_match_the_target_profile(self):
        wrong_path = str(Path(__file__).resolve())
        process = ProcessInfo(pid=123, executable_path=wrong_path)
        expected = {
            "path": str(Path(__file__).resolve().parent / "PlantsVsZombies.exe"),
            "file_version": "1.0.0.1051",
            "pe_machine": 0x014C,
            "sha256": "0" * 64,
        }

        with self.assertRaises(IdentityMismatchError):
            verify_target_identity(process, expected)


if __name__ == "__main__":
    unittest.main()
