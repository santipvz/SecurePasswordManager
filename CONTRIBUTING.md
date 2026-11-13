# Contributing

Use English for issues, commit messages, pull requests, and documentation. Each change should address one issue or one independently reviewable part of a larger issue.

## Branches and releases

- Start feature and routine fix branches from `develop`. Open their pull requests against `develop`, the default integration branch.
- Use descriptive names such as `feature/42-vault-search` or `fix/42-copy-timeout`. Codex branches may use the `codex/` prefix.
- Cut `release/<version>` from `develop` and open a pull request against `main`. Tag the resulting release commit on `main`. Bring any release-only fixes back to `develop` in a separate pull request.
- Cut `hotfix/<issue>-<description>` from `main`. Open a pull request against `main`, then bring the fix back to `develop` in a separate pull request.
- Keep source branches short-lived. Squash every pull request. Use a fresh release branch for each release and carry back only release-specific changes.

## Commits and pull requests

1. Make each commit a coherent change that can be reviewed independently. Keep any tests or documentation needed to understand that change in the same commit.
2. Open a focused PR with a clear summary and verification steps. Use `Closes #42` on a PR to `develop` that completes issue #42. Use `Refs #42` for partial work and for PRs to `main`. GitHub evaluates automatic closing keywords for PRs into the default branch.
3. When the PR is ready, request a review with `@codex review` unless automatic review has already started. Address actionable findings and request a fresh review after significant changes.
4. Use **Squash and merge** after checks pass and review findings are resolved. The squash commit should summarize the change and preserve the issue link.

[Linking issues to pull requests](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) · [Codex code review](https://learn.chatgpt.com/docs/third-party/github)
