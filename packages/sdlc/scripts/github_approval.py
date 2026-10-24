#!/usr/bin/env python3
"""Verify a role's actual GitHub PR approval for the clean current revision."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from sdlc import binding, git, read, require, run


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, help='GitHub owner/repository')
    parser.add_argument('--pr', required=True, type=int)
    parser.add_argument('--roles', required=True, type=Path, help='Managed role-to-login allowlist outside the checkout')
    args = parser.parse_args()
    request = json.load(sys.stdin)
    cwd = Path.cwd().resolve()
    try:
        require(args.pr > 0 and len(args.repo.split('/')) == 2, 'Invalid GitHub pull request')
        roles_path = args.roles.resolve(strict=True)
        require(not roles_path.is_relative_to(cwd), 'Role policy must be outside the agent checkout')
        roles = json.loads(read(roles_path))
        allowed = roles.get(request['role'], [])
        require(isinstance(allowed, list) and bool(allowed), 'No reviewers are authorized for this role')
        require(not git(cwd, 'status', '--porcelain'), 'Commit the artifacts and source before asking for GitHub approval')
        head = git(cwd, 'rev-parse', 'HEAD')
        require(request['digest'] == binding(cwd, request['stage']), 'Approval digest does not match the current artifacts')
        def api(path: str) -> object:
            result = run(['gh', 'api', path], cwd)
            require(result['code'] == 0, 'GitHub approval lookup failed')
            return json.loads(result['stdout'])
        prefix = f'repos/{args.repo}/pulls/{args.pr}'
        pr = api(prefix)
        require(isinstance(pr, dict) and pr['head']['sha'] == head, 'The pull request does not match the current revision')
        require(pr.get('state') == 'open' or pr.get('merged') is True, 'The pull request was closed without merge')
        # --paginate --slurp preserves all reviews, including a later dismissal.
        result = run(['gh', 'api', '--paginate', '--slurp', prefix + '/reviews'], cwd)
        require(result['code'] == 0, 'GitHub review lookup failed')
        reviews = [review for page in json.loads(result['stdout']) for review in page]
        latest = {}
        for review in sorted(reviews, key=lambda row: row['id']):
            if review.get('state') != 'PENDING':
                latest[review['user']['login']] = review
        for login in allowed:
            review = latest.get(login, {})
            independent = request['role'] not in ('code-owner', 'release-manager') or login != pr['user']['login']
            if independent and review.get('state') == 'APPROVED' and review.get('commit_id') == head:
                require(head == git(cwd, 'rev-parse', 'HEAD') and request['digest'] == binding(cwd, request['stage']), 'Revision changed during GitHub verification')
                print(json.dumps({**request, 'approved': True, 'approver': login, 'reference': review['html_url']}))
                return 0
        raise ValueError('No current independent approval from an authorized reviewer')
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'approved': False, 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
