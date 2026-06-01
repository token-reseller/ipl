import { fmt, signed, el, clear, table } from "../lib/format.js";
import { draw, teamColor, groupBy } from "../lib/charts.js";

export function render(root, meta) {
  root.innerHTML = "";
  const usages = meta.booster_usages;

  if (!usages.length) {
    root.append(el("p", { class: "loading", text: "No booster usages in the dataset." }));
    return;
  }

  // ---- Total ROI per team ----
  const byTeam = new Map();
  for (const u of usages) byTeam.set(u.name, (byTeam.get(u.name) || 0) + u.roi);
  const teamEntries = [...byTeam.entries()].sort((a, b) => b[1] - a[1]);
  const teamTrace = {
    type: "bar",
    x: teamEntries.map((e) => e[0]),
    y: teamEntries.map((e) => e[1]),
    marker: { color: teamEntries.map((e) => teamColor(e[0])) },
    text: teamEntries.map((e) => fmt(e[1], 0)),
    textposition: "outside",
    hovertemplate: "%{x}<br>Total ROI: %{y:.1f}<extra></extra>",
  };
  root.append(chartBlock("Total booster value extracted per fantasy team", [teamTrace], {}, 380));

  // ---- Avg ROI by booster x team ----
  const byTeamName = groupBy(meta.booster_avg, (r) => r.name);
  const boosters = [...new Set(meta.booster_avg.map((r) => r.booster))];
  const avgTraces = [...byTeamName.entries()].map(([name, rows]) => {
    const lookup = new Map(rows.map((r) => [r.booster, r.roi]));
    return {
      type: "bar",
      name,
      x: boosters,
      y: boosters.map((b) => lookup.get(b) ?? null),
      marker: { color: teamColor(name) },
    };
  });
  root.append(
    chartBlock("Average ROI by booster × fantasy team", avgTraces, { barmode: "group" }, 420),
  );

  // ---- Best individual plays ----
  const best = [...usages].sort((a, b) => b.roi - a.roi).slice(0, 15);
  root.append(
    el("div", { class: "block" }, [
      el("h2", { text: "Best individual booster plays" }),
      el("div", { class: "card" }, [
        table(
          [
            { key: "name", label: "Team" },
            { key: "m", label: "Match", align: "r" },
            { key: "booster", label: "Booster" },
            { key: "home", label: "Home" },
            { key: "away", label: "Away" },
            { key: "base", label: "Base", align: "r", fmt: (v) => fmt(v, 0) },
            { key: "applied", label: "Applied", align: "r", fmt: (v) => fmt(v, 0) },
            { key: "roi", label: "ROI Δ", align: "r", fmt: (v) => signed(v, 1), cls: "pos" },
          ],
          best,
        ),
      ]),
    ]),
  );

  // ---- Drill into a single usage ----
  const sorted = [...usages].sort((a, b) => a.m - b.m || a.name.localeCompare(b.name));
  const drill = el("div", { class: "block" });
  drill.append(el("h2", { text: "Drill into a single booster usage" }));

  const sel = el(
    "select",
    {},
    sorted.map((u, i) =>
      el("option", {
        value: String(i),
        text: `M${u.m}  ${u.home} vs ${u.away}  ·  ${u.name} · ${u.booster}  (Δ ${signed(u.roi, 1)})`,
      }),
    ),
  );
  const descHost = el("p", { class: "caption" });
  const xiHost = el("div", { class: "card" });
  sel.addEventListener("change", () => showUsage(meta, sorted[Number(sel.value)], descHost, xiHost));
  drill.append(
    el("div", { class: "filter", style: "margin-bottom:12px" }, [
      el("label", { text: "Booster usage" }),
      sel,
    ]),
    descHost,
    xiHost,
  );
  root.append(drill);
  showUsage(meta, sorted[0], descHost, xiHost);
}

function showUsage(meta, u, descHost, xiHost) {
  const desc = meta.booster_desc[u.booster] || "No description on file.";
  clear(descHost).append(el("b", { text: u.booster }), ` — ${desc}`);
  const xi = meta.booster_xi[`${u.tid}_${u.m}`] || [];
  clear(xiHost).append(
    table(
      [
        { key: "p", label: "Player" },
        { key: "ipl", label: "IPL" },
        { key: "role", label: "Role" },
        { key: "fp", label: "Foreign", fmt: (v) => (v ? "✓" : "") },
        { key: "cap", label: "C", fmt: (v) => (v ? "✓" : "") },
        { key: "vc", label: "VC", fmt: (v) => (v ? "✓" : "") },
        { key: "base", label: "Base", align: "r", fmt: (v) => fmt(v, 0) },
        { key: "applied", label: "Applied", align: "r", fmt: (v) => fmt(v, 0) },
        { key: "delta", label: "Δ", align: "r", fmt: (v) => signed(v, 1) },
      ],
      xi,
    ),
  );
}

function chartBlock(title, traces, layout, height) {
  const node = el("div", { class: "chart" });
  const wrap = el("div", { class: "block" }, [
    el("h2", { text: title }),
    el("div", { class: "card" }, [node]),
  ]);
  queueMicrotask(() => draw(node, traces, layout, height));
  return wrap;
}
