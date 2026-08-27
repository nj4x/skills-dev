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

## Wayfinding operations

GitHub has native sub-issues and issue dependencies. Use both — they render the frontier in the GitHub UI, so no body conventions are needed.

`gh` has no subcommand for either; go through `gh api`, and pass ids with `-F` (integer) rather than `-f` (string), which fails with `Invalid request`. Ids are the issue's `.id`, not its number.

Attach a ticket to its map:

```sh
id=$(gh api repos/{owner}/{repo}/issues/<ticket> --jq .id)
gh api -X POST repos/{owner}/{repo}/issues/<map>/sub_issues -F sub_issue_id=$id
```

Record that a ticket is blocked:

```sh
id=$(gh api repos/{owner}/{repo}/issues/<blocker> --jq .id)
gh api -X POST repos/{owner}/{repo}/issues/<ticket>/dependencies/blocked_by -F issue_id=$id
```

Read the whole map, frontier included — `total_blocked_by == 0` on an open child is takeable:

```sh
gh api repos/{owner}/{repo}/issues/<map>/sub_issues \
  --jq '.[] | "\(.number)\t\(.state)\t\(.issue_dependencies_summary.total_blocked_by)\t\(.title)"'
```

Claim a ticket with `gh issue edit <n> --add-assignee @me` before doing any work on it.

Labels `wayfinder:map`, `wayfinder:grilling`, `wayfinder:research`, `wayfinder:task`, and `wayfinder:prototype` already exist.

## PRs as a request surface

By default, PRs are not included in the triage queue. To enable PR-based work requests, update this file's frontmatter (add `prs_as_requests: true`) and configure the `triage` skill accordingly.
