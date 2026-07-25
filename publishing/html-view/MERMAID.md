# Mermaid.js Diagrams

When the source contains sequence diagrams, flowcharts, state machines, or class diagrams, use **Mermaid.js** for client-side rendering instead of hand-drawing inline SVGs. Mermaid produces consistent, well-laid diagrams from a declarative text syntax.

### Setup

Add these two elements to the HTML:

1. **CDN script** (before `</body>`):
   ```html
   <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
   <script>
   mermaid.initialize({
     startOnLoad: true,
     securityLevel: 'loose',
     theme: 'base',
     themeVariables: {
       primaryColor: '#0072b2',
       primaryTextColor: '#ffffff',
       primaryBorderColor: '#005a8e',
       lineColor: '#6b6b6b',
       secondaryColor: '#e69f00',
       tertiaryColor: '#009e73'
     }
   });
   </script>
   ```
2. **Diagram block** (where the diagram should appear):
   ```html
   <pre class="mermaid">
   sequenceDiagram
       ...
   </pre>
   ```

**Always set `securityLevel: 'loose'`** — without it, Mermaid sanitizes diagram text aggressively and can break rendering.

### Syntax rules (CRITICAL — Mermaid 11.x parser is strict)

These rules were learned from hard debugging. Violating any of them produces **"Syntax error in text"** with no line number.

1. **No `#` in message or note text.** The `#` character triggers Mermaid's HTML entity parser (e.g., `U#userId` tries to resolve `userId` as an entity code → parse error). Replace with the word "number" or omit entirely.
   - ❌ `Service->>DB: findByAccountId(U#userId)` → **Syntax error**
   - ✅ `Service->>DB: findByAccountId username`

2. **No colons in message text.** Colons delimit the message body from the participant. Use a space or dash instead.
   - ❌ `Note right of Service: accountType: CLASSROOM` → **Syntax error**
   - ✅ `Note right of Service: accountType CLASSROOM`

3. **No parentheses `()` in unquoted message text.** Parentheses are reserved for actor shapes. Either remove them or wrap the entire message in double quotes.
   - ❌ `Service->>Service: validateAccountType()` → **Syntax error**
   - ✅ `Service->>Service: validateAccountType`
   - ✅ `Service->>Service: "validateAccountType()"` (quoted works but looks odd in rendered output)

4. **No angle brackets `<>` in any text.** They are parsed as HTML tags. Spell out instead.
   - ❌ `Note right of Service: no <>= allowed` → **Syntax error**
   - ✅ `Note right of Service: no angle brackets or equals`

5. **No `+` in unquoted message text.** Plus signs can confuse the parser. Use "and" instead.
   - ❌ `Service->>DB: save(user + TempPwdEntity)` → **Syntax error**
   - ✅ `Service->>DB: save user and TemporaryPasswordEntity`

6. **No `.` after keywords like `event` or `topic`.** Dots in note text are fine, but avoid them right after Mermaid keywords.
   - ❌ `Service->>Kafka: publish(event.identity.user:CREATE)` → **Syntax error** (colon + parens)
   - ✅ `Service->>Kafka: publish event.identity.user CREATE`

7. **Keep note text concise.** Long notes with multiple special characters are error-prone. Move detailed content to the HTML prose sections instead.

### Safe character reference

| Character | Safe in message/note? | Replacement |
|-----------|----------------------|-------------|
| `#` | ❌ NO | Omit or use "number" |
| `:` | ❌ NO (in messages) | Space or dash |
| `()` | ❌ NO (unquoted) | Remove or quote entire text |
| `<>` | ❌ NO | Spell out "angle brackets" |
| `+` | ⚠️ Risky | Use "and" |
| `.` | ✅ OK in notes | — |
| `-` | ✅ OK | — |
| `/` | ✅ OK | — |
| `_` | ✅ OK | — |
| `=` | ⚠️ Risky | Use "equals" or space |
| `{}` | ⚠️ Risky unquoted | Remove or simplify |

### Converting PlantUML to Mermaid

