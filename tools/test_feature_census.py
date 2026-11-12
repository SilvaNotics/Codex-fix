"""Offline census regression tests; never starts Codex."""
import importlib.util
import sys
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


class CensusTests(unittest.TestCase):
    def test_ast_inventory_does_not_mistake_comments_or_regex_for_calls(self):
        self.assertIsNotNone(importlib.util.find_spec('feature_census'), 'feature census implementation missing')
        from feature_census import inventory
        rows, errors = inventory([('/main.js', '''
// c.checkGate("fake")
const r=/getLayer("fake")/;
const map=[{gateName:"123",featureKey:"guardian_approval"}];
const caps={toys:{statsig:["456",dynamic],children:{"toys.confetti":{settings:[s.confetti]}}}};
c.getFeatureGate("789");c.checkGate(name);c[method]("unknown");
c["getLayer"]("layer");c.getExperiment(`literal`);c.getDynamicConfig("cfg");
''')])
        self.assertEqual(errors, [])
        self.assertEqual({r['id'] for r in rows if r['id']}, {'123','456','789','layer','literal','cfg'})
        self.assertTrue(any(r['kind']=='named-gate-feature' and r['name']=='guardian_approval' for r in rows))
        self.assertTrue(any(r['kind']=='capability-statsig' and r['name']=='toys' for r in rows))
        self.assertTrue(any(r['classification']=='unclassified' and r['id'] is None for r in rows))
        self.assertTrue(all(isinstance(r['offset'],int) and r['context'] for r in rows))

    def test_inventory_batches_large_packages(self):
        from unittest.mock import patch
        import feature_census as census
        source = '/*' + 'x' * (1024 * 1024) + '*/c.checkGate("42");'
        with patch.object(census.subprocess, 'run', wraps=census.subprocess.run) as run:
            rows, errors = census.inventory([(f'/{i}.js', source) for i in range(5)])
        self.assertGreater(run.call_count, 1)
        self.assertEqual(len(rows), 5)
        self.assertEqual(errors, [])

    def test_launch_does_not_hash_or_scan_package_when_cache_missing(self):
        from unittest.mock import patch
        import feature_census as census
        import codex_zh_launch as launcher
        with patch.object(census, 'load_policy', return_value=None), patch('repair_codex.renderer_sources', side_effect=AssertionError('startup scanned package')):
            with self.assertRaisesRegex(RuntimeError, 'CLICKME|repair'):
                launcher.configure_features('not-initialized.asar')

    def test_launcher_uses_valid_cache_and_rejects_stale_cache(self):
        import tempfile
        from unittest.mock import patch
        import feature_census as census
        import codex_zh_launch as launcher
        with tempfile.TemporaryDirectory() as folder:
            asar = Path(folder) / 'app.asar'
            cache = Path(folder) / 'policy.json'
            write_asar(asar, {'webview/a.js': 'const m={gateName:"123",featureKey:"guardian_approval"};'})
            census.refresh(asar, cache)
            original = census.load_policy
            with patch.object(census, 'load_policy', side_effect=lambda a: original(a, cache)), patch('repair_codex.renderer_sources', side_effect=AssertionError('cache was ignored')):
                launcher.configure_features(asar)
            self.assertEqual(launcher.REQUIRED_GATES, ('123',))
            write_asar(asar, {'webview/a.js':'const m={gateName:"456",featureKey:"guardian_approval"};'})
            with patch.object(census, 'load_policy', side_effect=lambda a: original(a, cache)):
                with self.assertRaisesRegex(RuntimeError, 'CLICKME|repair'):
                    launcher.configure_features(asar)

    def test_entrypoints_run_census_before_install_or_repair(self):
        install = (SCRIPTS / 'install.ps1').read_text(encoding='utf-8-sig')
        repair = (SCRIPTS / 'repair-entry.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('census-entry.ps1', install)
        self.assertLess(install.index('census-entry.ps1'), install.index("$shell ="))
        self.assertIn('feature_census.py', repair)
        self.assertNotIn("& $python (Join-Path $PSScriptRoot 'repair_codex.py')", repair)
        self.assertNotIn('codex_zh_launch.py', repair)
        self.assertIn('exit $LASTEXITCODE', repair)

    def test_parse_failure_preserves_valid_snapshot(self):
        import tempfile
        import feature_census as census
        with tempfile.TemporaryDirectory() as folder:
            asar = Path(folder)/'app.asar'
            cache = Path(folder)/'policy.json'
            write_asar(asar, {'main.js': 'c.checkGate("123");'})
            census.refresh(asar, cache)
            before = cache.read_bytes()
            write_asar(asar, {'main.js': 'const = ;'})
            with self.assertRaisesRegex(ValueError, 'Incomplete AST census'):
                census.refresh(asar, cache)
            self.assertEqual(cache.read_bytes(), before)
            self.assertIsNone(census.load_policy(asar, cache))

    def test_policy_is_fingerprinted_fail_closed_and_preserves_previous_on_failure(self):
        import tempfile
        from unittest.mock import patch
        import feature_census as census
        self.assertTrue(hasattr(census, 'refresh'), 'persistent census implementation missing')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            asar = root / 'app.asar'
            write_asar(asar, {'main.js': 'c.checkGate("unknown");',
                             'webview/a.js': 'const m={gateName:"123",featureKey:"guardian_approval"};'})
            cache = root / 'policy.json'
            result = census.refresh(asar, cache)
            self.assertEqual(result['policy']['found'], {'guardian_approval':'123'})
            self.assertEqual(census.load_policy(asar, cache), {'guardian_approval':'123'})
            self.assertTrue(any(r['decision']=='held' for r in result['census']['rows']))
            self.assertTrue(any(r['decision']=='selected' for r in result['census']['rows']))
            before = cache.read_bytes()
            with patch.object(census.os, 'replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError): census.refresh(asar, cache)
            self.assertEqual(cache.read_bytes(), before)
            write_asar(asar, {'main.js': 'c.checkGate("new");'})
            self.assertIsNone(census.load_policy(asar, cache))
            changed = census.refresh(asar, cache)
            self.assertTrue(changed['census']['diff']['added'])
            self.assertTrue(changed['census']['diff']['removed'])
            self.assertEqual(changed['policy']['found'], {})
            cache.write_text('{bad', encoding='utf-8')
            self.assertIsNone(census.load_policy(asar, cache))

    def test_cached_policy_load_never_reads_or_hashes_package_body(self):
        import tempfile
        from unittest.mock import patch
        import feature_census as census
        with tempfile.TemporaryDirectory() as folder:
            asar = Path(folder)/'app.asar'
            cache = Path(folder)/'policy.json'
            write_asar(asar, {'webview/a.js':'const m={gateName:"123",featureKey:"guardian_approval"};'})
            census.refresh(asar, cache)
            with patch.object(census, 'package_fingerprint', side_effect=AssertionError('full hash on launch')), patch.object(census, 'package_sources', side_effect=AssertionError('source scan on launch')):
                self.assertEqual(census.load_policy(asar, cache), {'guardian_approval':'123'})


def write_asar(path, files):
    import json
    import struct
    tree = {'files':{}}
    content = b''
    for name, source in files.items():
        node = tree
        parts = name.split('/')
        for part in parts[:-1]: node = node['files'].setdefault(part, {'files':{}})
        raw = source.encode('utf-8')
        node['files'][parts[-1]] = {'size':len(raw),'offset':str(len(content))}
        content += raw
    header = json.dumps(tree).encode()
    size = 8 + len(header)
    path.write_bytes(struct.pack('<4I',4,size,len(header)+4,len(header)) + header + content)


if __name__ == '__main__':
    unittest.main()
