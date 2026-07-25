---
name: mail
description: >
  Read, search, send, move, and flag email over IMAP/SMTP.
  Use when the user asks to check email, show unread messages, reply to someone,
  archive mail from a sender, mark messages, or perform any mailbox operation.
disable-model-invocation: true
---

# Mail Skill

## Step 0 — Credential check (first invocation)

Before any other command, run:

```bash
python3 ~/.claude/skills/mail/mail.py setup-check
```

If it exits non-zero with `"missing_vars"`, tell the user to follow
`~/.claude/skills/mail/setup.md` and stop. Do not attempt any further commands.

If IMAP or SMTP show an error, report the JSON output verbatim and stop.

---

## CLI invocation pattern

`mail.py` loads credentials from `~/.claude/skills/mail/.env` automatically.
Never prepend `MAIL_PASSWORD=...` to the command — credentials must not appear
on the command line or in shell history.

```bash
python3 ~/.claude/skills/mail/mail.py <subcommand> [args]
```

---

## Subcommand reference

### list — show messages

```bash
python3 ~/.claude/skills/mail/mail.py list \
  [--folder INBOX] \
  [--filter unread|all|from:ADDR|subject:TEXT] \
  [--limit 20] \
  [--offset 0]
```

Returns a JSON array: `[{uid, date, from, to, subject, size, flags, folder}, ...]`

- Default filter: `unread`
- Default limit: 20
- Use `--offset N` to page through large result sets (see pagination below)

### read — read a single message

```bash
python3 ~/.claude/skills/mail/mail.py read UID [--folder INBOX] [--text-only]
```

Returns: `{uid, from, to, cc, subject, date, message_id, body, attachments:[{filename,size}]}`

Attachment bytes are never fetched — only filename and size.

### send — compose and send

```bash
python3 ~/.claude/skills/mail/mail.py send \
  --to ADDR \
  [--cc ADDR] \
  [--subject "Subject"] \
  [--body "Body text"] \
  [--reply-to-uid UID] \
  [--folder INBOX]
```

With `--reply-to-uid`, the original message's headers are fetched to set
`In-Reply-To`/`References` and prepend "Re:" to the subject automatically.

Returns: `{"status":"sent", "to":..., "subject":..., "message_id":...}`

**Safety gate: always show the user To, Subject, and the first 200 characters of
the body, then ask for confirmation before calling `send`.**

### move — move to another folder

```bash
python3 ~/.claude/skills/mail/mail.py move UID TARGET_FOLDER [--folder INBOX]
```

Returns: `{"status":"moved", "uid":..., "from":..., "to":...}`

If COPY succeeds but source deletion fails, returns `{"status":"partial",...}` —
report this to the user so they can manually clean up.

If the target folder doesn't exist, the IMAP server will return an error that
is surfaced as `{"error":"move_failed",...}`. Run `folders` to show available
folder names.

### flag — set or clear a flag

```bash
python3 ~/.claude/skills/mail/mail.py flag UID ACTION [--folder INBOX]
```

ACTION choices: `read`, `unread`, `star`, `delete`

- `delete` sets `\Deleted` and runs EXPUNGE. The response includes a `"warning"`
  field — always surface this to the user. **Prefer `move` to Trash for safety.**

### folders — list all folders

```bash
python3 ~/.claude/skills/mail/mail.py folders
```

Returns a JSON array of folder name strings. Run this to discover the correct
name before a `move` (e.g. "Archive", "[Gmail]/All Mail", "Trash").

### setup-check — validate connectivity

```bash
python3 ~/.claude/skills/mail/mail.py setup-check
```

Returns a JSON health report. Run on first invocation or when the user
reports connection errors.

---

## Output handling

All commands write JSON to stdout. Parse with `json.loads()`.

- **`list`**: render as a numbered table: `#N  FROM  SUBJECT  DATE`
- **`read`**: show From/Subject/Date as a header block, then the body. Mention
  attachment names and sizes if any.
- **`send`/`move`/`flag`**: show a one-line confirmation: "Sent to X", "Moved to Y", etc.
- **`{"error":..,"detail":..}`**: report the `detail` field in plain language.
- **`{"status":"partial",...}`**: report the `detail` field and suggest the user
  check both the source and target folder in their mail client.

---

## Multi-step recipes

### Archive everything from X

```
1. list --filter from:X --limit 100
2. For each UID in the result, move UID Archive [--folder INBOX]
3. If the result had exactly 100 items, repeat from step 1 with --offset 100,
   then --offset 200, etc., until the result is shorter than --limit.
   (Pagination: repeat until result length < limit.)
```

**Safety gate: show the user the count and a summary (sender, date range) before
moving more than 5 messages, and ask for confirmation.**

### Reply to the latest from Y

```
1. list --filter from:Y --limit 1
2. read <UID from step 1>
3. Draft the reply body with the user's help
4. [Safety gate: show To, Subject, first 200 chars of body — confirm before sending]
5. send --reply-to-uid <UID> --body "..." [--to addr if different from original sender]
```

### Mark all unread as read

```
1. list --filter unread --limit 100
2. For each UID, flag <UID> read
3. If result had 100 items, repeat with --offset 100, then 200, etc., until empty.
   (Pagination: repeat until result length < limit.)
```

**Safety gate: show the count before flagging more than 5 messages.**

---

## Safety rules (mandatory)

1. **Always confirm before sending.** Show the user To, Subject, and the first 200
   characters of the body. Never call `send` without user approval in the same session.

2. **Always confirm before bulk operations.** If a bulk move, flag, or delete would
   affect more than 5 messages, show the count and a brief summary first and ask
   for confirmation.

3. **Never infer the password.** It must come from `~/.claude/skills/mail/.env` or
   the user's shell environment. Never ask the user to type it or read it from context.

4. **Warn on permanent deletion.** When `flag delete` is used, surface the `warning`
   field from the response. Recommend `move` to Trash instead.

5. **Never bulk-delete.** There is no "delete all" shorthand in the CLI. Always work
   message-by-message with explicit UIDs.

---

## Environment variable reference

| Variable        | Required | Default | Example              |
|-----------------|----------|---------|----------------------|
| MAIL_USER       | yes      | —       | me@example.com       |
| MAIL_PASSWORD   | yes      | —       | (app password)       |
| MAIL_IMAP_HOST  | yes      | —       | imap.gmail.com       |
| MAIL_SMTP_HOST  | yes      | —       | smtp.gmail.com       |
| MAIL_IMAP_PORT  | no       | 993     | 993                  |
| MAIL_SMTP_PORT  | no       | 465     | 587 (for STARTTLS)   |

Set these in `~/.claude/skills/mail/.env` (see `setup.md`). The file must be
`chmod 600`.

---

## Provider quick-start

**Gmail**
```
MAIL_USER=you@gmail.com
MAIL_PASSWORD=abcdabcdabcdabcd   # 16-char App Password (not your Google password)
MAIL_IMAP_HOST=imap.gmail.com
MAIL_SMTP_HOST=smtp.gmail.com
```
Requires IMAP enabled in Gmail settings and a Gmail App Password (see setup.md).

**Fastmail**
```
MAIL_USER=you@fastmail.com
MAIL_PASSWORD=your-fastmail-app-password
MAIL_IMAP_HOST=imap.fastmail.com
MAIL_SMTP_HOST=smtp.fastmail.com
```

**iCloud**
```
MAIL_USER=you@icloud.com
MAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx   # App-specific password from appleid.apple.com
MAIL_IMAP_HOST=imap.mail.me.com
MAIL_SMTP_HOST=smtp.mail.me.com
MAIL_SMTP_PORT=587
```
