import { useState } from "react";
import { analyzeMajor } from "../api";

export default function MajorTile({ majorEntry, onSelect }) {
  const [loading, setLoading] = useState(false);
  const [reply, setReply] = useState(null);
  const [error, setError] = useState(null);

  async function handleClick() {
    onSelect(majorEntry); // opens split-screen, shows exposure gauge etc.
    setLoading(true);
    setError(null);
    try {
      const result = await analyzeMajor(
        majorEntry,
        `Tell me about the AI exposure and career outlook for ${majorEntry.major}.`
      );
      setReply(result.generated_guidance);
    } catch (err) {
      setError("Advisor is unavailable right now — the data view still works.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="tile"
      onClick={handleClick}
      style={{ backgroundColor: exposureColor(majorEntry.exposure) }}
    >
      <span className="tile-title">{majorEntry.major}</span>
      <span className="tile-exposure">{majorEntry.exposure.toFixed(1)}</span>

      {loading && <div className="advisor-loading">Advisor is thinking…</div>}
      {error && <div className="advisor-error">{error}</div>}
      {reply && <div className="advisor-reply">{reply}</div>}
    </div>
  );
}

function exposureColor(score) {
  if (score >= 7.5) return "#D85A30"; // coral — high exposure
  if (score >= 5) return "#EF9F27";   // amber — moderate
  return "#5DCAA5";                    // teal — low exposure
}