import { setTeamColors } from "./lib/charts.js";
import { el } from "./lib/format.js";
import * as standings from "./tabs/standings.js";
import * as players from "./tabs/players.js";
import * as boosters from "./tabs/boosters.js";
import * as captaincy from "./tabs/captaincy.js";

const TABS = {
  standings: standings,
  players: players,
  boosters: boosters,
  captaincy: captaincy,
};

const state = { meta: null, players: null, rendered: new Set() };

async function boot() {
  const meta = await fetchJSON("data/meta.json");
  state.meta = meta;
  setTeamColors(meta.teams.map((t) => t.name));

  // Header
  document.getElementById("league-title").textContent = meta.league;
  const stats = document.getElementById("header-stats");
  stats.append(
    chip("Teams", meta.n_teams),
    chip("Matches", meta.n_matches),
    chip("Player rows", meta.n_player_rows.toLocaleString()),
  );
  const gen = meta.generated_at ? ` · data generated ${meta.generated_at}` : "";
  document.getElementById("foot-meta").textContent = `${meta.league}${gen}`;

  // Tab wiring
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => activate(btn.dataset.tab));
  });

  activate("standings");
}

async function activate(name) {
  document.querySelectorAll(".tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name),
  );
  document.querySelectorAll(".panel").forEach((p) =>
    p.classList.toggle("active", p.id === name),
  );

  if (state.rendered.has(name)) return;

  const root = document.getElementById(name);

  if (name === "players") {
    root.innerHTML = '<p class="loading">Loading player data…</p>';
    if (!state.players) state.players = await fetchJSON("data/players.json");
    players.render(root, state.meta, state.players);
  } else {
    TABS[name].render(root, state.meta);
  }
  state.rendered.add(name);
}

function chip(label, value) {
  return el("span", { class: "chip", html: `${label} <b>${value}</b>` });
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Failed to load ${url}: ${res.status}`);
  return res.json();
}

boot().catch((err) => {
  document.querySelector("main").innerHTML =
    `<p class="loading">Could not load dashboard data.<br><code>${err.message}</code></p>`;
  console.error(err);
});
