"""Launcher checks must reject partial success and stale ports."""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('launcher', ROOT / 'codex_zh_launch.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class VerificationTests(unittest.TestCase):
    def healthy(self):
        return dict(patched=True, enable_i18n=True, officialLayout=True,
                    lang='zh-CN', cjk=30, len=200,
                    gates={g: True for g in module.REQUIRED_GATES},
                    navigation=True, settingsEntry=True)

    def test_package_lookup_reuses_family_without_second_powershell(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        package = {'exe': 'C:/Codex/ChatGPT.exe', 'family': 'OpenAI.Codex_test'}
        with patch.object(module, '_FAM', None), patch.object(module.os.path, 'isfile', return_value=True), patch.object(module.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=json.dumps(package))) as run:
            self.assertEqual(module.find_exe(), package['exe'])
            self.assertEqual(module.pkg_family(), package['family'])
            run.assert_called_once()

    def test_diagnostic_failure_does_not_escape_into_launcher(self):
        import sys
        from unittest.mock import patch
        from types import SimpleNamespace
        def broken():
            raise TypeError('invalid private configuration')
        with patch.dict(sys.modules, {'runtime_diagnostics': SimpleNamespace(collect=broken)}):
            self.assertEqual(module.component_diagnostics()['status'], 'unavailable')

    def test_partial_patch_is_not_success(self):
        state = self.healthy()
        self.assertEqual(module.verification_failures(state), [])
        for key, value in [('navigation', False), ('settingsEntry', False),
                           ('lang', 'en'), ('enable_i18n', False), ('cjk', 0)]:
            broken = dict(state, **{key: value})
            self.assertTrue(module.verification_failures(broken), key)
        state['gates'][module.REQUIRED_GATES[0]] = False
        self.assertTrue(module.verification_failures(state))
        self.assertTrue(module.verification_failures({}))

    def test_report_overwrites_old_success_atomically(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'verify.json'
            module.write_report({'status': 'passed'}, path)
            module.write_report({'status': 'failed'}, path)
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['status'], 'failed')
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_config_repairs_desktop_locale_without_touching_provider(self):
        import tomllib
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config.toml'
            original = ('model_provider="custom"\n[model_providers.custom]\n'
                        'base_url="https://example.invalid/v1"\nrequires_openai_auth=false\n'
                        '[desktop]\nlocaleOverride="en-US"\n')
            path.write_text(original, encoding='utf-8')
            with patch.object(module, 'CONFIG', str(path)):
                module.ensure_config()
                result = tomllib.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(result['desktop']['localeOverride'], 'zh-CN')
                self.assertEqual(result['model_providers'], tomllib.loads(original)['model_providers'])
                first = path.read_bytes()
                module.ensure_config()
                self.assertEqual(path.read_bytes(), first)

    def test_config_accepts_section_comments(self):
        import tomllib
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'config.toml'
            path.write_text('[desktop] # language\nlocaleOverride="en-US"\n'
                            '[plugins."computer-use@openai-bundled"] # installed\nenabled=false\n', encoding='utf-8')
            with patch.object(module, 'CONFIG', str(path)):
                module.ensure_config()
            data = tomllib.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(data['desktop']['localeOverride'], 'zh-CN')
            self.assertIs(data['plugins']['computer-use@openai-bundled']['enabled'], False)

    def test_port_reader_rejects_out_of_range(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'port'
            for value in ['0', '-1', '65536', 'NaN', '']:
                path.write_text(value)
                self.assertIsNone(module.read_devtools_port(path), value)
            path.write_text('45678\n/devtools/browser/test')
            self.assertEqual(module.read_devtools_port(path), 45678)

class RpcTests(unittest.IsolatedAsyncioTestCase):
    async def test_rpc_skips_events_and_rejects_protocol_errors(self):
        class Socket:
            def __init__(self, replies): self.replies = iter(replies)
            async def send(self, message): self.sent = json.loads(message)
            async def recv(self): return json.dumps(next(self.replies))
        ws = Socket([{'method':'Page.event'}, {'id': 9, 'result': {}},
                     {'id': 1, 'result': {'ok': True}}])
        rpc = module.CdpSession(ws)
        self.assertEqual(await rpc.call('Page.enable'), {'ok': True})
        ws = Socket([{'id': 1, 'error': {'code': -1, 'message': 'unsupported'}}])
        with self.assertRaisesRegex(RuntimeError, 'unsupported'):
            await module.CdpSession(ws).call('Page.enable')

    async def test_rpc_rejects_javascript_exceptions(self):
        class Socket:
            async def send(self, message): pass
            async def recv(self): return json.dumps({'id': 1, 'result': {
                'result': {'type': 'undefined'}, 'exceptionDetails': {'text': 'broken SDK'}}})
        with self.assertRaisesRegex(RuntimeError, 'broken SDK'):
            await module.CdpSession(Socket()).evaluate('bad()')

if __name__ == '__main__':
    unittest.main()
