# Design decisions: worker repo access and delegation model

Resolved via grilling and domain-modeling, captured in ADR-0075.

## ADRs

- [docs/adr/0075-worker-repo-access-and-delegation-model.md](../docs/adr/0075-worker-repo-access-and-delegation-model.md) — Worker accesses live repo_path, no clone or staging. Writes allowed within repo_path minus denylist. Delegation model: capable agent that opens the window trusts the model in it.
