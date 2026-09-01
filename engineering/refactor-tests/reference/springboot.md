# Spring Boot test-runtime reference

Phase C reference for the `refactor-tests` skill: cutting **wall time** out of a JVM Spring Boot suite without changing what it asserts. Layout (Phase A) and test-function redundancy (Phase B) are about files and functions; this file is about the cost of the **Spring application context**.

Java/Kotlin path templates, runner detection, and AST tooling live in `patterns.md`. Nothing here repeats them.

Steps C0–C4 run in order. **Traps** at the tail is consult-on-demand reference — read it when a switch appears to do nothing (Trap 1), a scheduled method fires anyway (Trap 2), a class carries `@DirtiesContext` and is therefore outside the cluster (Trap 3), a test passes alone but fails in the suite after consolidation (Trap 4), or a class is slow with no context to blame (Trap 5).

**Provenance legend** — every claim is marked:

| Mark | Meaning |
|---|---|
| `[C]` | Evidenced by a real commit that applied it (`2b0f6bf7`, a Kotlin + Spring Boot + Gradle service; ~16 `@SpringBootTest` classes). |
| `[S]` | Standard documented Spring/Spring Boot behaviour, not evidenced by that commit. Confirm against the project's Spring version before relying on it. |
| `[D]` | Derived risk — a consequence of `[C]`/`[S]` that the commit did not hit. Treat as a check to run, not a fact. |

---

## Step C0 — Does this file apply?

