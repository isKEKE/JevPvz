/* V17 / R12：窄屏布局量测。 */
(function () {
  const vw = innerWidth;
  const els = [...document.querySelectorAll("body *")].filter((n) => {
    const r = n.getBoundingClientRect();
    return r.width > 0 && r.right > vw + 1;
  });
  const roots = els.filter((n) => !(n.parentElement && els.includes(n.parentElement)));
  const label = (n) => n.tagName.toLowerCase() + (n.id ? "#" + n.id : "")
    + (typeof n.className === "string" && n.className ? "." + n.className.trim().split(/\s+/).join(".") : "");
  // .stage-label 与节点场是否重叠
  const labels = [...document.querySelectorAll(".stage-label")].map((n) => n.getBoundingClientRect());
  const fields = [...document.querySelectorAll(".rt-field-grid, .stage-body")].map((n) => n.getBoundingClientRect());
  const overlap = (a, b) => !(a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom);
  let labelOverlaps = 0;
  for (const l of labels) for (const f of fields) if (overlap(l, f)) labelOverlaps += 1;
  // 决策链四段是否互相叠压
  const stages = [...document.querySelectorAll(".rt-stage")].map((n) => n.getBoundingClientRect());
  let stageOverlaps = 0;
  for (let i = 0; i < stages.length; i += 1)
    for (let j = i + 1; j < stages.length; j += 1) if (overlap(stages[i], stages[j])) stageOverlaps += 1;
  // 页头是否还有逐字换行（同一文本节点占多行）
  const brandH = document.querySelector(".rt-brand-name")?.getBoundingClientRect().height || 0;
  return JSON.stringify({
    vw, docW: document.documentElement.scrollWidth, docH: document.documentElement.scrollHeight,
    hOverflow: document.documentElement.scrollWidth > vw + 1,
    overflowRoots: roots.map((n) => ({ sel: label(n), w: Math.round(n.getBoundingClientRect().width) })),
    labelOverlaps, stageOverlaps, brandHeight: Math.round(brandH),
  });
})();
