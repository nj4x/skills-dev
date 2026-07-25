# Reject indexing paths outside supported Git working trees

With Git working-tree roots as the identity unit (ADR-0006), a path outside a supported repository has no implicit target root. We decided to reject it rather than fall back to the path itself, which would recreate root proliferation, or use a synthetic loose-files root, which would conflate unrelated content.

For a path definitively outside Git and outside the explicit allowlist, the error names the path and search boundary and suggests recovery:

`/path/to/file: no Git repository found. Initialize one with 'git init', index from an existing repository, or add the path to allowed_non_git_roots.`

## Authoritative resolution outcomes

ADR-0006's sanitized Git-plumbing resolver—not filesystem inspection or manual `gitdir:` parsing—classifies every candidate. The outcomes are:

- **Supported Git working tree:** its canonical Git root wins, even if an allowlist entry also matches.
- **Linked worktree:** return `unsupported_linked_worktree`; an allowlist cannot rescue it because it is Git content with unsafe divergent-checkout semantics.
- **Bare repository:** return `unsupported_bare_repository`; an allowlist cannot rescue it.
- **Definitively no Git repository:** consult `allowed_non_git_roots` only after ADR-0006's positive three-part proof: no physical `.git` ancestor, the version-tested C-locale no-repository diagnostic exactly matches, and stdout is empty. A generic nonzero Git exit alone never qualifies.
- **Malformed Git metadata, Git unavailable, timeout, permission/I/O error, dubious ownership, or malformed tool result:** return a distinct unknown-resolution error naming the failing operation, without `git init` advice. The allowlist is not consulted.

This distinction ensures transient or malformed Git state is never mislabeled as non-Git—a necessary condition for ADR-0008 never to purge real data.

## Explicit non-Git escape hatch

Some legitimate document collections live outside repositories. `allowed_non_git_roots` is a narrow, auditable configuration escape hatch: after Git discovery has definitively found no repository, a path below an allowlisted directory resolves to that directory. Absent an entry, the request is rejected. Allowlisted roots are exempt from ADR-0008's purge.

When allowlist entries overlap, the **innermost longest-matching canonical prefix wins**. For example, with `/a` and `/a/b` allowlisted, `/a/b/doc.pdf` belongs to `/a/b`; configuration order never matters.

Git has strict precedence. If an allowlisted directory later becomes part of a repository, the repository root wins and the allowlist is inert for that path. Startup logging warns about an allowlist entry resolved inside Git, but does not make that harmless misconfiguration fatal.

## Cache and configuration consistency

The canonicalized `allowed_non_git_roots` configuration has a generation/fingerprint. It is part of ADR-0006's resolution token, and **every mutation** revalidates the token using uncached Git discovery and the current allowlist generation. A cached allowlist mapping cannot authorize a write after `git init`, Git metadata changes, or configuration edits. Such a change restarts resolution; repeated instability returns retryable `root_resolution_changed` with no mutation.

All root-taking entry points—indexing, watching, synchronization, graph tools, search tools, and startup reconciliation—use this one resolver. No handler may invent local root fallback logic.

## Considered Options

- **Path-as-root fallback (rejected):** restores the fragmentation this design eliminates.
- **Synthetic loose-files root (rejected):** combines unrelated source domains in one graph.
- **Reject all non-Git paths (rejected):** removes intentional document-indexing use cases.
- **Allowlist overrides Git (rejected):** lets configuration fragment repository identity.
- **Git-first resolver plus explicit longest-prefix allowlist (chosen):** strict by default, ergonomic for deliberate non-Git content, and deterministic under overlap.

## Consequences

- A path is indexable only under a supported Git working-tree root or a deliberate, auditable non-Git allowlist boundary.
- Unknown Git discovery never gets a misleading `git init` recommendation and never falls through to an allowlist.
- Linked worktrees and bare repositories receive directed unsupported errors rather than arbitrary root identity.
- Allowlist changes and Git topology changes cannot cause stale cached mappings to write under an obsolete root.
