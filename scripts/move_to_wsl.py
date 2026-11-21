"""Migrate live Codex settings and the active CC Switch provider."""
import argparse
import base64
from copy import deepcopy
from datetime import date, time
from functools import cache
from ipaddress import ip_address
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess
import sys
import tomllib
from urllib.parse import urlsplit


HOST_SECTIONS = {'windows', 'desktop', 'hooks', 'marketplaces', 'plugins', 'tui',
                 'sqlite_home', 'log_dir', 'cli_auth_credentials_store', 'mcp_oauth_credentials_store'}
MODEL_KEYS = {'model', 'model_provider', 'model_catalog_json', 'model_providers'}
WINDOWS_BINARIES = re.compile(r'(?i)(?:\.exe|\.cmd|\.bat|\.ps1|\.vbs)(?=$|\s|[\"\'])')
PATH_KEYS = {'cwd', 'config_file', 'model_instructions_file', 'experimental_instructions_file',
             'experimental_compact_prompt_file', 'shell', 'shell_path', 'command', 'args',
             'notify', 'writable_roots'}
SESSION_ENV = {'SKY_CUA_NATIVE_PIPE', 'SKY_CUA_NATIVE_PIPE_DIRECTORY'}


def decode_distros(raw):
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        text = raw.decode('utf-16')
    else:
        text = raw.decode('utf-16-le' if b'\0' in raw else 'utf-8-sig')
    return [line.strip() for line in text.splitlines()
            if line.strip() and line.strip() not in {'docker-desktop', 'docker-desktop-data'}]


def wsl(args, payload=None):
    result = subprocess.run(['wsl.exe', *args], input=payload, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(f'WSL 命令失败（退出码 {result.returncode}）。请确认发行版可启动且已安装 python3。')
    return result.stdout


def translate_path(value, convert):
    drive, tail = ntpath.splitdrive(value)
    if drive and (len(drive) > 2 or tail.startswith(('/', chr(92)))):
        return convert(ntpath.normpath(value))
    return value


def is_windows_command(command):
    return isinstance(command, str) and bool(
        WINDOWS_BINARIES.search(command) or command.lower() in {'cmd', 'powershell', 'pwsh', 'wscript', 'cscript'})


def portable(value, convert, is_path=False):
    if isinstance(value, dict):
        return {key: portable(item, convert, key in PATH_KEYS) for key, item in value.items()}
    if isinstance(value, list):
        return [portable(item, convert, is_path) for item in value]
    if is_path and isinstance(value, str):
        return translate_path(value, convert)
    return value


def merge(base, incoming):
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = value
    return base


def migration_config(windows, linux, windows_home, convert):
    skipped = sorted(HOST_SECTIONS & windows.keys())
    excluded = HOST_SECTIONS | MODEL_KEYS | {'mcp_servers', 'projects', 'notify'}
    result = merge(deepcopy(linux), portable({k: v for k, v in windows.items() if k not in excluded}, convert))
    if 'notify' in windows:
        if any(is_windows_command(arg) for arg in windows['notify']):
            skipped.append('notify')
        else:
            result['notify'] = portable(windows['notify'], convert, True)
    for name, project in windows.get('projects', {}).items():
        path = translate_path(name, convert)
        result.setdefault('projects', {}).setdefault(path, deepcopy(project))
    for name, server in windows.get('mcp_servers', {}).items():
        command = [server.get('command'), *server.get('args', [])]
        if name in linux.get('mcp_servers', {}) or any(is_windows_command(arg) for arg in command):
            skipped.append(f'mcp_servers.{name}')
            continue
        server = deepcopy(server)
        if name == 'node_repl':
            for key in SESSION_ENV:
                server.get('env', {}).pop(key, None)
        result.setdefault('mcp_servers', {})[name] = portable(server, convert)
    for key in ('model', 'model_provider', 'model_catalog_json'):
        if key in windows:
            result[key] = windows[key]
        else:
            result.pop(key, None)
    # Replace whole provider definitions so an old env_key cannot shadow the migrated auth.
    if windows.get('model_providers'):
        result.setdefault('model_providers', {}).update(deepcopy(windows['model_providers']))
    catalog = windows.get('model_catalog_json')
    if catalog is not None:
        if not isinstance(catalog, str) or not catalog:
            raise ValueError('model_catalog_json 必须是文件路径。')
        if catalog.startswith('/') and not catalog.startswith('//'):
            result['model_catalog_json'] = catalog
        else:
            source = ntpath.normpath(ntpath.join(windows_home, catalog))
            result['model_catalog_json'] = translate_path(source, convert)
        if not result['model_catalog_json'].startswith('/'):
            raise ValueError('无法将 model_catalog_json 转换为 WSL 绝对路径。')
    return result, skipped


def toml_string(value):
    return json.dumps(value, ensure_ascii=False).replace('\x7f', r'\u007f')


def toml_value(value):
    if isinstance(value, str):
        return toml_string(value)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, list):
        return '[' + ', '.join(map(toml_value, value)) + ']'
    if isinstance(value, dict):
        return '{' + ', '.join(f'{toml_string(k)} = {toml_value(v)}' for k, v in value.items()) + '}'
    raise TypeError('Unsupported TOML value')


