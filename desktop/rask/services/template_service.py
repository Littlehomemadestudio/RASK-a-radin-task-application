"""
rask.services.template_service
==============================

Quick-log templates.

A template is a pre-filled activity recipe: title, category, duration,
tags, notes, etc.  Templates let the user log common activities with
a single tap.  Each template tracks a ``use_count`` so the UI can show
the most-used ones first.

This service wraps the :mod:`rask.database` template repository with:
  • Input validation (title, tags)
  • Shortcut-key lookup (for keyboard quick-log)
  • ``use(id)`` -> creates an activity via :mod:`activity_service`
  • Archive / unarchive support
  • Reorder via the ``order_index`` column
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .. import database as db
from .. import config
from ..core.event_bus import bus
from ..core.logging_utils import get_logger, log_exception
from ..core.time_utils import now_iso_utc, today_iso
from ..core.validators import (
    is_valid_duration_min,
    sanitize_notes,
    sanitize_tags,
    sanitize_title,
)

__all__ = ["TemplateService", "template_service"]

_log = get_logger("services.template")


# =============================================================================
# === Helpers                                                                 ===
# =============================================================================

def _row_to_template(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Normalize a raw DB template row into a clean dict."""
    if row is None:
        return None
    out = dict(row)
    raw = out.pop("tags_json", None)
    if isinstance(raw, str) and raw:
        try:
            out["tags"] = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            out["tags"] = []
    elif isinstance(raw, list):
        out["tags"] = list(raw)
    else:
        out["tags"] = []
    if "archived" in out:
        out["archived"] = bool(out["archived"])
    for k in ("id", "category_id", "duration_min", "use_count", "order_index"):
        if out.get(k) is not None:
            try:
                out[k] = int(out[k])
            except (TypeError, ValueError):
                pass
    return out


def _rows_to_templates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        t = _row_to_template(r)
        if t is not None:
            out.append(t)
    return out


# =============================================================================
# === TemplateService                                                        ===
# =============================================================================

