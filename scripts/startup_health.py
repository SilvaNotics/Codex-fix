"""Narrow startup repairs; never change providers, credentials or runtime mode."""
import os
from pathlib import Path
import re
import time
import tomllib


def repair_catalog_path(config, backup_dir):
    """Use a CODEX_HOME-relative catalog path when the target is inside it."""
    config = Path(config)
    if not config.exists():
        return {'changed': False}
    before = config.read_bytes()
    text = before.decode('utf-8-sig')
    parsed = tomllib.loads(text)
    value = parsed.get('model_catalog_json')
    if not isinstance(value, str) or value.startswith('./'):
        return {'changed': False}
    target = Path(value)
    if not target.is_absolute():
        return {'changed': False}
    try:
        relative = target.resolve().relative_to(config.parent.resolve())
    except ValueError:
        return {'changed': False}
    if not target.is_file():
        raise RuntimeError('model_catalog_json points to a missing file; repair it before starting Codex')
    replacement = './' + relative.as_posix()
    if "'" in replacement or '\n' in replacement or '\r' in replacement:
        raise ValueError('Unsupported model catalog filename; configuration preserved')
    pattern = r'(?m)^[ \t]*model_catalog_json[ \t]*=[^\r\n]*'
    result, count = re.subn(pattern, lambda _: "model_catalog_json = '" + replacement + "'", text)
    expected = dict(parsed, model_catalog_json=replacement)
    if count != 1 or tomllib.loads(result) != expected:
        raise ValueError('Unsupported model_catalog_json TOML layout; configuration preserved')
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir/(config.name+'.bak-catalog-'+str(time.time_ns()))
    temporary = config.with_name(config.name+'.catalog-tmp-'+str(os.getpid()))
    encoded = (b'\xef\xbb\xbf' if before.startswith(b'\xef\xbb\xbf') else b'') + result.encode('utf-8')
    try:
        if config.read_bytes() != before:
            raise RuntimeError('Configuration changed during startup repair; retry')
        with backup.open('xb') as stream:
            stream.write(before)
        temporary.write_bytes(encoded)
        if config.read_bytes() != before:
            raise RuntimeError('Configuration changed during startup repair; original preserved')
        os.replace(temporary, config)
    finally:
        temporary.unlink(missing_ok=True)
    return {'changed': True, 'backup': str(backup)}
