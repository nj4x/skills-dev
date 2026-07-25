# Issue tracker: GitHub Issues

Issues and specs for this repo are tracked in GitHub Issues using the `gh` CLI.

## Conventions

- Skills like `to-tickets`, `to-spec`, and `triage` create issues via `gh issue create`
- Issue titles follow the pattern `<category>: <title>` (e.g., `feature: add user authentication`)
- Issue bodies use Markdown and may include labels for categorization
- Issue state is managed via labels and GitHub's native state (open/closed)

## When a skill says "publish to the issue tracker"

Create a new issue using `gh issue create` with the provided title and body. The skill will handle label assignment and state transitions.

## When a skill says "fetch the relevant ticket"

Read the issue via `gh issue view <number>` or the GitHub web UI. The user will normally pass the issue number directly.

## PRs as a request surface

By default, PRs are not included in the triage queue. To enable PR-based work requests, update this file's frontmatter (add `prs_as_requests: true`) and configure the `triage` skill accordingly.
