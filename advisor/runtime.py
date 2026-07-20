"""Runtime: turn a request into a grounded answer, with timeout, retry, route
tracking, and the multi-agent -> single-agent fallback.

The FastAPI layer stays thin; all the orchestration lives here so it is unit-testable
without a web server.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from advisor import errors
from advisor.agents import build_orchestrator, build_single_agent
from advisor.config import settings
from advisor.schemas import AdvisorRequest, AdvisorResponse, RouteInfo

log = logging.getLogger(__name__)


class AdvisorRuntime:
    """Owns the agents, sessions, and one runner per path. Built once at startup."""

    def __init__(self) -> None:
        self._session_service = InMemorySessionService()
        self._multi = build_orchestrator() if settings.enable_multi_agent else None
        self._single = build_single_agent()

        self._multi_runner = (
            Runner(
                agent=self._multi,
                app_name=settings.app_name,
                session_service=self._session_service,
            )
            if self._multi is not None
            else None
        )
        self._single_runner = Runner(
            agent=self._single,
            app_name=settings.app_name,
            session_service=self._session_service,
        )

    # -- prompt ------------------------------------------------------------
    @staticmethod
    def _prompt(req: AdvisorRequest) -> str:
        return (
            f"{req.grounding_block()}\n\n"
            f"STUDENT QUESTION: {req.query_context}\n\n"
            "Answer the student's question, grounded strictly in the verified data above "
            "(and any tool results). Apply the exposure-is-not-job-loss framing."
        )

    # -- one run over a runner --------------------------------------------
    async def _run_once(self, runner: Runner, prompt: str) -> tuple[str, RouteInfo]:
        user_id = "student"
        session_id = f"s-{uuid.uuid4().hex[:16]}"
        await self._session_service.create_session(
            app_name=settings.app_name, user_id=user_id, session_id=session_id
        )
        content = types.Content(role="user", parts=[types.Part(text=prompt)])

        called: list[str] = []
        used_search = False
        reply = ""
        async for event in runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            for part in (event.content.parts if event.content else []) or []:
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    called.append(fc.name)
                    if fc.name in {"news_agent", "google_search"}:
                        used_search = True
            # grounding metadata is another signal that search actually ran
            gm = getattr(event, "grounding_metadata", None)
            if gm is not None and getattr(gm, "web_search_queries", None):
                used_search = True
            if event.is_final_response() and event.content and event.content.parts:
                text = event.content.parts[0].text
                if text:
                    reply = text

        if not reply.strip():
            raise errors.EmptyResponse()
        route = RouteInfo(agents_called=called, used_search=used_search)
        return reply.strip(), route

    # -- retry wrapper -----------------------------------------------------
    async def _run_with_retry(
        self, runner: Runner, prompt: str, path: str
    ) -> tuple[str, RouteInfo]:
        last: Exception | None = None
        for attempt in range(settings.max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._run_once(runner, prompt), timeout=settings.request_timeout_s
                )
            except asyncio.TimeoutError as exc:
                last = errors.UpstreamTimeout()
                log.warning("%s path timed out (attempt %d)", path, attempt + 1)
            except Exception as exc:  # noqa: BLE001 - classified below
                last = exc
                classified = errors.classify(exc)
                log.warning(
                    "%s path failed (attempt %d): %s", path, attempt + 1, classified.error_code
                )
                if not classified.retryable:
                    raise classified from exc
            if attempt < settings.max_retries:
                await asyncio.sleep(settings.retry_base_delay_s * (2**attempt))
        raise errors.classify(last) if last else errors.AdvisorError()

    # -- public entrypoint -------------------------------------------------
    async def advise(self, req: AdvisorRequest) -> AdvisorResponse:
        prompt = self._prompt(req)
        started = time.perf_counter()

        # Primary: multi-agent.
        if self._multi_runner is not None:
            try:
                reply, route = await self._run_with_retry(
                    self._multi_runner, prompt, "multi_agent"
                )
                route.path = "multi_agent"
                route.latency_ms = int((time.perf_counter() - started) * 1000)
                return AdvisorResponse(
                    status="active_reasoning", generated_guidance=reply, route=route
                )
            except errors.AdvisorError as exc:
                if not settings.enable_fallback:
                    raise
                log.warning(
                    "multi-agent path unrecoverable (%s); falling back to single agent",
                    exc.error_code,
                )

        # Fallback: single agent.
        reply, route = await self._run_with_retry(
            self._single_runner, prompt, "single_agent"
        )
        route.path = "single_agent"
        route.latency_ms = int((time.perf_counter() - started) * 1000)
        degraded = self._multi_runner is not None  # we only got here by falling back
        return AdvisorResponse(
            status="degraded" if degraded else "active_reasoning",
            generated_guidance=reply,
            route=route,
            degraded=degraded,
        )


_runtime: AdvisorRuntime | None = None


def get_runtime() -> AdvisorRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AdvisorRuntime()
    return _runtime
