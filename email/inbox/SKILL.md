---
name: inbox
description: >
  Organize and triage your inbox. Groups unread emails into categories, asks
  once what to do with each category, remembers your choice, and on later runs
  executes the remembered actions automatically (mark read, trash, archive,
  summarize, deep-dive). Use when the user says "organize my inbox", "clean up
  my email", "process inbox", "triage my mail", or types /inbox.
disable-model-invocation: true
---

# Inbox Skill

A triage layer on top of the `mail` skill. It categorizes unread email, learns
per-category preferences (stored in `~/.claude/skills/inbox/prefs.json`), and
acts on them. Known categories run without asking; new ones prompt the user.

This skill **depends on the `mail` skill** (`~/.claude/skills/mail/mail.py`) for
all mailbox access. It never talks to IMAP directly.

---

## Action vocabulary

Every category maps to exactly one action:

| action      | What it does |
|-------------|--------------|
| `mark_read` | Flag each message `\Seen` (stays in inbox). |
| `trash`     | Move each message to the Trash folder. |
| `archive`   | Move each message to the Archive folder. |
| `summary`   | Dedup + a concise digest; full email shown on request. No mailbox change. |
| `dive_deep` | Per-thread preview (From/Subject/Date + ~400 chars); full body on request. No mailbox change. |
| `skip`      | Leave untouched, just report the count. |

---

## Step 0 — Prerequisite check

Run the mail skill's connectivity check first:

```bash
python3 ~/.claude/skills/mail/mail.py setup-check
```

If it exits non-zero, surface the JSON error, tell the user to follow
`~/.claude/skills/mail/setup.md`, and stop. Do not continue.

**Optional:** Step 7 (HTML dashboard) invokes the `html-view` skill. If it is
not installed, Step 7 is silently skipped — no other step is affected.

---

## Step 1 — Load saved preferences

```bash
python3 ~/.claude/skills/inbox/inbox.py load-prefs
```

Parse the JSON. If `categories` is empty, this is a **first run** — every
category encountered will be new and will prompt the user (Step 4).

The `prefs.json` file is human-readable; an advanced user may edit category
names and actions directly.

---

## Step 2 — Fetch unread messages

```bash
python3 ~/.claude/skills/mail/mail.py list --filter unread --limit 100 --newest-first
```

This returns a JSON array of `{uid, date, from, to, subject, size, flags, folder}`.
If exactly 100 items come back, there may be more — page with `--offset 100`,
then `--offset 200`, etc., until a page returns fewer than 100. Collect every
message's `uid`, `from`, `subject`, `date` into a working set.

> Large inboxes: it is fine to triage the most recent N unread first and tell
> the user how many remain. Do not silently drop messages — report the count.

---

## Step 3 — Categorize (in-context)

Group the messages yourself using the `from` address and `subject`, seeded by
the category names already in prefs. Suggested heuristics:

- Marketing / bulk senders (`noreply@`, `no-reply@`, `@mail.`, `@news.`,
  `marketing@`, `newsletter@`) → **Newsletters** or **Promotions**
- Order / receipt / invoice / shipping keywords in subject → **Receipts**
- GitHub / GitLab / Jira / CI senders → **Dev Notifications**
- A real person's name in `From` with a direct, non-bulk subject → **Personal**
- Banking / statement / security-alert senders → **Finance**
- Anything unclear → **Uncategorized**

