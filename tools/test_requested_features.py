"""Offline structural discovery and runtime policy regression tests."""
import json
import subprocess
import unittest
from test_repair import repair
import test_policy

DICTATION = '''
if(!navigator?.mediaDevices?.getUserMedia||"u"<typeof MediaRecorder)return{isLoading:!1,isError:!1,isCapable:!1};let t=e(p.dx,"602"),n=e(p.JW,"602"),{authLoading:r,authMethod:i}=e(l.PO),a=r||t;return{isLoading:a,isError:!1,isCapable:!a&&n&&"chatgpt"===i}
"dictation.global":{accessPolicy:"global-dictation",statsig:["602","603"],supportedClients:["electron"]}
'''


TOYS = 'toys:{statsig:["601"],supportedClients:["electron"],children:{"toys.audio-visualizer":{settings:[i.JW5.audioVisualizerEnabled.key]},"toys.confetti":{settings:[i.JW5.confettiEnabled.key]}}}'

PETS = '''
function collection(e){let{collectionSection:r,onCreateStart:l,onCreateCloudPet:o}=e;return r}
function legacy(){return(0,n.jsx)(page,{title:(0,n.jsx)(title,{slug:"pets"}),children:(0,n.jsx)(collection,{})})}
function action(){return visible?"settings.mini.hide":"settings.mini.show"}
function mini(){return(0,n.jsxs)(page,{action:(0,n.jsx)(action,{}),id:"settings.pets.visibility",children:(0,n.jsx)(collection,{collectionSection:custom})})}
function selector(){return(0,s.Zj)("604")?(0,n.jsx)(mini,{}):(0,n.jsx)(legacy,{})}
'''

