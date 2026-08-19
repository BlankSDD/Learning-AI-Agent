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

The follow-up analysis found an additional runtime issue: the old implementation treated the repeated search request as a reason to disable every remaining tool. That could prevent `open_document` from running even though it had not used its budget. The runtime contract is now narrower: reject only the repeated call, preserve other available tools, and enter finalization only after all tool budgets are exhausted.

## Today's knowledge summary

1. An evaluation set is a collection of representative user questions plus expected behavior. It is not a list of every possible user question, and a question outside the set does not make the Agent stop in production.
2. Evaluation is an offline quality check after an Agent run. The Agent itself stops because of its own runtime rules such as `empty_search`, a final answer, a tool budget, or `max_steps`.
3. `case_delay_seconds` reduces request burst pressure between cases. It does not fix an individual request that is already stuck, so a request-level timeout is also required.
4. Retry should be limited to transient failures such as connection errors, timeouts, HTTP 429, and temporary 5xx responses. Authentication, permission, balance, parameter, and parsing failures need diagnosis instead of blind retries.
5. A failed evaluation must be classified using `checks`, `trace`, `attempts`, and the retrieved sources. In `q019`, the failure was caused by Agent planning/tool-budget behavior, not by SQLite FTS5/BM25 or Embedding.

## Query rewrite

The next issue was not answer rewriting. The model had placed planning text into the `search_knowledge` argument, for example:

```text
请先搜索 Agent Loop 的资料，再打开命中的文档，结合原文解释它如何运行。
```

The local indexes should rank the topic, not the planning instructions. `rewrite_query()` now performs a no-cost lexical rewrite before InMemory BM25-style or SQLite FTS5/BM25 search:

```text
original query   -> 请先搜索 Agent Loop 的资料，再打开命中的文档，结合原文解释它如何运行
rewritten query  -> agent loop
```

It removes search-action phrases, generic explanation words, English question stopwords, and punctuation while preserving domain terms. It does not rewrite the final answer, does not use conversation history, and does not call an LLM. The tool payload and Trace retain both values so a ranking problem can be diagnosed as either a rewrite problem or an index problem.

The first local SQLite verification returned `claude-code/07-agent-sdk/agent-loop.md` as every top-five result for this query, with `agent loop` as the rewritten query. This is a retrieval-side verification only; a full Agent evaluation still needs the model gateway.

## DeepSeek-V4-Flash revalidation

The temporary configuration from `rivo-DS-V4-Flash.json` was loaded into process-only environment variables. The project `.env` was not changed, and the API key was not printed or written to a report.

| Case | Result | Details |
| --- | --- | --- |
| `q001` | PASS, `1/1` | Tool Calling and final JSON parsing worked; retrieval Hit@5 was 100%, but the model opened two extra documents, so Precision@5 was 25% and citation accuracy was 50%. |
| `q019` | PASS, `1/1` | `search_knowledge -> open_document -> final_answer`, 3 steps, 2 tool calls; citation accuracy and coverage were both 100%. |

The model gateway is therefore usable with the current OpenAI-compatible adapter when using streaming and `STUDYMATE_RESPONSE_FORMAT=none`. The earlier failure was a gateway/channel availability issue, not a StudyMate Tool Calling incompatibility.

## Follow-up optimization

The first `q001` result showed that a simple definition question caused two extra document reads. The Agent now applies a small, explicit runtime policy: after a successful search for a definition-style question, it enters finalization and does not expose `open_document`. Detail, process, difference, and source-explanation questions still keep document reading available. Batch calls are also counted one by one, so a model response cannot bypass the per-tool budget by returning two calls together.

The first version of that policy exposed a retrieval defect: the short query `MCP` ranked later configuration sections over the protocol definition, so the model correctly abstained. The local query aliases now expand `MCP` to `MCP + Model Context Protocol`. With SQLite FTS5/BM25, the top result became the glossary definition at `claude-code/99-other/glossary.md`. The live DeepSeek-V4-Flash run then completed `search_knowledge -> final_answer` in two steps, gave the correct definition, and cited that glossary chunk. Its only failed checks were based on q001's stale `mcp-quickstart.md` expectation, so q001 now expects the glossary source instead.

