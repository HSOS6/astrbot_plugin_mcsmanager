import ast
from pathlib import Path
import unittest


class ToolContractTests(unittest.TestCase):
    def test_send_command_documents_all_handler_parameters(self):
        source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        target = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "tool_send_command"
        )
        docstring = ast.get_docstring(target) or ""
        self.assertIn("instance(string):", docstring)
        self.assertIn("command(string):", docstring)
        self.assertEqual(
            [arg.arg for arg in target.args.args[-3:]],
            ["event", "instance", "command"],
        )

    def test_locate_contract_documents_player_and_type(self):
        source = Path(__file__).with_name("main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        target = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "tool_locate"
        )
        docstring = ast.get_docstring(target) or ""
        for parameter in ("instance(string):", "player(string):", "target(string):", "locate_type(string):"):
            self.assertIn(parameter, docstring)


if __name__ == "__main__":
    unittest.main()
