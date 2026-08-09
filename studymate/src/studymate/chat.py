from __future__ import annotations

from collections.abc import Callable

from .agent import AgentRunError, AgentRunner
from .citations import validate_citations
from .input import classify_input, parse_command
from .llm import LLMRequestError
from .models import Answer, ChatResponse, SearchResult
from .trace import AgentTrace, TraceStore


class ChatService:
    def __init__(
        self,
        *,
        search_index,
        llm,
        agent: AgentRunner | None = None,
        top_k: int = 5,
        max_history: int = 10,
        update_handler: Callable[[list[str]], str] | None = None,
        trace_store: TraceStore | None = None,
    ):
        self.search_index = search_index
        self.llm = llm
        self.agent = agent
        self.top_k = top_k
        self.max_history = max_history
        self.history: list[dict[str, str]] = []
        self.last_retrieved: list[SearchResult] = []
        self.update_handler = update_handler
        self.trace_store = trace_store
        self.last_trace: AgentTrace | None = None
        self.last_trace_path = None
        self.last_trace_write_error: str | None = None

    def handle(self, text: str) -> ChatResponse:
        stripped = text.strip()
        if stripped.startswith("/"):
            return self._handle_command(stripped)

        if self.agent is not None:
            return self._handle_agent(stripped)

        intent = classify_input(stripped)
        evidence = self.search_index.search(stripped, top_k=self.top_k)
        self.last_retrieved = evidence

        if not evidence:
            answer = Answer(
                answer="当前知识库中没有找到足够依据，请补充资料或换一个问题。",
                citations=[],
                confidence=0.0,
                need_more_context=True,
                next_steps=["补充相关 Markdown 资料"],
            )
        else:
            try:
                answer = self.llm.answer(
                    user_input=f"[{intent.kind.value}] {stripped}",
                    evidence=evidence,
                    history=list(self.history),
                )
            except LLMRequestError as exc:
                answer = Answer(
                    answer=f"AI 模型调用失败：{exc}",
                    citations=[],
                    confidence=0.0,
                    need_more_context=False,
                    next_steps=["检查 API Key、账户余额和网络配置", "稍后重试"],
                )
            validation = validate_citations(answer, evidence)
            if not validation.is_valid:
                answer = Answer(
                    answer=(
                        "模型返回了无法验证的引用，因此本次回答被拦截。"
                        "请重试或补充更明确的问题。"
                    ),
                    citations=[],
                    confidence=0.0,
                    need_more_context=True,
                    next_steps=["检查知识库来源", "重新提问"],
                )

        self.history.extend(
            [
                {"role": "user", "content": stripped},
                {"role": "assistant", "content": answer.answer},
            ]
        )
        self.history = self.history[-self.max_history :]
        return ChatResponse(
            answer=answer,
            history=list(self.history),
            retrieved=evidence,
        )

    def _handle_agent(self, stripped: str) -> ChatResponse:
        intent = classify_input(stripped)
        try:
            result = self.agent.run(
                user_input=f"[{intent.kind.value}] {stripped}",
                history=list(self.history),
            )
            answer = result.answer
            evidence = result.retrieved
            trace = result.trace
        except (AgentRunError, LLMRequestError) as exc:
            answer = Answer(
                answer=f"AI Agent 调用失败：{exc}",
                citations=[],
                confidence=0.0,
                need_more_context=False,
                next_steps=["检查模型是否支持原生 Tool Calling", "稍后重试"],
            )
            evidence = []
            trace = AgentTrace()
            trace.finish("agent_error", error=str(exc))

        self.last_retrieved = evidence
        self.last_trace = trace
        self.history.extend(
            [
                {"role": "user", "content": stripped},
                {"role": "assistant", "content": answer.answer},
            ]
        )
        self.history = self.history[-self.max_history :]
        self._persist_agent_turn(stripped, answer, trace)
        return ChatResponse(
            answer=answer,
            history=list(self.history),
            retrieved=evidence,
        )

    def _handle_command(self, text: str) -> ChatResponse:
        command = parse_command(text)
        if not command.is_valid:
            return ChatResponse(command=command, history=list(self.history))

        if command.name == "reset":
            self.history.clear()
            self.last_retrieved = []
            self.last_trace = None
            self.last_trace_path = None
            self.last_trace_write_error = None
            return ChatResponse(command=command, history=[])

        if command.name == "sources":
            answer = Answer(
                answer=self._format_sources(),
                citations=[],
                confidence=1.0,
                need_more_context=not bool(self.last_retrieved),
                next_steps=[],
            )
            return ChatResponse(
                answer=answer,
                command=command,
                history=list(self.history),
                retrieved=list(self.last_retrieved),
            )

        if command.name == "help":
            answer = Answer(
                answer=(
                    "/sources 查看来源，/trace 查看上一轮 Agent 执行轨迹，"
                    "/reset 重置会话，/update 更新文档，/quit 退出。"
                ),
                citations=[],
                confidence=1.0,
                need_more_context=False,
                next_steps=[],
            )
            return ChatResponse(answer=answer, command=command, history=list(self.history))

        if command.name == "trace":
            answer = Answer(
                answer=self._format_trace(),
                citations=[],
                confidence=1.0,
                need_more_context=self.last_trace is None,
                next_steps=[],
            )
            return ChatResponse(answer=answer, command=command, history=list(self.history))

        if command.name == "update":
            if self.update_handler is None:
                message = "当前会话没有配置文档更新器。请使用 `studymate update-docs`。"
            else:
                try:
                    message = self.update_handler(command.args)
                except Exception as exc:
                    message = f"文档更新失败：{exc}"
            answer = Answer(
                answer=message,
                citations=[],
                confidence=1.0 if "失败" not in message else 0.0,
                need_more_context=False,
                next_steps=[],
            )
            return ChatResponse(answer=answer, command=command, history=list(self.history))

        return ChatResponse(command=command, history=list(self.history))

    def _format_sources(self) -> str:
        if not self.last_retrieved:
            return "当前没有可展示的检索来源。"
        lines = ["上一次检索来源："]
        for result in self.last_retrieved:
            chunk = result.chunk
            lines.append(
                f"- {chunk.path}:{chunk.start_line}-{chunk.end_line} "
                f"(score={result.score:.3f})"
            )
        return "\n".join(lines)

    def _persist_agent_turn(
        self,
        user_input: str,
        answer: Answer,
        trace: AgentTrace,
    ) -> None:
        self.last_trace_path = None
        self.last_trace_write_error = None
        if self.trace_store is None:
            return
        try:
            self.last_trace_path = self.trace_store.append_turn(
                user_input=user_input,
                answer=answer.model_dump(mode="json"),
                trace=trace,
            )
        except OSError as exc:
            self.last_trace_write_error = str(exc)

    def _format_trace(self) -> str:
        if self.last_trace is None:
            return "当前会话还没有可展示的 Agent Trace。"
        lines = [self.last_trace.format_summary()]
        if self.last_trace_path is not None:
            lines.append(f"已落盘：{self.last_trace_path}")
        if self.last_trace_write_error:
            lines.append(f"Trace 落盘失败：{self.last_trace_write_error}")
        return "\n".join(lines)
