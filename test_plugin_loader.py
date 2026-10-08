import importlib.util
import sys
import tempfile
from pathlib import Path
import unittest


class PluginLoaderTests(unittest.TestCase):
    def test_helper_loads_without_plugin_directory_on_sys_path(self):
        source_dir = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as temp_dir:
            helper_copy = Path(temp_dir) / "mcsm_helpers.py"
            helper_copy.write_bytes((source_dir / "mcsm_helpers.py").read_bytes())
            original_path = list(sys.path)
            sys.path = [entry for entry in sys.path if Path(entry or ".").resolve() != source_dir]
            try:
                spec = importlib.util.spec_from_file_location("isolated_plugin_helper", helper_copy)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                ok, command, reason = module.build_locate_command(
                    "minecraft:village", "structure", "Steve"
                )
                self.assertTrue(ok, reason)
                self.assertEqual(command, "execute at Steve run locate structure minecraft:village")
            finally:
                sys.path = original_path


if __name__ == "__main__":
    unittest.main()
