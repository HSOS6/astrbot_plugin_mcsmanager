import json
import unittest

from mcsm_helpers import (
    build_locate_command,
    command_allowed,
    log_delta,
    parse_locate_output,
)


class McsmHelperTests(unittest.TestCase):
    def test_build_locate_command(self):
        ok, command, reason = build_locate_command("Minecraft:Village", "structure", "Steve")
        self.assertTrue(ok)
        self.assertEqual(command, "execute at Steve run locate structure minecraft:village")
        self.assertEqual(reason, "")
        ok, command, reason = build_locate_command("minecraft:plains", "biome", "Alex")
        self.assertTrue(ok)
        self.assertEqual(command, "execute at Alex run locate biome minecraft:plains")
        ok, command, reason = build_locate_command("minecraft:home", "poi", "Alex")
        self.assertTrue(ok)
        self.assertEqual(command, "execute at Alex run locate poi minecraft:home")

    def test_reject_invalid_type_or_player(self):
        self.assertFalse(build_locate_command("minecraft:village", "dimension", "Steve")[0])
        self.assertFalse(build_locate_command("minecraft:village", "structure", "Steve;op")[0])

    def test_reject_invalid_target(self):
        ok, _, _ = build_locate_command("minecraft:village;op attacker")
        self.assertFalse(ok)

    def test_command_policy(self):
        self.assertTrue(command_allowed("execute at Steve run locate structure minecraft:village")[0])
        self.assertTrue(command_allowed("execute at Steve run locate biome minecraft:plains")[0])
        self.assertTrue(command_allowed("execute at Steve run locate poi minecraft:home")[0])
        self.assertFalse(command_allowed("locate structure minecraft:village")[0])
        self.assertFalse(command_allowed("execute at Steve run op attacker")[0])
        self.assertFalse(command_allowed("op attacker")[0])
        self.assertFalse(command_allowed("say\nstop")[0])
        self.assertTrue(command_allowed("anything", allow_arbitrary=True)[0])
        self.assertTrue(command_allowed("spark healthreport")[0])
        self.assertTrue(command_allowed("/spark healthreport")[0])
        self.assertFalse(command_allowed("spark profiler start")[0])
        self.assertFalse(command_allowed("spark plugins")[0])
        self.assertTrue(command_allowed("spark tps", allowlist=["spark tps"])[0])
        self.assertFalse(command_allowed("spark healthreport", allowlist=["list"])[0])
        self.assertTrue(command_allowed("list", allowlist=["list"])[0])

    def test_log_delta(self):
        self.assertEqual(log_delta("old\n", "old\nnew\n"), "new\n")
        self.assertEqual(log_delta("old", "new"), "new")

    def test_parse_english_coordinates(self):
        parsed = parse_locate_output("The nearest structure is at [123, ~, -456]", "minecraft:village")
        self.assertTrue(parsed["found"])
        self.assertEqual(parsed["coordinates"], {"x": 123, "z": -456})

    def test_parse_chinese_coordinates(self):
        parsed = parse_locate_output("最近的结构坐标为 (123, -456)", "minecraft:village")
        self.assertTrue(parsed["found"])
        self.assertEqual(parsed["coordinates"], {"x": 123, "z": -456})

    def test_parse_unknown_is_not_success(self):
        parsed = parse_locate_output("命令已执行，但没有坐标", "minecraft:village")
        self.assertIsNone(parsed["found"])
        self.assertIsNone(parsed["coordinates"])

    def test_parse_not_found(self):
        parsed = parse_locate_output("Could not find that structure", "minecraft:village")
        self.assertFalse(parsed["found"])


if __name__ == "__main__":
    unittest.main()
