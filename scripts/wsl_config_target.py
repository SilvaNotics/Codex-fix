"""Read and write Codex files inside the selected Linux user's home."""
import base64
from contextlib import contextmanager, ExitStack
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time


FILES = ('config.toml', 'auth.json')


def read_files(directory):
    result = {}
    for name in FILES:
        path = directory / name
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            result[name] = None
            continue
        if not stat.S_ISREG(mode):
            raise RuntimeError(f'WSL {name} 不是普通文件，请处理后重试。')
        result[name] = base64.b64encode(path.read_bytes()).decode('ascii')
    return result


def private_file(directory, prefix, data):
    with tempfile.NamedTemporaryFile(dir=directory, prefix=prefix, delete=False) as stream:
        path = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    return path


@contextmanager
def lock_directory(directory):
    if os.name != 'posix':
        yield  # Windows runs the offline fixtures only.
        return
    import fcntl

    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def write_files(directory, request):
    before, after = request['before'], request['after']
    if after.keys() - set(FILES) or (before['auth.json'] is not None and 'auth.json' in after):
        raise RuntimeError('无效的 WSL 写入请求。')
    if read_files(directory) != before:
        raise RuntimeError('WSL 配置在预检后发生变化，请重新运行。')
    directory.mkdir(mode=0o700, exist_ok=True)
    backups = {}
    with lock_directory(directory), ExitStack() as cleanup:
        if read_files(directory) != before:
            raise RuntimeError('WSL 配置在预检后发生变化，请重新运行。')
        pending = {}
        for name in after:
            path = private_file(directory, f'.{name}.move-', base64.b64decode(after[name], validate=True))
            pending[name] = path
            cleanup.callback(path.unlink, missing_ok=True)
            if before[name] is not None:
                backups[name] = private_file(directory, f'{name}.bak-move-to-wsl-{time.time_ns()}-',
                                             base64.b64decode(before[name]))
        if read_files(directory) != before:
            raise RuntimeError('WSL 配置在写入前发生变化，请重新运行。')
        # Publish auth first without replacing any file created after preflight.
        installed_auth = None
        try:
            if 'auth.json' in pending:
                installed_auth = directory/'auth.json'
                os.link(pending['auth.json'], installed_auth)
            if 'config.toml' in pending:
                os.replace(pending['config.toml'], directory/'config.toml')
        except OSError:
            if (installed_auth is not None and installed_auth.exists()
                    and installed_auth.samefile(pending['auth.json'])):
                installed_auth.unlink()
            raise
    return {'backups': [str(path) for path in backups.values()]}


def execute(request, home):
    action = request['action']
    directory = home / '.codex'
    if directory.is_symlink():
        raise RuntimeError('WSL ~/.codex 是符号链接，请检查目标后手工迁移。')
    if action == 'read':
        return {'files': read_files(directory), 'path': str(directory/'config.toml')}
    catalog = request.get('catalog')
    if catalog:
        try:
            with Path(catalog).open('rb') as stream:
                json.load(stream)
        except (OSError, ValueError):
            raise RuntimeError('WSL 无法读取有效的模型目录 JSON，请检查 Windows 文件和盘符挂载。') from None
    if action == 'check_catalog':
        return {}
    if action == 'write':
        return write_files(directory, request)
    raise RuntimeError('无效的 WSL 迁移操作。')


if __name__ == '__main__':
    import pwd

    account = pwd.getpwuid(os.getuid())
    try:
        request = json.load(sys.stdin)
        home = Path(account.pw_dir)
        if request['action'] == 'write' and (request['expected_uid'] != account.pw_uid
                or request['expected_path'] != str(home/'.codex/config.toml')):
            raise RuntimeError('WSL 默认用户或主目录在预检后发生变化，请重新运行。')
        response = execute(request, home)
        if 'path' in response:
            response['user'] = account.pw_name
            response['uid'] = account.pw_uid
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        response = {'error': str(error) if type(error) is RuntimeError else f'WSL 配置操作失败 ({type(error).__name__})。'}
    print(json.dumps(response, ensure_ascii=True))
