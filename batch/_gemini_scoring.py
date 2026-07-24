"""
batch/_gemini_scoring.py

Thin shared helpers for the Karpathy-style rebuild scorers (occupation + major).

Why raw google-genai and not an ADK Runner (like task_scoring.py): these two
jobs make one independent structured call per unit with no tools and no shared
session — an ADK Runner/Session per call is pure overhead. The raw async client
gives clean concurrency and native structured output (response_schema), which is
all we need. temperature=0 and structured JSON are preserved, exactly as the
guardrails require.

Nothing here is imported by main.py or registered as a tool on root_agent — the
live chat path can never trigger these batch jobs.
"""

import asyncio

from google import genai
from google.genai import types

# Matches the model already used by task_scoring.py, so the two scoring paths
# are on the same model family.
MODEL = "gemini-3.5-flash"

_client: genai.Client | None = None


def client() -> genai.Client:
    """Lazily build one Vertex genai client (auth via the GOOGLE_* env vars)."""
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


async def score_json(prompt: str, schema, semaphore: asyncio.Semaphore,
                     max_retries: int = 4):
    """
    One structured, temperature-0 Gemini call → a validated `schema` instance.

    Retries transient failures (rate limits, 5xx, dropped responses) with
    exponential backoff. Raises only if every attempt fails, so a single bad
    unit surfaces loudly rather than silently scoring 0.
    """
    async with semaphore:
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = await client().aio.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0,
                        response_mime_type="application/json",
                        response_schema=schema,
                    ),
                )
                if resp.parsed is not None:
                    return resp.parsed
                # Fall back to manual validation if the SDK didn't pre-parse.
                if resp.text:
                    return schema.model_validate_json(resp.text)
                raise RuntimeError("empty response")
            except Exception as e:  # noqa: BLE001 — retry any transient failure
                last_err = e
                if attempt == max_retries - 1:
                    break
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"scoring failed after {max_retries} attempts: {last_err}")
