/* Small SVG chart helpers. No library, so the page has no build step. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const tip = () => document.getElementById("tip");

  function el(name, attrs, parent) {
    const n = document.createElementNS(NS, name);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function text(parent, x, y, str, attrs) {
    const t = el("text", Object.assign({ x, y }, attrs || {}), parent);
    t.textContent = str;
    return t;
  }
  function showTip(evt, html) {
    const t = tip();
    t.innerHTML = html;
    t.classList.add("on");
    const pad = 14, w = t.offsetWidth, h = t.offsetHeight;
    let x = evt.clientX + pad, y = evt.clientY + pad;
    if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
    if (y + h > window.innerHeight - 8) y = evt.clientY - h - pad;
    t.style.left = x + "px";
    t.style.top = y + "px";
  }
  function hideTip() { tip().classList.remove("on"); }
  function niceMax(v) {
    if (v <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    const m = v / p;
    return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10) * p;
  }
  function ticks(max, n) {
    const out = [];
    for (let i = 0; i <= n; i++) out.push((max / n) * i);
    return out;
  }
  function fmt(v) { return Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : (+v.toFixed(2)).toString(); }
  function svgFor(container, height) {
    container.innerHTML = "";
    const w = Math.max(container.clientWidth, 300);
    return { svg: el("svg", { viewBox: `0 0 ${w} ${height}`, role: "img" }, container), w };
  }

  /* Horizontal bars, one series. items: [{label, value, tipHtml}] */
  function hbars(container, items, opts) {
    const rowH = 26, top = 6, labelW = Math.min(300, container.clientWidth * 0.42);
    const h = top + items.length * rowH + 24;
    const { svg, w } = svgFor(container, h);
    svg.setAttribute("aria-label", opts.aria || "bar chart");
    const max = niceMax(Math.max(...items.map(d => d.value), 0.01));
    const x0 = labelW + 8, x1 = w - 48;
    const sx = v => x0 + (v / max) * (x1 - x0);
    ticks(max, 4).forEach(t => {
      el("line", { x1: sx(t), x2: sx(t), y1: top - 2, y2: h - 20, class: "grid" }, svg);
      text(svg, sx(t), h - 6, fmt(t), { "text-anchor": "middle" });
    });
    items.forEach((d, i) => {
      const y = top + i * rowH;
      const maxChars = Math.floor(labelW / 6.6);   // about 6.6px per character at 12px
      const name = d.label.length > maxChars ? d.label.slice(0, maxChars - 1).trimEnd() + "…" : d.label;
      text(svg, x0 - 8, y + 16, name, { "text-anchor": "end" });
      const bw = Math.max(sx(d.value) - x0, 1);
      // 4px rounded end, flat at the baseline
      const r = Math.min(4, bw);
      el("path", {
        d: `M${x0},${y + 5} h${bw - r} a${r},${r} 0 0 1 ${r},${r} v${16 - 2 * r} a${r},${r} 0 0 1 ${-r},${r} h${-(bw - r)} z`,
        fill: d.color || "var(--s1)"
      }, svg);
      text(svg, x0 + bw + 6, y + 17, fmt(d.value), { class: "val" });
      const hit = el("rect", { x: 0, y, width: w, height: rowH, fill: "transparent" }, svg);
      hit.addEventListener("mousemove", e => showTip(e, d.tipHtml || `${d.label}: ${fmt(d.value)}`));
      hit.addEventListener("mouseleave", hideTip);
    });
  }

  /* Lines over a shared x axis. series: [{name, color, dash, values: [y|null]}], xs: [labels]
     marks: optional [{i, label}] points to ring on the first series. */
  function lines(container, xs, series, opts) {
    const h = opts.height || 300, left = 44, right = opts.right || 120, top = 12, bottom = 28;
    const { svg, w } = svgFor(container, h);
    svg.setAttribute("aria-label", opts.aria || "line chart");
    const all = series.flatMap(s => s.values).filter(v => v != null);
    const max = niceMax(Math.max(...all, 0.01));
    const sx = i => left + (xs.length === 1 ? 0 : (i / (xs.length - 1)) * (w - left - right));
    const sy = v => top + (1 - v / max) * (h - top - bottom);
    ticks(max, 4).forEach(t => {
      el("line", { x1: left, x2: w - right, y1: sy(t), y2: sy(t), class: "grid" }, svg);
      text(svg, left - 6, sy(t) + 4, fmt(t), { "text-anchor": "end" });
    });
    const every = Math.ceil(xs.length / Math.max(2, Math.floor((w - left - right) / 56)));
    xs.forEach((x, i) => {
      const show = opts.showX ? opts.showX(i, w) : (i % every === 0 || i === xs.length - 1);
      if (show) text(svg, sx(i), h - 8, x, { "text-anchor": "middle" });
    });
    const labelYs = [];
    series.forEach(s => {
      let d = "", pen = false;
      s.values.forEach((v, i) => {
        if (v == null) { pen = false; return; }   // break the line at a gap
        d += (pen ? "L" : "M") + sx(i) + "," + sy(v);
        pen = true;
      });
      el("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-dasharray": s.dash || "none",
        "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
      // direct label at the last value
      let li = s.values.length - 1;
      while (li >= 0 && s.values[li] == null) li--;
      if (li >= 0 && opts.directLabels !== false) {
        let ly = sy(s.values[li]) + 4;
        labelYs.forEach(p => { if (Math.abs(p - ly) < 14) ly = p + (ly >= p ? 14 : -14); });
        labelYs.push(ly);
        text(svg, sx(li) + 8, ly, s.name, { style: "fill: var(--ink)" });
      }
    });
    (opts.marks || []).forEach(m => {
      const v = series[0].values[m.i];
      if (v == null) return;
      el("circle", { cx: sx(m.i), cy: sy(v), r: 5, fill: "var(--page)", stroke: "var(--ink)", "stroke-width": 2 }, svg);
    });
    // crosshair + tooltip
    const cross = el("line", { y1: top, y2: h - bottom, class: "axis", opacity: 0 }, svg);
    const hit = el("rect", { x: left, y: top, width: w - left - right, height: h - top - bottom, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", e => {
      const box = svg.getBoundingClientRect();
      const px = (e.clientX - box.left) * (w / box.width);
      const i = Math.max(0, Math.min(xs.length - 1, Math.round(((px - left) / (w - left - right)) * (xs.length - 1))));
      cross.setAttribute("x1", sx(i)); cross.setAttribute("x2", sx(i)); cross.setAttribute("opacity", 0.5);
      const rows = series.map(s => `${s.name}: ${s.values[i] == null ? "no value" : fmt(s.values[i])}`);
      showTip(e, `<strong>${xs[i]}</strong><br>${rows.join("<br>")}${opts.tipExtra ? opts.tipExtra(i) : ""}`);
    });
    hit.addEventListener("mouseleave", () => { cross.setAttribute("opacity", 0); hideTip(); });
  }

  /* Stacked columns. xs: labels, series: [{name, color, values: []}] */
  function stacked(container, xs, series, opts) {
    const h = opts.height || 320, left = 44, right = 8, top = 12, bottom = 28;
    const { svg, w } = svgFor(container, h);
    svg.setAttribute("aria-label", opts.aria || "stacked column chart");
    const totals = xs.map((_, i) => series.reduce((a, s) => a + (s.values[i] || 0), 0));
    const max = niceMax(Math.max(...totals, 0.01));
    const band = (w - left - right) / xs.length, bw = Math.max(6, band * 0.62);
    const sy = v => top + (1 - v / max) * (h - top - bottom);
    ticks(max, 4).forEach(t => {
      el("line", { x1: left, x2: w - right, y1: sy(t), y2: sy(t), class: "grid" }, svg);
      text(svg, left - 6, sy(t) + 4, fmt(t), { "text-anchor": "end" });
    });
    const every = Math.ceil(xs.length / Math.max(2, Math.floor((w - left) / 44)));
    xs.forEach((x, i) => {
      const cx = left + band * i + band / 2;
      if (i % every === 0 || i === xs.length - 1) text(svg, cx, h - 8, x, { "text-anchor": "middle" });
      let acc = 0;
      series.forEach((s, k) => {
        const v = s.values[i] || 0;
        if (v <= 0) return;
        const y1 = sy(acc + v), y0 = sy(acc);
        const gap = acc > 0 ? 2 : 0;   // 2px surface gap between segments
        const isTop = series.slice(k + 1).every(o => !(o.values[i] > 0));
        const hh = Math.max(y0 - y1 - gap, 0.5), r = isTop ? Math.min(4, hh) : 0;
        el("path", {
          d: `M${cx - bw / 2},${y1 + hh} v${-(hh - r)} a${r},${r} 0 0 1 ${r},${-r} h${bw - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${hh - r} z`,
          fill: s.color
        }, svg);
        acc += v;
      });
      const hit = el("rect", { x: left + band * i, y: top, width: band, height: h - top - bottom, fill: "transparent" }, svg);
      hit.addEventListener("mousemove", e => showTip(e, `<strong>${x}</strong>${opts.tipNote ? opts.tipNote(i) : ""}<br>` +
        series.map(s => `${s.name}: ${fmt(s.values[i] || 0)}`).reverse().join("<br>") + `<br>Total: ${fmt(totals[i])}`));
      hit.addEventListener("mouseleave", hideTip);
    });
  }

  function legend(container, series) {
    container.innerHTML = series.map(s =>
      `<span><i style="background:${s.color}${s.dash ? ";height:3px;border-radius:0" : ""}"></i>${s.name}</span>`).join("");
  }

  function table(container, head, rows, numeric) {
    const th = head.map((h, i) => `<th${numeric && numeric[i] ? ' class="n"' : ""}>${h}</th>`).join("");
    const tr = rows.map(r => "<tr>" + r.map((c, i) => `<td${numeric && numeric[i] ? ' class="n"' : ""}>${c}</td>`).join("") + "</tr>").join("");
    container.innerHTML = `<table><thead><tr>${th}</tr></thead><tbody>${tr}</tbody></table>`;
  }

  window.Charts = { hbars, lines, stacked, legend, table, fmt };
})();
