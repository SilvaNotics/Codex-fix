import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'scripts'

class RuntimeDiagnosticsTests(unittest.TestCase):
    def load(self):
        path = ROOT/'runtime_diagnostics.py'
        self.assertTrue(path.exists(), 'launcher needs layered runtime diagnostics')
        spec = importlib.util.spec_from_file_location('runtime_diagnostics_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # Production resolves backups relative to its script location; sandbox it.
        sandbox = tempfile.TemporaryDirectory()
        self.addCleanup(sandbox.cleanup)
        module.__file__ = str(Path(sandbox.name)/'scripts/runtime_diagnostics.py')
        return module

    def test_inventory_and_stale_paths_do_not_expose_secrets_or_mutate(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            codex = home/'.codex'
            codex.mkdir()
            config = codex/'config.toml'
            source = '''[mcp_servers.node_repl]
command = 'MISSING/node_repl.exe'
[mcp_servers.node_repl.env]
CODEX_CLI_PATH = 'MISSING/codex.exe'
SKY_CUA_NATIVE_PIPE = 'private-session-reference'
API_TOKEN = 'never-print-secret'
[plugins."documents@openai-primary-runtime"]
enabled = true
'''
            config.write_text(source, encoding='utf-8')
            plugin = home/'.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime/plugins/documents/.codex-plugin'
            plugin.mkdir(parents=True)
            (plugin/'plugin.json').write_text(json.dumps({'name':'documents','version':'test'}), encoding='utf-8')
            report = module.collect(home=home)
            self.assertEqual(config.read_text(encoding='utf-8'), source)
            self.assertTrue(report['plugins']['documents@openai-primary-runtime']['manifest_present'])
            self.assertFalse(report['plugins']['pdf@openai-primary-runtime']['manifest_present'])
            self.assertIn('node-repl-command-missing', report['warnings'])
            self.assertIn('node-repl-session-references-persisted', report['warnings'])
            self.assertNotIn('never-print-secret', json.dumps(report))
            self.assertNotIn('private-session-reference', json.dumps(report))
            self.assertEqual(report['verification_scope'], 'local-inventory-not-tool-execution')

    def test_session_cleanup_is_targeted_idempotent_and_backed_up(self):
        module = self.load()
        import tomllib
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.toml'
            source = ('# keep comments\n[mcp_servers.node_repl]\ncommand="node"\n'
                      '[mcp_servers.node_repl.env] # managed elsewhere\n'
                      'SKY_CUA_NATIVE_PIPE = "old-session"\n'
                      'SKY_CUA_NATIVE_PIPE_DIRECTORY = "old-dir"\n'
                      'KEEP="preserve-me"\n[mcp_servers.other.env]\n'
                      'SKY_CUA_NATIVE_PIPE="unrelated"\n')
            path.write_text(source, encoding='utf-8')
            result = module.repair_session_config(path)
            data = tomllib.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['mcp_servers']['node_repl']['env'], {'KEEP':'preserve-me'})
            self.assertEqual(data['mcp_servers']['other']['env']['SKY_CUA_NATIVE_PIPE'], 'unrelated')
            self.assertEqual(Path(result['backup']).read_text(encoding='utf-8'), source)
            self.assertFalse(module.repair_session_config(path)['changed'])

    def test_unsupported_layout_fails_without_writing(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'config.toml'
            source = '[mcp_servers.node_repl]\nenv={SKY_CUA_NATIVE_PIPE="old",KEEP="ok"}\n'
            path.write_text(source, encoding='utf-8')
            with self.assertRaises(ValueError):
                module.repair_session_config(path)
            self.assertEqual(path.read_text(encoding='utf-8'), source)
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_invalid_field_types_degrade_and_empty_session_keys_are_detected(self):
        module = self.load()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home/'.codex').mkdir()
            path = home/'.codex/config.toml'
            for source in ['plugins=1\nmcp_servers=[]', '[mcp_servers.node_repl]\ncommand=42\nenv=1', '[mcp_servers.node_repl.env]\nSKY_CUA_NATIVE_PIPE=""']:
                path.write_text(source, encoding='utf-8')
                report = module.collect(home)
                self.assertTrue(report['warnings'])
            self.assertTrue(report['node_repl']['persisted_session_references'])
            self.assertTrue(module.repair_session_config(path)['changed'])

    def test_explicit_disabled_plugin_is_preserved_by_config_repair(self):
        spec = importlib.util.spec_from_file_location('runtime_launcher_test', ROOT/'codex_zh_launch.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp)/'config.toml'
            text = '[plugins."computer-use@openai-bundled"]\nenabled = false\n'
            config.write_text(text, encoding='utf-8')
            launcher.CONFIG = str(config)
            launcher.BACKUP_DIR = tmp
            launcher.ensure_config({'computer_use'})
            self.assertEqual(config.read_text(encoding='utf-8'), text,
                             'launcher must not reverse explicit plugin permission choices')

if __name__ == '__main__':
    unittest.main()
