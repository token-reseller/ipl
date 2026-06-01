import { fmt, signed, el, clear, table } from "../lib/format.js";
import { draw, teamColor, groupBy } from "../lib/charts.js";

// Toggleable score components. `key` matches the per-match fields emitted by
// build_web_data.py: base / cap / vc / boost.
const COMPONENTS = [
  { key: "base", label: "Raw" },
  { key: "cap", label: "Captain" },
  { key: "vc", label: "VC" },
  { key: "boost", label: "Boosters" },
];

// Scope = a level ABOVE the component toggles: which matches feed every chart.
const PLAYOFF_N = 4; // IPL playoffs = the last 4 matches.
const SCOPES = [
  { key: "season", label: "Full season" },
  { key: "playoffs", label: `Playoffs (last ${PLAYOFF_N})` },
];

// All components on by default = the official overall standings.
const selected = new Set(COMPONENTS.map((c) => c.key));
let scope = "season";

let META = null;
let byTeam = null; // Map(name -> match rows, in match order)
let cardsHost, lineNode, barNode, captionNode, lineTitle;

export function render(root, meta) {
  META = meta;
  byTeam = groupBy(meta.team_trajectory, (r) => r.name);
  root.innerHTML = "";

  // ---- Scope segmented control (level above components) ----
  const seg = el(
    "div",
    { class: "segmented" },
    SCOPES.map((s) => {
      const btn = el("button", {
        class: scope === s.key ? "active" : "",
        text: s.label,
      });
      btn.addEventListener("click", () => {
        if (scope === s.key) return;
        scope = s.key;
        seg.querySelectorAll("button").forEach((b) =>
          b.classList.toggle("active", b === btn),
        );
        update();
      });
      return btn;
    }),
  );

  // ---- Component toggle bar ----
  captionNode = el("p", { class: "caption" });
  const toggles = el(
    "div",
    { class: "toggles" },
    COMPONENTS.map((c) => {
      const input = el("input", {
        type: "checkbox",
        ...(selected.has(c.key) ? { checked: "checked" } : {}),
      });
      input.addEventListener("change", () => {
        if (input.checked) selected.add(c.key);
        else selected.delete(c.key);
        update();
      });
      return el("label", { class: "toggle" }, [input, el("span", { text: c.label })]);
    }),
  );

  root.append(
    el("div", { class: "block" }, [
      el("h2", { text: "Standings explorer" }),
      el("p", { class: "hint", text: "Pick a scope, then toggle scoring components to see how each contributes to the rankings." }),
      el("div", { class: "control-row" }, [el("span", { class: "control-label", text: "Scope" }), seg]),
      toggles,
      captionNode,
    ]),
  );

  // ---- Hosts for cards + charts (updated in place) ----
  cardsHost = el("div", { class: "metrics" });
  root.append(el("div", { class: "block" }, [cardsHost]));

  lineTitle = el("h2", { text: "Cumulative points across the season" });
  lineNode = el("div", { class: "chart" });
  root.append(el("div", { class: "block" }, [lineTitle, el("div", { class: "card" }, [lineNode])]));

  barNode = el("div", { class: "chart" });
  root.append(
    el("div", { class: "block" }, [
      el("h2", { text: "Per-match points (grouped)" }),
      el("div", { class: "card" }, [barNode]),
    ]),
  );

  // ---- Static reference table (always full season) ----
  root.append(
    el("div", { class: "block" }, [
      el("h2", { text: "Multiplier boost vs raw selection (full season)" }),
      el("div", { class: "card" }, [
        table(
          [
            { key: "name", label: "Team" },
            { key: "rank", label: "Rank", align: "r" },
            { key: "raw_rank", label: "Raw rank", align: "r" },
            { key: "rank_delta", label: "Δ rank", align: "r", fmt: (v) => signed(v, 0) },
            { key: "points", label: "Points", align: "r", fmt: (v) => fmt(v, 0) },
            { key: "raw_points", label: "Raw", align: "r", fmt: (v) => fmt(v, 0) },
            { key: "boost", label: "Boost", align: "r", fmt: (v) => signed(v, 0) },
          ],
          meta.boost_compare,
        ),
      ]),
    ]),
  );

  update();
}

// Per-team series for the current scope + selected components.
// Playoffs scope keeps only the last N matches and restarts the cumulative.
function recompute() {
  const teams = [...byTeam.entries()].map(([name, allRows]) => {
    const rows = scope === "playoffs" ? allRows.slice(-PLAYOFF_N) : allRows;
    let cum = 0;
    const series = rows.map((r) => {
      const value = [...selected].reduce((s, k) => s + (r[k] || 0), 0);
      cum += value;
      return { m: r.m, fixture: r.fixture, booster: r.booster, value, cum };
    });
    return { name, series, total: cum };
  });
  teams.sort((a, b) => b.total - a.total);
  teams.forEach((t, i) => (t.rank = i + 1));
  return teams;
}

function update() {
  const labels = COMPONENTS.filter((c) => selected.has(c.key)).map((c) => c.label);
  const all = labels.length === COMPONENTS.length;
  const playoffs = scope === "playoffs";
  const scopeLabel = playoffs ? `Playoffs (last ${PLAYOFF_N})` : "Full season";

  captionNode.textContent = labels.length
    ? `${scopeLabel} · Showing: ${labels.join(" + ")}${all && !playoffs ? " = Overall" : ""}`
    : "Nothing selected — pick at least one component.";
  lineTitle.textContent = playoffs
    ? "Cumulative points across the playoffs"
    : "Cumulative points across the season";

  const teams = recompute();

  // ---- Cards ----
  clear(cardsHost);
  for (const t of teams) {
    // Secondary line: in playoffs scope the headline already IS the last-4
    // total, so show a per-match average; otherwise show the playoff total.
    let sub;
    if (playoffs) {
      const avg = t.series.length ? t.total / t.series.length : 0;
      sub = `${fmt(avg, 1)} / match avg`;
    } else {
      const last4 = t.series.slice(-PLAYOFF_N).reduce((s, x) => s + x.value, 0);
      sub = `${signed(last4, 1)} last ${PLAYOFF_N} (playoffs)`;
    }
    cardsHost.append(
      el("div", { class: "metric", style: `--accent:${teamColor(t.name)}` }, [
        el("div", { class: "rank", text: `#${t.rank}` }),
        el("div", { class: "name", text: t.name }),
        el("div", { class: "value", text: fmt(t.total, 0) }),
        el("div", { class: "delta", text: sub }),
      ]),
    );
  }

  // ---- Cumulative line ----
  const lineTraces = teams.map((t) => ({
    type: "scatter",
    mode: "lines+markers",
    name: t.name,
    x: t.series.map((s) => s.m),
    y: t.series.map((s) => s.cum),
    line: { color: teamColor(t.name), width: 2.5 },
    marker: { size: 4 },
    customdata: t.series.map((s) => [s.fixture, s.booster || "—", s.value]),
    hovertemplate:
      "<b>%{fullData.name}</b><br>Match %{x} · %{customdata[0]}<br>" +
      "Booster: %{customdata[1]}<br>Match pts: %{customdata[2]:.1f}<br>" +
      "Cumulative: %{y:.1f}<extra></extra>",
  }));
  draw(lineNode, lineTraces, {}, 470);

  // ---- Per-match bars ----
  const barTraces = teams.map((t) => ({
    type: "bar",
    name: t.name,
    x: t.series.map((s) => s.m),
    y: t.series.map((s) => s.value),
    marker: { color: teamColor(t.name) },
  }));
  draw(barNode, barTraces, { barmode: "group" }, 400);
}
