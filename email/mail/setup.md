# Mail Skill — Credential Setup

## 1. Create a credentials file

Create `~/.claude/skills/mail/.env` and lock it down immediately:

```bash
touch ~/.claude/skills/mail/.env
chmod 600 ~/.claude/skills/mail/.env
```

Then populate it:

```
MAIL_USER=you@example.com
MAIL_PASSWORD=your-app-password
MAIL_IMAP_HOST=imap.example.com
MAIL_SMTP_HOST=smtp.example.com
# MAIL_IMAP_PORT=993   # optional, 993 is the default
# MAIL_SMTP_PORT=465   # optional, 465 is the default (use 587 for STARTTLS)
```

`mail.py` reads this file directly so passwords never appear in shell history
or the process table.

---

## 2. Provider-specific setup

### Gmail

Gmail requires an **App Password** — your normal Google password won't work once
2-Step Verification is enabled (which it should be).

1. Go to your Google Account → Security → 2-Step Verification (enable if not already on).
2. Then visit: https://myaccount.google.com/apppasswords
3. Select app: "Mail", device: "Other (Custom name)", name it "claude-mail".
4. Copy the 16-character password Google shows you (no spaces).
5. Use it as `MAIL_PASSWORD` in `.env`.

```
MAIL_USER=you@gmail.com
MAIL_PASSWORD=abcdabcdabcdabcd
MAIL_IMAP_HOST=imap.gmail.com
MAIL_SMTP_HOST=smtp.gmail.com
```

You may also need to enable IMAP in Gmail settings:
Settings → See all settings → Forwarding and POP/IMAP → IMAP access → Enable.

### Fastmail

Fastmail supports app passwords at: Settings → Privacy & Security → Third-party apps.
Generate one and use:

```
MAIL_USER=you@fastmail.com
MAIL_PASSWORD=your-fastmail-app-password
MAIL_IMAP_HOST=imap.fastmail.com
MAIL_SMTP_HOST=smtp.fastmail.com
```

### iCloud Mail

Generate an app-specific password at https://appleid.apple.com → Sign-In and Security → App-Specific Passwords.

```
MAIL_USER=you@icloud.com
MAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx
MAIL_IMAP_HOST=imap.mail.me.com
MAIL_SMTP_HOST=smtp.mail.me.com
MAIL_SMTP_PORT=587
```

### Generic IMAP/SMTP

Fill in the values from your provider's documentation. Most providers use:
- IMAP: port 993 with SSL (default)
- SMTP: port 465 with SSL, or 587 with STARTTLS (set `MAIL_SMTP_PORT=587`)

---

## 3. Verify the setup

Run the built-in connectivity check:

```bash
python3 ~/.claude/skills/mail/mail.py setup-check
```

Expected output on success:

```json
{"status": "ok", "env_file_found": true, "missing_vars": [], "user": "you@example.com", "imap": "ok", "smtp": "ok"}
```

If IMAP or SMTP shows an error, double-check the host, port, and password.

---

## Note on OAuth2

This skill uses password / app-password authentication. OAuth2 (required for some
Google Workspace or modern Office 365 setups with "Modern Authentication" enforced)
is not supported in v1. If your organization mandates OAuth2, you'll need a mailbox
that allows IMAP password auth (e.g. a personal Gmail with an App Password).