The first live retry after this change failed before Agent execution because Rivo returned `get_channel_failed`. The new retry classifier reads both exception text and structured `body/code` fields, so `--retries 1` made exactly two attempts and then stopped. This error is treated as temporary channel unavailability; HTTP 401/403/402 remain non-retryable.

## Equivalent evidence sources

The later DeepSeek-V4-Flash retry succeeded after one temporary channel failure. It followed the expected definition-question path, `search_knowledge -> final_answer`, gave a grounded MCP explanation, and cited `ai-agent/tool-calling-vs-mcp.md`. The old q001 label required only `claude-code/99-other/glossary.md`, so the evaluation reported a failure despite the answer and cited material being correct.

This is an evaluation-labeling problem, not a retrieval or Agent failure. A concise concept can be correctly defined by several documents. The dataset now has two distinct source contracts:

- `expected_sources`: every listed source is required. Use this when a task genuinely needs several specific documents.
- `acceptable_sources`: any one listed source is enough. Use this for interchangeable evidence, such as an MCP definition in a glossary, quickstart, or conceptual comparison note.

The candidate list is one expected slot for Recall@K and citation coverage. For Precision@K and citation accuracy, each candidate path is relevant. This preserves strict checks where they are meaningful without making the dataset brittle to a valid choice among equivalent sources.

## Verification

- `pytest`: 84 passed.
- The one-case live run for `q001` completed successfully before the optimization; the post-optimization run was blocked by two consecutive Rivo `get_channel_failed` responses.
- The two-case live run for `q019` and `q020` completed in about 39 seconds with a 3-second case delay.
- No Embedding API was called.

## Tomorrow plan: 2026-08-20

### Study

1. Compare original and rewritten queries in `/trace`, then review whether the rewritten query improves Hit@K and MRR without widening unknown-topic matches.
2. Distinguish tool budget enforcement, invalid tool calls, tool execution errors, and model planning errors.
3. Review fixed backoff, retryable status codes, request timeout, and why 401/403/402 should not be retried.
4. Decide when an evaluation should require an exact tool sequence and when it should only require successful evidence retrieval, citation, and a correct final answer.

### Development

1. Keep the current Agent safety rule that blocks repeated `search_knowledge` calls, then add or verify a focused regression test for that behavior.
2. Add retrieval regression cases for query rewrite, including Chinese, English, CamelCase, and unknown identifiers.
3. Review whether `q019` is testing a strict workflow contract or a successful-answer contract; change the evaluation expectation only after this decision.
4. Run `q001`, `q019`, and `q020` again with one changed variable at a time. Keep the SQLite backend and Embedding disabled.

### Completion criteria

- Explain the exact cause of the `q019` failure from its Trace.
- Keep transient retries bounded and make sure permission or balance errors still fail fast.
- Run the full pytest suite and record the result in the next learning log.

## Local comparison-search verification

The follow-up local run used 220 knowledge documents and four queries:

| Query type | Memory result | SQLite result | Observation |
| --- | --- | --- | --- |
| Chinese comparison: `agentloop` vs `agent runtime` | Both topics reached Top-K | Both topics reached Top-K | Results were interleaved by topic. |
| English comparison: `tool calling` vs `MCP` | Both topics reached Top-K | Both topics reached Top-K | The two concepts were not allowed to be crowded out by one side. |
| Chinese definition: `MCP 是什么？` | `ai-agent/tool-calling-vs-mcp.md` at Top-1 | `claude-code/99-other/glossary.md` at Top-1 | Backend ranking differs because the indexes use different lexical scoring and document distributions. |
| English definition: `What is the agent loop?` | `claude-code/07-agent-sdk/agent-loop.md` at Top-1 | Same source family at Top-1 | Query rewrite kept the core phrase `agent loop`. |

The comparison command now prints and records `rewritten_query` and `comparison_topics`. For comparison queries, the displayed scores should not be read as a global descending list because topic-level result lists are interleaved. Compare coverage and within-backend rank instead. The full local test suite finished with `93 passed`; no Embedding or online model request was made.
