# Security Pattern Detection

This module contains Git command patterns for detecting security issues in code reviews, especially for large changesets.

Scope note: examples below assume committed scope and use the merge-base (three-dot) baseline `origin/$REVIEW_BASE_REF...HEAD`, where `REVIEW_BASE_REF` is the discovered PR base branch (default `main`). For working-tree scope, replace that baseline with `HEAD`. PR review consumes PR metadata and diffs without local worktree isolation.

## Priority 1: CRITICAL Security Issues

### Hardcoded AWS Credentials
```bash
git --no-pager diff "origin/...HEAD" | grep -E "AKIA[0-9A-Z]{16}"
git --no-pager diff "origin/...HEAD" | grep -iE "aws_access_key_id|aws_secret_access_key"
```

### Hardcoded Secrets & API Keys
```bash
git --no-pager diff "origin/...HEAD" | grep -iE "(password|secret|api.?key|token)\s*=\s*['\"]"
git --no-pager diff "origin/...HEAD" | grep -E "private static final String (PASSWORD|SECRET|API_KEY)"
```

### Database Credentials
```bash
git --no-pager diff "origin/...HEAD" | grep -iE "jdbc:.*://.*:.*@"
git --no-pager diff "origin/...HEAD" | grep -iE "DB_PASSWORD|DATABASE_PASS"
```

### PII in Logs
```bash
git --no-pager diff "origin/...HEAD" | grep -E "log\.(info|debug|warn).*email|ssn|credit.?card"
git --no-pager diff "origin/...HEAD" | grep -E "System\.out\.println.*password"
```

### SQL Injection Risks
```bash
git --no-pager diff "origin/...HEAD" | grep -E "\".*SELECT.*\+.*\""
git --no-pager diff "origin/...HEAD" | grep -E "jdbcTemplate\.execute\(.*\+.*\)"
```

### Dangerous Annotations
```bash
git --no-pager diff "origin/...HEAD" | grep -E "@PermitAll"
git --no-pager diff "origin/...HEAD" | grep -E "@PostConstruct.*Runtime\.exec"
```

### Command Injection
```bash
git --no-pager diff "origin/...HEAD" | grep -E "Runtime\.getRuntime\(\)\.exec"
git --no-pager diff "origin/...HEAD" | grep -E "ProcessBuilder.*\+"
```

### Weak CORS Configuration
```bash
git --no-pager diff "origin/...HEAD" | grep -E "setAllowedOrigins.*\"\*\""
git --no-pager diff "origin/...HEAD" | grep -E "addAllowedOrigin.*\"\*\""
```

---

## Priority 2: MAJOR Security Issues

### Exposed Sensitive Data
```bash
git --no-pager diff "origin/...HEAD" | grep -E "return.*\.item\(\)"  # DynamoDB raw access
git --no-pager diff "origin/...HEAD" | grep -E "Map<String,\s*AttributeValue>"  # Raw DynamoDB types
```

### Weak Authentication
```bash
git --no-pager diff "origin/...HEAD" | grep -E "Authentication.*null"
git --no-pager diff "origin/...HEAD" | grep -E "SecurityContextHolder.*clear"
```

### Insecure Data Handling
```bash
git --no-pager diff "origin/...HEAD" | grep -E "Base64\.encode"
git --no-pager diff "origin/...HEAD" | grep -E "new String.*getBytes"
```

---

## Security Pattern Priority Matrix

| Pattern | Severity | Points | Command Snippet |
|---------|----------|--------|----------------|
| AWS Credentials | 🔴 CRITICAL | -15 | `grep -E "AKIA[0-9A-Z]{16}"` |
| Hardcoded Secrets | 🔴 CRITICAL | -15 | `grep -iE "(password\|secret\|api.?key)"` |
| SQL Injection | 🔴 CRITICAL | -15 | `grep -E "\".*SELECT.*\+.*\""` |
| Command Injection | 🔴 CRITICAL | -15 | `grep -E "Runtime\.exec"` |
| PII in Logs | 🟠 MAJOR | -8 | `grep -E "log\..*email"` |
| Exposed DynamoDB | 🟠 MAJOR | -8 | `grep -E "AttributeValue"` |
| Weak CORS | 🟠 MAJOR | -8 | `grep -E "setAllowedOrigins.*\"\*\""` |
| Weak Auth | 🟠 MAJOR | -8 | `grep -E "Authentication.*null"` |

---

## Usage Guidelines

### For Small Changesets
Use basic commands to scan the full diff for security patterns.

### For Medium Changesets
Focus on high-risk areas:
- Configuration files
- API controllers
- Data access layers
- Authentication modules

### For Large Changesets
1. Start with CRITICAL pattern detection
2. Then MAJOR pattern detection
3. Finally targeted review by security-sensitive areas

### Performance Tips

- **Always use `--no-pager`** to avoid interactive pagers blocking automation
- **Add `|| true`** to grep commands that may find nothing (prevents pipeline failures)
- **Use `grep -v`** (not `grep -L`) to exclude patterns from piped input
- **Add `-A` and `-B` flags** for context lines when needed (e.g., `-A 5` for 5 lines after match)
- **Keep grep patterns simple** - complex regex can be slow on large diffs