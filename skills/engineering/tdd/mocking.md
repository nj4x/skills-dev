# When to Mock

Examples use TypeScript; the rules are language-neutral. This repo's idioms are in `docs/agents/testing.md`.

Double ports and system boundaries. Never double the project's own logic.

Double:

- System boundaries: network, database, filesystem, clock, randomness, subprocess
- The project's own ports: adapters that wrap a boundary and are passed in as dependencies (a `PaymentClient` around Stripe, a `RoundScorer` passed into `decideRound`)

Run for real:

- Own pure logic: parsers, calculators, domain rules
- Internal collaborators
- Anything you control that does not cross a boundary

## Placing a Double

**1. Inject first**

Take the dependency as a parameter, constructor argument or deps object:

```typescript
// Easy to double
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// Hard to double
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

**2. Patch only when the code has no injection point**

A patch is a checked patch: the double is type-checked against the real signature. Use the repo's checked-patch helper where it exists (`docs/agents/testing.md`, "Stub helper" heading).

```typescript
// GOOD: Typed against the real module, so a signature change fails the test
vi.spyOn(clock, "now").mockReturnValue(1_700_000_000_000);

// BAD: Untyped replacement drifts from the real signature
(clock as any).now = () => "noon";
```

**3. Prefer SDK-style interfaces over generic fetchers**

Create specific functions for each external operation instead of one generic function with conditional logic:

```typescript
// GOOD: Each function is independently doubled
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: Doubling requires conditional logic inside the double
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```

The SDK approach means:
- Each double returns one specific shape
- No conditional logic in test setup
- Easier to see which endpoints a test exercises
- Type safety per endpoint

## Asserting on a Double

Assert the return value or state first. Assert calls only on commands.

- **Command**: a call that crosses a boundary or port and is the observable outcome (email sent, row saved). Assert its arguments. Assert its count only when a duplicate would be a bug.
- **Query**: a call whose result the test already asserts. Assert nothing on the call.
- **Order**: never assert call order on the project's own collaborators.

```typescript
// GOOD: The command is the outcome
test("checkout sends a receipt", async () => {
  const cart = createCart();
  const paymentClient = { charge: vi.fn().mockResolvedValue({ status: "paid" }) };
  const email = { send: vi.fn() };
  await checkout(cart, paymentClient, email);
  expect(email.send).toHaveBeenCalledWith(cart.owner, "receipt");
});

// BAD: The query result is already asserted through the return value
test("price uses the rate", () => {
  const rates = { get: vi.fn().mockReturnValue(2) };
  expect(priceInEur(10, rates)).toBe(20);
  expect(rates.get).toHaveBeenCalledWith("EUR");
});
```
