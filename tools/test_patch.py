"""Exercise the actual injected JS, without launching Codex."""
import ast
import json
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

def literal(name):
    tree = ast.parse((ROOT / 'codex_zh_launch.py').read_text(encoding='utf-8'))
    return next(ast.literal_eval(n.value) for n in tree.body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))

class PatchTest(unittest.TestCase):
    def test_official_layout_gate_and_existing_features(self):
        # The SDK namespace is assigned after injection, as in a fresh renderer.
        script = '''global.window=global;global.setInterval=()=>0;global.setTimeout=()=>0;
        ''' + literal('PATCH') + '''
        const c={_memoCache:{stale:true}};
        window.__STATSIG__={firstInstance:c};
        const result={};
        for (const id of ['3085093835','1506311413','410065390','410262010','unknown'])
          result[id]=c.overrideAdapter.getGateOverride({name:id})?.value??null;
        result.cache=Object.keys(c._memoCache).length;
        console.log(JSON.stringify(result));'''
        p = subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True)
        values = json.loads(p.stdout)
        self.assertIs(values['3085093835'], True, 'official navigation must not fall back to legacy')
        for gate in ['1506311413','410065390','410262010']:
            self.assertIs(values[gate], True)
        self.assertIsNone(values['unknown'], 'unrelated gates must remain server controlled')
        self.assertEqual(values['cache'], 0)

if __name__ == '__main__':
    unittest.main()
