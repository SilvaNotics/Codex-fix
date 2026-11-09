import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('repair', ROOT / 'repair_codex.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

# Synthetic fixtures exercise discovery; not claims about future vendor versions.
FIXTURE = '''
let b=(0,h.Zj)("101");E[0]!==T?(t={enabled:T,featureName:"computer_use",hostId:C}):t=0;
let I=(0,u.Zj)("102");m[0]!==y?(t={enabled:y,featureName:"browser_use_external",hostId:g}):t=0;
let C=(0,d.Zj)("103");g[1]!==E?(n={enabled:E,featureName:"browser_use",hostId:y}):n=0;
x=(0,p.Ou)("105");O[0]!==x?(t=x?.get("enable_i18n",!1),O[0]=x):t=0;let M=t,L=x?.get("locale_source","IDE");
if(!e(o.JW,"104"))return!1;let t=e(a.lN);return"denied"!==t.status||"unsupported-auth"!==t.reason;
A=(0,r.un)(h.u,({get:e})=>e(I.JW,"104")),S=0;function O(){if(!t(A)&&!h)return"legacy";let T=0;if(!n&&h)return"rail-only";}
'''


class RepairTests(unittest.TestCase):
    def test_semantic_detection(self):
        found, _ = repair.discover([('test.js', FIXTURE)])
        self.assertEqual(found, dict(zip(repair.ROLES, ['101', '102', '103', '104', '105'])))

    def test_renamed_ids_and_minifier_symbols(self):
        modified = FIXTURE.replace('101', '901').replace('104', '904').replace('105', '905').replace('Zj', 'newAlias').replace('JW', 'newGate')
        found, _ = repair.discover([('renamed.js', modified)])
        self.assertEqual(found['computer_use'], '901')
        self.assertEqual(found['layout'], '904')
        self.assertEqual(found['i18n'], '905')

    def test_ambiguous_fails_closed(self):
        found, _ = repair.discover([('a.js', FIXTURE), ('b.js', FIXTURE.replace('101', '999'))])
        self.assertNotIn('computer_use', found)
        with self.assertRaises(ValueError):
            repair.updated_source((ROOT/'codex_zh_launch.py').read_text(encoding='utf-8'), found)

    def test_unrelated_nearby_id_not_used(self):
        found, _ = repair.discover([('test.js', FIXTURE.replace('featureName:"computer_use"', 'featureName:"unrelated"'))])
        self.assertNotIn('computer_use', found)

    def test_all_launcher_references_and_version_update(self):
        source = (ROOT/'codex_zh_launch.py').read_text(encoding='utf-8')
        found, _ = repair.discover([('test.js', FIXTURE)])
        result = repair.updated_source(source, found)
        self.assertEqual(repair.current_ids(result), found)
        for old in repair.current_ids(source).values():
            self.assertNotIn('"'+old+'"', result)
        self.assertIn('auto-', result)
        self.assertEqual(repair.updated_source(result, found), result)

    def test_current_ids_no_write(self):
        source = (ROOT/'codex_zh_launch.py').read_text(encoding='utf-8')
        self.assertEqual(repair.updated_source(source, repair.current_ids(source)), source)

    def test_failed_verification_restores_launcher(self):
        from argparse import Namespace
        from unittest.mock import patch
        source = (ROOT/'codex_zh_launch.py').read_bytes().replace(b'def configure_features(asar):', b'def legacy_configure(asar):')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root/'codex_zh_launch.py'
            launcher.write_bytes(source)
            with patch.object(repair, 'ROOT', root), patch.object(repair, 'renderer_sources', return_value=[('test.js', FIXTURE)]), patch.object(repair.subprocess, 'run', side_effect=[None, RuntimeError('simulated child failure')]):
                self.assertEqual(repair.run(Namespace(asar='test.asar', scan_only=False)), 1)
            self.assertEqual(launcher.read_bytes(), source)
            report = json.loads((root/'repair-report.json').read_text(encoding='utf-8'))
            self.assertTrue(report['rolled_back'])
            self.assertEqual(report['status'], 'failed')

    def test_asar_reader(self):
        body = FIXTURE.encode()
        header = json.dumps({'files': {'webview': {'files': {'main.js': {'size': len(body), 'offset': '0'}}}}}).encode()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'app.asar'
            path.write_bytes(struct.pack('<4I', 4, len(header)+8, len(header)+4, len(header))+header+body)
            found, _ = repair.discover(repair.renderer_sources(path))
            self.assertEqual(len(found), 5)


if __name__ == '__main__':
    unittest.main()
