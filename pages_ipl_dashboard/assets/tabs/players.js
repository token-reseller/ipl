import { fmt, el, clear, table } from "../lib/format.js";
import { draw, ROLE_COLORS } from "../lib/charts.js";

let DATA = null; // players.json payload
let state = { ipl: [], role: [], fteam: [], player: null };

export function render(root, _meta, players) {
  DATA = players;
  root.innerHTML = "";

  // ---- Filters ----
  const filters = el("div", { class: "filters" }, [
    multi("IPL team", DATA.ipl_teams, "ipl"),
    multi("Role", DATA.roles, "role"),
    multi("Picked by fantasy team", DATA.fantasy_teams, "fteam"),
  ]);
  root.append(filters);

  const caption = el("p", { class: "caption", id: "px-caption" });
  root.append(caption);

  const totalsHost = el("div", { class: "block", id: "px-totals" });
  const playerHost = el("div", { class: "block", id: "px-player" });
  root.append(totalsHost, playerHost);

  update();
}

function multi(label, options, key) {
  const sel = el(
    "select",
    { class: "multi", multiple: "multiple", size: Math.min(options.length, 5) },
    options.map((o) => el("option", { value: o, text: o })),
  );
  sel.addEventListener("change", () => {
    state[key] = [...sel.selectedOptions].map((o) => o.value);
    state.player = null; // reset player selection when filters change
    update();
  });
  return el("div", { class: "filter" }, [el("label", { text: label }), sel]);
}

function filteredRows() {
  return DATA.rows.filter(
    (r) =>
      (!state.ipl.length || state.ipl.includes(r.ipl)) &&
      (!state.role.length || state.role.includes(r.role)) &&
      (!state.fteam.length || state.fteam.includes(r.tname)),
  );
}

// Group by player -> season totals (mirrors dashboard.py:252-265).
function seasonTotals(rows) {
  const m = new Map();
  for (const r of rows) {
    const key = `${r.player}||${r.ipl}||${r.role}`;
    let a = m.get(key);
    if (!a) {
      a = {
        player: r.player,
        ipl: r.ipl,
        role: r.role,
        matches: new Set(),
        total_base: 0,
        total_applied: 0,
        cap: 0,
        vc: 0,
        n: 0,
      };
      m.set(key, a);
    }
    a.matches.add(r.m);
    a.total_base += r.base || 0;
    a.total_applied += r.applied || 0;
    a.cap += r.cap ? 1 : 0;
    a.vc += r.vc ? 1 : 0;
    a.n += 1;
  }
  return [...m.values()]
    .map((a) => ({
      player: a.player,
      ipl: a.ipl,
      role: a.role,
      matches_picked: a.matches.size,
      total_base: a.total_base,
      avg_base: a.n ? a.total_base / a.n : 0,
      total_applied: a.total_applied,
      cap: a.cap,
      vc: a.vc,
    }))
    .sort((x, y) => y.total_base - x.total_base);
}

function update() {
  const rows = filteredRows();
  document.getElementById("px-caption").textContent =
    `${rows.length.toLocaleString()} player-match rows match the current filters ` +
    `(out of ${DATA.rows.length.toLocaleString()}).`;

  const totals = seasonTotals(rows);
  const totalsHost = clear(document.getElementById("px-totals"));
  totalsHost.append(el("h2", { text: "Season totals (top 25 by base points)" }));
  totalsHost.append(
    el("div", { class: "card" }, [
      table(
        [
          { key: "player", label: "Player" },
          { key: "ipl", label: "IPL" },
          { key: "role", label: "Role" },
          { key: "matches_picked", label: "Picked", align: "r" },
          { key: "total_base", label: "Base", align: "r", fmt: (v) => fmt(v, 0) },
          { key: "avg_base", label: "Avg base", align: "r" },
          { key: "total_applied", label: "Applied", align: "r", fmt: (v) => fmt(v, 0) },
          { key: "cap", label: "C", align: "r" },
          { key: "vc", label: "VC", align: "r" },
        ],
        totals.slice(0, 25),
      ),
    ]),
  );

  renderPlayer(totals, rows);
}

function renderPlayer(totals, rows) {
  const host = clear(document.getElementById("px-player"));
  host.append(el("h2", { text: "Per-player match-by-match" }));

  if (!totals.length) {
    host.append(el("p", { class: "loading", text: "No players match the current filters." }));
    return;
  }

  const options = totals.map((t) => t.player);
  if (!state.player || !options.includes(state.player)) state.player = options[0];

  const sel = el(
    "select",
    {},
    options.map((p) =>
      el("option", { value: p, text: p, ...(p === state.player ? { selected: "selected" } : {}) }),
    ),
  );
  sel.addEventListener("change", () => {
    state.player = sel.value;
    renderPlayer(totals, rows);
  });
  host.append(el("div", { class: "filter", style: "max-width:320px;margin-bottom:14px" }, [
    el("label", { text: "Player" }),
    sel,
  ]));

  const pdf = rows
    .filter((r) => r.player === state.player)
    .sort((a, b) => a.m - b.m)
    .map((r) => ({
      ...r,
      pick_role: r.cap ? "Captain" : r.vc ? "Vice-captain" : "Regular",
    }));

  const node = el("div", { class: "chart" });
  host.append(el("div", { class: "card" }, [node]));

  const roles = ["Captain", "Vice-captain", "Regular"];
  const traces = roles
    .map((role) => {
      const rs = pdf.filter((r) => r.pick_role === role);
      return {
        type: "bar",
        name: role,
        x: rs.map((r) => r.m),
        y: rs.map((r) => r.applied),
        marker: { color: ROLE_COLORS[role] },
        customdata: rs.map((r) => [r.tname, r.ipl, r.base, r.booster || "—"]),
        hovertemplate:
          "Match %{x}<br>Picked by: %{customdata[0]}<br>IPL: %{customdata[1]}<br>" +
          "Base: %{customdata[2]:.1f} · Applied: %{y:.1f}<br>" +
          "Booster: %{customdata[3]}<extra>" + role + "</extra>",
      };
    })
    .filter((t) => t.x.length);
  queueMicrotask(() => draw(node, traces, { barmode: "stack" }, 420));

  // Raw rows expander.
  const raw = table(
    [
      { key: "tname", label: "Picked by" },
      { key: "m", label: "Match", align: "r" },
      { key: "ipl", label: "IPL" },
      { key: "role", label: "Role" },
      { key: "pick_role", label: "XI role" },
      { key: "base", label: "Base", align: "r" },
      { key: "applied", label: "Applied", align: "r" },
      { key: "booster", label: "Booster", fmt: (v) => v || "—" },
    ],
    pdf,
  );
  host.append(
    el("details", {}, [
      el("summary", { text: `Raw rows for ${state.player}` }),
      raw,
    ]),
  );
}
