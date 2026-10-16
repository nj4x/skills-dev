# Research: Should `wait-what` adopt ASD-STE100 writing rules?

**Date:** 2026-10-15
**Scope:** `skills/session/wait-what/SKILL.md` (the only file in the skill; no supporting files). ASD-STE100 Issue 9 (2025-01-15) read from the primary PDF. Repo STE references checked with `rg`.

---

## Summary

`wait-what` asks the agent to re-pitch its last message "talk in ASD-STE100 Simplified Technical English". The agent cannot load or enforce the full standard, and its dictionary is copyrighted. The useful part of STE for this skill is a small rule subset: short sentences, active voice, one term per concept, and no ambiguous pronouns. Recommendation: adopt selected rules, name them explicitly in the skill, and drop the claim of full STE compliance. Full adoption is not worth the cost.

---

## 1. What `wait-what` is and who reads what

The skill is `disable-model-invocation: true`, so only the user runs it (`skills/session/wait-what/SKILL.md:4`). Its full body is one paragraph (`SKILL.md:7`):

> Wait — I don't understand where you've got to here. Re-pitch that: give me a little bit of context, talk in ASD-STE100 Simplified Technical English, and use the ubiquitous language from `GLOSSARY.md` (follow `GLOSSARY-MAP.md` to the right one if the repo has more than one).

Two readers matter, and they differ:

- **The LLM reads `SKILL.md`.** It is an instruction, not prose for people. The model reads it as a prompt. STE's purpose (human non-native readers) does not apply to the file itself.
- **The human reads the output.** The user says "wait what" because the last message did not land. The output is what STE could improve. The reader is mid-session, has lost context, and may read English as a second language. The user never sees the skill text.

So the question is really: would STE rules improve the agent's re-pitch for a confused human reader? The answer is partly yes (see section 4).

### Provenance

The STE clause is **upstream text**, not a local edit. The `mattpocock/skills` `productivity/wait-what/SKILL.md` contains the same ASD-STE100 instruction (fetched via raw GitHub; the fetch tool returned a summary, not verbatim text, so the match is by summary only). The repo first received it in `734e3f3` (2026-08-05, "port skills from ~/projects/skills"). Later local edits changed only the glossary wording (`abf36b1`, `2a91870`, `0816eb5`). The README marks this as "Verbatim adoption" (`README.md:252`). Upstream sync notes are in `docs/research/upstream-skills-sync-2026-08-20.md:64,143-147`.

Consequence: changing the STE clause creates a local divergence from upstream. If adopted, `docs/agents/skill-authoring.md` ("Decisions rejected from upstream") should record it so future syncs do not reopen it.

---

## 2. ASD-STE100: what the primary source says

Source: ASD-STE100 Simplified Technical English, Issue 9, 2025-01-15, PDF at `https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf` (downloaded 2026-10-15; text extracted with `pdftotext`). Rule numbers below are from that PDF.

### Ownership, copyright, trademark

- Copyright: "The information in this document is the property of the Aerospace, Security and Defence Industries Association of Europe (ASD)." It states that "no reproduction or publication of it, in whole or in part, shall be made without the written authority of an officer of ASD." (Front matter, "Copyright notices".)
- Trademark: "ASD-STE100 Simplified Technical English is a European Union (EU) registered trademark owned by ASD," with registrations 004901195 (2006) and 017966390 (2018). (Front matter.)
- Usage carve-out: "Irrevocable permission to use, reproduce or publish this document ... free of charge" is granted to a closed list: ASD national associations and member companies, AIA and AIAC members, ICCAIA members, customers of those companies, defence ministries, A4A, airworthiness authorities, and universities and research institutes "for educational purposes." (Front matter, "Special usage rights".) An independent developer publishing a Claude Code skill is not on the list. The repo should not copy the dictionary or the rule text into the repo. Naming the standard and citing rule numbers is a different act, and the repo already does that (`skills/session/wait-what/SKILL.md:7`; `~/.claude/skills/caveman/SKILL.md:54`).
- Disclaimer: the standard says its rules and dictionary "are solely to offer recommendations and definitions ... not intended to create legal obligations." (Front matter, "Disclaimer of liability".) This is not legal advice. The copyright and trademark points above need a human check only if the repo ever redistributes STE text.

### Purpose and audience

- "The purpose of STE is to tell technical writers how to write technical texts in a clear, simple, and unambiguous manner that readers throughout the world will find easy to understand." (General introduction, "What is the purpose of STE?", p. i.)
- The motive is non-native readers: "it is not often the native language of the readers of technical documentation. Many readers have a limited knowledge of English." (General introduction, "When and why was STE developed?", p. i.)
- It is a writing standard for human technical writers, not a model prompt. It is not a "treatise on the English language" (General introduction, p. i).

### Writing rules relevant to the skill

