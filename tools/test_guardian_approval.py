"""Guardian rollout discovery; does not select a permissions mode."""
import json
import subprocess
import unittest
from test_repair import repair
import test_policy

MAPPING = '{gateName:"805",featureKey:"guardian_approval"}'


class GuardianApprovalTests(unittest.TestCase):
    def test_exact_mapping_tracks_id_changes_and_rejects_decoys(self):
        for gate in ('805', '3902016271'):
            text = ('{gateName:"999",featureKey:"other"},' +
                    MAPPING.replace('805', gate) +
                    ';const defaultMode=(0,s.Zj)("1597774583");')
            found, evidence = repair.discover([('execution.js', text)])
            self.assertEqual(found, {'guardian_approval': gate})
            self.assertEqual(evidence['guardian_approval'][0]['offset'], text.index('{gateName:"' + gate))
        for text in ('guardian_approval', MAPPING.replace('featureKey', 'other'),
                     MAPPING.replace('guardian_approval', 'guardian_approval_default'),
                     '{gateName:"805"};{featureKey:"guardian_approval"}'):
            self.assertNotIn('guardian_approval', repair.discover([('decoy.js', text)])[0])

    def test_missing_ambiguous_or_colliding_mapping_defaults(self):
        for text in ('', MAPPING + MAPPING.replace('805', '806'),
                     MAPPING + 'toys:{statsig:["805"],supportedClients:["electron"],children:{"toys.audio-visualizer":{settings:[i.JW5.audioVisualizerEnabled.key]},"toys.confetti":{settings:[i.JW5.confettiEnabled.key]}}}'):
            module = test_policy.PolicyTests().configure(text)
            self.assertNotIn('guardian_approval', module.ACTIVE_FEATURES)
            self.assertEqual(module.FEATURE_POLICY['guardian_approval']['mode'], 'official-default')

    def test_report_does_not_claim_publication_menu_or_service_verified(self):
        for text in (MAPPING, ''):
            policy = test_policy.PolicyTests().configure(text).FEATURE_POLICY['guardian_approval']
            self.assertEqual(policy['verification_scope'], 'rollout-gate-only')
            for field in ('official_publication', 'menu_visibility', 'risk_review_service'):
                self.assertEqual(policy[field], 'not-probed')

    def test_actual_patch_preserves_default_selection_and_other_gate_overrides(self):
        module = test_policy.PolicyTests().configure(MAPPING)
        self.assertEqual(module.REQUIRED_GATES, ('805',))
        js = '''global.window=global;global.setInterval=()=>0;global.setTimeout=()=>0;
const preferences={mode:'full-access'};
const c={overrideAdapter:{getGateOverride:g=>({value:false,ruleID:'previous'})}};
window.__STATSIG__={firstInstance:c};
''' + module.PATCH + '''
void window.__STATSIG__;
console.log(JSON.stringify({rollout:c.overrideAdapter.getGateOverride({name:'805'}).value,
defaultMode:c.overrideAdapter.getGateOverride({name:'1597774583'}),preferences}));
'''
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True, timeout=15)
        state = json.loads(result.stdout)
        self.assertTrue(state['rollout'])
        self.assertEqual(state['defaultMode'], {'value': False, 'ruleID': 'previous'})
        self.assertEqual(state['preferences'], {'mode': 'full-access'})
        self.assertEqual(module.verification_failures({'patched': True, 'gates': {'805': True}}), [])


if __name__ == '__main__':
    unittest.main()