class RequestedFeatures(unittest.TestCase):
    def test_pets_layout_resolves_both_component_branches(self):
        found, evidence = repair.discover([('pets.js', PETS)])
        self.assertEqual(found.get('pets_layout'), '604')
        self.assertEqual(evidence['pets_layout'][0]['file'], 'pets.js')
        # Other consumers of the same ID and nearby unrelated reads are not selectors.
        decoys = 'function useMiniLanguage(){return(0,s.Zj)("999")} (0,s.Zj)("2635985366");'
        self.assertEqual(repair.discover([('pets.js', decoys + PETS)])[0].get('pets_layout'), '604')
        self.assertNotIn('pets_layout', repair.discover([('pets.js', decoys + PETS.replace(
            'function selector(){return(0,s.Zj)("604")?(0,n.jsx)(mini,{}):(0,n.jsx)(legacy,{})}', ''))])[0])
        renamed = PETS.replace('604', '704').replace('mini', 'newMini').replace('legacy', 'oldPets')
        # Preserve semantic message IDs while renaming component symbols.
        renamed = renamed.replace('settings.newMini.', 'settings.mini.')
        self.assertEqual(repair.discover([('new.js', renamed)])[0].get('pets_layout'), '704')

    def test_pets_regex_braces_cannot_borrow_unrelated_visibility(self):
        text = PETS.replace('id:"settings.pets.visibility",', '')
        text = text.replace('function mini(){', 'function mini(){const pattern=/{/;')
        text += 'function unrelated(){const pattern=/}/;return "settings.pets.visibility"}'
        found, evidence = repair.discover([('regex.js', text)])
        self.assertNotIn('pets_layout', found)
        self.assertEqual(evidence['pets_layout'], [])

    def test_component_resolution_cached_per_chunk_including_empty_bodies(self):
        from collections import Counter
        from unittest.mock import patch
        # Missing is shared by both branches, so its empty result is reusable too.
        text = PETS.replace('(collection,{})', '(collection,{children:(0,n.jsx)(missing,{})})')
        text = text.replace('(collection,{collectionSection:custom})',
                            '(collection,{collectionSection:custom,children:(0,n.jsx)(missing,{})})')
        text += 'function secondSelector(){return(0,s.Zj)("604")?(0,n.jsx)(mini,{}):(0,n.jsx)(legacy,{})}'
        sources = [('a.js', text), ('b.js', text)]
        expected = repair.discover(sources)
        with patch.object(repair, 'component_body', wraps=repair.component_body) as resolve:
            self.assertEqual(repair.discover(sources), expected)
        self.assertEqual(Counter(call.args[1] for call in resolve.call_args_list),
                         Counter({'mini': 2, 'legacy': 2, 'collection': 2, 'missing': 2, 'page': 2, 'action': 2}))
        self.assertEqual([row['file'] for row in expected[1]['pets_layout']],
                         ['a.js', 'a.js', 'b.js', 'b.js'])

    def test_pets_layout_defaults_on_missing_misbound_or_ambiguous_structure(self):
        variants = [
            PETS.replace('settings.pets.visibility', 'other'),
            PETS.replace('settings.mini.hide', 'other'),
            PETS.replace('slug:"pets"', 'slug:"other"'),
            PETS.replace('(collection,{})', '(unrelated,{})'),
            PETS.replace('(mini,{})', '(unrelated,{})'),
            PETS.replace('onCreateCloudPet:', 'other:'),
            PETS.replace('?(0,n.jsx)(mini,{}):(0,n.jsx)(legacy,{})',
                         '?(0,n.jsx)(legacy,{}):(0,n.jsx)(mini,{})'),
            PETS + 'function mini(){return "unrelated"}',
            PETS + PETS.replace('604', '704').replace('mini', 'secondMini').replace('legacy', 'secondLegacy')
                .replace('collection', 'secondCollection').replace('action', 'secondAction')
                .replace('secondCollectionSection', 'collectionSection')
                .replace('settings.secondMini.', 'settings.mini.'),
        ]
        for text in variants:
            with self.subTest(text=text):
                module = test_policy.PolicyTests().configure(TOYS + DICTATION + text)
                self.assertEqual(module.FEATURE_POLICY['pets_layout']['mode'], 'official-default')
                self.assertEqual(set(module.REQUIRED_GATES), {'601', '602', '603'})
        # Distinct IDs in separately valid entries must also fail closed.
        found, _ = repair.discover([('a.js', PETS), ('b.js', PETS.replace('604', '704'))])
        self.assertNotIn('pets_layout', found)

    def test_pets_layout_actual_patch_only_overrides_selected_gate(self):
        for gate in ('604', '704'):
            module = test_policy.PolicyTests().configure(TOYS + DICTATION + PETS.replace('604', gate))
            self.assertEqual(module.FEATURE_POLICY['pets_layout'],
                             {'mode': 'override', 'id': gate, 'reason': 'unique-structural-match'})
            js = '''global.window=global;global.setInterval=()=>0;global.setTimeout=()=>0;
const prefs={petVisible:false,petVisibility:'on-demand'};
const previous={getGateOverride:g=>({name:g.name,value:false,ruleID:'previous'})};
const c={overrideAdapter:previous};window.__STATSIG__={firstInstance:c};
''' + module.PATCH + '''
void window.__STATSIG__;
const ids=''' + json.dumps([gate, '601', '602', '603', '2635985366', '1655510532', '2380644311', '1532120159']) + ''';
console.log(JSON.stringify({values:ids.map(name=>c.overrideAdapter.getGateOverride({name}).value),prefs,
untouched:c.overrideAdapter.getGateOverride({name:'2635985366'}).ruleID}));'''
            result = subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True, timeout=15)
            result = json.loads(result.stdout)
            self.assertEqual(result['values'], [True, True, True, True, False, False, False, False])
            self.assertEqual(result['prefs'], {'petVisible': False, 'petVisibility': 'on-demand'})
            self.assertEqual(result['untouched'], 'previous')
            self.assertEqual(module.verification_failures(
                {'patched': True, 'gates': dict.fromkeys(module.REQUIRED_GATES, True)}), [])
        module = test_policy.PolicyTests().configure(TOYS + PETS.replace('604', '601'))
        self.assertNotIn('pets_layout', module.ACTIVE_FEATURES)
        self.assertNotIn('toys', module.ACTIVE_FEATURES)

    def test_confetti_rollout_bound_to_local_setting(self):
        found, evidence = repair.discover([('toys.js', TOYS)])
        self.assertEqual(found.get('toys'), '601')
        self.assertEqual(evidence['toys'][0]['file'], 'toys.js')
        changed = TOYS.replace('601', '701').replace('JW5', 'renamed')
        self.assertEqual(repair.discover([('new.js', changed)])[0].get('toys'), '701')
        self.assertNotIn('toys', repair.discover([('bad.js', TOYS.replace('confettiEnabled', 'other'))])[0])

    def test_dictation_gate_requires_media_auth_and_global_agreement(self):
        found, _ = repair.discover([('dictation.js', DICTATION)])
        self.assertEqual(found.get('dictation'), '602')
        self.assertEqual(found.get('dictation_global'), '603')
        renamed = DICTATION.replace('602', '702').replace('603', '703').replace('p.JW', 'p.renamed')
        self.assertEqual(repair.discover([('new.js', renamed)])[0]['dictation'], '702')
        self.assertNotIn('dictation', repair.discover([('bad.js', DICTATION.replace('getUserMedia', 'unrelated'))])[0])
        self.assertNotIn('dictation', repair.discover([('bad.js', DICTATION.replace('["602","603"]', '["999","603"]'))])[0])

    def test_global_dictation_scanned_lazily_once_per_chunk_with_duplicate_evidence(self):
        from unittest.mock import patch
        text = DICTATION + DICTATION
        sources = [('a.js', text), ('b.js', text), ('unused.js', '"dictation.global"')]
        expected = repair.discover(sources)
        with patch.object(repair, 'anchored_matches', wraps=repair.anchored_matches) as search:
            self.assertEqual(repair.discover(sources), expected)
        globals_searched = [call for call in search.call_args_list if call.args[2] == '"dictation.global"']
        self.assertEqual(len(globals_searched), 2)
        offsets = [text.index('if(!navigator'), text.index('if(!navigator', len(DICTATION))]
        for role, gate in [('dictation', '602'), ('dictation_global', '603')]:
            self.assertEqual(expected[1][role], [
                {'id': gate, 'file': filename, 'offset': offset}
                for filename in ('a.js', 'b.js') for offset in offsets for _ in range(2)])
        # Empty results must also be cached; chunks without media need no scan.
        with patch.object(repair, 'anchored_matches', wraps=repair.anchored_matches) as search:
            self.assertNotIn('dictation', repair.discover([('empty.js', text.replace('dictation.global', 'other'))])[0])
        self.assertEqual(sum(call.args[2] == '"dictation.global"' for call in search.call_args_list), 1)

    def test_node_subprocesses_have_bounded_timeout(self):
        import ast
        from pathlib import Path
        tree = ast.parse(Path(__file__).read_text(encoding='utf-8'))
        runs = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == 'run']
        self.assertEqual(len(runs), 2)
        for run in runs:
            keywords = {item.arg: item.value for item in run.keywords}
            self.assertIn('timeout', keywords)
            self.assertGreater(ast.literal_eval(keywords['timeout']), 0)
            self.assertLessEqual(ast.literal_eval(keywords['timeout']), 30)

    def test_policy_runtime_preserves_opt_outs_and_unrelated_gates(self):
        module = test_policy.PolicyTests().configure(TOYS + DICTATION)
        self.assertEqual(set(module.REQUIRED_GATES), {'601', '602', '603'})
        self.assertEqual(module.FEATURE_POLICY['pets_layout']['mode'], 'official-default')
        js = '''global.window=global;global.setInterval=()=>0;global.setTimeout=()=>0;
const prefs={confettiEnabled:false,petVisible:false};
const previous={getGateOverride(g){return {name:g.name,value:false}}};
const c={overrideAdapter:previous};window.__STATSIG__={firstInstance:c};
''' + module.PATCH + '''
void window.__STATSIG__;
const gate=id=>c.overrideAdapter.getGateOverride({name:id}).value;
console.log(JSON.stringify({gates:['601','602','603','2380644311','1655510532','1532120159'].map(gate),prefs,
confetti:gate('601')&&prefs.confettiEnabled}));'''
        result = subprocess.run(['node', '-e', js], capture_output=True, text=True, check=True, timeout=15)
        values = json.loads(result.stdout)
        self.assertEqual(values['gates'], [True, True, True, False, False, False])
        self.assertEqual(values['prefs'], {'confettiEnabled': False, 'petVisible': False})
        self.assertFalse(values['confetti'])
        state = {'patched': True, 'gates': dict.fromkeys(module.REQUIRED_GATES, True)}
        self.assertEqual(module.verification_failures(state), [])
        state['gates']['603'] = False
        self.assertEqual(module.verification_failures(state), ['gate:603'])

    def test_each_requested_role_falls_back_on_ambiguity_or_missing(self):
        text = TOYS + DICTATION
        module = test_policy.PolicyTests().configure(text + TOYS.replace('601', '701'))
        self.assertEqual(module.FEATURE_POLICY['toys']['mode'], 'official-default')
        self.assertEqual(set(module.REQUIRED_GATES), {'602', '603'})
        module = test_policy.PolicyTests().configure(text.replace('getUserMedia', 'unrelated'))
        self.assertEqual(set(module.REQUIRED_GATES), {'601'})
        module = test_policy.PolicyTests().configure(text + DICTATION.replace('603', '703'))
        self.assertEqual(module.FEATURE_POLICY['dictation_global']['mode'], 'official-default')
        self.assertEqual(set(module.REQUIRED_GATES), {'601', '602'})
        self.assertNotEqual(module.PATCH_VERSION, test_policy.PolicyTests().configure(text).PATCH_VERSION)
        module = test_policy.PolicyTests().configure(text.replace('601', '602'))
        self.assertNotIn('toys', module.ACTIVE_FEATURES)
        self.assertNotIn('dictation', module.ACTIVE_FEATURES)
        # Global must not be partially forced after its shared composer gate is rejected.
        self.assertNotIn('dictation_global', module.ACTIVE_FEATURES)

if __name__ == '__main__':
    unittest.main()
