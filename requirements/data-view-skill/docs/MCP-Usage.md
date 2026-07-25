# MCP Usage for Data View Skill

How to use MCP semantic search tools when creating Data View documents.

---

## Available MCP Tools

| Tool | Purpose |
|------|---------|
| `index_files` | Index source documents into vector database |
| `search_documents` | Semantic search across indexed documents |
| `list_indexed_files` | Check which files are already indexed |

---

## When to Use MCP Search

Use semantic search to:
1. **Find entity definitions** — search for attribute names, types, constraints
2. **Find access patterns** — search for API endpoints, query parameters
3. **Find business rules** — search for constraints, validation rules
4. **Find event definitions** — search for Kafka topics, event names
5. **Validate design decisions** — search for requirements that inform denormalization choices

---

## Indexing Workflow

```
1. Call list_indexed_files(base_dirs=[source_directory])
2. IF files already indexed → proceed to search
3. IF files NOT indexed → ask user for permission to index
4. Call index_files(paths=[source_directory])
5. Proceed to search
```

---

## Search Patterns for Data View

| What You Need | Search Query Example |
|---------------|---------------------|
| Entity attributes | `"Group entity attributes type constraints"` |
| API endpoints | `"POST /v2/groups create group request body"` |
| Pagination | `"pageTag pageSize pagination next page"` |
| Events consumed | `"UserDeleted event consumed handler"` |
| Authorization rules | `"Super Admin Group Admin permission required"` |
| Uniqueness constraints | `"unique GroupId GroupAccountId"` |
| Circular reference | `"circular reference prevention nested group"` |

---

## Progressive Source Discovery

When searching, track already-processed files and exclude them in subsequent searches:

```
results1 = search_documents(query="group membership role")
processed = [r.file_path for r in results1]

results2 = search_documents(
    query="member role OWNER MANAGER",
    exclude_files=processed
)
```

This discovers NEW relevant documents instead of re-finding the same top matches.

---

## MCP Connection Recovery

If MCP tool call fails:
1. Ask user: "The MCP server `mcp-vectors` appears disconnected. Please reconnect it, then let me know when ready."
2. Wait for user confirmation before retrying.