Apply Phase C only when **all** hold. Run from `PROJECT_PATH` (the skill's Step 1 resolves an absolute path; enter it before running these checks).

**Check 1: JVM build**

At least one of `build.gradle`, `build.gradle.kts`, or `pom.xml` exists in the current directory.

**Check 2: Spring Boot dependency**

```sh
rg 'org\.springframework\.boot' build.gradle build.gradle.kts pom.xml 2>/dev/null | grep -q .
```

Non-zero exit = no Spring Boot dependency found; skip Phase C. Zero exit = Spring Boot dependency present, continue.

**Check 3: Context-loading tests exist**

```sh
rg -l '@(SpringBootTest|WebMvcTest|DataJpaTest|WebFluxTest)' -g 'src/test/**' 2>/dev/null | wc -l
```

Count must be ≥ 2. If `src/test` does not exist, the command returns 0 and Phase C is skipped.

**Decision:** if all three checks pass, proceed to Step C1. Otherwise skip Phase C and note in the report.

---

## The cost model: contexts, not tests

Spring's TestContext framework caches application contexts keyed by configuration. Two test classes with the **same key** share one context; two with **different keys** each pay a full application startup. `[S]`

Suite wall time therefore tracks **distinct cache keys**, not test count. A suite of 400 tests across 3 keys is fast; 16 tests across 16 keys is slow. Optimise key diversity first, per-context background work second.

### What goes into the cache key

| Key input | Notes |
|---|---|
| `@ContextConfiguration` locations/classes | Includes what `@SpringBootTest` resolves to `[S]` |
| Active profiles (`@ActiveProfiles`) | `[S]` |
| `@TestPropertySource` locations and inline properties | `[S]` |
| `@SpringBootTest(properties = ...)` / `webEnvironment` | `[S]` |
| Context initializers, parent context | `[S]` |
| **Registered `ContextCustomizer` set** | The lever that matters — see below `[S]` |

A `ContextCustomizer` participates in `equals`/`hashCode`, so anything a customizer folds in becomes part of the key. Two that dominate real suites:

| Customizer source | What it folds in |
|---|---|
| springmockk `MockkContextCustomizer` | The set of `@MockkBean` / `@SpykBean` declarations on the test class `[S]` (implementation: data class over `Definition` set with derived `equals`/`hashCode`) |
| Spring Boot `MockitoContextCustomizer` | The set of `@MockBean` / `@SpyBean` declarations `[S]` |

**Consequence:** every test class with its own bespoke mock set forces its own full application startup — even when the classes are otherwise annotated identically. This is the single highest-leverage finding. `[C]`

`@DirtiesContext` is the other side: it **evicts** the context after the method or class, so the next class with that key pays a fresh startup. `[S]`

---

## Step C1 — Measure the baseline

Do this before any edit. Record the numbers in the ledger under `spring.baseline`.

| What | How |
|---|---|
| Distinct contexts + cache hit/miss | **For Gradle:** add `systemProperty 'logging.level.org.springframework.test.context.cache', 'DEBUG'` to the `test` task (see Trap 1 below for the reason). Spring logs cache statistics (`size`, `maxSize`, `hitCount`, `missCount`) as contexts are acquired; the final `missCount` is the number of contexts built. Alternatively, set the logger level in `src/test/resources/logback-test.xml`: `<logger name="org.springframework.test.context.cache" level="DEBUG"/>`. `[S]` |
| Contexts, fallback count | Count Spring Boot startup lines in the run log — one `Starting …` / `Started … in N seconds` pair per context refresh. `[S]` |
| Wall time | **Gradle:** `./gradlew cleanTest test` or `./gradlew test --rerun-tasks` (vanilla `gradle test` is UP-TO-DATE on the second run and reports zero elapsed time). Run twice on the same warm daemon and keep the second; first run warms the JVM. **Maven:** `mvn clean test` and `mvn test` (no UP-TO-DATE skipping; both measure full execution). `[D]` |
| Slowest classes | Gradle: `build/reports/tests/test/index.html` sorts classes by duration. Maven: Surefire `*.txt` reports carry per-class elapsed time. `[S]` |

**Cache eviction check:** if `missCount` exceeds the number of distinct keys you can account for, contexts are being evicted. Either `@DirtiesContext` is in play, or the key count exceeded `spring.test.context.cache.maxSize` (default 32) and the LRU cache is thrashing. `[S]` Raising `maxSize` is a legitimate fix only when key count is genuinely irreducible — reduce keys first.

**Alternative: in-process listener.** Register an `AbstractTestExecutionListener` subclass via `META-INF/spring.factories` under `org.springframework.test.context.TestExecutionListener`. The listener captures `System.identityHashCode(testContext.applicationContext)` in `prepareTestInstance` to group classes by context, and `TimeSource.Monotonic` marks in `beforeTestClass`/`afterTestClass` to separate context startup overhead from per-method time. A JVM shutdown hook writes the grouped report to `build/reports/`. A CI step cats it into `$GITHUB_STEP_SUMMARY` with `if: always()` so it publishes even on a failing run. This approach measures what actually happened, not what the cache statistics claim should happen, and it persists across runs as a CI artifact.

---

## Step C2 — Base-class consolidation (highest leverage)

Collapse a cluster of near-identical context-loading test classes onto one shared abstract base holding the **union** of their mocks.

### C2.1 — Detect the cluster

For every test class matched in Step C0, extract with the language's AST parser (`patterns.md` → AST editor guidance):

- the class-level annotation set (`@SpringBootTest` and its attributes, `@AutoConfigure*`, `@ActiveProfiles`, `@TestPropertySource`, `@DirtiesContext`)
- the declared mock fields: `{ name, type, annotation }` for each `@MockkBean` / `@SpykBean` / `@MockBean` / `@SpyBean`

A **cluster** is the set of classes sharing an identical class-level annotation set (ignoring mock fields) and carrying **no** `@DirtiesContext`. In the reference commit the cluster was every class annotated `@SpringBootTest` + `@AutoConfigureWebTestClient` + `@AutoConfigureRestDocs` — ~16 classes, each with its own mock subset. `[C]`

**Cluster scope:** the only lever here is sharing one context across classes that already agree on their annotations. Re-annotating a `@SpringBootTest` as a "faster" `@WebMvcTest`/`@DataJpaTest` slice is a different cache key and a different wiring — a test-design change, out of scope for this skill.

**Threshold decision:** Clusters of fewer than 3 classes are not worth a base class by default. Skip them — the mock union gains little, and refactoring adds coupling. Override only when a 2-class cluster has a measured >15s context cost (in which case sharing it halves the startup cost). Note: Phase C gates entry at ≥2 classes (Step C0) but refuses to act at <3 classes (here); projects at exactly 2 classes enter Phase C only to receive no consolidation. This is intentional: the measurement baseline (Step C1) becomes useful for that 2-class project later.

### C2.2 — Compute the mock union

Union the mock fields across the cluster, keyed by **declared type**.

| Situation | Resolution |
|---|---|
| Same type, same field name across classes | One base field, that name. `[C]` |
| Same type, differing field names | Pick the majority name; subclass bodies referencing the minority name need renaming in the same edit. In a tie, pick the alphabetically first. `[D]` |
| **Differing types under one field name** | Do **not** consolidate this cluster automatically — record it as `skipped` with the conflicting pair and surface it in the report. `[D]` |
| Mixed `@MockkBean` and `@SpykBean` on the same type | Different bean semantics; keep the spy out of the base and drop that class from the cluster. `[D]` |

### C2.3 — Write the base class

Place it under a `support/` package in the test tree. Give it the cluster's class-level annotations, the union of mock fields, and **no test methods**.

```kotlin
/**
 * Shared Spring context for the WebTestClient / REST Docs test classes.
 *
 * The set of `@MockkBean` declarations below is part of the Spring context cache key
 * (springmockk contributes it via `MockkContextCustomizer`). Declaring the union here once
 * means every subclass shares a single application context instead of forcing its own.
 *
 * A subclass MUST NOT declare additional `@MockkBean`/`@SpykBean` fields: one extra mock
 * changes the cache key and costs another full application startup.
 *
 * Mocks a given subclass does not use are harmless - MockK only fails on an unstubbed call
 * that actually happens, and springmockk clears every mock in the context after each test.
 */
@SpringBootTest
@AutoConfigureWebTestClient
@AutoConfigureRestDocs
abstract class AbstractApiDocumentationTest {

    @MockkBean
    protected lateinit var organizationService: OrganizationService
    // ... one field per union member
}
```

Carry that invariant into the class doc verbatim — it is the only thing stopping the next author from re-fragmenting the key. `[C]`

Field visibility must be **`protected`** (Kotlin/Java), not `private`: subclasses stub these fields directly and inherited `private` is invisible. `[C]`

### C2.4 — Rewrite each subclass

Per class in the cluster, in a **single atomic file write** (`patterns.md` → AST editor guidance):

1. Delete the class-level annotations now held by the base.
2. Delete every mock field declaration.
3. Add `: AbstractApiDocumentationTest()` (Kotlin) / `extends AbstractApiDocumentationTest` (Java) to the class header. A Kotlin class with a constructor parameter list keeps it: `class FooTest(@Autowired private val client: WebTestClient) : AbstractApiDocumentationTest()`. `[C]`
4. Remove imports that just went unused — the mock annotation, the `@AutoConfigure*`/`@SpringBootTest` imports, and each mocked service type. Add the base-class import. `[C]`
5. Leave every test body, `@BeforeEach`, `companion object`, and `@Autowired` field untouched. Stubbing calls such as `coEvery { permissionService.validateAuthorization(any(), any()) } just Runs` keep compiling against the inherited field. `[C]`

Record `{ file, base_class, annotations_removed, mocks_removed }` in the ledger immediately after each write.

### C2.5 — Inherited mocks: what is safe and what is not

A subclass now inherits mocks it never touches. **This is safe** when the mock is strict:

- `@MockkBean` defaults to `relaxed=false`, i.e. a **strict** mock. `[S]` Strict MockK throws on any unstubbed method call — it does not silently return a default. `[S]`
- A class that relied on the **real** bean, now forced to inherit a strict mock of it, **fails loudly** on the first call. That failure is the correct signal: drop that class from the cluster. `[D]`
- springmockk clears every mock in the context after each test (`@MockkBean.clear` defaults to `AFTER`), so stubbing does not leak between test methods. `[S]`

**The trap:** if you add `relaxed=true` to any union member, that protection disappears — a class that depended on the real bean now silently gets default returns. `[D]` Never use `relaxed=true` in a shared base class.

**The verification check:** for each test class added to the union, diff its pre-consolidation `@MockkBean` type set against the final union. The difference is exactly the set of beans that class now inherits as mocks. Before running the suite, audit each: if any test in that class asserts on the bean's behaviour, that test will now fail (good — you caught a real issue). **Remediation:** drop that class from the cluster (it needs its own context), split the cluster into two groups, or move the class to a different base class. Do **not** add the bean to the shared union — doing so forces every class in the cluster to inherit that mock, defeating the purpose. `[D]`

---

## Step C3 — Kill per-context background work

Each item below is paid **once per cached context** and is usually blocking. Applying them multiplies through every context that survives Step C2.

| Knob | Set where | Why |
|---|---|---|
| `spring.cloud.bootstrap.enabled=false` | **System property on the test task** — see Trap 1 below | Skips building a separate bootstrap `ApplicationContext` per test context `[C]` |
| `spring.cloud.config.enabled=false` | test `application.yml` | No Config server is reachable from a test run; avoids the fetch and its retries `[C]` |
| `spring.kafka.listener.auto-startup=false` | test `application.yml` | Application `@KafkaListener`s otherwise start consumer threads per context, all reconnect-looping against an absent broker `[C]` |
| `autoStartup = "\${spring.kafka.listener.auto-startup:true}"` | on each `@KafkaListener` in **main source** | Makes the flag above reach listeners declared with explicit attributes; `:true` default keeps production behaviour `[C]` When is the annotation attribute required? Only when the `@KafkaListener` already carries an explicit `autoStartup` attribute that overrides the factory default. If no `@KafkaListener` in the codebase sets `autoStartup` explicitly, the factory property alone is sufficient. Adding the annotation attribute is still recommended — it makes the configurability explicit and prevents a future `autoStartup = "true"` from silently defeating the test switch. |
| Per-listener concurrency in test config | test `application.yml` | Concurrency is a thread multiplier; the reference project reduced it 10 → 1 per listener `[C]` |
| `management.metrics.export.statsd.enabled=false` | test `application.yml` | Avoids a StatsD registry, UDP client, and publisher thread per context `[C]` |
| `initialDelayString` on `@Scheduled` + a long initial delay in test config | annotation in **main source**, value in test `application.yml` | See Trap 2 below `[C]` |

**Escape hatch:** a test that asserts on a disabled component re-enables it locally. In the reference project `KafkaErrorHandlerTest` declares its **own** `@KafkaListener` on the test class, which `spring.kafka.listener.auto-startup=false` does not touch. `[C]` Before flipping any switch, `rg` the test tree for assertions on the component; if one exists, give that class a local override rather than dropping the switch.

---

## Step C4 — Verify and report

Zero behaviour change is the bar. Re-run the full suite and record the post-C2/C3 context count and wall time in the ledger under `spring.post_context_cost`. Every check below must pass; mocked beans fail loudly when a test relied on the real implementation, catching the C2.5 risk here.

| Check | Pass condition | Gate decision |
|---|---|---|
| Suite green | Full suite re-run matches the Phase B baseline test-for-test: same passing ids, same failing ids. Any newly failing id is a regression. | **Gate: MUST PASS** |
| Context count | `missCount` (Step C1 method) is recorded; compare to baseline. | Reported but not gated; context count may not fall if all clusters were skipped. |
| Wall time | Second warm run, same machine as baseline. Reported as before → after. | Reported but not gated; wall time is machine-noisy and hard to reproduce reliably. |
| No new eviction | Final cache `size` ≤ `maxSize`; no context built twice for the same key. | Informational check. |
| Production config untouched | `git diff` on main-source config: every new property has a default preserving current behaviour (`:0`, `:true`). Main-source `application.yml` unchanged. | **Gate: MUST PASS** |
| Disabled components unasserted | For each switch flipped in Step C3, `rg` confirms no test asserts on that component, or that class carries a local override. | **Gate: MUST PASS** |
| Mock union safe | For each mock newly inherited by a class that did not declare it, no test in that class exercised the real bean. | **Gate: MUST PASS** |

- **Healthy** (suite green + production config untouched + disabled components unasserted + mock union safe): set `phase: done`.
- **Regressed** (a new suite failure, or a gate check fails): record which consolidations caused the failures and which classes to drop from the cluster. Set `phase: failed-context`.

Record the post-C4 ledger state so a resume mid-Phase-C has the consolidation history.

---

## Traps

### Trap 1 — `spring.cloud.bootstrap.enabled` cannot live in `application.yml`

`BootstrapApplicationListener` runs **before** `src/test/resources/application.yml` is loaded, so the property is read before the file exists as far as the listener is concerned. Setting it in YAML is silently a no-op. It must be a system property on the test task. `[C]`

```groovy
tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'spring.cloud.bootstrap.enabled', 'false'
}
```

Maven equivalent: a `<systemPropertyVariables>` entry in the Surefire plugin configuration. `[S]`

The same ordering caveat applies to any property consumed by an `ApplicationListener` that runs ahead of config-file loading. `[D]` When a YAML switch appears to do nothing, this is the first thing to check.

### Trap 2 — `fixedDelayString` alone always fires once immediately

A `@Scheduled(fixedDelayString = ...)` method runs **once at startup** regardless of how large the delay is. In the reference project that meant every context paid a blocking 2s Kafka `describeCluster` timeout plus DynamoDB `describeTable` retries — per context. `[C]`

The fix is production-safe: add an `initialDelayString` bound to a property that **defaults to 0**, then set a long value in test config only.

```kotlin
@Scheduled(
    fixedDelayString = "\${organization.healthcheck.kafka.interval}",
    initialDelayString = "\${organization.healthcheck.kafka.initial-delay:0}"
)
```

```yaml
# src/test/resources/application.yml
organization:
  healthcheck:
    kafka:
      interval: 60m
      initial-delay: 1d   # never fires during a run
```

Production keeps the old behaviour exactly — `:0` means fire immediately. `[C]` Prefer this shape over disabling scheduling wholesale: `initialDelayString` leaves the bean, its wiring, and any test that calls `check()` directly intact.

### Trap 3 — `@DirtiesContext` classMode is a wall-time multiplier

`AFTER_EACH_TEST_METHOD` rebuilds the context — and anything embedded in it, such as an `@EmbeddedKafka` broker — **per test method**. `AFTER_CLASS` rebuilds once. In the reference project this was the difference between four ~15s startups and one. `[C]`

The reason a class needs `AFTER_EACH_TEST_METHOD` is usually **shared mutable state between methods**, not the context itself. Remove the sharing and the weaker classMode becomes correct. The reference commit gave each test method its own Kafka topic (offset assertions expected a committed offset of exactly 1, which only held if no earlier method had published to that topic), then relaxed to `AFTER_CLASS`. `[C]`

Never blanket-add `@DirtiesContext` to fix a flaky test — it converts one flake into a per-class full startup and evicts a context other classes were sharing. Find the leaked state.

### Trap 4 — cross-context mock and system-property leakage

Once contexts are shared, teardown that used to be local becomes global:

| Leak | Fix |
|---|---|
| `clearAllMocks()` in `@AfterEach` resets **every** `@MockkBean` in **every** cached context in the JVM, not just this class's | Clear by name: `clearMocks(mockLogger)` `[C]` |
| `EmbeddedKafkaBroker.destroy()` leaves `spring.kafka.bootstrap-servers` and `EmbeddedKafkaBroker.SPRING_EMBEDDED_KAFKA_BROKERS` set, so every context built later in the JVM binds to a dead broker port — a system property outranks `application.yml` | `System.clearProperty(...)` for both in `@AfterAll` `[C]` |
| A `@KafkaListener` declared on the **test class** is re-registered per test instance, because Spring re-runs bean post-processors for each instance | `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` `[C]` |
| `ContainerTestUtils.waitForAssignment` blocks ~60s then throws for a container that will never be assigned — including the application's own listeners, now stopped by `auto-startup=false` | Filter to `it.isRunning` before waiting `[C]` |

### Trap 5 — real sleeps in mocked config

A mock returning a production delay value makes the test wait for real when the code under test uses `runBlocking`/`Thread.sleep` rather than a virtual-time test dispatcher. The reference project returned `5000` ms from a mocked config property and paid 5s per affected test; nothing asserted the duration, so it dropped to `1` ms — non-zero, so the delay path is still exercised. `[C]`

`rg` mocked config getters for values in the hundreds-of-ms-and-up range and check whether any assertion depends on the magnitude.
