import codecs
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "' 中文编译检查\r\nOption Explicit\r\nWScript.Quit 0\r\n"
NORMALIZED = SOURCE.encode('utf-16')


@unittest.skipUnless(os.name == 'nt', 'Requires Windows PowerShell and Script Host')
class WindowsEntrypointTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='Codex entry test ')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        scripts = self.root/'scripts'
        scripts.mkdir()
        for name in ('CLICKME.cmd', 'repair-codex.cmd', 'scripts/repair-entry.ps1', 'scripts/normalize-vbs.ps1'):
            if (ROOT/name).is_file():
                shutil.copyfile(ROOT/name, self.root/name)
        self.vbs = scripts/'start-codex.vbs'
        self.backup = self.root/'output/backups/start-codex.vbs.bak-encoding'
        self.receipt = scripts/'child-receipt.txt'
        self.env = dict(os.environ, LOCALAPPDATA=str(self.root/'fixture-local'))
        path_key = next(key for key in self.env if key.lower() == 'path')
        self.env[path_key] = str(Path(sys.executable).parent) + os.pathsep + self.env[path_key]
        (scripts/'repair_codex.py').write_text(
            "import sys\nfrom pathlib import Path\n"
            "Path(__file__).with_name('child-receipt.txt').write_text('\\n'.join(sys.argv[1:]), encoding='utf-8')\n",
            encoding='ascii')

    def run_cmd(self, name, *args):
        return subprocess.run(['cmd.exe', '/d', '/c', name, *args], cwd=self.root, env=self.env,
                              input=b'\r\n', capture_output=True, timeout=20)

    def test_clickme_converts_utf8_bom_and_runs_windows_script_host(self):
        original = SOURCE.encode('utf-8-sig')
        self.vbs.write_bytes(original)
        result = self.run_cmd('CLICKME.cmd')
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(self.vbs.read_bytes(), NORMALIZED)
        self.assertEqual(self.backup.read_bytes(), original)
        timestamp = self.vbs.stat().st_mtime_ns
        result = self.run_cmd('CLICKME.cmd')
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(self.vbs.stat().st_mtime_ns, timestamp)
        self.vbs.write_bytes(SOURCE.encode('utf-8'))
        self.assertEqual(self.run_cmd('CLICKME.cmd').returncode, 0)
        self.assertEqual(self.vbs.read_bytes(), NORMALIZED)
        self.assertEqual(self.backup.read_bytes(), original)

    def test_repair_runs_shared_encoding_check(self):
        original = SOURCE.encode('utf-8')
        self.vbs.write_bytes(original)
        result = self.run_cmd('repair-codex.cmd')
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(self.vbs.read_bytes(), NORMALIZED)
        self.assertEqual(self.backup.read_bytes(), original)
        self.assertTrue(self.receipt.is_file())

    def test_repair_scan_only_forwards_arguments_and_leaves_vbs_untouched(self):
        original = SOURCE.encode('utf-8')
        self.vbs.write_bytes(original)
        result = self.run_cmd('repair-codex.cmd', '--scan-only', '--asar', 'fixture space.asar')
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(self.receipt.read_text(encoding='utf-8').splitlines(),
                         ['--scan-only', '--asar', 'fixture space.asar'])
        self.assertEqual(self.vbs.read_bytes(), original)
        self.assertFalse(self.backup.exists())

    def test_repair_rejects_invalid_encoding_before_running_child(self):
        invalid = (NORMALIZED + b'a', codecs.BOM_UTF16_LE + bytes.fromhex('00 D8'), b'\xff')
        for payload in invalid:
            with self.subTest(payload=payload):
                self.vbs.write_bytes(payload)
                result = self.run_cmd('repair-codex.cmd')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.vbs.read_bytes(), payload)
                self.assertFalse(self.backup.exists())
                self.assertFalse(self.receipt.exists())
