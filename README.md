# Market Pulse — Reddit Data API Review

This repository is a **public review package** for the Reddit Data API access request for Market Pulse.

Market Pulse is currently a **personal, non-commercial local software project**. It is not publicly deployed and has no external users. Development and automated tests currently use synthetic fixture data. Live Reddit access remains disabled until Reddit Data API access and the intended use are approved.

## What Market Pulse does

A user enters a research topic. Market Pulse:

1. performs a **read-only** search of public Reddit posts related to that topic;
2. limits retrieval to the recent monthly search window exposed by the API;
3. normalizes the returned posts locally;
4. identifies recurring phrases/themes using a **deterministic local algorithm**;
5. shows the themes together with the Reddit posts that support them.

The product is designed around evidence traceability: a derived theme is shown only when enough distinct source posts support it.

## What Market Pulse does not do

Market Pulse does **not**:

- create posts or comments;
- send messages;
- vote;
- moderate communities;
- automate Reddit accounts;
- train an AI or machine-learning model on Reddit data;
- send Reddit content to an external AI/LLM provider in the current implementation.

## API behavior

The current Reddit adapter is implemented in Python using PRAW/prawcore.

It is intentionally bounded:

- one manually initiated analysis at a time;
- read-only search against public posts;
- per-operation time limits;
- bounded total calls per analysis;
- rate-limit headers are observed;
- HTTP 429 stops retrieval;
- retries and waits are bounded by the analysis deadline;
- credentials and authorization values are scrubbed from recorded errors.

The source files in this repository are a review snapshot of the API-facing portion of the private Market Pulse codebase. They are provided so Reddit can inspect the intended API interaction. This review repository is **not intended to be a standalone runnable distribution**.

## Data flow

See [docs/data-flow.md](docs/data-flow.md).

## Retention / removal handling

See [docs/retention-policy.md](docs/retention-policy.md).

The 48-hour maximum retention window described there is a **proposed conservative policy pending Reddit clarification**, not a claim that Reddit has approved that exact period.

## Files relevant to API review

- `src/market_pulse/retrieval/reddit/adapter.py` — Reddit Data API access and rate/time bounding.
- `src/market_pulse/retrieval/reddit/normalize.py` — normalization of Reddit post results.
- `src/market_pulse/retrieval/port.py` — source boundary and normalized retrieval contract.
- `.env.example` — configuration names only; **no credentials or secrets are included**.
- `docs/data-flow.md` — how Reddit data moves through Market Pulse.
- `docs/retention-policy.md` — proposed short-lived handling of source-derived text.

## Current status

- Local MVP: working with synthetic fixture data.
- Reddit integration code: implemented but live use is gated.
- Intended use: personal/non-commercial development and validation.
- Live Reddit Data API usage: **not enabled until approval**.
