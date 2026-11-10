"""Offline path regressions; never execute CDP utility entry points."""
import ast
import os
from pathlib import Path
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parent


def port_reader(name, path):
    tree = ast.parse((TOOLS/name).read_text(encoding='utf-8'))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == '_port')
    namespace = {'os': os, '__file__': str(path)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), name, 'exec'), namespace)
    return namespace['_port']


class ToolPathsTests(unittest.TestCase):
    def test_cdp_utilities_read_shared_output_logs_port(self):
        for name in ('cdp_shot.py', 'eval_js.py'):
            with self.subTest(tool=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root/'tools').mkdir()
                logs = root/'output/logs'
                logs.mkdir(parents=True)
                (logs/'cdp_port.txt').write_text('45678\n', encoding='utf-8')
                # Old files must not override the current layout's port.
                (root/'tools/cdp_port.txt').write_text('12345', encoding='utf-8')
                (root/'cdp_port.txt').write_text('23456', encoding='utf-8')
                self.assertEqual(port_reader(name, root/'tools'/name)(), 45678)

    def test_cdp_utilities_use_default_when_shared_port_is_unavailable(self):
        for name in ('cdp_shot.py', 'eval_js.py'):
            with self.subTest(tool=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                logs = root/'output/logs'
                logs.mkdir(parents=True)
                read = port_reader(name, root/'tools'/name)
                self.assertEqual(read(), 9333)
                (logs/'cdp_port.txt').write_text('invalid', encoding='utf-8')
                self.assertEqual(read(), 9333)


if __name__ == '__main__':
    unittest.main()
