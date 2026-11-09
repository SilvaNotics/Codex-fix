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

    def test_bundle_check_detects_removed_gate(self):
        import struct
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'app.asar'
            def bundle(body):
                header = json.dumps({'files': {'webview': {'files': {'main.js': {
                    'size': len(body), 'offset': '0'}}}}}).encode()
                path.write_bytes(struct.pack('<4I', 4, len(header)+8, len(header)+4, len(header)) + header + body)
            bundle(b' '.join(x.encode() for x in (*module.REQUIRED_GATES, '72216192', 'enable_i18n')))
            self.assertEqual(module.bundle_missing_markers(path), [])
            bundle(b'3085093835')
            self.assertIn('1506311413', module.bundle_missing_markers(path))

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
            self.assertIs(data['plugins']['computer-use@openai-bundled']['enabled'], True)

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
