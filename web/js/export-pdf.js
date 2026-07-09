// export-pdf.js — PDF report generation via jsPDF (loaded from CDN, cached by SW).
window.RaskPDF = (function () {
  function ensureJsPDF() {
    return new Promise((resolve, reject) => {
      if (window.jspdf && window.jspdf.jsPDF) return resolve(window.jspdf.jsPDF);
      const s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js";
      s.onload = () => {
        if (window.jspdf && window.jspdf.jsPDF) resolve(window.jspdf.jsPDF);
        else reject(new Error("jsPDF failed to load"));
      };
      s.onerror = () => reject(new Error("jsPDF failed to load"));
      document.head.appendChild(s);
    });
  }

  async function exportReport(startISO, endISO, lang) {
    const jsPDF = await ensureJsPDF();
    const { jsPDF: JsPDF } = window.jspdf;
    const doc = new JsPDF({ unit: "pt", format: "a4" });
    const W = doc.internal.pageSize.getWidth();
    const H = doc.internal.pageSize.getHeight();
    const M = 40;
    let y = M;

    // Title
    doc.setFont("helvetica", "bold");
    doc.setFontSize(24);
    doc.setTextColor(212, 175, 55);
    doc.text("Rask — Time Report", M, y);
    y += 30;
    doc.setFont("helvetica", "normal");
    doc.setFontSize(11);
    doc.setTextColor(80, 80, 80);
    doc.text(`Period: ${startISO} -> ${endISO}`, M, y);
    y += 24;

    const acts = await window.RaskDB.activitiesByDateRange(startISO, endISO);
    const total = acts.reduce((s, a) => s + (a.duration_sec || 0), 0);

    doc.setFont("helvetica", "bold");
    doc.setFontSize(14);
    doc.setTextColor(20, 20, 20);
    doc.text(`Total: ${window.DateUtils.fmtHuman(total, lang)}`, M, y);
    y += 26;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    doc.setTextColor(40, 40, 40);

    const cats = await window.RaskDB.allCategories();
    const catMap = {};
    cats.forEach((c) => { catMap[c.id] = c; });

    for (const a of acts) {
      if (y > H - M) { doc.addPage(); y = M; }
      const cat = a.category_id ? catMap[a.category_id] : null;
      const catName = cat ? (lang === "fa" ? cat.name_fa : cat.name_en) : "—";
      const line = `${a.date_iso}  ${(a.title || "(no title)").slice(0, 40).padEnd(40)}  ${catName.slice(0, 12).padEnd(12)}  ${window.DateUtils.fmtHuman(a.duration_sec, lang)}`;
      doc.text(line, M, y);
      y += 14;
    }

    // Footer
    doc.addPage();
    y = M;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(16);
    doc.setTextColor(212, 175, 55);
    doc.text("Summary", M, y); y += 24;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(11);
    doc.setTextColor(40, 40, 40);
    doc.text(`Activities: ${acts.length}`, M, y); y += 16;
    doc.text(`Total time: ${window.DateUtils.fmtHuman(total, lang)}`, M, y); y += 16;
    // Per-category breakdown
    const perCat = {};
    acts.forEach((a) => {
      const cid = a.category_id || 0;
      perCat[cid] = (perCat[cid] || 0) + (a.duration_sec || 0);
    });
    doc.text("By category:", M, y); y += 16;
    Object.entries(perCat).sort((a,b) => b[1] - a[1]).forEach(([cid, sec]) => {
      const c = catMap[parseInt(cid, 10)];
      const name = c ? (lang === "fa" ? c.name_fa : c.name_en) : "—";
      doc.text(`  ${name}: ${window.DateUtils.fmtHuman(sec, lang)}`, M, y);
      y += 14;
    });

    doc.save(`rask_report_${startISO}_to_${endISO}.pdf`);
  }

  return { exportReport };
})();
