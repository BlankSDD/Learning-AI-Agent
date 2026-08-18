# 2026-08-19: Evaluation pacing, case selection, and retry behavior

## User question

The full evaluation set made many model requests in a row. The goal was to run one case at a time, or a small high-value subset, with a few seconds between cases so that the model gateway is less likely to rate-limit or block the requests.

## What changed

`EvaluationRunner` now supports:

- `case_delay_seconds`: wait between cases, never before the first case.
- `retries`: retry only transient transport, timeout, HTTP 429, and HTTP 500/502/503/504 failures.
- `retry_delay_seconds`: wait before a transient retry.
- `attempts`: persist the actual number of attempts in each case result.

The CLI supports:

```powershell
py -m studymate eval `
  --case-id q001 `
  --case-id q019 `
  --case-id q020 `
  --delay-seconds 3 `
  --retries 1 `
  --retry-delay-seconds 5
```

`--limit 3` can be used instead of explicit case ids. Unknown ids fail before any model request is sent. Permission errors (401/403), insufficient balance (402), malformed parameters, and response parsing errors are intentionally not retried.

## Request timeout

The Python OpenAI SDK can wait for a long time when a gateway connection is stuck. `STUDYMATE_TIMEOUT_SECONDS` now bounds one model request and defaults to `60`. During diagnosis, setting it to `20` prevents one blocked request from holding the whole evaluation for many minutes.

## High-value run

The following low-frequency runs were performed against SQLite FTS5/BM25:

| Case | Purpose | Result |
| --- | --- | --- |
| `q001` | Normal MCP retrieval, citation, and multi-step Agent execution | PASS, `1/1`, 3 steps, 1 attempt |
| `q019` | Expected `search_knowledge -> open_document` behavior | FAIL, model called `search_knowledge` twice; the second call was blocked by the per-run tool budget |
| `q020` | Unknown English topic and abstention | PASS, `empty_search`, 1 step, 1 attempt |

The `q019` failure is not evidence that SQLite retrieval is broken. The trace shows the first search returned the Claude Code index document, then the model asked for another search instead of opening a returned document. This is an Agent behavior or evaluation expectation issue and should be analyzed separately from network failures.

## Today's knowledge summary

1. An evaluation set is a collection of representative user questions plus expected behavior. It is not a list of every possible user question, and a question outside the set does not make the Agent stop in production.
2. Evaluation is an offline quality check after an Agent run. The Agent itself stops because of its own runtime rules such as `empty_search`, a final answer, a tool budget, or `max_steps`.
3. `case_delay_seconds` reduces request burst pressure between cases. It does not fix an individual request that is already stuck, so a request-level timeout is also required.
4. Retry should be limited to transient failures such as connection errors, timeouts, HTTP 429, and temporary 5xx responses. Authentication, permission, balance, parameter, and parsing failures need diagnosis instead of blind retries.
5. A failed evaluation must be classified using `checks`, `trace`, `attempts`, and the retrieved sources. In `q019`, the failure was caused by Agent planning/tool-budget behavior, not by SQLite FTS5/BM25 or Embedding.

## Verification

- `pytest`: 76 passed.
- The one-case live run for `q001` completed successfully in about 24 seconds.
- The two-case live run for `q019` and `q020` completed in about 39 seconds with a 3-second case delay.
- No Embedding API was called.

## Tomorrow plan: 2026-08-20

### Study

1. Read the `q019` trace and review why the model chose a second search after the first search returned evidence.
2. Distinguish tool budget enforcement, invalid tool calls, tool execution errors, and model planning errors.
3. Review fixed backoff, retryable status codes, request timeout, and why 401/403/402 should not be retried.
4. Decide when an evaluation should require an exact tool sequence and when it should only require successful evidence retrieval, citation, and a correct final answer.

### Development

1. Keep the current Agent safety rule that blocks repeated `search_knowledge` calls, then add or verify a focused regression test for that behavior.
2. Review whether `q019` is testing a strict workflow contract or a successful-answer contract; change the evaluation expectation only after this decision.
3. Run `q001`, `q019`, and `q020` again with one changed variable at a time. Keep the SQLite backend and Embedding disabled.

### Completion criteria

- Explain the exact cause of the `q019` failure from its Trace.
- Keep transient retries bounded and make sure permission or balance errors still fail fast.
- Run the full pytest suite and record the result in the next learning log.