**Conflict resolution — first-match wins, in this priority order:**
1. Known sender address (a sender you've categorized before)
2. Subject keyword match
3. Domain / sender-pattern match

Produce a mapping `{ "CategoryName": [uid, uid, ...], ... }`.

For each category **already in prefs**, use its saved action — do not ask again.
Each category **not in prefs** is handled in Step 4.

---

## Step 4 — Ask about new categories

For every new category, show a compact summary and ask once. Use the
`AskUserQuestion` tool (or a numbered prompt) like:

```
Found 12 messages in "Newsletters"
(senders: Substack, Medium Daily, The Verge, …)

What should I do with these?
  1. Mark as read
  2. Move to Trash
  3. Move to Archive
  4. Summarize (dedup + digest, full email on request)
  5. Skip (leave untouched)
  6. Rename this category first
```

- Map the reply to an action from the vocabulary above.
- If the user picks rename, update the category key and re-ask the action.
- Ask whether to remember this for next time (default: yes).

When all new categories are resolved, persist. Build the updated prefs object
in-context and pipe it via **stdin** (never as a shell argument):

```bash
echo '<full prefs JSON>' | python3 ~/.claude/skills/inbox/inbox.py save-prefs
```

Set `last_updated` to the current timestamp. Each category entry has the shape
`{"action": "...", "folder_target": null|"Trash"|"Archive", "notes": null|"..."}`.

---

## Step 5 — Execute actions

Process categories in this order so the inbox quiets down first:
**`trash` → `mark_read` → `archive` → `summary` / `dive_deep` → `skip`.**

### Safety gate (mandatory)

Before any **destructive** action (`trash`, `mark_read`, `archive`) that affects
**more than 5 messages**, show the count and a one-line summary (senders + date
range) and ask for a single confirmation. Example:

> "Proceeding with saved preferences: 8 messages → Trash, 15 → marked read. OK?"

No timers, no auto-proceed — wait for an explicit yes. This is the safeguard
against a miscategorized personal email being trashed on a later run.

### Per-action execution

**`trash`**
1. Resolve the trash folder name once: `python3 ~/.claude/skills/mail/mail.py folders` → pick `Trash` (or `[Gmail]/Trash`).
2. For each UID: `python3 ~/.claude/skills/mail/mail.py move <uid> <TrashFolder>`
3. Report: "Moved N messages to Trash."

**`archive`** — same as trash, targeting the `Archive` folder.

**`mark_read`**
- For each UID: `python3 ~/.claude/skills/mail/mail.py flag <uid> read`
- Report: "Marked N messages as read."

**`summary`**
1. Fetch bodies: `python3 ~/.claude/skills/mail/mail.py read <uid> --text-only` for each UID (respect the body-fetch cap below).
2. Dedup: normalize subjects (strip `Re:` / `Fwd:` prefixes), group near-identical threads, keep the newest per thread.
3. Present a tight digest grouped by sub-topic (e.g. "3 GitHub PRs on foo/bar", "2 receipts from Amazon").
4. Offer: "Reply with a UID to read any of these in full." When asked, print the full `body` from the data you already fetched (re-fetch only if not in context).

**`dive_deep`**
- Fetch full bodies (respect the cap). Per thread, show From / Subject / Date and the first ~400 characters.
- Group by sender/thread, drop duplicates.
- Offer full body on request, same as `summary`.

**`skip`** — report "Left N messages untouched."

### Body-fetch cap

To protect the context window, fetch at most ~30 full bodies per `summary` /
`dive_deep` category per run. If a category exceeds that, summarize from headers
(the `list` data) and fetch individual bodies only when the user asks. Tell the
user when you've capped.

---

## Step 6 — Session tally

After all categories are processed, print a per-category result summary:

```
Inbox organized:
  • 12 newsletters → marked read
  • 7 receipts     → trashed
  • 3 GitHub       → summarized (2 unique threads)
  • 4 personal     → left untouched
```

Remind the user their preferences are saved and `/inbox` can be re-run anytime.

---

## Step 7 — HTML Dashboard (optional; uses html-view skill)

After the tally, generate a browsable HTML report by invoking the html-view skill.
If html-view is not installed or fails, this step is silently skipped — no other
step is affected.

### 7a — Check prerequisite

Confirm `~/.claude/skills/html-view/SKILL.md` exists. If absent, print:
```
html-view skill not found — skipping HTML report.
```
Stop Step 7 here (not an error).

### 7b — Assemble the session report in-context

Build a Markdown document from the session state (Steps 3–6). Use this structure:

```markdown
# Inbox Report — <session_date>

## <CategoryName>

**Action:** <action> | **Count:** <N>

<per-message list: "- From: X — Subject: Y" for up to 10 messages>
<digest text if available>

## <Next category>
...

## Session Summary

| Category | Action | Count |
|---|---|---|
| Newsletters | mark_read | 7 |
| ...         | ...       | … |

**Total processed:** N messages
```

One `##` section per category, then a `## Session Summary` table at the end.

### 7c — Invoke html-view

Pass the assembled Markdown to the html-view skill using the Skill tool:

```
skill: "html-view"
args: "<absolute path to the Markdown file, or the Markdown text directly>"
```

The skill selects **dashboard** mode automatically (multiple peer sections + a
summary table). It writes a self-contained HTML file and returns its path.

If the skill invocation fails for any reason, print:
```
html-view failed — skipping HTML report.
```
Stop Step 7 here.

### 7d — Report completion

Print the absolute path and file size returned by html-view. Ask the user if they
want to open it (`open <path>`) — do not auto-open.

---

## Notes

- **Email bodies are never written to disk.** When the optional HTML report
  (Step 7) runs, sender/subject metadata is written to ephemeral `mktemp` files
  and deleted immediately by an `EXIT` trap. Only category→action preferences
  persist (to `prefs.json`).
- **Folder names are discovered once per session** via `folders`, then reused for
  every move.
- **prefs.json is user-editable.** Mention this if the user wants to tweak a
  category or action without re-running the dialog.
