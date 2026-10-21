"""GitHub-only sync; Gitee origin and branch tracking are never changed."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = 'https://github.com/liuda30201/AI-Coding.git'
REMOTE = 'github'
BRANCH = 'main'


def git(*args, capture=False):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=capture,
                            text=True, encoding='utf-8')
    if result.returncode:
        raise RuntimeError('Git command failed: git ' + ' '.join(args))
    return result.stdout.strip() if capture else ''


def allowed(name):
    p = Path(name)
    return ('__pycache__' not in p.parts and p.suffix.lower() in
            {'.py', '.md', '.html', '.json', '.css', '.js', '.cmd', '.bat', '.ps1', '.txt'}
            and not any(part.startswith('.') for part in p.parts)
            and not any(word in p.name.lower() for word in ('credential', 'private_key', 'id_rsa')))


def inspect_content(name, text):
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key.lower() in {'my_api_key', 'api_key', 'access_token', 'secret', 'password', 'token'} and item:
                    raise ValueError('Nonempty credential field in ' + name)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    if name.endswith('.json'):
        walk(json.loads(text))
    # shortcut: heuristic secret detection is not a full audit; review every diff before publishing.
    if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{24,}', text):
        raise ValueError('Possible private key or token in ' + name)


def configure():
    remotes = git('remote', capture=True).splitlines()
    if REMOTE not in remotes:
        git('remote', 'add', REMOTE, URL)
    if git('remote', 'get-url', REMOTE, capture=True) != URL:
        raise ValueError('github remote points elsewhere; refusing to change it')
    if git('remote', 'get-url', '--push', REMOTE, capture=True) != URL:
        raise ValueError('github push URL mismatch')


def remote_head():
    output = git('ls-remote', REMOTE, 'refs/heads/' + BRANCH, capture=True)
    rows = output.splitlines()
    if not rows:
        raise ValueError('GitHub main head is unavailable')
    row = rows[0].split()
    if len(row) != 2 or row[1] != 'refs/heads/' + BRANCH:
        raise ValueError('GitHub main head is unavailable')
    return row[0]


def is_ancestor(older, newer):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer],
                          cwd=ROOT).returncode == 0


def relation(remote_hash):
    local_hash = git('rev-parse', 'HEAD', capture=True)
    if remote_hash == local_hash:
        return 0, 0
    try:
        git('cat-file', '-e', remote_hash + '^{commit}')
    except RuntimeError:
        raise ValueError('Remote commit is not local; run pull on a clean tree before sync')
    if is_ancestor(remote_hash, local_hash):
        return int(git('rev-list', '--count', remote_hash + '..HEAD', capture=True)), 0
    if is_ancestor(local_hash, remote_hash):
        return 0, int(git('rev-list', '--count', 'HEAD..' + remote_hash, capture=True))
    raise ValueError('Local and GitHub histories diverged; manual merge required')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'pull', 'sync', 'self-test'], nargs='?', default='status')
    parser.add_argument('-m', '--message', default='Update project and site announcements')
    parser.add_argument('--yes', action='store_true', help='Explicitly confirm commit and GitHub push')
    args = parser.parse_args()
    if args.action == 'self-test':
        assert allowed('src/crawler.py') and allowed('README.md')
        assert not allowed('src/__pycache__/crawler.pyc') and not allowed('.env')
        assert not allowed('private_key.txt')
        inspect_content('sample.json', '{"my_api_key":"","stations":[]}')
        try:
            inspect_content('sample.json', '{"my_api_key":"example"}')
        except ValueError:
            pass
        else:
            raise AssertionError('Credential guard failed')
        print('PASS: path filter and credential field guard')
        return
    configure()
    remote_hash = remote_head()
    if args.action == 'status':
        ahead, behind = relation(remote_hash)
        git('status', '--short', '--branch')
        print(f'Local ahead: {ahead}; GitHub ahead: {behind}', flush=True)
        return
    if args.action == 'pull':
        if git('status', '--porcelain', capture=True):
            raise ValueError('Commit or save local changes before pull; no automatic stash/reset')
        git('fetch', REMOTE, BRANCH)
        git('merge', '--ff-only', REMOTE + '/' + BRANCH)
        return
    ahead, behind = relation(remote_hash)
    print(f'Local ahead: {ahead}; GitHub ahead: {behind}', flush=True)
    if behind:
        raise ValueError('GitHub has new commits. Pull from a clean tree first; divergence needs manual merge')
    if git('diff', '--cached', '--name-only', capture=True):
        raise ValueError('Existing staged changes found; review and commit/unstage them first')
    raw = git('ls-files', '--modified', '--deleted', '--others', '--exclude-standard', '-z', capture=True)
    names = sorted(set(raw.split('\0')) - {''})
    names = [name for name in names if '__pycache__' not in Path(name).parts and not name.endswith('.pyc')]
    for name in names:
        if not allowed(name):
            raise ValueError('Unsupported/private path needs manual review: ' + name)
        if (ROOT / name).exists():
            inspect_content(name, (ROOT / name).read_text(encoding='utf-8'))
    if names:
        git('diff', '--stat')
        print('Files to commit: ' + ', '.join(names), flush=True)
    if not args.yes and input('Commit these changes and push to GitHub main? Type YES: ').strip() != 'YES':
        print('Cancelled; no commit or push')
        return
    if names:
        git('add', '-A', '--', *names)
        git('diff', '--cached', '--check')
        git('commit', '-m', args.message)
    # Normal push rejects concurrent remote changes; never force and never change upstream.
    git('push', REMOTE, 'HEAD:refs/heads/' + BRANCH)
    print('GitHub main synced. Gitee origin configuration unchanged.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, ValueError, OSError, UnicodeError) as exc:
        print('STOP: ' + str(exc), file=sys.stderr)
        sys.exit(1)
