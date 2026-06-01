// Small formatting + DOM helpers shared across tabs.

export function fmt(value, dec = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  });
}

export function signed(value, dec = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const s = fmt(Math.abs(value), dec);
  return value >= 0 ? `+${s}` : `−${s}`;
}

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k === "text") node.textContent = v;
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(child));
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

// columns: [{ key, label, fmt?: (v,row)=>string, cls?: string, align?: 'r'|'l' }]
export function table(columns, rows) {
  const thead = el("thead", {}, [
    el(
      "tr",
      {},
      columns.map((c) =>
        el("th", { class: c.align === "r" ? "num" : "" }, c.label),
      ),
    ),
  ]);
  const tbody = el(
    "tbody",
    {},
    rows.map((row) =>
      el(
        "tr",
        {},
        columns.map((c) => {
          const raw = row[c.key];
          const txt = c.fmt ? c.fmt(raw, row) : raw ?? "—";
          return el(
            "td",
            { class: [c.align === "r" ? "num" : "", c.cls || ""].join(" ").trim() },
            txt,
          );
        }),
      ),
    ),
  );
  return el("div", { class: "table-wrap" }, [el("table", {}, [thead, tbody])]);
}

export function pill(text, kind = "") {
  return el("span", { class: `pill ${kind}`.trim(), text }) ;
}
