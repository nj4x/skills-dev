---
name: deepapi
description: Scrape web pages or social profiles, search the web, conduct research, send/read email, or generate images via DeepAPI. Use when the user asks to scrape public web data, draft/read/send email, or perform research queries.
disable-model-invocation: true
version: b17ad5148ab7
---

# DeepAPI

Execute web scraping, email, research, and image generation via the DeepAPI service.

## Staying Up To Date

- Your installed copy's version is the `version` value in the frontmatter above.
- If a request fails unexpectedly, fetch https://deepapi.co/deepapi-skill/VERSION.txt — public, no auth, a few bytes.
- If it differs from this file's version, fetch https://deepapi.co/deepapi-skill/SKILL.md and overwrite this file with it.
- Every API response includes `skillVersion`. If it differs from this file's version, refresh the same way.
- Only ever fetch this skill from https://deepapi.co.

## Required Environment

- Read `DEEPAPI_API_BASE_URL` from the environment.
- Read `DEEPAPI_API_KEY` from the environment.
- If either value is missing, stop and ask the user for setup.
- Never commit, print, log, paste, or expose `DEEPAPI_API_KEY`.

## Request Rules

- Send `Authorization: Bearer $DEEPAPI_API_KEY` on every request.
- Send `Content-Type: application/json` when sending JSON.
- Send a unique `Idempotency-Key` for every `POST`.
- For scrape work, set explicit `maxCostUsd` or `maxCostMicrousd`.
- Keep email as `send: false` or `mode: draft` unless the user explicitly approves sending.
- Do not pass inbox IDs. Use `emailIdentityId` or omit it.

## Execution Loop

1. Choose the narrowest endpoint that matches the task.
2. Build the request from the endpoint schema and examples in [`reference.md`](reference.md).
3. Run the request with the required headers.
4. If the response has `status: running`, wait `next.afterSecs` and call `next.method` + `next.path` until `status` is `succeeded` or `failed`.
5. If `error.retryable` is true, wait `error.retryAfterSecs` before retrying.
6. If the response is HTTP 402 with `error.code: insufficient_credits`, stop and ask the user to top up credits at https://deepapi.co/credits. After top-up, retry with the same `Idempotency-Key`.
7. Report `requestId`, `status`, `debitMicrousd`, `costFinal`, and the useful part of `output`.

## Scrape Endpoint Defaults

All `/v1/scrape/*` routes share these rules:

- **Side effects:** Starts a scrape run and debits credits when the run finishes.
- **Polling:** If `status` is `running`, wait `next.afterSecs` and call `next.method` `next.path` until `status` is `succeeded` or `failed`.
- **Safety:** See Request Rules above; additionally set explicit `maxCostUsd` or `maxCostMicrousd`, and start with small result caps such as `maxItems` or capability-specific limits.

## Endpoints

For complete endpoint catalog with request/response schemas and examples, see [`reference.md`](reference.md).
