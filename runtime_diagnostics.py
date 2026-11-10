"""Read-only local inventory. Never imports plugins or starts MCP servers."""
import argparse
import json
import os
import re
import time
from copy import deepcopy
from pathlib import Path
import tomllib

BUNDLED = ('codex-app-tools', 'unified-computer-use', 'computer-use',
           'chrome', 'browser', 'latex', 'visualize')
PRIMARY = ('documents', 'pdf', 'spreadsheets', 'presentations', 'template-creator')


SESSION_KEYS = ('SKY_CUA_NATIVE_PIPE', 'SKY_CUA_NATIVE_PIPE_DIRECTORY')


def repair_session_config(path):
    """Remove only persisted node_repl session references; validate semantic diff.

    Unsupported TOML spellings fail closed rather than rewriting user settings.
    Backups may contain credentials and stay beside the private config, never in reports.
    """
    path = Path(path)
    try:
        before = path.read_bytes()
    except FileNotFoundError:
        return {'changed': False}
    text = before.decode('utf-8-sig')
    parsed = tomllib.loads(text)
    expected = deepcopy(parsed)
    env = expected.get('mcp_servers', {}).get('node_repl', {}).get('env', {})
    keys = [key for key in SESSION_KEYS if key in env]
    if not keys:
        return {'changed': False}
    for key in keys:
        del env[key]
    section = re.compile(r'''^[ \t]*\[[ \t]*mcp_servers\.(?:node_repl|"node_repl"|'node_repl')\.env[ \t]*\][ \t]*(?:#.*)?$''')
    field = re.compile(r'''^[ \t]*(?:SKY_CUA_NATIVE_PIPE(?:_DIRECTORY)?|"SKY_CUA_NATIVE_PIPE(?:_DIRECTORY)?"|'SKY_CUA_NATIVE_PIPE(?:_DIRECTORY)?')[ \t]*=''')
    inside = False
    lines = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith('['):
            inside = bool(section.fullmatch(line.rstrip('\r\n')))
        if inside and field.match(line):
            continue
        lines.append(line)
    result = ''.join(lines)
    if tomllib.loads(result) != expected:
        raise ValueError('Unsupported session-reference TOML layout; configuration left unchanged')
    encoded = (b'\xef\xbb\xbf' if before.startswith(b'\xef\xbb\xbf') else b'') + result.encode('utf-8')
    # Refuse a concurrent writer instead of discarding its changes.
    if path.read_bytes() != before:
        raise RuntimeError('Codex configuration changed during cleanup; retry after closing the editor')
    backup = path.with_name(path.name+'.bak-session-'+str(time.time_ns()))
    with backup.open('xb') as stream:
        stream.write(before)
    temporary = path.with_name(path.name+'.session-tmp-'+str(os.getpid()))
    try:
        temporary.write_bytes(encoded)
        if path.read_bytes() != before:
            raise RuntimeError('Codex configuration changed during cleanup; original preserved')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {'changed': True, 'removed_keys': keys, 'backup': str(backup)}


def collect(home=None):
    home = Path(home) if home is not None else Path.home()
    codex = home/'.codex'
    warnings = []
    try:
        config = tomllib.loads((codex/'config.toml').read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        config = {}
        warnings.append('config-missing')
    except (OSError, ValueError):
        config = {}
        warnings.append('config-unreadable-or-invalid')
    def table(value):
        if isinstance(value, dict):
            return value
        if 'config-invalid-field-type' not in warnings:
            warnings.append('config-invalid-field-type')
        return {}
    plugin_settings = table(config.get('plugins', {}))
    plugins = {}
    roots = [('openai-bundled', codex/'.tmp/bundled-marketplaces/openai-bundled', BUNDLED),
             ('openai-primary-runtime', home/'.cache/codex-runtimes/codex-primary-runtime/plugins/openai-primary-runtime', PRIMARY)]
    for market, root, names in roots:
        for name in names:
            identity = name+'@'+market
            path = root/'plugins'/name/'.codex-plugin/plugin.json'
            manifest = None
            present = path.is_file()
            if present:
                try:
                    data = json.loads(path.read_text(encoding='utf-8-sig'))
                    if isinstance(data, dict) and data.get('name') == name:
                        manifest = data
                except (OSError, ValueError):
                    pass
            setting = table(plugin_settings.get(identity, {}))
            plugins[identity] = {
                'manifest_present': present,
                'manifest_valid': manifest is not None,
                'version': manifest.get('version') if manifest else None,
                'configured_enabled': setting.get('enabled'),
                'loaded': 'not-probed',
            }
    if not all(plugins[n+'@openai-primary-runtime']['manifest_valid'] for n in PRIMARY):
        warnings.append('primary-runtime-plugins-incomplete-use-official-sync')
    mcp = table(config.get('mcp_servers', {}))
    node = mcp.get('node_repl')
    health = {'configured': isinstance(node, dict), 'loaded': 'not-probed'}
    if isinstance(node, dict):
        command = node.get('command', '')
        if not isinstance(command, str):
            warnings.append('node-repl-command-invalid-type')
            command = ''
        # Only assert absence for an explicit path; PATH-only commands are unknown.
        health['command_exists'] = Path(command).is_file() if command and ('/' in command or '\\' in command) else None
        if health['command_exists'] is False:
            warnings.append('node-repl-command-missing')
        env = table(node.get('env', {}))
        health['path_checks'] = {}
        for key in ('CODEX_CLI_PATH', 'NODE_REPL_NODE_PATH'):
            value = env.get(key)
            if isinstance(value, str) and value:
                exists = Path(value).is_file()
                health['path_checks'][key] = exists
                if not exists:
                    warnings.append('node-repl-'+key.lower().replace('_', '-')+'-missing')
        health['persisted_session_references'] = any(k in env for k in SESSION_KEYS)
        if health['persisted_session_references']:
            warnings.append('node-repl-session-references-persisted')
    return {
        'verification_scope': 'local-inventory-not-tool-execution',
        'plugins': plugins,
        'node_repl': health,
        'user_mcp_count': len(mcp),
        'browser_extensions': 'not-probed',
        'office_addins': 'not-probed',
        'app_managed_mcp': 'not-probed',
        'warnings': warnings,
        'policy': 'preserve-official-sync-and-user-permissions',
    }


def main():
    parser = argparse.ArgumentParser(description='Read-only local Codex component diagnostics; no secrets or tool execution.')
    parser.add_argument('--output', type=Path, help='Write JSON to this exact path; stdout otherwise')
    args = parser.parse_args()
    text = json.dumps(collect(), ensure_ascii=False, indent=2)
    if args.output:
        temporary = args.output.with_suffix(args.output.suffix+'.tmp')
        temporary.write_text(text, encoding='utf-8')
        os.replace(temporary, args.output)
    else:
        print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
