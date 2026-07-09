"""
csv_export.py — Generate a CSV report of activities.

Pure stdlib csv module — works on both desktop and Android.
"""
from __future__ import annotations

import csv
from pathlib import Path

from rask.data import repositories as repos


def export_csv(path: Path, start_iso: str | None = None,
               end_iso: str | None = None) -> int:
    """Export activities to CSV. Returns number of rows written."""
    if start_iso and end_iso:
        acts = repos.ActivityRepository.by_date_range(start_iso, end_iso)
    else:
        acts = repos.ActivityRepository.all_for_export()

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "id", "title", "category_id", "kind", "date", "start", "end",
            "duration_sec", "duration_hhmm", "note", "voice_input", "created_at",
        ])
        for a in acts:
            hh, rem = divmod(a.duration_sec, 3600)
            mm, _ = divmod(rem, 60)
            w.writerow([
                a.id, a.title, a.category_id or "", a.kind, a.date_iso,
                a.start_iso or "", a.end_iso or "",
                a.duration_sec, f"{hh:02d}:{mm:02d}",
                a.note, int(a.voice_input), a.created_at,
            ])
    return len(acts)
