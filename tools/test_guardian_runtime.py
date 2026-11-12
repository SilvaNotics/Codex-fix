"""Guardian diagnosis and installed official selector behavior."""
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from guardian_runtime import DIAGNOSTIC_JS, classify
from repair_codex import find_asar, renderer_sources


class GuardianRuntimeTests(unittest.TestCase):
    def test_mismatch_is_specific_and_not_success(self):
        result = classify({'hasEvaluations': False, 'cacheUserHashMatches': False,
                           'menus': [{'visible': True, 'text': '请求批准 完全访问'}]})
        self.assertEqual(result['menu_visibility'], 'absent')
        self.assertEqual(result['limitation'],
                         'official-evaluations-rejected-current-user-cache-mismatch')
        self.assertFalse(result['enablement_patch_available'])
        self.assertEqual(result['risk_review_service'], 'not-probed')

    def test_closed_menu_is_not_absent(self):
        self.assertEqual(classify({})['menu_visibility'], 'not-probed')

    def test_visible_is_independent_of_gate(self):
        result = classify({'gate': False, 'menus': [{'visible': True, 'text': '帮我批准'}]})
        self.assertEqual(result['menu_visibility'], 'visible')
        self.assertIsNone(result['limitation'])
        self.assertEqual(result['risk_review_service'], 'not-probed')

    def test_payload_never_writes_state(self):
        for forbidden in ('store.set(', 'updateUser', 'setData(', '$emt(',
                          'hasEvaluations =', 'location.reload', '.click('):
            self.assertNotIn(forbidden, DIAGNOSTIC_JS)

    def test_installed_official_selector_local_feature_is_insufficient(self):
        """Run the exact installed BFUY factory, mocking only its DBCl imports."""
        factory = None
        for name, source in renderer_sources(find_asar()):
            if '/244404.' not in name:
                continue
            start = source.index('BFUY(e,t,l){')
            end = source.index(',Y72c(', start)
            factory = source[start:end]
            break
        self.assertIsNotNone(factory, 'Current installed selector module absent')
        script = r'''
const factory=({FACTORY}).BFUY;
const db={L9S:(requirements)=>requirements?.only ?? ['auto','guardian-approvals','full-access'],
 bAH:config=>config?.features?.guardian_approval,
 NsC:()=> 'auto', Bnq:()=> 'user', bzb:()=>false, ic_:()=> 'auto'};
const exports={};const req=()=>db;
req.d=(target,a,b)=>Object.assign(target,b);
factory({},exports,req);
const base={isConfigDataPending:false,requirements:null,resolvedConfig:{features:{}},
 isGuardianApprovalEnabledByStatsig:false,showFullAccessInComposer:true};
const call=x=>exports.lS({...base,...x});
console.log(JSON.stringify({
 off:call({}), localTrue:call({resolvedConfig:{features:{guardian_approval:true}}}),
 published:call({isGuardianApprovalEnabledByStatsig:true}),
 explicitFalse:call({isGuardianApprovalEnabledByStatsig:true,resolvedConfig:{features:{guardian_approval:false}}}),
 managed:call({isGuardianApprovalEnabledByStatsig:true,requirements:{only:['auto']}})
}));
'''.replace('FACTORY', factory)
        completed = subprocess.run(['node', '-e', script], capture_output=True,
                                   text=True, timeout=20, check=True)
        states = json.loads(completed.stdout)
        self.assertFalse(states['off']['isGuardianModeAvailable'])
        self.assertFalse(states['localTrue']['isGuardianModeAvailable'])
        self.assertTrue(states['published']['isGuardianModeAvailable'])
        self.assertFalse(states['explicitFalse']['isGuardianModeAvailable'])
        self.assertFalse(states['managed']['isGuardianModeAvailable'])
        self.assertEqual(states['published']['configNonFullAccessMode'], 'auto')


if __name__ == '__main__':
    unittest.main()