def dump_config(config):
    lines = []

    def table(data, path):
        if path:
            if lines:
                lines.append('')
            lines.append('[' + '.'.join(map(toml_string, path)) + ']')
        for key, value in data.items():
            if not isinstance(value, dict):
                lines.append(f'{toml_string(key)} = {toml_value(value)}')
        for key, value in data.items():
            if isinstance(value, dict):
                table(value, (*path, key))

    table(config, ())
    return '\n'.join(lines) + '\n'


def parse_config(data, label):
    try:
        return tomllib.loads(data.decode('utf-8-sig'))
    except ValueError:
        raise ValueError(f'{label} config.toml 无法解析，已保留原文件。') from None


def key_only_auth(data):
    try:
        value = json.loads(data)
    except ValueError:
        return None
    if (isinstance(value, dict) and value.get('auth_mode', 'apikey') == 'apikey'
            and isinstance(value.get('OPENAI_API_KEY'), str) and value['OPENAI_API_KEY']
            and not (value.keys() - {'auth_mode', 'OPENAI_API_KEY', 'tokens', 'last_refresh'})
            and not value.get('tokens')):
        return value['OPENAI_API_KEY']
    return None


def source_api_key(config, windows_home):
    provider = config.get('model_providers', {}).get(config.get('model_provider'), {})
    if not provider.get('requires_openai_auth') or provider.get('env_key') or provider.get('experimental_bearer_token'):
        return None
    auth = windows_home / 'auth.json'
    return key_only_auth(auth.read_bytes()) if auth.is_file() else None


def is_loopback_endpoint(endpoint):
    try:
        host = urlsplit(endpoint).hostname
        return host == 'localhost' or bool(host and ip_address(host).is_loopback)
    except ValueError:
        return False


def encode(data):
    return base64.b64encode(data).decode('ascii')


def target(distro, **request):
    source = Path(__file__).with_name('wsl_config_target.py').read_bytes()
    bootstrap = 'import sys,base64;exec(base64.b64decode(sys.stdin.buffer.readline()))'
    data = (encode(source) + '\n' + json.dumps(request)).encode('ascii')
    raw = wsl(['--distribution', distro, '--exec', 'python3', '-c', bootstrap], data)
    response = json.loads(raw)
    if 'error' in response:
        raise RuntimeError(response['error'])
    return response


