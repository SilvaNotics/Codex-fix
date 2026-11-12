import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))

class UiRolloutTests(unittest.TestCase):
    def test_parameter_patch_preserves_unrelated_layer_values(self):
        import json,subprocess
        import codex_zh_launch as launcher
        launcher.apply_feature_policy({'layer:enable_suggested_followups':'123'})
        js='global.window=global;global.setInterval=()=>0;global.setTimeout=()=>0;class Layer{constructor(name){this.name=name}get(k,d){return d}};const c={getLayer:n=>new Layer(n)};window.__STATSIG__={firstInstance:c};'+launcher.PATCH+';void window.__STATSIG__;console.log(JSON.stringify([c.getLayer("123").get("enable_suggested_followups",false),c.getLayer("123").get("enable_i18n",false),c.getLayer("999").get("enable_suggested_followups",false)]));'
        r=subprocess.run(['node','-e',js],capture_output=True,text=True,check=True,timeout=15)
        self.assertEqual(json.loads(r.stdout),[True,False,False])
        self.assertEqual(launcher.REQUIRED_GATES,())

    def test_learning_layers_require_exact_data_and_ui_sinks(self):
        import ui_rollouts
        from feature_census import inventory
        text='function card(){encoded_follow_up_actions;flatMap(ed).slice(0,3);c?.getLayer("123").get("enable_suggested_followups",!1)!==!0?null:(l=jsx(eu,{followUps:d,reference:r}));}'
        def discover(texts):
            rows,errors=inventory(texts)
            self.assertEqual(errors,[])
            return ui_rollouts.reviewed_layers(rows)
        self.assertEqual(discover([('x.js',text)]),{'layer:enable_suggested_followups':'123'})
        self.assertEqual(discover([('x.js',text.replace('followUps:','other:'))]),{})
        self.assertEqual(discover([('x.js',text),('y.js',text.replace('123','456'))]),{})

if __name__=='__main__':unittest.main()
