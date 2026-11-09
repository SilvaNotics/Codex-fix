import importlib.util
import sys
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from test_repair import FIXTURE

ROOT = Path(__file__).resolve().parents[1]

class PolicyTests(unittest.TestCase):
    def load(self):
        spec = importlib.util.spec_from_file_location('policy_launcher', ROOT/'codex_zh_launch.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def configure(self, text):
        module = self.load()
        from test_repair import repair
        with patch.dict(sys.modules, {'repair_codex': repair}), patch.object(repair, 'renderer_sources', return_value=[('fixture.js', text)]):
            module.configure_features('test.asar')
        return module

    def test_removed_dual_layout_defaults_only_layout(self):
        module = self.configure(FIXTURE.replace('return"legacy"', 'return"single-layout"'))
        self.assertNotIn('layout', module.ACTIVE_FEATURES)
        self.assertEqual(module.FEATURE_POLICY['layout']['mode'], 'official-default')
        self.assertEqual(module.REQUIRED_GATES, ('101', '102', '103'))
        # Execute generated JS: removed gate must not be forced (nor forced false).
        js = 'global.window={__STATSIG__:{firstInstance:{}}};\n' + module.PATCH + '\nconst a=window.__STATSIG__.firstInstance.overrideAdapter;console.log(JSON.stringify([a.getGateOverride({name:"104"}),a.getGateOverride({name:"101"}).value]));process.exit(0);'
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [None, True])
        state = {'patched': True, 'enable_i18n': True, 'lang': 'zh-CN', 'cjk': 30,
                 'gates': dict.fromkeys(module.REQUIRED_GATES, True)}
        self.assertEqual(module.verification_failures(state), [])

    def test_all_changed_defaults_not_chinese_required(self):
        module = self.configure('const completelyDifferentSDK = true;')
        self.assertEqual(module.REQUIRED_GATES, ())
        self.assertEqual(module.verification_failures({'patched': True}), [])
        self.assertTrue(all(x['mode'] == 'official-default' for x in module.FEATURE_POLICY.values()))

    def test_renamed_recover_and_version_changes(self):
        before = self.configure(FIXTURE)
        after = self.configure(FIXTURE.replace('104', '904'))
        self.assertIn('904', after.REQUIRED_GATES)
        self.assertNotEqual(before.PATCH_VERSION, after.PATCH_VERSION)

    def test_collision_defaults_both(self):
        module = self.configure(FIXTURE.replace('102', '101'))
        self.assertNotIn('computer_use', module.ACTIVE_FEATURES)
        self.assertNotIn('browser_use_external', module.ACTIVE_FEATURES)

if __name__ == '__main__':
    unittest.main()
