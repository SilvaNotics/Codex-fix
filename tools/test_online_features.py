"""Regression tests for bundled local settings and SDK coexistence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('online_repair', ROOT/'repair_codex.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)

FIXTURE = '''
let s=(0,r.un)(u.u,({get:e})=>{let t=e(a.b),n=e(g.JW,"4114442250");if(!0===t?.config["features.remote_connections"])return!0;let i=t?.config.features;return null==i||"object"!=typeof i||Array.isArray(i)?n:Object.getOwnPropertyDescriptor(i,"remote_connections")?.value===!0||n});
let d=(0,r.un)(u.u,({get:e})=>{let t=e(p.IU);if(!supported(t)||!e(g.JW,"1304276663")||"windows"===t&&!e(g.JW,"2124127696"))return!1;let n=e(requirements);return null!=n&&n.allowAppshots!==!1});
'''

class OnlineFeatures(unittest.TestCase):
    def test_discovers_local_features_without_relaxing_policy(self):
        found, evidence = repair.discover([('fixture.js', FIXTURE)])
        self.assertEqual(found.get('ssh'), '4114442250')
        self.assertEqual(found.get('appshots'), '1304276663')
        self.assertEqual(found.get('appshots_windows'), '2124127696')
        found, _ = repair.discover([('fixture.js', FIXTURE.replace('allowAppshots', 'unrelated'))])
        self.assertNotIn('appshots', found)
        found, _ = repair.discover([('fixture.js', FIXTURE.replace('4114442250', '9114442250').replace('1304276663', '9304276663').replace('2124127696', '9124127696'))])
        self.assertEqual(found['ssh'], '9114442250')
        self.assertEqual(found['appshots_windows'], '9124127696')
        found, _ = repair.discover([('one.js', FIXTURE), ('two.js', FIXTURE.replace('4114442250', '999'))])
        self.assertNotIn('ssh', found)

    def test_preserves_existing_override_adapter(self):
        spec = importlib.util.spec_from_file_location('online_launcher', ROOT/'codex_zh_launch.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        js = '''global.window=global;global.setInterval=()=>0;global.setTimeout=()=>0;
const original={getGateOverride(g){return g.name==='vendor'?{value:true}:null},getExperimentOverride(){return {value:'vendor-experiment'}}};
const c={overrideAdapter:original};window.__STATSIG__={firstInstance:c};
''' + launcher.PATCH + '''
void window.__STATSIG__;
console.log(JSON.stringify({vendor:c.overrideAdapter.getGateOverride({name:'vendor'}),experiment:c.overrideAdapter.getExperimentOverride({name:'test'}),local:c.overrideAdapter.getGateOverride({name:'1506311413'})}));'''
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True)
        values = json.loads(result.stdout)
        self.assertEqual(values['vendor'], {'value': True})
        self.assertEqual(values['experiment'], {'value': 'vendor-experiment'})
        self.assertTrue(values['local']['value'])

    def test_generated_patch_enables_settings_without_changing_policy(self):
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('generated_launcher', ROOT/'codex_zh_launch.py')
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        import sys
        with patch.dict(sys.modules, {'repair_codex': repair}), patch.object(repair, 'renderer_sources', return_value=[('fixture.js', FIXTURE)]):
            launcher.configure_features('fixture.asar')
        js = '''global.window=global;global.setInterval=()=>0;global.setTimeout=()=>0;
''' + launcher.PATCH + '''
const c={};window.__STATSIG__={firstInstance:c};
const gate=id=>c.overrideAdapter.getGateOverride({name:id})?.value===true;
const ssh=gate('4114442250');
const appshot=(allow,native)=>gate('1304276663')&&gate('2124127696')&&allow!==false&&native;
console.log(JSON.stringify([ssh,appshot(true,true),appshot(false,true),appshot(true,false)]));'''
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [True, True, False, False])

if __name__ == '__main__':
    unittest.main()
