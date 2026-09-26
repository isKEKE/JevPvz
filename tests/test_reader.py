import struct
import unittest

from configs.pvz_1051 import ARRAY_HEADER_OFFSETS, FIELD_OFFSETS
from game.arrays import ArrayFormatError, inspect_array_header, iter_live_slots
from game.reader import read_game_progress, read_items, read_plant_definition_cost, read_plants, read_raw_snapshot, read_zombies
from runtime.memory import ShortReadError, read_u32


class FakeMemory:
    def __init__(self):
        self.bytes = {}

    def put(self, address, value):
        for offset, byte in enumerate(value):
            self.bytes[address + offset] = byte

    def put_u32(self, address, value):
        self.put(address, struct.pack("<I", value))

    def read_bytes(self, address, size):
        try:
            return bytes(self.bytes[address + offset] for offset in range(size))
        except KeyError as exc:
            received = sum(address + offset in self.bytes for offset in range(size))
            raise ShortReadError(address, size, received) from exc

    def read_u32(self, address):
        return read_u32(self, address)


class SparseArrayTests(unittest.TestCase):
    def setUp(self):
        self.memory = FakeMemory()
        self.board = 0x100000
        self.data = 0x200000
        self.layout = FIELD_OFFSETS["plants"]
        header = self.board + self.layout["header"]
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["data"], self.data)
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["max_used"], 4)
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["capacity"], 8)
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["free_list_head"], 0)
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["live_count"], 2)
        stride = self.layout["stride"]
        id_offset = self.layout["object_id"]
        self.memory.put_u32(self.data + 0 * stride + id_offset, 0x00001234)
        self.memory.put_u32(self.data + 1 * stride + id_offset, 0x00010002)
        self.memory.put_u32(self.data + 2 * stride + id_offset, 0x00000010)
        self.memory.put_u32(self.data + 3 * stride + id_offset, 0x00020003)

    def test_scans_to_high_water_and_filters_by_id_high_word(self):
        header = inspect_array_header(
            self.memory, self.board, self.layout, ARRAY_HEADER_OFFSETS
        )
        slots = iter_live_slots(
            self.memory, header, self.layout["stride"], self.layout["object_id"]
        )

        self.assertEqual([slot.index for slot in slots], [1, 3])
        self.assertEqual(header.live_count, 2)

    def test_rejects_impossible_header_bounds(self):
        header_address = self.board + self.layout["header"]
        self.memory.put_u32(header_address + ARRAY_HEADER_OFFSETS["live_count"], 5)

        with self.assertRaises(ArrayFormatError):
            inspect_array_header(self.memory, self.board, self.layout, ARRAY_HEADER_OFFSETS)

    def test_decodes_live_plant_fields_and_preserves_unknown_type_codes(self):
        stride = self.layout["stride"]
        type_offset = self.layout["type"]
        row_offset = self.layout["row"]
        column_offset = self.layout["column"]
        for index, (plant_type, row, column) in {
            1: (1, 0, 3),
            3: (900, 7, 12),
        }.items():
            address = self.data + index * stride
            self.memory.put_u32(address + type_offset, plant_type)
            self.memory.put_u32(address + row_offset, row)
            self.memory.put_u32(address + column_offset, column)

        result = read_plants(self.memory, self.board)

        self.assertEqual(result["scanned_live_count"], 2)
        self.assertEqual(result["entities"][0]["type"], 1)
        self.assertEqual(result["entities"][1]["type"], 900)
        self.assertEqual(result["entities"][1]["row"], 7)
        self.assertEqual(result["entities"][1]["column"], 12)
        self.assertEqual(result["dynamic_semantics"], "not_verified_with_gameplay")

    def test_keeps_item_type_unknown_and_selects_only_plausible_float_coordinates(self):
        board = 0x300000
        data = 0x400000
        layout = FIELD_OFFSETS["items"]
        header = board + layout["header"]
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["data"], data)
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["max_used"], 1)
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["capacity"], 4)
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["free_list_head"], 1)
        self.memory.put_u32(header + ARRAY_HEADER_OFFSETS["live_count"], 1)
        self.memory.put_u32(data + layout["object_id"], 0x00010000)
        self.memory.put(data + layout["x"], struct.pack("<f", 551.0))
        self.memory.put(data + layout["y"], struct.pack("<f", 448.0))
        self.memory.put_u32(data + layout["type"], 4)
        self.memory.put_u32(data + layout["collecting_candidate"], 0)

        result = read_items(self.memory, board)
        item = result["entities"][0]

        self.assertEqual(item["coordinate_interpretation"], "f32_pixel_candidate")
        self.assertEqual((item["x"], item["y"]), (551.0, 448.0))
        self.assertEqual(item["type_meaning"], "unknown")
        self.assertTrue(item["type_4_sun_candidate"])

    def test_reads_bucket_helmet_hp_separately_from_body_hp(self):
        board = 0x300000
        data = 0x400000
        layout = FIELD_OFFSETS["zombies"]
        header = board + layout["header"]
        for field, value in {"data": data, "max_used": 1, "capacity": 4,
                             "free_list_head": 1, "live_count": 1}.items():
            self.memory.put_u32(header + ARRAY_HEADER_OFFSETS[field], value)
        self.memory.put_u32(data + layout["object_id"], 0x00010000)
        self.memory.put_u32(data + layout["row"], 2)
        self.memory.put_u32(data + layout["type"], 4)
        self.memory.put(data + layout["x"], struct.pack("<f", 680.0))
        self.memory.put(data + layout["y"], struct.pack("<f", 250.0))
        for field, value in {"hp": 270, "helmet_hp": 1100,
                             "shield_hp": 0, "balloon_hp": 0}.items():
            self.memory.put(data + layout[field], struct.pack("<i", value))

        zombie = read_zombies(self.memory, board)["entities"][0]

        self.assertEqual(zombie["hp"], 270)
        self.assertEqual(zombie["helmet_hp"], 1100)
        self.assertEqual(zombie["shield_hp"], 0)
        self.assertEqual(zombie["balloon_hp"], 0)

    def test_reads_plant_definition_cost_after_type_code_validation(self):
        from configs.pvz_1051 import CANDIDATE_OFFSETS

        module_base = 0x1000000
        layout = CANDIDATE_OFFSETS["plant_definition"]
        address = module_base + layout["table_rva"] + 1 * layout["stride"]
        self.memory.put_u32(address + layout["type"], 1)
        self.memory.put_u32(address + layout["cost"], 50)
        self.assertEqual(read_plant_definition_cost(self.memory, module_base, 1), {"type_code": 1, "cost": 50})

        self.memory.put_u32(address + layout["type"], 2)
        with self.assertRaisesRegex(ValueError, "type mismatch"):
            read_plant_definition_cost(self.memory, module_base, 1)

    def test_reads_cone_bucket_shield_balloon_and_unarmored_hp_separately(self):
        board = 0x300000
        data = 0x400000
        layout = FIELD_OFFSETS["zombies"]
        header = board + layout["header"]
        count = 5
        for field, value in {"data": data, "max_used": count, "capacity": 8,
                             "free_list_head": count, "live_count": count}.items():
            self.memory.put_u32(header + ARRAY_HEADER_OFFSETS[field], value)
        entries = [
            (2, 270, 370, 0, 0),    # traffic cone
            (4, 270, 1100, 0, 0),   # bucket
            (6, 270, 0, 1100, 0),   # screen door shield
            (16, 270, 0, 0, 200),   # balloon
            (0, 270, 0, 0, 0),      # ordinary zombie
        ]
        for index, (type_code, hp, helmet, shield, balloon) in enumerate(entries):
            address = data + index * layout["stride"]
            self.memory.put_u32(address + layout["object_id"], 0x00010000 + index)
            self.memory.put_u32(address + layout["row"], index % 5)
            self.memory.put_u32(address + layout["type"], type_code)
            self.memory.put(address + layout["x"], struct.pack("<f", 680.0))
            self.memory.put(address + layout["y"], struct.pack("<f", 250.0))
            for field, value in {"hp": hp, "helmet_hp": helmet,
                                 "shield_hp": shield, "balloon_hp": balloon}.items():
                self.memory.put(address + layout[field], struct.pack("<i", value))

        zombies = read_zombies(self.memory, board)["entities"]

        self.assertEqual(
            [(z["type"], z["hp"], z["helmet_hp"], z["shield_hp"], z["balloon_hp"]) for z in zombies],
            entries,
        )

    def test_progress_reads_single_byte_flags_and_preserves_other_progress_codes(self):
        from configs.pvz_1051 import CANDIDATE_OFFSETS

        root = 0x500000
        board = 0x600000
        scene_offsets = CANDIDATE_OFFSETS["scene"]
        progress_offsets = CANDIDATE_OFFSETS["progress"]
        self.memory.put_u32(root + scene_offsets["scene"], 3)
        self.memory.put_u32(root + scene_offsets["mode"], 0)
        for name, value in {"background": 0, "level": 5, "total_waves": 20,
                            "current_wave": 3}.items():
            self.memory.put_u32(board + progress_offsets[name], value)
        # Nonzero neighbors would turn a four-byte read into a large false flag.
        self.memory.put(board + progress_offsets["pause_flag"], b"\x01\xAA\xBB\xCC")
        self.memory.put(board + progress_offsets["won_flag"], b"\x00\xDD\xEE\xFF")

        progress = read_game_progress(self.memory, root, board)
        fields = progress["raw_candidate_fields"]

        self.assertEqual(fields["scene"]["value"], 3)
        self.assertEqual(fields["mode"]["value"], 0)
        self.assertEqual(fields["background"]["value"], 0)
        self.assertEqual(fields["level"]["value"], 5)
        self.assertEqual(fields["current_wave"]["value"], 3)
        self.assertEqual(fields["total_waves"]["value"], 20)
        self.assertEqual(fields["pause_flag"]["value"], 1)
        self.assertEqual(fields["won_flag"]["value"], 0)
        self.assertEqual(progress["read_errors"], [])

    def test_snapshot_keeps_root_scene_when_menu_has_no_board(self):
        from configs.pvz_1051 import BOARD_POINTER_OFFSETS, BOARD_ROOT_RVA, CANDIDATE_OFFSETS

        module_base = 0x1000000
        root = 0x500000
        self.memory.put_u32(module_base + BOARD_ROOT_RVA, root)
        self.memory.put_u32(root + BOARD_POINTER_OFFSETS[0], 0)
        self.memory.put_u32(root + CANDIDATE_OFFSETS["scene"]["scene"], 1)
        self.memory.put_u32(root + CANDIDATE_OFFSETS["scene"]["mode"], 0)

        snapshot = read_raw_snapshot(self.memory, module_base)

        self.assertEqual(snapshot["board_address"], "0x00000000")
        self.assertEqual(snapshot["candidates"]["game_progress"]["raw_candidate_fields"]["scene"]["value"], 1)
        self.assertEqual(snapshot["candidates"]["game_progress"]["raw_candidate_fields"]["mode"]["value"], 0)
        self.assertIn("level", {error["field"] for error in snapshot["candidates"]["game_progress"]["read_errors"]})


if __name__ == "__main__":
    unittest.main()
