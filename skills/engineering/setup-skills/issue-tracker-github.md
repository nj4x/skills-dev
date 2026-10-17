# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --json number,title,body,labels,comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Make an issue a sub-issue of a parent**: `gh issue create --parent <parent> ...` when creating it, or `gh issue edit <parent> --add-sub-issue <child>` afterwards (both need `gh` 2.94 or later). On older `gh`, use `gh api --method POST repos/<owner>/<repo>/issues/<parent>/sub_issues -F sub_issue_id=<child-db-id>`, where `<child-db-id>` is the child's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number`); the endpoint hangs off the parent and takes only `sub_issue_id`. Where sub-issues aren't enabled, put `Part of #<parent>` at the top of the child body instead.
- **List the sub-issues of a parent**: `gh issue view <parent> --json subIssues --jq '.subIssues.nodes[].number'` (`gh` 2.94 or later). On older `gh`, use `gh api --paginate repos/<owner>/<repo>/issues/<parent>/sub_issues --jq '.[].number'`. Both print one child `#number` per line.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Closing work

Tickets close through the PR that ships them. GitHub acts only on a closing keyword (`Closes`, `Fixes`, `Resolves`, and their variants) in the PR description or a commit message, and only when the PR targets the default branch. `Refs #<n>`, `Ticket: #<n>`, `Part of #<n>`, and a `#<n>` in the PR title close nothing.

Decide the issue-link line per ticket, so one PR can mix both forms:

- Use `Refs #<n>` when the ticket still has unticked `## On close` items, or when the PR does not target the default branch (stacked PRs). Close that ticket by hand once its commits reach the default branch and its `## On close` items are ticked.
- Otherwise put one `Closes #<n>` line for the ticket in the PR body, never only in the title.
- For an issue in another repo, use `owner/repo#<n>` (for example `Closes owner/repo#<n>`).

Once its commits reach the default branch, read the issue state (`gh issue view <n> --json state`) and close it only if it is still open and its `## On close` items are ticked.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh api --paginate 'repos/{owner}/{repo}/pulls?state=open' --jq '.[] | select(.author_association | IN("OWNER","MEMBER","COLLABORATOR") | not) | {number, title, author: .user.login, author_association, labels: [.labels[].name]}'`. This drops `OWNER`/`MEMBER`/`COLLABORATOR` and keeps every other association. (`gh pr list --json` has no `authorAssociation` field, so the REST endpoint is used instead.)
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Read it as in **Read an issue** above.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue made a sub-issue of the map (see **Make an issue a sub-issue of a parent** above). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Execution map**: the successor a closed decision map hands its build work to — an issue titled `<parent map name> — implementation`, labelled `wayfinder:execution-map`, whose children are build slices worked with `/implement`.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.
