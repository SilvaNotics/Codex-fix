"""Regression for startup exiting before a renderer exists."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import tomllib

ROOT = Path(__file__).resolve().parents[1] / 'scripts'


class StartupHealthTests(unittest.TestCase):
    def test_missing_catalog_preserves_configuration(self):
        spec = importlib.util.spec_from_file_location('startup_health', ROOT/'startup_health.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home/'config.toml'
            original = "model_catalog_json = '" + str(home/'missing.json') + "'\n"
            config.write_text(original, encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'missing file'):
                module.repair_catalog_path(config, home/'backups')
            self.assertEqual(config.read_text(encoding='utf-8'), original)
            self.assertFalse((home/'backups').exists())

    def test_catalog_path_becomes_relative_without_changing_other_config(self):
        spec = importlib.util.spec_from_file_location('startup_health', ROOT/'startup_health.py')
        self.assertIsNotNone(spec)
        self.assertTrue((ROOT/'startup_health.py').exists(), 'startup health repair is missing')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            catalog = home/'models.json'
            catalog.write_text('{}')
            config = home/'config.toml'
            original = "model_catalog_json = '" + str(catalog) + "'\n[desktop]\nrunCodexInWindowsSubsystemForLinux=true\n[model_providers.custom]\nbase_url='https://example.invalid'\n"
            config.write_text(original, encoding='utf-8')
            outcome = module.repair_catalog_path(config, home/'backups')
            expected = tomllib.loads(original)
            expected['model_catalog_json'] = './models.json'
            self.assertEqual(tomllib.loads(config.read_text(encoding='utf-8')), expected)
            self.assertTrue(outcome['changed'])
            self.assertEqual(Path(outcome['backup']).read_text(encoding='utf-8'), original)
            self.assertFalse(module.repair_catalog_path(config, home/'backups')['changed'])


if __name__ == '__main__':
    unittest.main()
