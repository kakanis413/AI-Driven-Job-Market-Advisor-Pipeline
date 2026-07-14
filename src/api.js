const AGENT_API_URL = import.meta.env.VITE_AGENT_API_URL || "http://localhost:8000";

// GET — static file, no processing, same result for everyone
export async function loadMajors() {
  const res = await fetch("/data.json");
  if (!res.ok) {
    throw new Error(`Failed to load data.json: ${res.status}`);
  }
  return res.json();
}

// POST — dynamic, depends on which major + what the student asks
export async function analyzeMajor(majorEntry, queryContext) {
  const payload = {
    major_name: majorEntry.major,
    exposure: majorEntry.exposure,
    median_pay: majorEntry.median_pay,
    growth: majorEntry.growth ?? "not yet available",
    occupations: majorEntry.occupations.map((o) => ({
      soc: o.soc,
      title: o.title,
      exposure: o.exposure,
    })),
    query_context: queryContext,
  };

  const res = await fetch(`${AGENT_API_URL}/api/v1/analyze-major`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Agent request failed: ${res.status}`);
  }

  return res.json(); // { agent_node, status, generated_guidance }
}