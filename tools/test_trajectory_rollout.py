"""Read-only trajectory proof regression tests, including opt-in installed ASAR."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import trajectory_rollout as rollout


def fixture(gate='805'):
    registry = ('({ChYf(e,t,n){n.d(t,{G:()=>h});var d=n("OMIV");let p=('
                + rollout.BUILDER + ')({"codex.trajectory-refresh":{statsig:["'
                + gate + '"]}}),h=atom(scope,' + rollout.EVALUATOR + ');}});')
    sdk = '''({OMIV(e,t,n){let d=atom(scope,(e,{get:t})=>t(s)?.getFeatureGate(e,{disableExposureLog:!0}).value??(0,a.wc)(e)?.value??!1);n.d(t,{},{JW:d});}});'''
    consumer = '''({UI(e,t,n){var l=n("zTeN"),i=n("zd8w"),r=n("ABep"),cap=n("ChYf"),ctx=n("QCUA");function View(){let q=(0,i.useContext)(ctx.b),K="activity"===q,mode=source(),eb=(0,l._U)("standard"===mode&&!K?cap.G:null,{name:"codex.trajectory-refresh"})?.isCapable===!0;return(0,r.jsxs)(ctx.b,{value:eb?"chat-refresh":q,children:[]})}}});'''
    return [('registry.js', registry), ('sdk.js', sdk), ('ui.js', consumer)]


class TrajectoryTests(unittest.TestCase):
    def test_positive_and_changed_id(self):
        for gate in ('805', '99887766'):
            with self.subTest(gate=gate):
                found, audit = rollout.discover(fixture(gate))
                self.assertEqual(found, {rollout.ROLE: gate})
                self.assertEqual(audit['decision'], 'approve')
                self.assertEqual(audit['evidence'][0]['offset_unit'], 'UTF-16 code units')

    def test_fail_closed_mutations(self):
        cases = [
            (0, 'statsig:["805"]', 'statsig:["805","806"]'),
            (0, 'statsig:["805"]', 'statsig:[computed]'),
            (0, 'statsig:["805"]', 'statsig:["805"],accessPolicy:"auth"'),
            (0, 'isCapable:!n&&t(d.JW,e)', 'isCapable:!n&&!t(d.JW,e)'),
            (0, 'isCapable:l.every', 'isCapable:l.some'),
            (1, '.value??(0,a.wc)', '.details??(0,a.wc)'),
            (2, 'n("ChYf")', 'n("Unrelated")'),
            (2, 'n("zTeN")', 'n("Lookalike")'),
            (2, 'cap.G:null', 'cap.BAD:null'),
            (2, 'isCapable===!0', 'isCapable===!1'),
            (2, 'value:eb?', 'value:!eb?'),
            (2, '"standard"===mode&&!K', '"standard"===mode&&K'),
            (2, 'value:eb?"chat-refresh":q', 'value:eb?q:"chat-refresh"'),
            (2, 'ctx.b,{value:', 'ctx.other,{value:'),
            (2, 'function View(){', 'function View(cap){'),
            (2, 'function View(){', 'function View(l){'),
            (2, ';return(0,r.jsxs)', ';eb=true;return(0,r.jsxs)'),
            (2, ';return(0,r.jsxs)', ';q="activity";return(0,r.jsxs)'),
            (2, ';return(0,r.jsxs)', ';function unrelated(){return(0,r.jsxs)'),
        ]
        for index, old, new in cases:
            with self.subTest(old=old, new=new):
                sources = fixture()
                name, text = sources[index]
                self.assertIn(old, text)
                sources[index] = name, text.replace(old, new)
                self.assertEqual(rollout.discover(sources)[0], {})

    def test_regex_braces_and_unrelated_sink_do_not_leak(self):
        sources = fixture()
        file, text = sources[-1]
        text = text.replace('value:eb?"chat-refresh":q', 'value:q')
        text += 'function Other(){let a=/{/,b=/}/;return jsx(ctx.b,{value:eb?"chat-refresh":q})}'
        sources[-1] = file, text
        self.assertEqual(rollout.discover(sources)[0], {})

    def test_ambiguous_module_rejected(self):
        sources = fixture()
        sources.append(('collision.js', sources[0][1].replace('"805"', '"806"')))
        self.assertEqual(rollout.discover(sources)[0], {})

    def test_parse_failure_rejected(self):
        sources = fixture() + [('broken.js', '"codex.trajectory-refresh";function {')]
        found, audit = rollout.discover(sources)
        self.assertEqual(found, {})
        self.assertTrue(audit['errors'])

    def test_format_and_local_rename(self):
        sources = [(f, (s.replace('eb', 'chosen').replace('cap', 'binding') if f == 'ui.js' else s).replace(';', ';\n'))
                   for f, s in fixture()]
        # Do not rename semantic property strings (isCapable etc.).
        self.assertEqual(rollout.discover(sources)[0], {rollout.ROLE: '805'})

    @unittest.skipUnless(os.environ.get('CODEX_TEST_INSTALLED_ASAR') == '1', 'opt-in installed ASAR scan')
    def test_installed_asar(self):
        from repair_codex import find_asar, renderer_sources
        asar = find_asar()
        before = asar.stat()
        found, audit = rollout.discover(renderer_sources(asar))
        self.assertEqual(found, {rollout.ROLE: '1527462160'})
        self.assertEqual(audit['errors'], [])
        self.assertEqual(len(audit['evidence']), 1)
        self.assertIn('/485738.', audit['evidence'][0]['consumer_file'])
        self.assertEqual((before.st_size, before.st_mtime_ns),
                         (asar.stat().st_size, asar.stat().st_mtime_ns))
        print('Installed ASAR:', asar, 'proof:', audit['evidence'])


if __name__ == '__main__':
    unittest.main()
