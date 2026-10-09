import json
import unittest
from pathlib import Path

from mcsm_helpers import command_allowed


class CommandPolicyTests(unittest.TestCase):
    def test_arbitrary_mode_cannot_bypass_blocked_roots(self):
        for command in ("stop", "op give x", "ban Alex", "reload"):
            with self.subTest(command=command):
                self.assertFalse(command_allowed(command, allow_arbitrary=True)[0])

    def test_direct_locate_is_not_a_default_command(self):
        self.assertFalse(command_allowed("locate structure minecraft:village")[0])

    def test_exact_allowlist_entry_remains_supported(self):
        self.assertTrue(command_allowed("spark healthreport")[0])
        self.assertTrue(command_allowed("spark tps", allowlist=["spark tps"])[0])
        self.assertFalse(command_allowed("spark plugins", allowlist=["spark tps"])[0])


class ContractTests(unittest.TestCase):
    def test_locate_has_independent_permission_gate(self):
        source = Path("main.py").read_text(encoding="utf-8")
        locate_start = source.index('async def tool_locate')
        locate_end = source.index('@filter.llm_tool(name="mcsm_send_command")', locate_start)
        locate_body = source[locate_start:locate_end]
        self.assertIn("_can_use_locate(event)", locate_body)

    def test_schema_has_locate_permission_level(self):
        schema = json.loads(Path("_conf_schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["locate_permission_level"]["default"], 1)
        self.assertEqual(schema["locate_permission_level"]["type"], "int")
        self.assertEqual(schema["llm_command_allowlist"]["default"], [
            "list", "seed", "time", "weather", "difficulty", "spark healthreport",
        ])


if __name__ == "__main__":
    unittest.main()