def main():
    parser = argparse.ArgumentParser(description='将 Windows Codex 和当前 CC Switch 端点配置迁移到 WSL。')
    parser.add_argument('--distro', help='已安装的 WSL 发行版名称')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='预检并显示目标，不写入文件')
    mode.add_argument('--yes', action='store_true', help='直接迁移到 --distro 指定的发行版')
    args = parser.parse_args()
    if args.yes and not args.distro:
        parser.error('--yes 需要同时指定 --distro')
    distros = decode_distros(wsl(['--list', '--quiet']))
    if not distros:
        raise RuntimeError('没有找到可用的 WSL 发行版。')
    if args.distro:
        distro = next((name for name in distros if name.casefold() == args.distro.casefold()), None)
        if not distro:
            raise RuntimeError('所选发行版未安装。')
    else:
        for i, name in enumerate(distros, 1):
            print(f'  {i}. {name}')
        choice = input('选择发行版编号（回车取消）：').strip()
        if not choice:
            return 0
        if not choice.isdecimal() or not 1 <= int(choice) <= len(distros):
            raise RuntimeError('无效的发行版编号。')
        distro = distros[int(choice) - 1]

    @cache
    def convert(path):
        result = wsl(['--distribution', distro, '--exec', 'wslpath', '-a', '-u', path]).decode('utf-8').rstrip('\r\n')
        if not result.startswith('/'):
            raise RuntimeError('wslpath 未返回绝对路径，请检查发行版的 Windows 盘挂载。')
        return result

    home = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex').resolve()
    try:
        before_windows = (home/'config.toml').read_bytes()
    except FileNotFoundError:
        raise RuntimeError('找不到 Windows CODEX_HOME 下的 config.toml。') from None
    windows = parse_config(before_windows, 'Windows')
    snapshot = target(distro, action='read')
    before = snapshot['files']
    linux = parse_config(base64.b64decode(before['config.toml'] or ''), 'WSL')
    merged, skipped = migration_config(windows, linux, str(home), convert)
    encoded = dump_config(merged).encode('utf-8')
    if parse_config(encoded, '生成的') != merged:
        raise ValueError('生成的配置未通过 TOML 一致性检查。')
    after = {} if merged == linux and before['config.toml'] is not None else {'config.toml': encode(encoded)}
    api_key = source_api_key(windows, home)
    if api_key is not None:
        existing = before['auth.json']
        if existing is not None and key_only_auth(base64.b64decode(existing)) != api_key:
            raise RuntimeError('WSL 已有独立的 auth.json。请在 WSL 中处理该登录后重试，脚本会保留原文件。')
        if existing is None:
            after['auth.json'] = encode(json.dumps({'OPENAI_API_KEY': api_key}).encode('utf-8'))
    provider = merged.get('model_providers', {}).get(merged.get('model_provider'), {})
    catalog = merged.get('model_catalog_json')
    if catalog:
        target(distro, action='check_catalog', catalog=catalog)
    print(f'{distro} / {snapshot["user"]} → {snapshot["path"]}')
    if catalog:
        print(f'共享模型目录：{catalog}')
    if skipped:
        print('保留 WSL 原设置或跳过宿主专用项：' + ', '.join(skipped))
    if provider.get('env_key'):
        print(f'请在 WSL app-server 环境中提供 {provider["env_key"]}。')
    if is_loopback_endpoint(provider.get('base_url') or merged.get('openai_base_url') or ''):
        print('当前端点使用 localhost/环回地址。请确认 WSL 能访问该代理，必要时在 WSL 中调整 base_url。')
    if 'auth.json' in after:
        print('将建立只包含 API Key 的 WSL auth.json。')
    if args.dry_run or not after:
        print('预检通过，未写入文件。' if args.dry_run else '目标配置已一致。')
        return 0
    if not args.yes and input('输入 yes 写入 WSL 配置：').strip().lower() != 'yes':
        return 0
    if (home/'config.toml').read_bytes() != before_windows or source_api_key(windows, home) != api_key:
        raise RuntimeError('Windows 端点配置在预检后发生变化，请重新运行。')
    response = target(distro, action='write', before=before, after=after, catalog=catalog,
                      expected_uid=snapshot['uid'], expected_path=snapshot['path'])
    for backup in response['backups']:
        print('备份：' + backup)
    print('迁移完成。请在 Codex 的连接设置中重连该 WSL 发行版。')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        # Do not include parser input, subprocess payloads or credentials in console errors.
        print('迁移失败：' + (str(error) if type(error) in (ValueError, RuntimeError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
    except (EOFError, KeyboardInterrupt):
        sys.exit(1)
