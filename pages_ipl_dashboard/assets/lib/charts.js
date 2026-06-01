// Thin Plotly.js wrappers with a shared dark theme.

export const TEAM_COLORS = ["#60a5fa", "#34d399", "#fbbf24", "#f87171"];
export const ROLE_COLORS = {
  Captain: "#ef4444",
  "Vice-captain": "#f59e0b",
  Regular: "#3b82f6",
};

// Stable team -> color map, assigned in standings order.
let _teamColor = {};
export function setTeamColors(teamNames) {
  _teamColor = {};
  teamNames.forEach((name, i) => {
    _teamColor[name] = TEAM_COLORS[i % TEAM_COLORS.length];
  });
}
export function teamColor(name) {
  return _teamColor[name] || "#94a3b8";
}

const FONT = {
  family: "Inter, system-ui, -apple-system, sans-serif",
  color: "#cbd5e1",
  size: 12,
};

function baseLayout(overrides = {}) {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: FONT,
    margin: { l: 56, r: 16, t: 12, b: 44 },
    hoverlabel: { bgcolor: "#0f172a", font: { color: "#e2e8f0" } },
    legend: { orientation: "h", y: -0.18, x: 0, font: { size: 11 } },
    xaxis: { gridcolor: "rgba(148,163,184,0.12)", zeroline: false },
    yaxis: { gridcolor: "rgba(148,163,184,0.12)", zeroline: false },
    ...overrides,
  };
}

const CONFIG = { displayModeBar: false, responsive: true };

export function draw(node, traces, layout = {}, height = 420) {
  Plotly.react(node, traces, baseLayout({ height, ...layout }), CONFIG);
}

// Group rows by a key, returns Map(key -> rows[]) preserving insertion order.
export function groupBy(rows, keyFn) {
  const m = new Map();
  for (const r of rows) {
    const k = keyFn(r);
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(r);
  }
  return m;
}
