import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'scripts'
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


REMOTE_HOSTS = '''
let sentinel="701",gate="702",state=(0,r.un)(l.u,({get:e})=>{let t=e(a.Dc),{data:n}=e(s.I2,t);return allowed(n?.config,e(p.JW,gate))});function allowed(cfg,rollout){if(!0===cfg?.["features.remote_connections"])return!0;let features=cfg?.features;return null==features||"object"!=typeof features||Array.isArray(features)?rollout:Object.getOwnPropertyDescriptor(features,"remote_connections")?.value===!0||rollout}
'''


class RepairTests(unittest.TestCase):
    def test_no_overrides_fails_without_launching(self):
        from argparse import Namespace
        from unittest.mock import patch
        for scan_only in (False, True):
            with self.subTest(scan_only=scan_only), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / 'scripts'
                root.mkdir()
                launcher = root/'codex_zh_launch.py'
                launcher.write_bytes((ROOT/'codex_zh_launch.py').read_bytes())
                with patch.object(repair, 'ROOT', root), patch.object(repair, 'renderer_sources', return_value=[]), patch.object(repair.subprocess, 'run') as child:
                    status = repair.run(Namespace(asar='test.asar', scan_only=scan_only))
                child.assert_not_called()
                report = json.loads((root.parent/'output/logs/repair-report.json').read_text(encoding='utf-8'))
                self.assertNotEqual(status, 0)
                self.assertEqual(report['status'], 'failed')
                self.assertCountEqual(report['defaulted_features'], repair.ROLES)

    def test_partial_overrides_report_partial_after_successful_runtime_check(self):
        from argparse import Namespace
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'scripts'
            root.mkdir()
            (root/'codex_zh_launch.py').write_bytes((ROOT/'codex_zh_launch.py').read_bytes())
            logs = root.parent/'output/logs'
            policy = {role: {'mode': 'override' if role == 'ssh' else 'official-default'} for role in repair.ROLES}

            from contextlib import redirect_stdout
            from io import StringIO
            policy['ssh']['id'] = '702'

            def child(command, **kwargs):
                if command[1] != '-c':
                    self.assertEqual(command[2], '--repair')
                    self.assertEqual(Path(command[3]), Path('test.asar').resolve())
                    Path(command[4]).write_text(json.dumps({'status': 'passed', 'features': policy}), encoding='utf-8')
                return SimpleNamespace(returncode=0)

            output = StringIO()
            with patch.object(repair, 'ROOT', root), patch.object(repair, 'renderer_sources', return_value=[('remote.js', REMOTE_HOSTS)]), patch.object(repair.subprocess, 'run', side_effect=child), redirect_stdout(output):
                self.assertEqual(repair.run(Namespace(asar='test.asar', scan_only=False)), 0)
            report = json.loads((logs/'repair-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'partial')
            self.assertCountEqual(report['defaulted_features'], set(repair.ROLES) - {'ssh'})
            self.assertNotIn('previous', report)
            lines = output.getvalue().splitlines()
            self.assertIn('扫描清单（1/13 项命中）', lines)
            self.assertIn('启动核验清单（1/13 项通过）', lines)
            scan = [line for line in lines[1:14]]
            verified = lines[lines.index('启动核验清单（1/13 项通过）') + 1:][:13]
            for phase in (scan, verified):
                self.assertEqual([line.strip().split('：')[0] for line in phase], list(repair.ROLES))

    def test_shared_report_cannot_be_mistaken_for_this_repair(self):
        from argparse import Namespace
        from types import SimpleNamespace
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'scripts'
            root.mkdir()
            (root/'codex_zh_launch.py').write_bytes((ROOT/'codex_zh_launch.py').read_bytes())
            logs = root.parent/'output/logs'

            def child(command, **kwargs):
                if command[1] != '-c':
                    (logs/'verification.json').write_text('{"status":"passed"}', encoding='utf-8')
                return SimpleNamespace(returncode=0)

            with patch.object(repair, 'ROOT', root), patch.object(repair, 'renderer_sources', return_value=[('test.js', FIXTURE)]), patch.object(repair.subprocess, 'run', side_effect=child):
                self.assertEqual(repair.run(Namespace(asar='test.asar', scan_only=False)), 1)
            report = json.loads((logs/'repair-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'failed')
            self.assertNotIn('features', report)

    def test_reactive_mini_layout_needs_both_pets_branches(self):
        mini = ('M={collection:{id:"pets-collection"},visibility:{id:"pets-visibility"}},'
                'v=(0,n.un)(p.u,({get:e})=>e(x.JW,"703")),other=()=>{return false;},'
                'T=(0,n.un)(p.u,({get:e})=>{if(!e(f.P,"703"))return[M.pick,M.size,r.d];'
                'let t=[M.collection,M.createMini];return t})')
        self.assertEqual(repair.discover([('pets.js', mini)])[0], {'pets_layout': '703'})
        different = mini.replace('f.P,"703"', 'f.P,"704"')
        self.assertEqual(repair.discover([('pets.js', different)])[0], {})
        self.assertEqual(repair.discover([('pets.js', mini.replace('M.createMini', 'M.visibility'))])[0], {})

    def test_remote_host_rollout_binds_the_argument_to_its_id(self):
        found, _ = repair.discover([('remote.js', REMOTE_HOSTS)])
        self.assertEqual(found, {'ssh': '702'})
        changed = REMOTE_HOSTS.replace('e(p.JW,gate)', 'e(p.JW,sentinel)')
        self.assertEqual(repair.discover([('remote.js', changed)])[0], {'ssh': '701'})
        self.assertEqual(repair.discover([('a.js', REMOTE_HOSTS), ('b.js', changed)])[0], {})
        wrong = REMOTE_HOSTS.replace('allowed(n?.config', 'unrelated(n?.config')
        self.assertEqual(repair.discover([('remote.js', wrong)])[0], {})

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
            root = Path(directory) / 'scripts'
            root.mkdir()
            launcher = root/'codex_zh_launch.py'
            launcher.write_bytes(source)
            with patch.object(repair, 'ROOT', root), patch.object(repair, 'renderer_sources', return_value=[('test.js', FIXTURE)]), patch.object(repair.subprocess, 'run', side_effect=[None, RuntimeError('simulated child failure')]):
                self.assertEqual(repair.run(Namespace(asar='test.asar', scan_only=False)), 1)
            self.assertEqual(launcher.read_bytes(), source)
            report = json.loads((root.parent/'output/logs/repair-report.json').read_text(encoding='utf-8'))
            self.assertEqual(Path(report['backup']).parent, root.parent/'output/backups')
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
