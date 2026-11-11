/* Loads the clean CSVs and draws the page. */
(async function () {
  const C = window.Charts;
  const theme = new URLSearchParams(location.search).get("theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;

  function parseCSV(textIn) {
    const rows = [];
    let row = [], cell = "", q = false;
    for (let i = 0; i < textIn.length; i++) {
      const ch = textIn[i];
      if (q) {
        if (ch === '"' && textIn[i + 1] === '"') { cell += '"'; i++; }
        else if (ch === '"') q = false;
        else cell += ch;
      } else if (ch === '"') q = true;
      else if (ch === ",") { row.push(cell); cell = ""; }
      else if (ch === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
      else if (ch !== "\r") cell += ch;
    }
    if (cell || row.length) { row.push(cell); rows.push(row); }
    const head = rows.shift();
    return rows.filter(r => r.length === head.length).map(r => {
      const o = {};
      head.forEach((h, i) => {
        const v = r[i];
        o[h] = v === "true" ? true : v === "false" ? false : v !== "" && !isNaN(v) && h !== "file_month" && h !== "agency_code" ? +v : v;
      });
      return o;
    });
  }
  const load = name => fetch(`data/${name}.csv`).then(r => {
    if (!r.ok) throw new Error(name);
    return r.text();
  }).then(parseCSV);

  const [agencyYear, occYear, bench, reasons, months, gaps] = await Promise.all(
    ["agency_year", "occupation_year", "benchmark_year", "reason_year", "agency_month", "coverage_gaps"].map(load));

  // OPM cuts agency names at 40 characters. Full names for the ones that get cut.
  const FULL = {
    "DEPARTMENT OF HOUSING AND URBAN DEVELOPM": "Department of Housing and Urban Development",
    "NAT AERONAUTICS AND SPACE ADMINISTRATION": "National Aeronautics and Space Administration",
    "NAT ARCHIVES AND RECORDS ADMINISTRATION": "National Archives and Records Administration",
    "U.S. AGENCY FOR INTERNATIONAL DEV": "U.S. Agency for International Development",
    "U.S.AGENCY FOR GLOBAL MEDIA": "U.S. Agency for Global Media",
  };
  const title = s => FULL[s] || s.toLowerCase().replace(/\b\w/g, c => c.toUpperCase())
    .replace(/\b(Of|And|For|The|On)\b/g, w => w.toLowerCase()).replace(/^./, c => c.toUpperCase())
    .replace(/\bU\.s\./i, "U.S.");
  const fyLabel = fy => `FY${fy}`;
  const monthLabel = ym => `${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+ym.slice(4) - 1]} ${ym.slice(0, 4)}`;
  const years = [...new Set(agencyYear.map(r => r.fiscal_year))].sort();
  const lastFull = Math.max(...agencyYear.filter(r => !r.provisional).map(r => r.fiscal_year));
  const lastMonth = months.reduce((m, r) => r.file_month > m ? r.file_month : m, "");

  document.getElementById("meta").textContent =
    `Data through ${monthLabel(lastMonth)}. FY${lastFull + 1} is provisional: late records for it are still arriving.`;

  /* 0. Headline numbers, computed from the CSVs */
  const benchRate = (fy, series) => (bench.find(b => b.fiscal_year === fy && b.series === series) || {}).quit_rate;
  const lastDrp = Math.max(...bench.filter(b => b.series.includes("without DRP") && !b.provisional).map(b => b.fiscal_year));
  document.getElementById("kpiGaps").textContent = gaps.length;
  document.getElementById("kpiCore").textContent = C.fmt(benchRate(lastFull, "Federal civilian (OPM), permanent non-seasonal staff"));
  document.getElementById("kpiCoreL").textContent = `quits per 100 permanent staff, FY${lastFull}`;
  document.getElementById("kpiAll").textContent = C.fmt(benchRate(lastFull, "Federal civilian (OPM, covered agencies)"));
  document.getElementById("kpiAllL").textContent = `quits per 100, all staff, FY${lastFull}`;
  document.getElementById("kpiDrp").textContent = C.fmt(benchRate(lastDrp, "Federal civilian (OPM), quits without DRP"));
  document.getElementById("kpiDrpL").textContent = `quits per 100, all staff, without DRP-flagged quits, FY${lastDrp}`;

  /* 1. Monthly reports per agency */
  const agencySel = document.getElementById("agencySel");
  const byAgency = {};
  months.forEach(r => (byAgency[r.agency_code] = byAgency[r.agency_code] || { name: title(r.agency), rows: [] }).rows.push(r));
  const agencyCodes = Object.keys(byAgency).sort((a, b) => byAgency[a].name.localeCompare(byAgency[b].name));
  agencySel.innerHTML = agencyCodes.map(c => `<option value="${c}">${byAgency[c].name}</option>`).join("");
  agencySel.value = byAgency.AR ? "AR" : agencyCodes[0];

  function drawMonthly() {
    const a = byAgency[agencySel.value];
    const rows = a.rows.slice().sort((x, y) => x.file_month.localeCompare(y.file_month));
    const xs = rows.map(r => r.file_month.slice(0, 4));
    const marks = rows.map((r, i) => r.is_gap ? { i } : null).filter(Boolean);
    C.lines(document.getElementById("chartMonthly"), xs, [
      { name: "Reported", color: "var(--s1)", values: rows.map(r => r.separations) },
    ], {
      height: 260, right: 24, directLabels: false,
      // one label per January, every second year on narrow screens
      showX: (i, w) => rows[i].file_month.endsWith("01") && (w > 640 || +rows[i].file_month.slice(0, 4) % 2 === 0),
      aria: `Separations reported each month, ${a.name}`, marks,
      tipExtra: i => `<br>${monthLabel(rows[i].file_month)}${rows[i].is_gap ? "<br><strong>Fails the coverage check</strong>" : ""}`
    });
    const g = rows.filter(r => r.is_gap);
    document.getElementById("capMonthly").textContent = g.length
      ? `${a.name}: ${g.length} month${g.length > 1 ? "s" : ""} failed the check (ringed): ${g.map(r => `${monthLabel(r.file_month)} (${r.separations.toLocaleString("en-US")} reported against a usual ${Math.round(r.baseline).toLocaleString("en-US")})`).join(", ")}.`
      : `${a.name}: no month failed the check.`;
  }

  /* 2. Agency ranking */
  const fySel = document.getElementById("fySel");
  fySel.innerHTML = years.slice().reverse().map(y => `<option value="${y}">${fyLabel(y)}${y > lastFull ? " (provisional)" : ""}</option>`).join("");
  fySel.value = lastFull;
  const whoSel = document.getElementById("whoSel");
  const WHO = {
    core: { rate: r => r.core_quit_rate, note: "Permanent and conditional appointments on regular schedules only. Seasonal, intermittent and temporary staff are left out of both quits and headcount." },
    all: { rate: r => r.quit_rate, note: "All staff and all quits, including seasonal and temporary jobs and any quit flagged as part of the Deferred Resignation Program." },
    nodrp: { rate: r => r.quit_rate_excl_drp, note: "All staff, with quits flagged as part of the Deferred Resignation Program left out." },
  };

  function drawRank() {
    const fy = +fySel.value, who = WHO[whoSel.value];
    const rows = agencyYear.filter(r => r.fiscal_year === fy && r.avg_headcount >= 5000);
    const ranked = rows.filter(r => !r.incomplete && who.rate(r) !== "" && who.rate(r) != null)
      .map(r => ({ r, v: who.rate(r) }))
      .sort((a, b) => b.v - a.v);
    C.hbars(document.getElementById("chartRank"), ranked.map(({ r, v }) => ({
      label: title(r.agency), value: v,
      tipHtml: `<strong>${title(r.agency)}</strong><br>All quits: ${r.quits.toLocaleString("en-US")}${r.drp_quits ? ` (${r.drp_quits.toLocaleString("en-US")} DRP-flagged)` : ""}<br>Permanent, regular schedule: ${r.core_quits.toLocaleString("en-US")}<br>Average headcount ${r.avg_headcount.toLocaleString("en-US")}`
    })), { aria: `Quit rate by agency, ${fyLabel(fy)}` });
    document.getElementById("capRank").textContent =
      `${fyLabel(fy)}${fy > lastFull ? ", provisional" : ""}. Agencies with an average of at least 5,000 employees. ${who.note}`;
    const out = rows.filter(r => r.incomplete);
    document.getElementById("notRanked").innerHTML = out.length
      ? `<strong>Not ranked in ${fyLabel(fy)}:</strong> ${out.map(r => `${title(r.agency)} (${r.gap_months} month${r.gap_months > 1 ? "s" : ""} failed the coverage check)`).join(", ")}.`
      : "";
  }

  /* 3. Reasons */
  const SEG = [
    { name: "Quit", color: "var(--s1)" },
    { name: "Retirement or early out", color: "var(--s2)" },
    { name: "DRP-flagged exit", color: "var(--s3)" },
    { name: "Reduction in force", color: "var(--s4)" },
    { name: "Transfer, termination or other", color: "var(--s5)" },
  ];
  const rYears = [...new Set(reasons.map(r => r.fiscal_year))].sort();
  const rSeries = SEG.map(s => ({ ...s, values: rYears.map(y => (reasons.find(r => r.fiscal_year === y && r.segment === s.name) || { rate: 0 }).rate) }));
  C.legend(document.getElementById("legendReason"), rSeries);
  C.table(document.getElementById("tableReason"), ["Fiscal year", ...SEG.map(s => s.name)],
    rYears.map((y, i) => [fyLabel(y) + (y > lastFull ? " (provisional)" : ""), ...rSeries.map(s => C.fmt(s.values[i]))]),
    [false, true, true, true, true, true]);
  const drawReason = () => C.stacked(document.getElementById("chartReason"), rYears.map(y => String(y)), rSeries,
    { aria: "Separations per 100 employees by reason and fiscal year", tipNote: i => rYears[i] > lastFull ? " (provisional)" : "" });

  /* 4. Benchmark */
  const BENCH = [
    { key: "Federal civilian (OPM, covered agencies)", name: "Federal, OPM", color: "var(--s1)" },
    { key: "Federal (BLS)", name: "Federal, BLS", color: "var(--s2)" },
    { key: "Total nonfarm (BLS)", name: "All jobs, BLS", color: "var(--s3)" },
    { key: "Federal civilian (OPM), permanent non-seasonal staff", name: "Federal, OPM, permanent", color: "var(--s4)" },
  ];
  const bYears = [...new Set(bench.map(r => r.fiscal_year))].sort();
  const bSeries = BENCH.map(s => ({ ...s, values: bYears.map(y => { const r = bench.find(b => b.fiscal_year === y && b.series === s.key); return r ? r.quit_rate : null; }) }));
  C.legend(document.getElementById("legendBench"), bSeries);
  const noDrpRows = bench.filter(b => b.series.includes("without DRP"));
  C.table(document.getElementById("tableBench"), ["Fiscal year", ...BENCH.map(s => s.name), "Federal, OPM, without DRP quits"],
    bYears.map((y, i) => [fyLabel(y), ...bSeries.map(s => s.values[i] == null ? "" : C.fmt(s.values[i])),
      (noDrpRows.find(r => r.fiscal_year === y) || { quit_rate: "" }).quit_rate]),
    [false, true, true, true, true, true]);
  const drawBench = () => C.lines(document.getElementById("chartBench"), bYears.map(String), bSeries,
    { height: 300, right: 110, aria: "Yearly quit rate, federal and all jobs" });

  /* 5. Occupations */
  const fySelOcc = document.getElementById("fySelOcc");
  const oYears = [...new Set(occYear.map(r => r.fiscal_year))].sort();
  fySelOcc.innerHTML = oYears.slice().reverse().map(y => `<option value="${y}">${fyLabel(y)}${y > lastFull ? " (provisional)" : ""}</option>`).join("");
  fySelOcc.value = lastFull;
  function drawOcc() {
    const fy = +fySelOcc.value, who = WHO[document.getElementById("whoSelOcc").value];
    const val = who.rate;
    const rows = occYear.filter(r => r.fiscal_year === fy && r.avg_headcount >= 10000 && val(r) !== "" && val(r) != null).sort((a, b) => val(b) - val(a));
    document.getElementById("capOcc").textContent = `${fyLabel(fy)}${fy > lastFull ? ", provisional" : ""}. Groups with at least 10,000 employees, covered agencies only. ${who.note}`;
    C.hbars(document.getElementById("chartOcc"), rows.map(r => ({
      label: title(r.occupational_group.replace(/ (GROUP|FAMILY)$/, "")), value: val(r),
      tipHtml: `<strong>${title(r.occupational_group)}</strong><br>${r.quits.toLocaleString("en-US")} quits<br>Average headcount ${r.avg_headcount.toLocaleString("en-US")}`
    })), { aria: `Quit rate by occupational group, ${fyLabel(fy)}` });
  }

  /* 6. Gaps table, sortable by clicking a column header */
  const gapCols = [
    { head: "Agency", key: g => title(g.agency), show: g => title(g.agency) },
    { head: "File month", key: g => g.file_month, show: g => monthLabel(g.file_month) },
    { head: "Reported", key: g => g.separations, show: g => g.separations.toLocaleString("en-US"), n: true },
    { head: "Usual (median of previous 12 months)", key: g => g.baseline, show: g => Math.round(g.baseline).toLocaleString("en-US"), n: true },
  ];
  let gapSort = { i: 1, dir: -1 };
  function drawGaps() {
    const rows = gaps.slice().sort((a, b) => {
      const x = gapCols[gapSort.i].key(a), y = gapCols[gapSort.i].key(b);
      return (x < y ? -1 : x > y ? 1 : 0) * gapSort.dir;
    });
    C.table(document.getElementById("tableGaps"),
      gapCols.map((c, i) => c.head + (i === gapSort.i ? (gapSort.dir > 0 ? " ▲" : " ▼") : "")),
      rows.map(g => gapCols.map(c => c.show(g))), gapCols.map(c => !!c.n));
    document.querySelectorAll("#tableGaps th").forEach((th, i) => {
      th.classList.add("sortable");
      th.tabIndex = 0;
      th.setAttribute("aria-sort", i === gapSort.i ? (gapSort.dir > 0 ? "ascending" : "descending") : "none");
      const go = () => { gapSort = { i, dir: gapSort.i === i ? -gapSort.dir : -1 }; drawGaps(); };
      th.addEventListener("click", go);
      th.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
    });
  }
  drawGaps();

  function drawAll() { drawMonthly(); drawRank(); drawReason(); drawBench(); drawOcc(); }
  agencySel.addEventListener("change", drawMonthly);
  fySel.addEventListener("change", drawRank);
  whoSel.addEventListener("change", drawRank);
  fySelOcc.addEventListener("change", drawOcc);
  document.getElementById("whoSelOcc").addEventListener("change", drawOcc);
  let t;
  window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(drawAll, 150); });
  drawAll();
})().catch(err => {
  document.querySelector("main").insertAdjacentHTML("afterbegin",
    `<p class="aside">The data files did not load (${err.message}). Open this page through a local web server, for example <code>python -m http.server</code> in the dashboard folder.</p>`);
});
