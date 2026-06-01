import { fmt, el, table, pill } from "../lib/format.js";
import { draw, teamColor, groupBy } from "../lib/charts.js";

const SYMBOLS = { "Hit (top-3)": "circle", Miss: "x" };

export function render(root, meta) {
  root.innerHTML = "";

  // ---- Hit-rate summary ----
  root.append(
    el("div", { class: "block" }, [
      el("h2", { text: "Captaincy hit-rate (captain finished top-3 in the XI)" }),
      el("div", { class: "card" }, [
        table(
          [
            { key: "name", label: "Team" },
            { key: "picks", label: "Picks", align: "r" },
            { key: "hits", label: "Hits", align: "r" },
            { key: "hit_rate", label: "Hit %", align: "r" },
            { key: "avg_base", label: "Avg base", align: "r" },
            { key: "avg_applied", label: "Avg applied", align: "r" },
          ],
          meta.captain_summary,
        ),
      ]),
    ]),
  );

  // ---- Captain points per match scatter ----
  const byTeam = groupBy(meta.captain_picks, (r) => r.name);
  const traces = [];
  for (const [name, rows] of byTeam.entries()) {
    for (const outcome of ["Hit (top-3)", "Miss"]) {
      const rs = rows.filter((r) => (r.hit ? "Hit (top-3)" : "Miss") === outcome);
      if (!rs.length) continue;
      traces.push({
        type: "scatter",
        mode: "markers",
        name: `${name} · ${outcome}`,
        legendgroup: name,
        x: rs.map((r) => r.m),
        y: rs.map((r) => r.base),
        marker: { color: teamColor(name), symbol: SYMBOLS[outcome], size: 10, line: { width: 1, color: "#0b1120" } },
        customdata: rs.map((r) => [r.player, r.ipl, r.applied]),
        hovertemplate:
          "<b>%{fullData.name}</b><br>Match %{x}<br>%{customdata[0]} (%{customdata[1]})<br>" +
          "Base: %{y:.1f} · Applied: %{customdata[2]:.1f}<extra></extra>",
      });
    }
  }
  const node = el("div", { class: "chart" });
  root.append(
    el("div", { class: "block" }, [
      el("h2", { text: "Captain points per match" }),
      el("div", { class: "card" }, [node]),
    ]),
  );
  queueMicrotask(() => draw(node, traces, {}, 460));

  // ---- Most-captained per team (expanders) ----
  const mc = groupBy(meta.most_captained, (r) => r.name);
  const expanders = el("div", { class: "block" }, [
    el("h2", { text: "Most-captained players per team" }),
    ...[...mc.entries()].map(([name, rows]) =>
      el("details", {}, [
        el("summary", { text: name }),
        table(
          [
            { key: "player", label: "Player" },
            { key: "ipl", label: "IPL" },
            { key: "times", label: "Times", align: "r" },
            { key: "avg_base", label: "Avg base", align: "r" },
          ],
          rows,
        ),
      ]),
    ),
  ]);
  root.append(expanders);

  // ---- All captaincy picks ----
  root.append(
    el("div", { class: "block" }, [
      el("h2", { text: "All captaincy picks" }),
      el("div", { class: "card" }, [
        table(
          [
            { key: "name", label: "Team" },
            { key: "m", label: "Match", align: "r" },
            { key: "player", label: "Player" },
            { key: "ipl", label: "IPL" },
            { key: "role", label: "Role" },
            { key: "base", label: "Base", align: "r", fmt: (v) => fmt(v, 0) },
            { key: "applied", label: "Applied", align: "r", fmt: (v) => fmt(v, 0) },
            { key: "rank", label: "Rank in XI", align: "r" },
            { key: "hit", label: "Outcome", fmt: (v) => (v ? pill("Hit", "hit") : pill("Miss", "miss")) },
            { key: "booster", label: "Booster", fmt: (v) => v || "—" },
          ],
          [...meta.captain_picks].sort((a, b) => a.name.localeCompare(b.name) || a.m - b.m),
        ),
      ]),
    ]),
  );
}
