# Review brief template

`render_review_brief.py` fills the `{{slot}}` markers below and prints the brief; pass its stdout verbatim as the `Agent({subagent_type: "general-purpose", ...})` prompt. Add no claims about the diff to it. A re-review runs the script again with `--diff-changed` set. Everything under the line is the brief.

---

Review the {{scope}} changes for ticket #{{ticket}} in {{worktree}} (branch {{branch}}). Effort: {{effort}}. Run git as `{{git}}`; run one plain command per Bash call.

Read the ticket first: `gh issue view {{ticket}} --json body -q .body`, then the docs it cites and the repo's coding standards.

Call `Skill("code-review", args="--build-cmd \"{{build_cmd}}\"")` yourself and return its report, reformatted per the Report rules below. The build gate must resolve (green or red) before you report. The Test step owns test execution: read test files and cite the test evidence below; run lint and type check only.

Test evidence from the Test step, on this exact tree: `{{test_evidence}}`.

Diff changed since the last review: {{diff_changed}}.

Check specifically, against code, not against this brief:
{{checks}}

Report rules:
- Name the weakest point of each changed file: the symbol, and the concrete input or state that would break it, confirmed by reading the code that guards it.
- Take every line count and test count from `git diff --stat` or the build gate output. State no test count, deploy step, or runtime behaviour you did not read from a command's output or from code.
- Return Critical, Major and Minor findings with file and symbol. A finding names a line this diff changed and the failure it causes. List each check that passed under "Verified", one line each, apart from the findings.
- Run every finder and verifier code-review dispatches in the foreground, and report only after each has returned. Quote each finder's own verdict line from its returned report; a finder that has not returned has no verdict to quote.
- Give no grade, score or emoji.
- Put any summary, statistics and action items above the verdict. The report's last line is `Verdict: approve` or `Verdict: request-changes`, with no heading mark or emoji before it and nothing after it. Approve only with zero Critical and Major findings.
