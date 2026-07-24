# Real-Time Dynamic "Top 3 Careers" via News Agent & Latency Optimization Spec

## 1. Executive Summary & Problem Statement
Currently, career demand and projections in `data.json` rely on baseline government datasets (OEWS). While foundational, these static sources only update annually.

By leveraging our `news_agent` (Google Search grounding), we augment static baseline metrics with real-time labor market trends (hiring surges, emerging roles, quarterly tech shifts). Simultaneously, we implement a multi-tiered caching strategy (in-memory tool caching + server-side TTL caching) to optimize response latency.

## 2. Architectural Design

[Static Baseline Data]           [Real-Time News Agent]
(data.json: pay, growth)        (Google Search Grounding)
│                                │
└──────────────┬─────────────────┘
│
▼
[Orchestrator / Blending Engine]
│
▼
[Top 3 Hot Careers Right Now]
│
▼
[24-Hour TTL Server Cache]

## 3. Implementation Strategy
- Constrain news search queries to recent timeframes (past 30–90 days).
- Blend static baseline metrics with live search sentiment into a combined rank.
- Cache tool lookups in memory and endpoint results with a 24-hour TTL in FastAPI.