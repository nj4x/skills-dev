# MCP Semantic Search Usage Guide

> The MCP `mcp-vectors` server provides powerful semantic search capabilities for exploring source documents. **Use these tools instead of simple file reading for better content discovery.**

## Available MCP Tools

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `index_files` | Index documents for semantic search | **ONLY after user approval** - Before any semantic search operations |
| `search_documents` | Find related content by meaning | Exploring sources, validating requirements, finding categories |
| `list_indexed_files` | Check what's already indexed | Before indexing to avoid redundant work |

---

## Indexing Source Documents

> **⛔ CRITICAL**: Document indexing is OPTIONAL and requires EXPLICIT user approval. Do NOT index documents without user consent.

### Indexing Approval Checkpoint

**You MUST ask the user for approval before indexing documents using this EXACT format:**

```
"Would you like me to index the source documents at `<ABSOLUTE_PATH>` for semantic search?

This enables more accurate content discovery but may take a few moments.

Options:
1. Yes, index the documents
2. No, check if already indexed first  
3. No, skip indexing - use direct file reading"
```

### After User Responds

| User Response | Action |
|---------------|--------|
| "Yes, index the documents" | Call `index_files` with the source directory path |
| "No, check if already indexed first" | Call `list_indexed_files` to check status |
| "No, skip indexing" | Use `read_file` and `search_files` as fallback |

> **PATH REQUIREMENT**: Always use ABSOLUTE paths when calling MCP tools.

---

## Semantic Search Usage

Use `search_documents` for:
- **Exploring source content**: Find all mentions of a concept
- **Validating requirements**: Check if source supports a requirement
- **Discovering categories**: Find groupings and topics
- **Cross-referencing**: Find related content across documents

Use natural language queries - semantic search understands meaning, not just keywords.

---

## Mandatory Search Trigger

> **⚡ RULE**: When user provides a source directory path in their request (e.g., `/Users/.../FeatureSets_v2.0`), semantic search via MCP tools is MANDATORY.

**Sequence when source directory is provided:**
1. Call `list_indexed_files` with `base_dirs=[<source_directory>]` to check if already indexed
2. IF already indexed → Skip to step 4
3. IF not indexed → Ask user for indexing approval (per approval process above)
   - IF user approves → Index documents
   - IF user declines → Notify user: "Indexing is required for semantic search when source directory is provided. Proceeding with indexing." → Index documents anyway
4. THEN use `search_documents` for ALL content exploration and validation

**Note**: Indexing approval is for user awareness and courtesy. When a source directory is explicitly provided in the user request, semantic search is mandatory and requires indexed content to function effectively.

---

## MCP Connection Recovery

> **⚡ RULE**: If MCP tool call fails or server appears disconnected, DO NOT silently fall back to file reading.

**Error Handling Sequence:**

1. **IF MCP call fails** (connection error, timeout, server unavailable):
   - Ask user: "The MCP server `mcp-vectors` appears to be disconnected. Please reconnect it in Cline's MCP Servers settings (click the server icon in the toolbar), then let me know when ready."
   - WAIT for user confirmation

2. **IF user confirms reconnection** → Retry the MCP call

3. **IF user cannot reconnect** (explicitly says so) → Check for CLI fallback availability using the **mcp-skill**:
   - Use the **mcp-skill** to access MCP server functionality via CLI interface
   - Call `mcp-vectors --client --help` to verify CLI availability
   - IF CLI available → Use CLI fallback transparently (see [mcp-skill documentation](<skill dir>/../mcp-skill/docs/fallback-strategy.md) for implementation details)
   - IF CLI unavailable → Use fallback methods (`read_file`, `search_files`)

> **⛔ DO NOT** skip MCP tools silently when source directory is provided. Always inform the user of connection issues and wait for resolution.

### CLI Fallback with mcp-skill

When the standard MCP protocol is unavailable, the **mcp-skill** provides CLI interface access to MCP server functionality:

- **Discovery**: `mcp-vectors --client --help` lists available tools
- **Tool Invocation**: `mcp-vectors --client --tool <tool_name> --param:<param_name> <param_value>`
- **Array Parameters**: Use JSON-encoded arrays (see [mcp-skill CLI usage](<skill dir>/../mcp-skill/docs/cli-usage.md))

Example CLI fallback for `index_files`:
```bash
mcp-vectors --client --tool index_files --param:paths '["/docs/project1", "/docs/project2"]' --param:recursive true
```

See the **mcp-skill** documentation for complete CLI usage patterns and fallback implementation strategies.

---

## Source Document Access Workflow

> **⚡ MANDATORY FIRST STEP**: Before ANY file exploration, determine the source access method.

**Decision Tree:**

```
IF user request contains a source directory path (e.g., `/Users/.../FeatureSets_v2.0`)
  → IMMEDIATELY call `list_indexed_files` with base_dirs=[source_directory]
  → IF files are indexed → Proceed using semantic search
  → IF files are NOT indexed → Ask user for indexing approval:
      "Would you like me to index the source documents for semantic search?"
      → IF user approves → Call `index_files`, then proceed
      → IF user declines → Notify: "Indexing required for semantic search. Proceeding." → Call `index_files`

IF user request does NOT contain a source directory path
  → Use `read_file` and `search_files` as fallback methods
```

> **⛔ DO NOT** use `list_files` or `read_file` to explore source directories when a source path is provided. Use MCP semantic search tools instead.