| Topic | Rule (Issue 9) | Text |
|---|---|---|
| Sentence length, instructions | Rule 5.1 (Part 1, Section 5, p. 1-5-1) | "Use a maximum of 20 words in each sentence." Applies to "warnings, cautions, and other safety instructions" too. |
| Sentence length, descriptive | Rule 6.3 (Part 1, Section 6) | "Use a maximum of 25 words in each sentence." |
| Short, clear sentences | Rule 4.1 (Part 1, Section 4, p. 1-4-1) | "Write short and clear sentences that give accurate instructions and information." Procedures use the imperative. |
| One instruction per sentence | Rule 5.2 | "Write only one instruction in each sentence unless two or more actions occur at the same time." |
| Active voice | Rule 3.6 | "Use the active voice. In descriptive writing, you can use the passive voice only when the agent is unknown." |
| One term per concept | Rule 1.11 | "Do not use different technical nouns for the same item." |
| Technical nouns | Rules 1.1, 1.6 | Words must be approved in the dictionary, or be technical nouns/verbs. Rule 1.6: non-approved words only as technical nouns or parts of technical nouns. |
| Technical nouns as verbs | Rule 1.7 | "Do not use words that are technical nouns as verbs." |
| Ambiguous pronouns | GR-3 (Part 1, General recommendations) | "If a pronoun can refer to one or more nouns in a text, it can cause ambiguity ... replace the pronoun with the word that it refers to." |
| Multi-word nouns | Part 1, Section 2 | "keep multi-word nouns to a maximum of three words" (for non-native readers). |
| Dictionary | Part 2 | Controlled list of approved words, with parts of speech and approved meanings (Rules 1.2, 1.3). |

### Correction to a repo claim

`~/.claude/skills/caveman/SKILL.md:54` reads: "ASD-STE100 is the floor: 20 words max, active voice, imperative for instructions, one term per thing, pronoun only with an obvious referent." The 20-word cap is for **procedural** text (Rule 5.1). Descriptive text allows 25 (Rule 6.3). The caveman line applies 20 to everything. That is a minor inaccuracy and is worth fixing if anyone edits caveman.

### Source-quality note

The WebSearch summary for this task gave the 20/25 limits from memory and did not quote the rules. The figures above come from the PDF text, not the summary. The asd-ste100.org HTML pages (home, FAQ) returned HTTP 403 to WebFetch, so the FAQ was not checked. Anything the FAQ says about use outside aerospace or about AI tools is therefore unverified.

---

## 3. Existing STE use in the repo

`rg` for `ASD-STE100`, `Simplified Technical English`, and `\bSTE\b`:

- `skills/session/wait-what/SKILL.md:7`: the instruction under review.
- `~/.claude/skills/caveman/SKILL.md:54`: STE as "the floor" for caveman output (see the correction above).
- `~/.claude/skills/wait-what/SKILL.md:7`: a symlink to the repo file, same text.

No other repo file uses STE. `skills/dev/writing-for-agents/SKILL.md` has no STE reference. Its "Leading words" and "Negation" sections argue for a short, positive, concrete style (`skills/dev/writing-for-agents/SKILL.md`, "Leading words" section). Its guidance (prompt the positive; use leading words) points the same way as the selected STE rules, but it does not mention STE.

---

## 4. Assessment against the actual `wait-what` text

### Word counts (`wc -w`)

- Sentence 1, "Wait — I don't understand where you've got to here.": 8 words. Within the 20-word limit.
- Sentence 2, "Re-pitch that: give me ... more than one).": 35 words. Over the 20-word procedural limit (Rule 5.1) and over 25 (Rule 6.3). It is a single instruction with four clauses.

### What STE would help with

1. **Sentence length.** Sentence 2 bundles four instructions: re-pitch, give context, use STE, use glossary terms, plus a glossary fallback. Splitting them into short imperative sentences matches Rules 5.1 and 5.2. For an LLM this matters less than for a human; the model parses long sentences fine. The rule helps when the same text also describes what the output must look like.
2. **Vague scope.** "a little bit of context" has no measure. An STE-style rewrite still needs a concrete target, such as "one short paragraph". This is not an STE gain, but STE's preference for precise wording points the same way.
3. **Ambiguous referents.** Re-pitched output often says "it" or "this" after several topics. GR-3 gives a direct fix: name the thing again. This helps the human reader most, since the user has lost the thread.
4. **Passive and mixed voice.** Re-pitches tend toward passive explanations ("the cache is bypassed when..."). Rule 3.6 pushes the agent to name the actor.
5. **One term per concept.** "Use the ubiquitous language from `GLOSSARY.md`" already asks for one term per concept. STE Rule 1.11 says the same thing more strictly. The glossary asks for domain terms, so it is a natural fit.

### What STE would not help with, or would hurt

