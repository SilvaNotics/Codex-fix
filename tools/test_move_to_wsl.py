import base64
import os
from pathlib import Path
import stat
import sys
import tempfile
import tomllib
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from move_to_wsl import decode_distros, dump_config, key_only_auth, migration_config
from wsl_config_target import execute


def mounted(path):
    return '/mnt/' + path[0].lower() + '/' + path[3:].replace(chr(92), '/')


class MigrationTests(unittest.TestCase):
    def test_distro_list_handles_wsl_utf16_and_spaces(self):
        data = 'Ubuntu 24.04\r\nDebian\r\ndocker-desktop\r\n'.encode('utf-16-le')
        self.assertEqual(decode_distros(data), ['Ubuntu 24.04', 'Debian'])

    def test_merge_keeps_linux_settings_and_replaces_overlapping_provider(self):
        win = {
            'model_provider': 'relay', 'model_catalog_json': './目录 with spaces.json',
            'model_providers': {'relay': {'base_url': 'https://example.invalid',
                                          'experimental_bearer_token': 'fixture-token'}},
            'desktop': {'runCodexInWindowsSubsystemForLinux': True},
            'windows': {'sandbox': 'elevated'},
            'projects': {r'E:\Project': {'trust_level': 'trusted'}},
            'sandbox_workspace_write': {'writable_roots': [r'E:\A B']},
            'mcp_servers': {'native': {'command': r'C:\Desktop\node_repl.exe'},
                            'win_only': {'command': 'cmd', 'args': ['/c', 'script.cmd']},
                            'server': {'command': 'node', 'args': [r'E:\Tools\server.js']}},
        }
        linux = {'model_providers': {'relay': {'env_key': 'OLD_KEY'}, 'other': {'name': 'other'}},
                 'mcp_servers': {'native': {'command': '/usr/bin/node_repl'}},
                 'projects': {'/home/dev/project': {'trust_level': 'trusted'}},
                 'desktop': {'localeOverride': 'en-US'}}
        result, skipped = migration_config(win, linux, r'C:\Users\John Doe\.codex', mounted)
        self.assertEqual(result['model_catalog_json'], '/mnt/c/Users/John Doe/.codex/目录 with spaces.json')
        self.assertEqual(result['model_providers']['relay'], win['model_providers']['relay'])
        self.assertIn('other', result['model_providers'])
        self.assertEqual(result['mcp_servers']['native'], linux['mcp_servers']['native'])
        self.assertEqual(result['mcp_servers']['server']['args'], ['/mnt/e/Tools/server.js'])
        self.assertEqual(result['sandbox_workspace_write']['writable_roots'], ['/mnt/e/A B'])
        self.assertIn('/mnt/e/Project', result['projects'])
        self.assertIn('/home/dev/project', result['projects'])
        self.assertEqual(result['desktop'], linux['desktop'])
        self.assertNotIn('windows', result)
        self.assertIn('mcp_servers.win_only', skipped)
        self.assertEqual(tomllib.loads(dump_config(result)), result)
        self.assertEqual(migration_config(win, result, r'C:\Users\John Doe\.codex', mounted)[0], result)

    def test_key_only_auth_does_not_accept_chatgpt_tokens(self):
        self.assertEqual(key_only_auth(b'{"OPENAI_API_KEY":"example"}'), 'example')
        self.assertIsNone(key_only_auth(b'{"OPENAI_API_KEY":"example","tokens":{"fixture":"oauth"}}'))
        self.assertIsNone(key_only_auth(b'{"OPENAI_API_KEY":"example","auth_mode":"chatgpt"}'))

    def test_target_backs_up_before_writing_and_rejects_stale_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            dest = home / '.codex'
            dest.mkdir()
            config = dest / 'config.toml'
            config.write_bytes(b'model="before"\n')
            before = execute({'action': 'read'}, home)['files']
            after = {'config.toml': base64.b64encode(b'model="after"\n').decode()}
            request = {'action': 'write', 'before': before, 'after': after}
            response = execute(request, home)
            self.assertEqual(config.read_bytes(), b'model="after"\n')
            self.assertEqual(Path(response['backups'][0]).read_bytes(), b'model="before"\n')
            if os.name == 'posix':
                for path in (config, Path(response['backups'][0])):
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with self.assertRaises(RuntimeError):
                execute(request, home)
            self.assertEqual(config.read_bytes(), b'model="after"\n')

    def test_existing_wsl_auth_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            dest = home / '.codex'
            dest.mkdir()
            auth = dest / 'auth.json'
            auth.write_bytes(b'{"auth_mode":"chatgpt"}')
            before = execute({'action': 'read'}, home)['files']
            after = {'auth.json': base64.b64encode(b'{"OPENAI_API_KEY":"fixture"}').decode()}
            with self.assertRaises(RuntimeError):
                execute({'action': 'write', 'before': before, 'after': after}, home)
            self.assertEqual(auth.read_bytes(), b'{"auth_mode":"chatgpt"}')

    def test_missing_catalog_aborts_before_creating_config(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            with self.assertRaises(RuntimeError):
                execute({'action': 'check_catalog', 'catalog': str(home/'missing')}, home)
            self.assertFalse((home / '.codex').exists())
