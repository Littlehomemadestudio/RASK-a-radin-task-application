// export-csv.js — CSV export of activities.
window.RaskCSV = (function () {
  function escape(s) {
    if (s == null) return "";
    s = String(s);
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  }
  async function exportRange(startISO, endISO) {
    const acts = startISO && endISO
      ? await window.RaskDB.activitiesByDateRange(startISO, endISO)
      : await window.RaskDB.allActivities();
    const rows = [[
      "id","title","category_id","kind","date","start","end",
      "duration_sec","duration_hhmm","note","voice_input","created_at"
    ]];
    for (const a of acts) {
      const h = Math.floor(a.duration_sec / 3600);
      const m = Math.floor((a.duration_sec % 3600) / 60);
      rows.push([
        a.id, a.title, a.category_id || "", a.kind, a.date_iso,
        a.start_iso || "", a.end_iso || "",
        a.duration_sec, `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}`,
        a.note || "", a.voice_input ? 1 : 0, a.created_at || "",
      ].map(escape).join(","));
    }
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const fname = startISO
      ? `rask_export_${startISO}_to_${endISO}.csv`
      : `rask_export_all.csv`;
    const a = document.createElement("a");
    a.href = url;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return acts.length;
  }
  return { exportRange };
})();
