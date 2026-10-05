# Reddit data flow

Market Pulse is a local, read-only application.

```text
User topic
  -> local Market Pulse web app
  -> RedditAdapter
  -> Reddit Data API search
  -> public post results
  -> local normalization and deduplication
  -> deterministic recurring-phrase analysis
  -> themes with supporting evidence
  -> local UI
```

The current integration does not post, comment, vote, message users, moderate communities, automate accounts, train an AI/ML model, or send Reddit content to an external LLM provider.

Retrieval is bounded by per-operation time limits, a maximum number of calls per analysis, and observed rate-limit behavior. If retrieval is incomplete, Market Pulse reports a partial or failed result instead of presenting incomplete data as complete.
