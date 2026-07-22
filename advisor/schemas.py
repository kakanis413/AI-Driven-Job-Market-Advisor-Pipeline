"""The one request/response contract the React app talks to.

Deliberately backward-compatible with the existing `src/lib/advisor.ts`: same field names,
and the response still carries `generated_guidance`.

The one intentional change: `median_pay` and `growth` are nullable. The real
`public/data.json` has `growth: null` for every major and `median_pay: null` for 9 of them.
Accepting null lets the agent say "not available" instead of being handed a fake $0.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Growth = Literal["declining", "slower", "average", "faster"]


class OccupationInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., min_length=1, max_length=200)
    exposure: float | None = Field(default=None, ge=0, le=10)
    soc: str | None = Field(default=None, max_length=20)


class AdvisorRequest(BaseModel):
    """What the frontend POSTs: the student's question, plus the clicked major's
    record when there is one. `major_name` is optional so the advisor can also
    answer general questions with no major attached (general mode); in that mode
    it must stay conceptual and invent no numbers."""

    model_config = ConfigDict(extra="ignore")

    major_name: str | None = Field(default=None, min_length=1, max_length=200)
    exposure: float | None = Field(default=None, ge=0, le=10)
    median_pay: int | None = Field(default=None, ge=0)
    growth: str | None = Field(default=None, max_length=40)
    occupations: list[OccupationInfo] = Field(default_factory=list, max_length=50)
    query_context: str = Field(..., min_length=1, max_length=2000)
    cip: str | None = Field(default=None, max_length=20)

    @field_validator("query_context")
    @classmethod
    def _no_blank_question(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("query_context must not be blank")
        return v.strip()

    @field_validator("median_pay", mode="before")
    @classmethod
    def _zero_pay_is_unknown(cls, v: object) -> object:
        # The current frontend coerces null -> 0 to dodge a 422. Treat 0 as "unknown"
        # so the advisor never reports a median salary of $0 as fact.
        return None if v == 0 else v

    @field_validator("growth", mode="before")
    @classmethod
    def _normalize_growth(cls, v: object) -> object:
        if v is None:
            return None
        s = str(v).strip().lower()
        if s in {"", "not available", "n/a", "null", "none", "unknown"}:
            return None
        return s

    @property
    def is_general(self) -> bool:
        """No major attached → general mode (conceptual answers, no invented numbers)."""
        return not (self.major_name and self.major_name.strip())

    def grounding_block(self) -> str:
        """The verified-facts block handed to the agents. Unknowns are explicit."""
        if self.is_general:
            return (
                "NO MAJOR SELECTED — GENERAL MODE.\n"
                "You have NO verified data for any specific major in this turn. Answer "
                "conceptually about majors, AI exposure and careers. You may state no "
                "specific salary, exposure score, or growth figure unless a tool you "
                "called returned it. If the student asks about a particular major's "
                "numbers, say you need them to pick it on the map (or call data_agent) "
                "rather than estimating."
            )
        pay = f"${self.median_pay:,}" if self.median_pay else "not available"
        exposure = f"{self.exposure}/10" if self.exposure is not None else "not available"
        growth = self.growth or "not available"
        if self.occupations:
            occs = "\n".join(
                f"  - {o.title}"
                + (f" (AI exposure {o.exposure}/10)" if o.exposure is not None else "")
                for o in self.occupations[:12]
            )
        else:
            occs = "  - not available"
        return (
            "VERIFIED DATA FOR THIS MAJOR (the only numbers you may state):\n"
            f"  major: {self.major_name}\n"
            f"  AI exposure: {exposure}\n"
            f"  median pay: {pay}\n"
            f"  growth outlook: {growth}\n"
            "  occupations this major feeds into:\n"
            f"{occs}"
        )


class RouteInfo(BaseModel):
    """Observability: which specialists actually ran, so routing is auditable."""

    path: str = "root_agent"
    agents_called: list[str] = Field(default_factory=list)
    used_search: bool = False
    latency_ms: int = 0


class AdvisorResponse(BaseModel):
    agent_node: str = "college_advisor"
    status: Literal["active_reasoning"] = "active_reasoning"
    generated_guidance: str
    route: RouteInfo = Field(default_factory=RouteInfo)


class NewsItem(BaseModel):
    """One cited news item. `url` MUST come from search grounding metadata —
    an item whose URL cannot be matched to a grounding chunk is dropped, not
    rendered (NEWS_TAB.md hard rule 1)."""

    title: str = Field(..., min_length=1, max_length=300)
    source: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=8, max_length=2000)
    published: str | None = Field(default=None, max_length=20)
    summary: str = Field(default="", max_length=600)
    # Enriched server-side from the REAL article page (og:image) and the source
    # domain (favicon). Both nullable — never invented; a card renders without
    # them when the page has none. See advisor/news.py:_enrich.
    image: str | None = Field(default=None, max_length=2000)
    favicon: str | None = Field(default=None, max_length=2000)


class NewsFeed(BaseModel):
    """GET /api/v1/news response — the one shape shared by tab and chat."""

    family: str
    fetched_at: str
    items: list[NewsItem] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Structured error envelope — never a raw stack trace."""

    agent_node: str = "college_advisor"
    status: Literal["error"] = "error"
    generated_guidance: str = ""
    error: str
    error_code: str
    retryable: bool = False
