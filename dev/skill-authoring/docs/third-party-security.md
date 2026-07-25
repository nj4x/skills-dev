# Third-Party Skill Security Checklist

Use this checklist when your skill installs packages, downloads binaries, fetches remote scripts, or executes code from outside your repository. Skills that touch third-party code are a supply-chain surface — audit before shipping.

---

## When This Applies

Skip this checklist if your skill:
- Contains only prose instructions (no scripts/)
- Runs only first-party code already in your repo
- Makes no network calls

Apply this checklist if your skill:
- Runs `npm install`, `pip install`, `cargo add`, or similar
- Fetches a script and pipes it to a shell (`curl | sh`, `wget | bash`)
- Downloads a binary or archive and executes it
- Pulls a Docker image
- Calls an external API and acts on the response

---

## Checklist

### Dependency pinning
- [ ] All package installs pin an exact version (not `latest`, not a range)
- [ ] A lockfile is committed alongside any `package.json` / `requirements.txt` / `Cargo.toml`
- [ ] Checksums or hashes are verified where the package manager supports it (`pip install --require-hashes`, `npm ci`)

### Remote execution
- [ ] No `curl | sh` or `wget | bash` without first downloading, inspecting, and then executing
- [ ] Any remotely fetched script is pinned to a specific commit SHA, not a branch or tag
- [ ] The fetch URL is from an authoritative source (official package registry or the project's canonical repo)

### Network calls in scripts/
- [ ] Every outbound network call in `scripts/` is documented in the skill body with its destination and purpose
- [ ] No credentials, tokens, or secrets are passed as command-line arguments (use env vars or a secrets manager)
- [ ] No collected data is sent to an unexpected destination

### Trust and provenance
- [ ] The skill name is not similar to a well-known skill (typosquatting check)
- [ ] The source repo has a visible history and is not a fresh clone of a well-known project
- [ ] If the skill came from a third party, you have read every file in the skill folder before installing

### Sandboxing
- [ ] The skill has been dry-run in a sandbox environment (Docker, VM, or a fresh checkout) before adding to a production project
- [ ] File access in scripts/ is scoped to the expected directories — no writes outside the project root

---

## On Receiving a Third-Party Skill

Before installing any skill you didn't author:

1. **Read the full skill body** — check for instructions that steer the agent in unexpected ways
2. **Check the description** — confirm the trigger conditions match documented intent; a mismatched description may fire the skill when you don't want it
3. **Audit `scripts/`** — look for unconditional network calls, file writes outside the project, or credential capture
4. **Verify the skill name** — search for the name in your existing skills; confirm it doesn't shadow one you rely on
5. **Sandbox first** — test in an isolated environment before adding to your main project config
6. **Pin the version** — reference a specific commit, not `main` or `latest`

---

*Referenced from SKILL.md anti-patterns section. See [common-anti-patterns.md](common-anti-patterns.md) AP-20 for the anti-pattern entry.*