1. **Full dictionary restriction.** The agent cannot load the STE dictionary (Part 2 is large and copyrighted; see section 2). Without it the model approximates. "Talk in ASD-STE100" becomes a style claim the model cannot check, and a user cannot verify either. The instruction promises more than the agent can deliver.
2. **Domain vocabulary conflicts.** Glossary terms such as verbs or multi-word nouns (for example "tracer bullet", "grilling", "critic" as a verb) may not be approved. Rules 1.6 and 1.7 forbid non-approved words except as technical nouns, and forbid technical nouns used as verbs. The skill says to use glossary terms, so strict STE and the glossary rule will collide. In practice the glossary should win for domain terms (the skill's purpose is shared language), with STE applied to everything else.
3. **Non-native readers.** The main STE benefit is for non-native readers. The user is an English-speaking developer who runs this skill in English and reads English output. Non-native reader benefit is weak here. The benefit that still applies is for a reader who has lost context, which is a different problem.
4. **Checker and cost.** No STE checker exists in the repo, and the ASD tools page is a commercial product list (`asd-ste100.org/software.html`, not fetched). Compliance can only be judged by the model, and that is weak.
5. **Token cost.** Strict STE is short but produces more sentences and more repeated nouns (GR-3 says to repeat the noun instead of pronouns). That adds tokens to each re-pitch. Small, but not zero.

---

## 5. Before and after rewrites

These rewrite passages in the skill and a sample re-pitch. The sample facts are invented to show form; they are not from any real session.

### Passage A: the skill instruction (`SKILL.md:7`, sentence 2)

Before (35 words):
> Re-pitch that: give me a little bit of context, talk in ASD-STE100 Simplified Technical English, and use the ubiquitous language from `GLOSSARY.md` (follow `GLOSSARY-MAP.md` to the right one if the repo has more than one).

After (sentences 3-8 words each, one instruction each, rule names explicit):
> Re-pitch that message. Give a little context first. Use short sentences, each 20 words or fewer. Use active voice. Use the terms in `GLOSSARY.md`. If the repo has more than one glossary, check `GLOSSARY-MAP.md` first.

Notes: the rewrite replaces the claim "talk in ASD-STE100" with the three rules the agent can apply. It drops the full-standard claim. "A little context" remains vague; a concrete target could be added ("one short paragraph").

### Passage B: a sample re-pitch, dense (illustrative)

Before (one 31-word sentence plus a clause chain, with "it" and "this"):
> The retry loop re-sends every 5xx response, so the dedupe key we added last step is skipped whenever the body is partial, and that is what causes the duplicate events we were chasing.

Word count: 31. Two referents for "that" and "it" in the same sentence.

After (STE-style, nouns repeated, one idea per sentence):
> The retry loop re-sends every 5xx response. The dedupe key is skipped when the body is partial. That skip causes the duplicate events. Fix: check body length before the retry.

Per-sentence word counts: 7, 10, 6, 7. All under 20. "That skip" is one referent; if ambiguous, repeat "The dedupe skip".

### Passage C: pronoun ambiguity (GR-3 pattern)

Before:
> It fails when it reads the cache, so disable it.

After:
> The cache read fails when it runs first. Disable the cache read.

Per-sentence word counts: 8, 4. The rewrite removes "it" as a referent for two different things. Rule source: GR-3.

### Passage D: passive, unknown agent versus known agent (Rule 3.6)

Before:
> The config is overwritten by the migration.

After:
> The migration overwrites the config.

Word count: 5 to 5. The agent is known, so Rule 3.6's passive exception does not apply.

---

## 6. Recommendation

**Adopt selected rules. Do not adopt full STE.**

Selected rules, stated in the skill so the agent can apply them without the dictionary:

1. Sentences of 20 words or fewer. (Rule 5.1, applied to all output for simplicity.)
2. Active voice; name the actor. (Rule 3.6.)
3. One term per concept; use the `GLOSSARY.md` term every time. (Rule 1.11 plus the existing glossary rule.)
4. No bare pronoun when two nouns could be its referent. (GR-3.)

Reasons:

- The benefit is for a confused human reader in the middle of a session. The four rules above target exactly that: short sentences, clear referents, one term per concept. The full dictionary adds cost and conflicts with the glossary.
- The agent cannot load the dictionary or check it, and the claim "talk in ASD-STE100" is not verifiable. An explicit rule list is verifiable by the user at a glance.
- Copyright and trademark terms mean the repo should cite rule numbers and paraphrase, not reproduce STE text. The proposed list does that.
- Cost: a few words in the SKILL.md, a short local divergence from upstream (record it in `docs/agents/skill-authoring.md`), and a risk that over-strict sentence limits cut needed context. Mitigation: keep "give a little context" as the first priority, so the length rule does not remove the context the user asked for.
- Upstream sync: the change touches a line that is upstream text. Future upstream diffs will show it as a conflict. Record the decision so a future sync does not undo it silently.

Alternative: keep the text as is. The "talk in ASD-STE100" claim is weak but harmless, and the cost of changing it is a local fork. This is a defensible option if the repo prefers upstream parity. The recommendation above is for the case where readability of the re-pitch is the goal.

Full adoption: not recommended. Reasons are in section 4 (dictionary restriction, glossary conflict, no checker, copyright boundary).

---

## Open items

- The ASD-STE100 FAQ (`https://www.asd-ste100.org/STE_faq.html`) returned HTTP 403 to WebFetch. Check it by hand before claiming anything about use outside aerospace.
- Rules 3.6, 4.1, 5.1, 6.3, GR-3 were read from the Issue 9 PDF text. Check page numbers against a printed copy before quoting page references in a published doc.
- Upstream `wait-what` text was checked by summary only. Confirm verbatim before recording the divergence in `skill-authoring.md`.
