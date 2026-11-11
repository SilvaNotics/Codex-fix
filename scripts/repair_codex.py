"""Conservative, standalone Codex launcher ID rediscovery (stdlib only).
Never writes the official ASAR or account configuration. No network required.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
ROLES = ('computer_use', 'browser_use_external', 'browser_use', 'layout', 'i18n',
         'ssh', 'appshots', 'appshots_windows', 'toys', 'dictation', 'dictation_global', 'pets_layout')


def renderer_sources(path):
    with Path(path).open('rb') as stream:
        prefix = stream.read(16)
        if len(prefix) != 16:
            raise ValueError('Invalid ASAR header')
        _, size, _, length = struct.unpack('<4I', prefix)
        if not 0 < length <= 64 * 1024 * 1024:
            raise ValueError('Invalid ASAR JSON size')
        header = json.loads(stream.read(length))
        def walk(node, prefix=''):
            for name, item in node.get('files', {}).items():
                name = prefix + '/' + name
                if 'files' in item:
                    yield from walk(item, name)
                elif name.startswith('/webview/') and name.endswith('.js') and not item.get('unpacked'):
                    yield name, item
        for name, item in walk(header):
            stream.seek(8 + size + int(item['offset']))
            body = stream.read(item['size'])
            if len(body) != item['size']:
                raise ValueError('Truncated ASAR entry')
            yield name, body.decode('utf-8')


def anchored_matches(pattern, text, anchor, before, after):
    """Search bounded semantic neighborhoods, retaining original offsets."""
    start = 0
    seen = set()
    while (position := text.find(anchor, start)) >= 0:
        left = max(0, position - before)
        right = min(len(text), position + len(anchor) + after)
        for match in re.finditer(pattern, text[left:right]):
            offset = left + match.start()
            if offset not in seen:
                seen.add(offset)
                yield match, offset
        start = position + len(anchor)


def component_body(text, name):
    """Resolve one named declaration, respecting braces in strings/comments.

    Duplicate declarations in a chunk are ambiguous (never guess module scope).
    Non-comment slashes (regex or division) are deliberately unsupported: without
    a full JS lexer their braces could cross function boundaries. Fail closed.
    """
    declarations = list(re.finditer(r'\bfunction ' + re.escape(name) + r'\([^()]*\)\{', text))
    if len(declarations) != 1:
        return ''
    start = declarations[0].end()
    token = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`|/\*[\s\S]*?\*/|//[^\n]*|[{}/]''')
    depth = 1
    for match in token.finditer(text, start):
        if match[0] == '/':
            return ''
        if match[0] == '{':
            depth += 1
        elif match[0] == '}':
            depth -= 1
            if not depth:
                return text[start:match.start()]
    return ''


def discover(sources):
    """Match multiple semantic anchors, not minified module/variable names.

    These intentionally narrow recipes may stop on new minifier structures.
    Unique matches are evidence of structural similarity, not proof of semantics.
    """
    evidence = {role: [] for role in ROLES}
    ident = r'[A-Za-z_$][\w$]*'
    call = rf'\(0,{ident}\.{ident}\)\("(\d+)"\)'
    for filename, text in sources:
        # Cheap semantic anchors avoid running broad regexes over unrelated chunks.
        for role in ROLES[:3]:
            if 'featureName:"' + role + '"' not in text:
                continue
            # Current renderer: gate read immediately before memo bookkeeping
            # and the corresponding featureName. Never use nearest arbitrary ID.
            pattern = call + r'[^;]{0,240}?;[^;]{0,240}?featureName:"' + role + '"'
            for match in re.finditer(pattern, text):
                evidence[role].append({'id': match.group(1), 'file': filename, 'offset': match.start()})
        pattern = call + r';[^;]{0,180}?\.get\("enable_i18n",!1\)[^;]{0,160};[^;]{0,180}?\.get\("locale_source","IDE"\)'
        for match in re.finditer(pattern, text):
            evidence['i18n'].append({'id': match.group(1), 'file': filename, 'offset': match.start()})
        # Require both the unsupported-auth gate guard and the actual legacy/rail
        # layout selector to reference exactly the same ID in the same JS entry.
        guard = rf'if\(!{ident}\({ident}\.{ident},"(\d+)"\)\)return!1;let {ident}={ident}\({ident}\.{ident}\);return"denied"!=={ident}\.status\|\|"unsupported-auth"!=={ident}\.reason'
        for match in re.finditer(guard, text):
            gate = match.group(1)
            selector = rf'{ident}=\(0,{ident}\.{ident}\)\({ident}\.{ident},\(\{{get:{ident}\}}\)=>{ident}\({ident}\.{ident},"{gate}"\)\).{{0,1100}}?return"legacy";.{{0,300}}?return"rail-only"'
            if any(anchored_matches(selector, text, 'return"rail-only"', 2400, 40)):
                evidence['layout'].append({'id': gate, 'file': filename, 'offset': match.start()})
        # Bind the rollout read to the SSH config OR chain, not a nearby ID.
        ssh = (rf'({ident})=({ident})\({ident}\.JW,"(\d+)"\);'
               rf'if\(!0===({ident})\?\.config\["features\.remote_connections"\]\)return!0;'
               rf'let ({ident})=\4\?\.config\.features;return null==\5\|\|"object"!=typeof \5\|\|'
               rf'Array\.isArray\(\5\)\?\1:Object\.getOwnPropertyDescriptor\(\5,"remote_connections"\)\?\.value===!0\|\|\1')
        for match, offset in anchored_matches(ssh, text, 'features.remote_connections', 800, 1000):
            evidence['ssh'].append({'id': match.group(3), 'file': filename, 'offset': offset})
        # Keep allowAppshots and native-supported checks in the vendor code.
        appshots = (rf'if\(!{ident}\(({ident})\)\|\|!({ident})\(({ident})\.JW,"(\d+)"\)'
                    rf'\|\|"windows"===\1&&!\2\(\3\.JW,"(\d+)"\)\)return!1;'
                    rf'.{{0,260}}?allowAppshots!==!1')
        for match, offset in anchored_matches(appshots, text, 'allowAppshots!==!1', 1000, 50):
            for role, group in [('appshots', 4), ('appshots_windows', 5)]:
                evidence[role].append({'id': match.group(group), 'file': filename, 'offset': offset})
        toys = (r'toys:\{statsig:\["(\d+)"\],supportedClients:\["electron"\],children:\{'
                rf'"toys.audio-visualizer":\{{settings:\[{ident}\.{ident}\.audioVisualizerEnabled\.key\]\}},'
                rf'"toys.confetti":\{{settings:\[{ident}\.{ident}\.confettiEnabled\.key\]\}}\}}\}}')
        for match, offset in anchored_matches(toys, text, '"toys.confetti"', 450, 150):
            evidence['toys'].append({'id': match.group(1), 'file': filename, 'offset': offset})
        # This is a dual-layout gate, not a settings-entry or visibility gate.
        # Resolve BOTH selected components and their shared pet collection.
        if '"settings.pets.visibility"' in text and '"settings.mini.show"' in text:
            bodies = {}
            def body(name):
                if name not in bodies:
                    bodies[name] = component_body(text, name)
                return bodies[name]
            jsx = rf'\(0,{ident}\.jsxs?\)\(({ident}),\{{'
            selector = (r'function ' + ident + r'\(\)\{return' + call +
                        rf'\?\(0,{ident}\.jsx\)\(({ident}),\{{\}}\)'
                        rf':\(0,{ident}\.jsx\)\(({ident}),\{{\}}\)\}}')
            for match in re.finditer(selector, text):
                new = body(match.group(2))
                old = body(match.group(3))
                if '"settings.pets.visibility"' not in new or 'slug:"pets"' not in old:
                    continue
                new_refs = set(re.findall(jsx, new))
                old_refs = set(re.findall(jsx, old))
                collections = [name for name in new_refs & old_refs
                               if all(marker in body(name)
                                      for marker in ('collectionSection:', 'onCreateStart:', 'onCreateCloudPet:'))]
                actions = [body(name) for name in new_refs - old_refs]
                if len(collections) != 1 or not any('"settings.mini.show"' in body and
                                                       '"settings.mini.hide"' in body for body in actions):
                    continue
                evidence['pets_layout'].append({'id': match.group(1), 'file': filename,
                                                'offset': match.start(),
                                                'new_component': match.group(2),
                                                'old_component': match.group(3),
                                                'collection_component': collections[0]})
        # Composer rollout: bind loading/value reads, media support and ChatGPT auth.
        # Require independent agreement with the named global capability's first gate.
        media = (rf'if\(!navigator\?\.mediaDevices\?\.getUserMedia\|\|"u"<typeof MediaRecorder\)'
                 rf'return\{{isLoading:!1,isError:!1,isCapable:!1\}};let ({ident})=({ident})\(({ident})\.{ident},"(\d+)"\),'
                 rf'({ident})=\2\(\3\.{ident},"\4"\),\{{authLoading:({ident}),authMethod:({ident})\}}=\2\({ident}\.{ident}\),'
                 rf'({ident})=\6\|\|\1;return\{{isLoading:\8,isError:!1,isCapable:!\8&&\5&&"chatgpt"===\7\}}')
        global_dictation = r'"dictation.global":\{accessPolicy:"global-dictation",statsig:\["(\d+)","(\d+)"\],supportedClients:\["electron"\]\}'
        capabilities = None
        for match, offset in anchored_matches(media, text, 'getUserMedia', 30, 650):
            if capabilities is None:
                capabilities = list(anchored_matches(global_dictation, text, '"dictation.global"', 0, 220))
            for capability, _ in capabilities:
                if match.group(4) == capability.group(1):
                    for role, gate in [('dictation', match.group(4)), ('dictation_global', capability.group(2))]:
                        evidence[role].append({'id': gate, 'file': filename, 'offset': offset})
    found = {}
    for role, rows in evidence.items():
        ids = {row['id'] for row in rows}
        if len(ids) == 1:
            found[role] = next(iter(ids))
    # Shared IDs across unrelated roles cannot be safely forced.
    from collections import Counter
    counts = Counter(found.values())
    found = {role: value for role, value in found.items() if counts[value] == 1}
    if 'dictation' not in found:
        found.pop('dictation_global', None)
    return found, evidence


def current_ids(source):
    tree = ast.parse(source)
    literals = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('PATCH', 'REQUIRED_GATES'):
                    literals[target.id] = ast.literal_eval(node.value)
    gates = literals['REQUIRED_GATES']
    if len(gates) != 4:
        raise ValueError('Unsupported launcher gate structure')
    layer = re.search(r'const LAYER = "(\d+)"', literals['PATCH']).group(1)
    return dict(zip(ROLES, [*gates, layer]))


def updated_source(source, found):
    old = current_ids(source)
    if set(found) != set(ROLES[:5]) or len(set(found.values())) != 5:
        raise ValueError('Missing, ambiguous or colliding feature IDs; refusing modification')
    # One simultaneous replacement prevents overlapping old/new ID collisions.
    mapping = {old[role]: found[role] for role in ROLES[:5]}
    pattern = r'(["\'])(' + '|'.join(re.escape(x) for x in mapping) + r')\1'
    result = re.sub(pattern, lambda m: m[1] + mapping[m[2]] + m[1], source)
    if result != source:
        version = 'auto-' + hashlib.sha256(json.dumps(found, sort_keys=True).encode()).hexdigest()[:12]
        result = re.sub(r'"(?:layout-v1|auto-[0-9a-f]{12})"', json.dumps(version), result)
    compile(result, '<repaired launcher>', 'exec')
    if current_ids(result) != found:
        raise ValueError('Post-edit consistency check failed')
    return result


def find_asar():
    ps = "$p=Get-AppxPackage OpenAI.Codex | Sort-Object Version | Select-Object -Last 1; if($p){Join-Path $p.InstallLocation 'app\\resources\\app.asar'}"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=45, creationflags=0x08000000)
    path = Path(result.stdout.strip())
    if result.returncode or not path.is_file():
        raise RuntimeError('找不到已安装的 Codex app.asar')
    return path


def atomic_write(path, data):
    temporary = path.with_name(path.name + '.repair-tmp')
    temporary.write_bytes(data)
    os.replace(temporary, path)


def run(args):
    launcher = ROOT / 'codex_zh_launch.py'
    asar = Path(args.asar) if args.asar else find_asar()
    report = {'status': 'scanning', 'asar': str(asar), 'time': time.strftime('%Y-%m-%dT%H:%M:%S')}
    output = ROOT.parent / 'output'
    logs = output / 'logs'
    backups = output / 'backups'
    logs.mkdir(parents=True, exist_ok=True)
    backups.mkdir(parents=True, exist_ok=True)
    report_path = logs / 'repair-report.json'
    backup = None
    try:
        found, evidence = discover(renderer_sources(asar))
        report.update(found=found, evidence=evidence)
        before = launcher.read_bytes()
        source = before.decode('utf-8')
        report['previous'] = current_ids(source)
        if 'def configure_features(asar):' in source:
            # Runtime discovery supersedes source rewriting and stale ID persistence.
            report['features'] = {role: {'mode': 'override' if role in found else 'official-default',
                                         'id': found.get(role)} for role in ROLES}
            after = before
        else:
            # Compatibility for older launchers remains fail-closed.
            legacy_found = {role: found[role] for role in ROLES[:5] if role in found}
            if set(legacy_found) != set(ROLES[:5]):
                raise RuntimeError('旧版启动器不支持逐项回退，请先升级项目。')
            after = updated_source(source, legacy_found).encode('utf-8')
        report['changed'] = after != before
        print(json.dumps({'previous': report['previous'], 'detected': found, 'changed': report['changed']}, ensure_ascii=False, indent=2))
        if args.scan_only:
            report['status'] = 'scan-only'
            return 0
        # Verify dependencies before modifying a launcher. Scanner itself is stdlib-only.
        subprocess.run([sys.executable, '-c', 'import websockets'], check=True, timeout=15)
        if after != before:
            backup = backups / (launcher.name + '.bak-repair-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
            backup.write_bytes(before)
            report['backup'] = str(backup)
            atomic_write(launcher, after)
        print('正在运行启动器并核验。已有非调试实例可能被重启，请勿在 Codex 执行任务期间运行。', flush=True)
        # Child owns normal launcher mutex. ID repair uses a separate exclusive lock.
        # Do not accept a stale passed report if child exits early due to its mutex.
        verification = logs / 'verification.json'
        previous_report = verification.stat().st_mtime_ns if verification.exists() else None
        completed = subprocess.run([sys.executable, str(launcher)], timeout=240)
        state = json.loads(verification.read_text(encoding='utf-8')) if verification.exists() else {}
        if completed.returncode or state.get('status') != 'passed' or verification.stat().st_mtime_ns == previous_report:
            raise RuntimeError('启动后的真实界面核验未通过；如有修改将恢复启动器。')
        report['features'] = state.get('features', report.get('features', {}))
        report['status'] = 'passed'
        defaults = [role for role, policy in report['features'].items() if policy['mode'] == 'official-default']
        report['defaulted_features'] = defaults
        if defaults:
            print('以下功能已交还官方默认行为（不表示功能已移除或已经可用）：' + ', '.join(defaults))
        print('检测与当前有效覆盖项核验通过。未修改官方安装包或账号配置。')
        return 0
    except Exception as error:
        if backup:
            atomic_write(launcher, backup.read_bytes())
            report['rolled_back'] = True
        report.update(status='failed', error=str(error))
        print('失败：' + str(error), file=sys.stderr)
        if backup:
            print('启动器源码已恢复；当前应用内存中的注入不会自动撤销，请完全退出后重开。', file=sys.stderr)
        return 1
    finally:
        atomic_write(report_path, json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description='Codex 开关自动检测修复（不猜测、不全开）')
    parser.add_argument('--scan-only', action='store_true', help='只扫描，不修改或启动')
    parser.add_argument('--asar', help='扫描指定 ASAR（测试用）')
    args = parser.parse_args()
    # Windows OS lock automatically releases after crashes; lock file may remain.
    import msvcrt
    logs = ROOT.parent / 'output' / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs / 'repair.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('已有检测修复正在运行。')
            return 1
        try:
            return run(args)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == '__main__':
    raise SystemExit(main())
