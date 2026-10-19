# Good and Bad Tests

Examples use TypeScript; the rules are language-neutral. This repo's idioms are in `docs/agents/testing.md`.

## Good Tests

**Integration-style**: Test through real interfaces, not mocks of internal parts.

```typescript
// GOOD: Tests observable behavior
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

Characteristics:

- Tests behavior users/callers care about
- Uses public API only
- Survives internal refactors
- Describes WHAT, not HOW
- One logical assertion per test; in a parametrized test, per case, with no branching on the parameter

## Bad Tests

**Implementation-detail tests**: Coupled to internal structure.

```typescript
// BAD: Tests implementation details
test("checkout calls paymentService.process", async () => {
  const mockPayment = jest.mock(paymentService);
  await checkout(cart, payment);
  expect(mockPayment.process).toHaveBeenCalledWith(cart.total);
});
```

Red flags:

- Mocking internal collaborators
- Testing private methods
- Asserting call counts or order on queries or on the project's own collaborators. Call assertions apply to commands only
- Test breaks when refactoring without behavior change
- Test name describes HOW not WHAT
- Verifying through external means instead of interface

```typescript
// BAD: Bypasses interface to verify
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// GOOD: Verifies through interface
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

**Tautological tests**: Expected value restates the implementation, so the test passes by construction.

```typescript
// BAD: Expected value is recomputed the way the code computes it
test("calculateTotal sums line items", () => {
  const items = [{ price: 10 }, { price: 5 }];
  const expected = items.reduce((sum, i) => sum + i.price, 0);
  expect(calculateTotal(items)).toBe(expected);
});

// GOOD: Expected value is an independent, known literal
test("calculateTotal sums line items", () => {
  expect(calculateTotal([{ price: 10 }, { price: 5 }])).toBe(15);
});
```

**Grow or sibling**: A new case joins an existing `test.each` table only when it differs in data alone. Give every row a named id.

```typescript
// GOOD: Same seam, setup and assertion shape; only input and expected value differ
test.each([
  { id: "dot-decimal", input: "1.5", expected: 1.5 },
  { id: "comma-decimal", input: "1,5", expected: 1.5 },
])("parsePrice [$id]", ({ input, expected }) => {
  expect(parsePrice(input)).toBe(expected);
});

// GOOD: A different assertion shape gets a sibling test
test("parsePrice rejects empty input", () => {
  expect(() => parsePrice("")).toThrow(EmptyInput);
});

// BAD: Branching on the parameter hides two tests in one
test.each([
  { id: "comma-decimal", input: "1,5", expected: 1.5 },
  { id: "empty", input: "", expected: EmptyInput },
])("parsePrice [$id]", ({ input, expected }) => {
  if (expected === EmptyInput) expect(() => parsePrice(input)).toThrow(EmptyInput);
  else expect(parsePrice(input)).toBe(expected);
});
```

**Same lines, different assertion**: Each property the code enforces gets its own row, even when the row covers no new lines.

```typescript
// GOOD: Anchor, case and length rows run the same lines as the happy case, and each pins a different property
test.each([
  { id: "valid", input: "AAPL", expected: true },
  { id: "trailing-newline", input: "AAPL\n", expected: false },
  { id: "lowercase", input: "aapl", expected: false },
  { id: "too-long", input: "TOOLONGX", expected: false },
])("isValidSymbol [$id]", ({ input, expected }) => {
  expect(isValidSymbol(input)).toBe(expected);
});
```

The `trailing-newline`, `lowercase` and `too-long` rows add no coverage. They must not be cut as redundant: removing one lets a regex-anchor, case or length regression pass.