When the source markdown contains PlantUML diagrams, convert them:

| PlantUML | Mermaid |
|----------|--------|
| `actor "Admin" as Actor` | `actor Admin` |
| `participant "API Gateway" as GW` | `participant GW as API Gateway` |
| `Actor -> GW: message` | `Admin->>GW: message` |
| `GW --> Service: response` | `GW-->>Service: response` |
| `note right: text` | `Note right of Service: text` |
| `note left: text` | `Note left of Admin: text` |
| `note over A,B: text` | `Note over A,B: text` |
| `alt condition` / `end` | `alt condition` / `end` |
| `@startuml` / `@enduml` | (omit — not needed) |
| `autonumber` | `autonumber` |
| `activate` / `deactivate` | (omit — Mermaid auto-activates) |

**Key difference**: PlantUML allows rich text with `()`, `:`, `#`, `+` in messages. Mermaid does not. Always sanitize these when converting.

### Diagram container styling

Wrap each diagram in a styled container:

```html
<div class="diagram-wrap">
  <div class="diagram-title">UC-001: Create Classroom Account</div>
  <pre class="mermaid">
  sequenceDiagram
      ...
  </pre>
</div>
```

CSS for the container:
```css
.diagram-wrap {
  margin: 1.5rem 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow-x: auto;
  padding: 1rem;
  background: var(--bg-alt);
}
.diagram-wrap .diagram-title {
  font-size: .75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .05em;
  color: var(--text-muted);
  margin-bottom: .75rem;
}
```

### Large sequence diagrams — multi-file pattern

For **large sequence diagrams** (complex flows with many participants, alt branches, or notes), use the **multi-file pattern** to keep the main HTML clean and let the diagram render at full size with native browser scrolling:

1. **Create a separate `-diagram.html` file** (e.g., `uc-001-diagram.html`) containing only the diagram:
   - Minimal CSS (dark mode support, diagram title styling)
   - The `<pre class="mermaid">` block
   - Mermaid CDN script with `securityLevel: 'loose'` and `useMaxWidth: false`
   - No external dependencies, fully self-contained

2. **In the main HTML**, replace the inline diagram with a styled link:
   ```html
   <a class="diagram-link" href="uc-001-diagram.html" target="_blank">
     View Sequence Diagram &rarr;
   </a>
   ```
   ```css
   .diagram-link {
     display: inline-block;
     margin: 1.5rem 0;
     padding: .75rem 1rem;
     background: var(--primary-light);
     border: 1px solid var(--primary);
     border-radius: var(--radius);
     color: var(--primary);
     font-weight: 500;
   }
   .diagram-link:hover {
     background: var(--primary);
     color: #fff;
     text-decoration: none;
   }
   ```

3. **When to use multi-file vs inline**:
   - **Multi-file**: Sequence diagrams with > 8 participants, > 15 messages, or complex alt/loop blocks
   - **Inline**: Flowcharts, state diagrams, class diagrams, or simple sequence diagrams (< 8 participants, < 15 messages)

4. **Benefits**:
   - Main HTML stays focused on content
   - Diagram page can use full viewport with native scroll (horizontal + vertical)
   - Cleaner separation of concerns
   - Each file is smaller and faster to load

### Multi-file output

When generating multiple HTML pages (e.g., one per use case), each page includes its own Mermaid CDN script. This is acceptable — each page is self-contained and works offline after first load (browser caches the CDN script).

**Parallel fan-out (≥ 2 files):** When producing two or more independent HTML files, launch one Agent subagent per file **in a single message** (parallel execution). Pass each subagent the shared design-system constraints — colour palette, typography scale, layout tokens, and the inter-file nav structure — in its prompt. Each subagent writes its HTML to a unique temp path (avoids returning large HTML through the main context). Main thread reconciles: verify nav links are consistent across all files, check the design tokens are used uniformly, then move the files to their final destinations. Single-file outputs use the existing single-pass path unchanged; if any subagent fails, regenerate that file serially.
