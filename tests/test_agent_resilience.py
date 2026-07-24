"""The news path must degrade, never abort: a failure inside a wrapped agent
comes back to the orchestrator as a structured 'unavailable' result (which its
instruction tells it to route around), not an exception that 5xxs the request.
"""

from __future__ import annotations

import asyncio

from google.adk.tools.agent_tool import AgentTool

from advisor.agents import ResilientAgentTool, build_news_agent


def test_resilient_agent_tool_degrades_instead_of_raising(monkeypatch):
    async def _boom(self, *, args, tool_context):
        raise RuntimeError("simulated transient google_search failure")

    monkeypatch.setattr(AgentTool, "run_async", _boom)

    tool = ResilientAgentTool(agent=build_news_agent())
    result = asyncio.run(tool.run_async(args={"request": "any"}, tool_context=None))

    assert result["status"] == "unavailable"
    assert result["agent"] == "news_researcher"
    assert "invent" in result["message"]


def test_resilient_agent_tool_passes_success_through(monkeypatch):
    async def _ok(self, *, args, tool_context):
        return "two cited news items"

    monkeypatch.setattr(AgentTool, "run_async", _ok)

    tool = ResilientAgentTool(agent=build_news_agent())
    result = asyncio.run(tool.run_async(args={"request": "any"}, tool_context=None))

    assert result == "two cited news items"


def test_news_agent_instruction_contains_recency_constraints():
    """Ensure news_agent prompt explicitly enforces 30-to-90-day time horizon constraints."""
    agent = build_news_agent()
    instructions = agent.instruction.lower()

    # Verify recency constraints are set in system instructions
    assert "30 to 90 days" in instructions or "30-90 days" in instructions
    assert "factual" in instructions


def test_news_agent_instruction_contains_fallback_clause():
    """Ensure news_agent has clear instructions on how to respond when no recent news exists."""
    agent = build_news_agent()
    instructions = agent.instruction.lower()

    # Verify explicit fallback phrase directive
    assert "no significant new hiring trends reported" in instructions or "if no relevant news" in instructions

