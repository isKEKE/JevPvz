/* Verify 阶段量测：在真实页面上取 V15/V16/V6 需要的 DOM 证据。 */
(function () {
  const box = (sel) => { const n = document.querySelector(sel); return n ? n.getBoundingClientRect() : null; };
  const out = { doc: { w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight },
    viewport: { w: innerWidth, h: innerHeight } };
  const threatRows = [...document.querySelectorAll(".threat-row")];
  out.threats = { n: threatRows.length,
    rows: new Set(threatRows.map((n) => Math.round(n.getBoundingClientRect().y))).size,
    overflowPx: (() => { const t = box(".rt-target"), w = box(".rt-world");
      return t && w ? Math.round(t.bottom - w.bottom) : null; })(),
    rowsScroll: (() => { const r = document.querySelector(".threat-rows");
      return r ? { client: Math.round(r.clientHeight), scroll: Math.round(r.scrollHeight),
        scrollable: r.scrollHeight > r.clientHeight + 1 } : null; })(),
    nowrap: threatRows.every((n) => getComputedStyle(n).whiteSpace === "nowrap") };
  const inv = [...document.querySelectorAll(".inv-item")];
  out.inventory = { n: inv.length,
    rows: new Set(inv.map((n) => Math.round(n.getBoundingClientRect().y))).size,
    overflowPx: (() => { const s = box("#inv-list"), w = box(".rt-world");
      return s && w ? Math.round(s.right - w.right) : null; })(),
    abbrs: inv.map((n) => n.querySelector(".inv-abbr").textContent) };
  const cc = document.querySelector(".cell-corners");
  out.reticle = cc ? { present: true, border: getComputedStyle(cc).borderTopColor,
    width: getComputedStyle(cc).borderTopWidth } : { present: false };
  const zc = getComputedStyle(document.querySelector(".cell-zombie-mark") || document.body);
  out.zombieMark = { background: zc.backgroundColor, size: zc.width + "x" + zc.height };
  out.lawn = { zombies: [...document.querySelectorAll("#lawn .cell-zombie-label")].map((n) => n.textContent) };
  const gv = box("#game-viewport");
  out.gameViewport = gv ? [Math.round(gv.width), Math.round(gv.height)] : null;
  out.nav = [...document.querySelectorAll(".page-nav a")].map((a) => a.getAttribute("href"));
  return JSON.stringify(out, null, 1);
})();
