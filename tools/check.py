#!/usr/bin/env python3
"""Check host tools and source packaging without a phone or private inputs."""
import ast
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
paths = subprocess.check_output(
    ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT
).decode().split('\0')
for name in sorted(set(paths)):
    path = ROOT / name
    if not path.is_file():
        continue
    if path.suffix == '.py':
        ast.parse(path.read_text(), filename=name)
    elif path.suffix == '.sh':
        subprocess.run(['bash', '-n', str(path)], check=True)
    elif path.suffix == '.patch':
        result = subprocess.run(['git', 'apply', '--numstat', str(path)], cwd=ROOT, capture_output=True, text=True)
        if result.returncode:
            sys.exit(f'{name}: malformed patch\n{result.stderr}')
    elif path.suffix == '.md':
        for target in re.findall(r'\]\(([^\s)]+)\)', path.read_text()):
            link = urlsplit(target)
            if not link.scheme and link.path and not (path.parent / unquote(link.path)).exists():
                sys.exit(f'{name}: missing link target {target}')

for suite in ['tools', 'tools-claude']:
    result = subprocess.run(
        [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', suite, '-p', 'test_*.py'],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode:
        sys.exit(result.stdout + result.stderr)
    print(f'{suite}: existing synthetic tests passed')
subprocess.run(['sh', 'phone/wifi/test.sh'], cwd=ROOT, check=True)
subprocess.run(['actionlint'], cwd=ROOT, check=True)
subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
print('Host syntax, synthetic and pd-mapper tests, patch structure, links and whitespace passed; no phone was accessed')
