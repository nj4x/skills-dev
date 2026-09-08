# Fowler Smell Baseline

Language-agnostic catalogue of recurring code smells (Refactoring ch.3). Finders reference this document as a vocabulary supplement; repo-specific standards take precedence when they conflict.

## Binding Rules

1. **Repo overrides baseline.** A documented repo standard (e.g. kotlin-standards.md, a CONTRIBUTING rule) always wins over this baseline — suppress any smell it endorses.
2. **Skip tooling-enforced smells.** Do not flag anything a linter, formatter, or static analyser already enforces; note it as a positive if the tooling is working.
3. **Smells are Notes only.** Every smell finding is reported at **Note** severity. It never affects the grade. "Works but could be nicer = Note."
4. **De-dup precedence.** If a smell overlaps a finding already reported by Finder B or Finder C at the same `file:line` (e.g. Duplicated Code ↔ Finder B "cross-file duplication"; Speculative Generality ↔ Finder C "dead code"), keep only the higher-severity Finder B/C finding; do not double-report.
5. **Judgement-call standard.** Only raise a smell you can name concretely with its paired fix and a specific code location. Prefer omission over speculation.

## The 12 Smells

| Smell | What it is | How to fix |
|---|---|---|
| **Mysterious Name** | A function, variable, or type whose name doesn't reveal what it does or holds. | Rename it; if no honest name comes, the design is murky. |
| **Duplicated Code** | The same logic shape appears in more than one hunk or file in the change. | Extract the shared shape, call it from both. |
| **Feature Envy** | A method that reaches into another object's data more than its own. | Move the method onto the data it envies. |
| **Data Clumps** | The same few fields or params keep travelling together (a type wanting to be born). | Bundle them into one type, pass that. |
| **Primitive Obsession** | A primitive or string standing in for a domain concept that deserves its own type. | Give the concept its own small type. |
| **Repeated Switches** | The same `switch`/`if`-cascade on the same type recurs across the change. | Replace with polymorphism, or one map both sites share. |
| **Shotgun Surgery** | One logical change forces scattered edits across many files in the diff. | Gather what changes together into one module. |
| **Divergent Change** | One file or module is edited for several unrelated reasons. | Split so each module changes for one reason. |
| **Speculative Generality** | Abstraction, parameters, or hooks added for needs the spec doesn't have. | Delete it; inline back until a real need shows. |
| **Message Chains** | Long `a.b().c().d()` navigation the caller shouldn't depend on. | Hide the walk behind one method on the first object. |
| **Middle Man** | A class or function that mostly just delegates onward. | Cut it, call the real target direct. |
| **Refused Bequest** | A subclass or implementer that ignores or overrides most of what it inherits. | Drop the inheritance, use composition. |
