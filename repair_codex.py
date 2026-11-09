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
ROLES = ('computer_use', 'browser_use_external', 'browser_use', 'layout', 'i18n')


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


def discover(sources):
    """Match multiple semantic anchors, not minified module/variable names.

    These intentionally narrow recipes may stop on new minifier structures.
    Unique matches are evidence of structural similarity, not proof of semantics.
    """
    evidence = {role: [] for role in ROLES}
    ident = r'[A-Za-z_$][\w$]*'
    call = rf'\(0,{ident}\.{ident}\)\("(\d+)"\)'
    for filename, text in sources:
        for role in ROLES[:3]:
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
            if re.search(selector, text):
                evidence['layout'].append({'id': gate, 'file': filename, 'offset': match.start()})
    found = {}
    for role, rows in evidence.items():
        ids = {row['id'] for row in rows}
        if len(ids) == 1:
            found[role] = next(iter(ids))
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
    if set(found) != set(ROLES) or len(set(found.values())) != 5:
        raise ValueError('Missing, ambiguous or colliding feature IDs; refusing modification')
    # One simultaneous replacement prevents overlapping old/new ID collisions.
    mapping = {old[role]: found[role] for role in ROLES}
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
    report_path = ROOT / 'repair-report.json'
    backup = None
    try:
        found, evidence = discover(renderer_sources(asar))
        report.update(found=found, evidence=evidence)
        if set(found) != set(ROLES):
            raise RuntimeError('无法唯一定位全部功能开关；为防误改，已停止。请查看 repair-report.json。')
        before = launcher.read_bytes()
        source = before.decode('utf-8')
        report['previous'] = current_ids(source)
        after = updated_source(source, found).encode('utf-8')
        report['changed'] = after != before
        print(json.dumps({'previous': report['previous'], 'detected': found, 'changed': report['changed']}, ensure_ascii=False, indent=2))
        if args.scan_only:
            report['status'] = 'scan-only'
            return 0
        # Verify dependencies before modifying a launcher. Scanner itself is stdlib-only.
        subprocess.run([sys.executable, '-c', 'import websockets'], check=True, timeout=15)
        if after != before:
            backup = launcher.with_name(launcher.name + '.bak-repair-' + time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
            backup.write_bytes(before)
            report['backup'] = str(backup)
            atomic_write(launcher, after)
        print('正在运行启动器并核验。已有非调试实例可能被重启，请勿在 Codex 执行任务期间运行。', flush=True)
        # Child owns normal launcher mutex. ID repair uses a separate exclusive lock.
        # Do not accept a stale passed report if child exits early due to its mutex.
        verification = ROOT / 'verification.json'
        previous_report = verification.stat().st_mtime_ns if verification.exists() else None
        completed = subprocess.run([sys.executable, str(launcher)], timeout=240)
        state = json.loads(verification.read_text(encoding='utf-8')) if verification.exists() else {}
        if completed.returncode or state.get('status') != 'passed' or verification.stat().st_mtime_ns == previous_report:
            raise RuntimeError('启动后的真实界面核验未通过；如有修改将恢复启动器。')
        report['status'] = 'passed'
        print('检测修复及启动核验通过。未修改官方安装包或账号配置。')
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
    with (ROOT / 'repair.lock').open('a+b') as lock:
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
