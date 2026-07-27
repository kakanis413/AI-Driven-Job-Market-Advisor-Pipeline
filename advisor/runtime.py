"""Runtime: turn a request into a grounded answer, with timeout, retry, and TTL caching.

Supports sync responses and async token streaming for low-latency TTFT.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Dict, Tuple, AsyncGenerator

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from advisor import errors
from advisor.agents import root_agent
from advisor.config import settings
from advisor.schemas import AdvisorRequest, AdvisorResponse, RouteInfo
from advisor.tools import get_top_majors

log = logging.getLogger(__name__)

RESPONSE_CACHE: Dict[str, Tuple[float, AdvisorResponse]] = {}
CACHE_TTL_SECONDS = 86400  # 24 Hours
MAX_CACHE_SIZE = 500       # Prevent unbounded memory usage
_CACHE_LOCK = asyncio.Lock()

# Tools whose use means the answer touched live web results. `parallel_research`
# counts: it wraps the news agent, so a turn that called it did search.
_SEARCH_TOOLS = {"news_researcher", "parallel_research", "google_search"}

# One event of the stream: ("token", text) is answer prose, ("status", label) names
# the hop currently running so a tool-bound wait isn't a blank screen.
StreamEvent = Tuple[str, str]

# Shown verbatim to the student. Only tools that can cost real time get a label —
# an instant lookup that flashes a status is noise, not information.
_TOOL_STATUS: Dict[str, str] = {
    "parallel_research": "Searching recent news…",
    "news_researcher": "Searching recent news…",
    "google_search": "Searching the web…",
    "get_recent_news": "Checking recent headlines…",
    "compare_majors": "Comparing majors…",
    "get_top_majors": "Ranking majors…",
    # BigQuery escalation. This is the slowest path in the system — measured 13.3s to
    # first token — and before these entries existed it was also the only one that
    # emitted no status at all, so the panel sat frozen for the whole wait.
    "execute_sql": "Querying the warehouse…",
    "ask_data_insights": "Querying the warehouse…",
    "forecast": "Querying the warehouse…",
    "analyze_contribution": "Querying the warehouse…",
    "detect_anomalies": "Querying the warehouse…",
    "get_table_info": "Reading the data schema…",
    "get_dataset_info": "Reading the data schema…",
    "list_table_ids": "Reading the data schema…",
    "list_dataset_ids": "Reading the data schema…",
    "search_catalog": "Searching the data catalog…",
}


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text.strip("?.! ")


class AdvisorRuntime:
    """Owns the agent, sessions, and runner. Built once at startup."""

    def __init__(self) -> None:
        self._session_service = InMemorySessionService()
        self._runner = Runner(
            agent=root_agent,
            app_name=settings.app_name,
            session_service=self._session_service,
        )

    # --- cache: one implementation, shared by advise() and advise_stream() ---

    @staticmethod
    def _cache_key(req: AdvisorRequest) -> str:
        major_name = getattr(req, "major", "") or getattr(req, "major_name", "") or ""
        raw_query = (
            getattr(req, "query_context", "")
            or getattr(req, "query", "")
            or getattr(req, "message", "")
            or ""
        )
        key = f"{_normalize_text(major_name)}:{_normalize_text(raw_query)}"
        if getattr(req, "is_university_compare", False):
            school = _normalize_text(getattr(req, "university", "") or "")
            intended = _normalize_text(getattr(req, "intended_major", "") or "")
            key = f"{key}:{school}:{intended}"
        return key

    async def _cache_get(self, cache_key: str) -> AdvisorResponse | None:
        async with _CACHE_LOCK:
            hit = RESPONSE_CACHE.get(cache_key)
            if hit is None:
                return None
            timestamp, cached_response = hit
            if time.time() - timestamp >= CACHE_TTL_SECONDS:
                log.info("Expired TTL Cache entry for key: %r", cache_key)
                del RESPONSE_CACHE[cache_key]
                return None
        # Copy before marking the hit: mutating the stored object would rewrite the
        # cached entry's route to "cache_hit" forever, losing the original timing.
        replay = cached_response.model_copy(deep=True)
        replay.route.path = "cache_hit"
        return replay

    async def _cache_put(self, cache_key: str, response: AdvisorResponse) -> None:
        async with _CACHE_LOCK:
            if len(RESPONSE_CACHE) >= MAX_CACHE_SIZE:
                del RESPONSE_CACHE[next(iter(RESPONSE_CACHE))]
            RESPONSE_CACHE[cache_key] = (time.time(), response)

    @staticmethod
    def _prompt(req: AdvisorRequest) -> str:
        query_text = (
            getattr(req, "query_context", "")
            or getattr(req, "query", "")
            or getattr(req, "message", "")
            or ""
        )
        
        preloaded_context = ""
        norm_q = _normalize_text(query_text)
        if any(w in norm_q for w in ["exposed", "exposure", "highest ai", "top ai", "most exposed"]):
            try:
                # Matches exact tools.py signature: metric="exposure", n=5, order="desc"
                top_ai = get_top_majors(metric="exposure", n=5, order="desc")
                preloaded_context = f"\nPRE-LOADED TOP AI EXPOSURE DATA:\n{top_ai}\n"
                log.info("fast-path: injected top major data into prompt context")
            except Exception as e:
                log.warning("Fast-path preloaded data fetch skipped: %s", e)

        closing = (
            "Answer the student's question generally and conversationally. State no "
            "specific numbers you were not given by a tool or context. Apply the "
            "exposure-is-not-job-loss framing."
            if req.is_general
            else "Answer the student's question, grounded strictly in the verified data "
            "above (and any tool results). Apply the exposure-is-not-job-loss framing."
        )
        
        grounding = req.grounding_block() if hasattr(req, "grounding_block") else ""
        
        return (
            f"{grounding}\n"
            f"{preloaded_context}\n"
            f"STUDENT QUESTION: {query_text}\n\n"
            f"{closing}"
        )

    async def advise_stream(self, req: AdvisorRequest) -> AsyncGenerator[StreamEvent, None]:
        """Yield the advisor's turn as typed events: ("status", label) and ("token", text).

        Four things this must get right, all of which are invisible until you look
        at what the student actually sees:

        - `StreamingMode.SSE` is what makes ADK emit partial events at all. Without
          it `run_async` yields one complete message per agent turn, so "streaming"
          delivers the whole answer in a single chunk at the very end and
          time-to-first-token equals total latency.
        - Only the root agent's text is the answer. Sub-agents (news_researcher)
          also emit text events; forwarding those dumps raw news bullets into the
          chat before the real reply — the reported "confusing sometimes".
        - The 24h RESPONSE_CACHE has to work on this path too, or moving the
          frontend onto streaming silently drops every cache hit.
        - A turn that calls a slow tool produces NO token for several seconds,
          because the tool runs before any text exists. Streaming cannot mask that;
          "status" events name the hop that is actually running so the wait reads as
          work rather than a hang.
        """
        cache_key = self._cache_key(req)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            log.info("stream cache HIT | key=%r", cache_key)
            yield ("token", cached.generated_guidance)
            return

        log.info("stream cache MISS | key=%r", cache_key)
        prompt = self._prompt(req)
        user_id = "student"
        session_id = f"s-{uuid.uuid4().hex[:16]}"
        await self._session_service.create_session(
            app_name=settings.app_name, user_id=user_id, session_id=session_id
        )
        content = types.Content(role="user", parts=[types.Part(text=prompt)])

        root_author = root_agent.name
        started = time.perf_counter()
        first_token_ms: int | None = None
        streamed_parts: list[str] = []
        called: list[str] = []
        used_search = False
        saw_partial = False

        async for event in self._runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        ):
            for part in (event.content.parts if event.content else []) or []:
                fc = getattr(part, "function_call", None)
                # Partial events repeat the same function_call part, so the name
                # must be deduped or one call is logged several times.
                if fc is not None and fc.name not in called:
                    called.append(fc.name)
                    if fc.name in _SEARCH_TOOLS:
                        used_search = True
                    label = _TOOL_STATUS.get(fc.name)
                    if label:
                        yield ("status", label)

            # Sub-agent chatter is working material, not the answer.
            if event.author != root_author:
                continue

            is_partial = bool(getattr(event, "partial", False))
            # The final event repeats the full text that the partials already
            # delivered. Emitting it too would show the answer twice.
            if not is_partial and saw_partial:
                continue

            for part in (event.content.parts if event.content else []) or []:
                text = getattr(part, "text", None)
                if not text:
                    continue
                if is_partial:
                    saw_partial = True
                if first_token_ms is None:
                    first_token_ms = int((time.perf_counter() - started) * 1000)
                    log.info("stream | first token in %dms", first_token_ms)
                streamed_parts.append(text)
                yield ("token", text)

        reply = "".join(streamed_parts).strip()
        if not reply:
            raise errors.EmptyResponse()

        route = RouteInfo(
            path="root_agent_stream",
            agents_called=called,
            used_search=used_search,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        log.info(
            "stream response | agents=%s search=%s ttft=%sms total=%dms",
            called, used_search, first_token_ms, route.latency_ms,
        )
        await self._cache_put(
            cache_key,
            AdvisorResponse(
                status="active_reasoning", generated_guidance=reply, route=route
            ),
        )

    async def _run_once(self, prompt: str) -> tuple[str, RouteInfo]:
        user_id = "student"
        session_id = f"s-{uuid.uuid4().hex[:16]}"
        await self._session_service.create_session(
            app_name=settings.app_name, user_id=user_id, session_id=session_id
        )
        content = types.Content(role="user", parts=[types.Part(text=prompt)])

        called: list[str] = []
        used_search = False
        reply = ""
        async for event in self._runner.run_async(
            user_id=user_id, session_id=session_id, new_message=content
        ):
            for part in (event.content.parts if event.content else []) or []:
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    called.append(fc.name)
                    if fc.name in _SEARCH_TOOLS:
                        used_search = True
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

    async def _run_with_retry(self, prompt: str) -> tuple[str, RouteInfo]:
        last: Exception | None = None
        for attempt in range(settings.max_retries + 1):
            try:
                return await asyncio.wait_for(
                    self._run_once(prompt), timeout=settings.request_timeout_s
                )
            except asyncio.TimeoutError:
                last = errors.UpstreamTimeout()
                log.warning("Request timed out (attempt %d)", attempt + 1)
            except Exception as exc:
                last = exc
                classified = errors.classify(exc)
                log.warning(
                    "Request failed (attempt %d): %s", attempt + 1, classified.error_code
                )
                if not classified.retryable:
                    raise classified from exc
            if attempt < settings.max_retries:
                await asyncio.sleep(settings.retry_base_delay_s * (2**attempt))
        raise errors.classify(last) if last else errors.AdvisorError()

    async def advise(self, req: AdvisorRequest) -> AdvisorResponse:
        cache_key = self._cache_key(req)

        cached = await self._cache_get(cache_key)
        if cached is not None:
            log.info("runtime cache HIT | key=%r", cache_key)
            return cached

        log.info("runtime cache MISS | key=%r", cache_key)
        prompt = self._prompt(req)
        started = time.perf_counter()

        reply, route = await self._run_with_retry(prompt)
        route.path = "root_agent"
        route.latency_ms = int((time.perf_counter() - started) * 1000)

        response = AdvisorResponse(
            status="active_reasoning",
            generated_guidance=reply,
            route=route,
        )
        await self._cache_put(cache_key, response)
        return response


_runtime: AdvisorRuntime | None = None


def get_runtime() -> AdvisorRuntime:
    global _runtime
    if _runtime is None:
        _runtime = AdvisorRuntime()
    return _runtime