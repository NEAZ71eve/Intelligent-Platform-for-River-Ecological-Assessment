#!/usr/bin/env python3
"""Run a release's Python command with a strict subset of systemd EnvironmentFile.

Invoke as root when the environment file is root-only. Credentials stay in the
process environment; they are never interpolated into a shell or command line.
The application command runs as the unprivileged service account.

Supported entries: single-line KEY=value, KEY='value', or KEY="value".
Names must match [A-Za-z_][A-Za-z0-9_]*. Blank lines and full-line # comments
are allowed. No escapes, control characters, duplicate keys, multiline values,
whitespace around '=' or unquoted values, or inner matching quote characters.
The other quote character inside a quoted value is preserved literally.
PATH, LANG and DJANGO_SETTINGS_MODULE are fixed; caller environment is ignored.
"""
import argparse
import os
from pathlib import Path
import pwd
import re


ENVIRONMENT_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
FIXED_ENVIRONMENT = {
    'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
    'LANG': 'C.UTF-8',
    'DJANGO_SETTINGS_MODULE': 'config.settings',
}


def parse_environment(text):
    """Parse the documented literal subset without expanding or trimming values."""
    invalid = 'Unsupported environment-file format.'
    text = text.replace('\r\n', '\n')
    if any((ord(char) < 32 and char != '\n') or ord(char) == 127
           or char in '\u0085\u2028\u2029' for char in text):
        raise ValueError(invalid)
    result = {}
    for line in text.split('\n'):
        if not line.strip(' ') or line.lstrip(' ').startswith('#'):
            continue
        key, separator, value = line.partition('=')
        if not separator or ENVIRONMENT_NAME.fullmatch(key) is None or key in result:
            raise ValueError(invalid)
        if '\\' in value:
            raise ValueError(invalid)
        if value[:1] in {'"', "'"}:
            quote = value[0]
            if len(value) < 2 or value[-1] != quote or quote in value[1:-1]:
                raise ValueError(invalid)
            value = value[1:-1]
        elif value != value.strip() or '"' in value or "'" in value:
            raise ValueError(invalid)
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--env-file', required=True, type=Path)
    parser.add_argument('--release', required=True, type=Path)
    parser.add_argument('--user', default='hyhq')
    parser.add_argument('command', nargs=argparse.REMAINDER,
                        help='Python arguments relative to release/backend, e.g. manage.py migrate --noinput')
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('A Python command is required.')
    try:
        environment = parse_environment(args.env_file.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        parser.error('Cannot read environment file in the documented format.')
    environment.update(FIXED_ENVIRONMENT)
    if environment.get('ENV') != 'production' or environment.get('DJANGO_DEBUG') != '0' or environment.get('ALLOW_DEV_AUTH') != '0':
        parser.error('This wrapper requires production mode with debug and development auth disabled.')
    release = args.release.resolve(strict=True)
    account = pwd.getpwnam(args.user)
    if os.getuid() == 0:
        os.initgroups(account.pw_name, account.pw_gid)
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    elif os.getuid() != account.pw_uid:
        parser.error('Run as root or the chosen service account.')
    environment.update(HOME=account.pw_dir, USER=account.pw_name, LOGNAME=account.pw_name,
                       PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    os.chdir(release / 'backend')
    python = release / '.venv/bin/python'
    os.execve(str(python), [str(python), *command], environment)


if __name__ == '__main__':
    main()