class TemplateService:
    """CRUD + use() for quick-log templates."""

    def __init__(self) -> None:
        # Simple shortcut->template_id cache.  Refreshed on every list().
        self._shortcut_cache: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Pre-populate the shortcut cache."""
        try:
            self._rebuild_shortcut_cache()
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
        _log.debug("TemplateService initialized (%d shortcuts)",
                    len(self._shortcut_cache))

    def _rebuild_shortcut_cache(self) -> None:
        """Rebuild the shortcut->id cache from the DB."""
        self._shortcut_cache.clear()
        for t in self.list(include_archived=True):
            sc = t.get("shortcut")
            if sc:
                self._shortcut_cache[sc] = t["id"]

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def add(
        self,
        name: str,
        title: str,
        category_id: Optional[int] = None,
        duration_min: Optional[int] = None,
        tags: Optional[List[str]] = None,
        notes: Optional[str] = None,
        shortcut: Optional[str] = None,
        icon: Optional[str] = None,
        color: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new template.

        Parameters
        ----------
        name : str
            Short display name (1..200 chars).
        title : str
            The activity title that will be used when the template is
            applied (1..200 chars).
        category_id : int, optional
            FK into ``categories``.
        duration_min : int, optional
            Default duration in minutes (0..1440).  ``None`` means
            "ask the user".
        tags : list[str], optional
            Up to 10 tags (sanitized).
        notes : str, optional
            Default notes (≤ 5000 chars).
        shortcut : str, optional
            Single-key shortcut (e.g. ``"1"``, ``"f"``).
        icon : str, optional
            Icon name (e.g. ``"ring"``, ``"book"``).
        color : str, optional
            Hex color for UI display.

        Returns the newly-created template dict.
        """
        clean_name = sanitize_title(name)
        clean_title = sanitize_title(title)
        if not clean_name:
            raise ValueError("Template name must be non-empty")
        if not clean_title:
            raise ValueError("Template title must be non-empty")

        if duration_min is not None:
            if not is_valid_duration_min(duration_min):
                duration_min = max(0, min(1440, int(duration_min or 0)))

        clean_tags = sanitize_tags(tags)
        clean_notes = sanitize_notes(notes) if notes else None
        clean_shortcut = (shortcut.strip()[:5] if shortcut else None)

        # Determine order_index (place at the end).
        existing = self.list(include_archived=True)
        order_index = len(existing)

        try:
            new_id = db.template_add(
                name=clean_name,
                title=clean_title,
                category_id=category_id,
                duration_min=duration_min,
                tags=clean_tags,
                notes=clean_notes,
                shortcut=clean_shortcut,
                icon=icon,
                color=color,
                order_index=order_index,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"name": clean_name})
            raise

        template = self.get(new_id)
        if template is None:
            template = {"id": new_id, "name": clean_name,
                        "title": clean_title}
        if clean_shortcut:
            self._shortcut_cache[clean_shortcut] = new_id
        bus.publish("template.added", template)
        _log.info("Template added: id=%s name=%r", new_id, clean_name)
        return template

    # ------------------------------------------------------------------
    # Update / delete
    # ------------------------------------------------------------------

    def update(self, id: int, **fields: Any) -> Dict[str, Any]:
        """Update template fields.  Returns the updated template dict."""
        if not isinstance(id, int) or id <= 0:
            raise ValueError(f"Invalid template id: {id!r}")
        existing = self.get(id)
        if existing is None:
            raise KeyError(f"Template {id} not found")

        updates: Dict[str, Any] = {}
        if "name" in fields:
            n = sanitize_title(fields["name"])
            if not n:
                raise ValueError("name must be non-empty")
            updates["name"] = n
        if "title" in fields:
            t = sanitize_title(fields["title"])
            if not t:
                raise ValueError("title must be non-empty")
            updates["title"] = t
        if "category_id" in fields:
            cid = fields["category_id"]
            if cid is None or (isinstance(cid, int) and cid > 0):
                updates["category_id"] = cid
        if "duration_min" in fields:
            d = fields["duration_min"]
            if d is None or is_valid_duration_min(d):
                updates["duration_min"] = d
        if "tags" in fields:
            updates["tags"] = sanitize_tags(fields["tags"])
        if "notes" in fields:
            updates["notes"] = sanitize_notes(fields["notes"]) \
                if fields["notes"] else None
        if "shortcut" in fields:
            sc = fields["shortcut"]
            updates["shortcut"] = sc.strip()[:5] if sc else None
        if "icon" in fields:
            updates["icon"] = fields["icon"]
        if "color" in fields:
            updates["color"] = fields["color"]
        if "archived" in fields:
            updates["archived"] = bool(fields["archived"])
        if "order_index" in fields:
            try:
                updates["order_index"] = int(fields["order_index"])
            except (TypeError, ValueError):
                pass

        if not updates:
            return existing

        try:
            db.template_update(id, **updates)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id, "updates": updates})
            raise

        updated = self.get(id) or existing
        self._rebuild_shortcut_cache()
        bus.publish("template.updated", updated)
        _log.info("Template updated: id=%s fields=%s", id, list(updates.keys()))
        return updated

    def delete(self, id: int) -> bool:
        """Delete a template permanently."""
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.template_delete(id)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            self._rebuild_shortcut_cache()
            bus.publish("template.deleted", {"id": id})
            _log.info("Template deleted: id=%s", id)
        return ok

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, id: int) -> Optional[Dict[str, Any]]:
        if not isinstance(id, int) or id <= 0:
            return None
        try:
            return _row_to_template(db.template_get(id))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return None

    def list(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        """Return all templates.

        Sorted by ``use_count DESC, order_index ASC`` so the most-used
        templates appear first.
        """
        try:
            return _rows_to_templates(
                db.template_list(include_archived=include_archived))
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {})
            return []

    def top_used(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Return the N most-used non-archived templates."""
        if limit <= 0:
            return []
        all_tpl = self.list(include_archived=False)
        all_tpl.sort(key=lambda t: int(t.get("use_count", 0)), reverse=True)
        return all_tpl[:limit]

    def by_shortcut(self, key: str) -> Optional[Dict[str, Any]]:
        """Return the template bound to `key`, or ``None``.

        `key` is the raw shortcut string (e.g. ``"1"``, ``"f"``).
        Case-sensitive.
        """
        if not key:
            return None
        # Try cache first.
        tid = self._shortcut_cache.get(key)
        if tid:
            tpl = self.get(tid)
            if tpl and not tpl.get("archived"):
                return tpl
            # Stale cache entry — rebuild.
            self._rebuild_shortcut_cache()
        # Fallback: scan DB.
        for tpl in self.list(include_archived=False):
            if tpl.get("shortcut") == key:
                return tpl
        return None

    # ------------------------------------------------------------------
    # Use (apply template -> activity)
    # ------------------------------------------------------------------

    def use(self, id: int) -> Dict[str, Any]:
        """Apply a template: create a new activity with its defaults.

        Increments the template's ``use_count`` and updates
        ``last_used_iso``.  Returns the newly-created activity dict.

        Raises ``KeyError`` if the template doesn't exist.
        """
        tpl = self.get(id)
        if tpl is None:
            raise KeyError(f"Template {id} not found")
        if tpl.get("archived"):
            raise ValueError(f"Template {id} is archived")

        # Lazy import to avoid circular dependency.
        from .activity_service import activity_service

        try:
            activity = activity_service.add(
                title=tpl.get("title", ""),
                category_id=tpl.get("category_id"),
                duration_min=int(tpl.get("duration_min") or 0),
                date_iso=today_iso(),
                notes=tpl.get("notes"),
                tags=tpl.get("tags", []),
                kind="template",
                template_id=id,
            )
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"template_id": id})
            raise

        # Increment use count + update last_used_iso.  The DB layer's
        # activity_add already does this if template_id is set, but
        # we double-check defensively.
        try:
            now = now_iso_utc()
            db.template_update(id, last_used_iso=now)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"template_id": id})

        bus.publish("template.used", {
            "template_id": id,
            "activity_id": activity.get("id"),
            "template_name": tpl.get("name"),
        })
        _log.info("Template used: id=%s -> activity %s",
                  id, activity.get("id"))
        return activity

    # ------------------------------------------------------------------
    # Archive / unarchive
    # ------------------------------------------------------------------

    def archive(self, id: int) -> bool:
        """Archive a template (hide from default list)."""
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.template_update(id, archived=1)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            self._rebuild_shortcut_cache()
            bus.publish("template.archived", {"id": id})
        return ok

    def unarchive(self, id: int) -> bool:
        """Restore an archived template."""
        if not isinstance(id, int) or id <= 0:
            return False
        try:
            ok = db.template_update(id, archived=0)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"id": id})
            return False
        if ok:
            self._rebuild_shortcut_cache()
            bus.publish("template.unarchived", {"id": id})
        return ok

    # ------------------------------------------------------------------
    # Reorder
    # ------------------------------------------------------------------

    def reorder(self, ids: List[int]) -> bool:
        """Reassign ``order_index`` for each template id, in order.

        Returns ``True`` if all ids exist and were updated.
        """
        if not ids or not isinstance(ids, list):
            return False
        try:
            for i, tid in enumerate(ids):
                if not isinstance(tid, int):
                    return False
                db.template_update(tid, order_index=i)
        except Exception as exc:  # noqa: BLE001
            log_exception(_log, exc, {"ids": ids})
            return False
        bus.publish("template.reordered", {"order": list(ids)})
        return True


# =============================================================================
# === Module-level singleton                                                 ===
# =============================================================================

template_service: TemplateService = TemplateService()
