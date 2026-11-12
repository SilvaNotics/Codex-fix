"""Package census: syntax evidence is an inventory, never permission to enable gates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def inventory(sources, node=None):
    """Return AST evidence with JS UTF-16 offsets and explicit parse failures."""
    runtime = node or shutil.which('node')
    if not runtime:
        raise RuntimeError('Node.js is required for the AST census; supported discovery remains available')
    rows, errors = [], []
    batch, size = [], 0
    def parse(entries):
        result = subprocess.run([str(runtime), str(ROOT / 'census_ast.cjs')],
                                input=json.dumps(entries, ensure_ascii=True),
                                capture_output=True, text=True, encoding='utf-8', timeout=180,
                                creationflags=0x08000000 if os.name == 'nt' else 0)
        if result.returncode:
            raise RuntimeError('AST census failed: ' + result.stderr[:1000])
        data = json.loads(result.stdout)
        rows.extend(data['rows'])
        errors.extend(data['errors'])
    for entry in sources:
        if batch and size + len(entry[1]) > 4 * 1024 * 1024:
            parse(batch)
            batch, size = [], 0
        batch.append(entry)
        size += len(entry[1])
    if batch:
        parse(batch)
    return rows, errors


CACHE = ROOT.parent / 'output' / 'logs' / 'feature-census.json'
SCHEMA = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def scanner_fingerprint():
    return digest({name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                   for name in ('feature_census.py', 'census_ast.cjs', 'reviewed_features.py', 'repair_codex.py', 'vendor/acorn.cjs')})


def package_identity(asar):
    """Cheap launch check; full content digest is computed only at initialization."""
    path = Path(asar)
    stat = path.stat()
    match = re.search(r'OpenAI\.Codex_([0-9.]+)_', str(path))
    return {'path': str(path.resolve()), 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'version': match.group(1) if match else 'unknown'}


def package_fingerprint(asar):
    path = Path(asar)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return dict(package_identity(asar), sha256=sha)


def package_sources(asar):
    """All packed JS plus unpacked JS, main/preload/renderer alike."""
    with Path(asar).open('rb') as stream:
        prefix = stream.read(16)
        if len(prefix) != 16:
            raise ValueError('Invalid ASAR header')
        _, size, _, length = struct.unpack('<4I', prefix)
        if not 0 < length <= 64 * 1024 * 1024:
            raise ValueError('Invalid ASAR JSON size')
        header = json.loads(stream.read(length))
        def walk(node, parts=()):
            for name, item in sorted(node.get('files', {}).items()):
                if name in ('.', '..') or '/' in name or '\\' in name:
                    raise ValueError('Unsafe ASAR entry')
                current = (*parts, name)
                if 'files' in item:
                    yield from walk(item, current)
                elif name.endswith(('.js', '.cjs', '.mjs')):
                    if item.get('link'):
                        raise ValueError('Linked JS entry unsupported')
                    if item.get('unpacked'):
                        body = Path(str(asar) + '.unpacked').joinpath(*current).read_bytes()
                    else:
                        stream.seek(8 + size + int(item['offset']))
                        body = stream.read(item['size'])
                    if len(body) != item['size']:
                        raise ValueError('Truncated ASAR JS entry')
                    yield '/' + '/'.join(current), body.decode('utf-8')
        yield from walk(header)


def load_policy(asar, cache=CACHE):
    """Reject stale, malformed, altered or unsupported cache; caller rediscovers."""
    try:
        data = json.loads(Path(cache).read_text(encoding='utf-8'))
        if data['schema'] != SCHEMA or data['scanner'] != scanner_fingerprint():
            return None
        identity = package_identity(asar)
        if any(data['package'].get(key) != value for key, value in identity.items()):
            return None
        if data['checksum'] != digest({k:v for k,v in data.items() if k != 'checksum'}):
            return None
        found = data['policy']['found']
        from repair_codex import ROLES
        from reviewed_features import APPROVED
        allowed = set(ROLES) | {'feature:' + name for name in APPROVED}
        if not isinstance(found, dict) or any(k not in allowed or not isinstance(v, str) or not v.isdecimal() for k,v in found.items()):
            return None
        if len(set(found.values())) != len(found):
            return None
        return found
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=True, sort_keys=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def refresh(asar, cache=CACHE, node=None):
    """One atomic snapshot contains census AND resolved supported policy."""
    from repair_codex import discover, ROLES
    fingerprint = package_fingerprint(asar)
    # Inventory consumes bounded batches; do not retain the entire package in RAM.
    from repair_codex import renderer_sources
    found, evidence = discover(renderer_sources(asar))
    source_count = 0
    def counted_sources():
        nonlocal source_count
        for entry in package_sources(asar):
            source_count += 1
            yield entry
    rows, errors = inventory(counted_sources(), node)
    if errors:
        raise ValueError('Incomplete AST census; previous snapshot preserved: ' + json.dumps(errors[:5]))
    from reviewed_features import review_candidates
    additional, review_audit = review_candidates(rows)
    combined = dict(found, **additional)
    from collections import Counter
    counts = Counter(combined.values())
    found = {role: gate for role, gate in combined.items() if counts[gate] == 1}
    for audit in review_audit:
        if audit['decision'] == 'approve' and 'feature:' + audit['name'] not in found:
            audit.update(decision='hold', reason='ID collides with another reviewed role.')
    for row in rows:
        roles = [role for role, gate in found.items() if gate == row['id']]
        row['decision'] = 'selected' if roles else 'held'
        row['classification'] = 'supported-id-reference' if roles else row['classification']
        row['reason'] = ('existing-supported-structural-rule: ' + ','.join(roles) if roles else
                         'computed-or-nonliteral; not resolved' if row['id'] is None else
                         'unknown polarity/purpose: may be rollout, kill switch, SDK implementation or unrelated API; official default')
    identities = sorted({json.dumps([r['kind'], r['name'], r['id']], ensure_ascii=True) for r in rows})
    previous = {}
    try:
        previous = json.loads(Path(cache).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    old = previous.get('census', {}).get('identities', []) if isinstance(previous, dict) else []
    if not isinstance(old, list) or not all(isinstance(x, str) for x in old):
        old = []
    data = {'schema': SCHEMA, 'scanner': scanner_fingerprint(), 'package': fingerprint,
            'policy': {'found': found, 'features': {role: {'id': found.get(role),
                      'mode': 'override' if role in found else 'official-default',
                      'reason': 'unique-supported-structural-rule' if role in found else 'missing-ambiguous-or-colliding-supported-rule'} for role in ROLES},
                       'evidence': evidence, 'review': review_audit},
            'census': {'scope': 'all ASAR packed/unpacked JavaScript; no dataflow/alias resolution; SDK-named calls are candidates, not proven SDK receivers',
                       'offset_unit': 'UTF-16 code units (AST); supported-rule evidence uses Python code points',
                       'source_count': source_count, 'rows': rows, 'errors': errors,
                       'identities': identities, 'previous_package': previous.get('package') if isinstance(previous, dict) else None,
                       'diff': {'added': sorted(set(identities)-set(old)), 'removed': sorted(set(old)-set(identities))}}}
    if package_fingerprint(asar) != fingerprint:
        raise ValueError('Package changed during census; previous snapshot preserved')
    data['checksum'] = digest(data)
    atomic_json(cache, data)
    return data


def main():
    parser = argparse.ArgumentParser(description='Read-only package census; persist supported policy, never start Codex')
    parser.add_argument('--asar')
    parser.add_argument('--output', default=str(CACHE))
    parser.add_argument('--node')
    args = parser.parse_args()
    from repair_codex import find_asar
    asar = Path(args.asar) if args.asar else find_asar()
    node = args.node
    bundled = asar.parent / 'cua_node' / 'node.exe'
    if not node and not shutil.which('node') and bundled.is_file():
        node = bundled
    try:
        data = refresh(asar, Path(args.output), node)
    except Exception as error:
        print('Census failed; previous policy preserved: ' + str(error))
        return 1
    print(json.dumps({'package': data['package'], 'sources': data['census']['source_count'],
                      'candidates': len(data['census']['rows']), 'supported': data['policy']['found'],
                      'added': len(data['census']['diff']['added']), 'removed': len(data['census']['diff']['removed'])}, ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

