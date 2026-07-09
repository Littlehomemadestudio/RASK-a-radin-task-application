"""
reminders.py — Goal reminders scheduled via WorkManager (Android).

On Android this uses AlarmManager (exact alarm) to fire goal reminders.
On desktop this is a no-op.

Scheduling strategy:
  - Daily goal reminder: 21:00 local time, only if goal not yet hit.
  - Streak reminder: 22:00 if streak currently active.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Optional

from rask import config as cfg
from rask.data import database as db
from rask.data import repositories as repos
from rask.utils import date_utils as du


def schedule_daily_reminder(hour: int = 21, minute: int = 0) -> None:
    try:
        from jnius import autoclass  # type: ignore
        Context = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        AlarmManager = autoclass("android.app.AlarmManager")

        ctx = Context.mActivity.getApplicationContext()
        am = ctx.getSystemService(ctx.ALARM_SERVICE)

        # Intent targeting our ReminderReceiver (defined in java-src)
        intent = Intent("com.rask.REMINDER_FIRE")
        intent.setPackage(ctx.getPackageName())
        pi = PendingIntent.getBroadcast(
            ctx, 2001, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        )

        now = datetime.now()
        fire = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if fire <= now:
            fire += timedelta(days=1)
        trigger_at_ms = int(fire.timestamp() * 1000)

        am.setExactAndAllowWhileIdle(
            AlarmManager.RTC_WAKEUP, trigger_at_ms, pi
        )
    except Exception as e:
        print(f"[reminders] schedule: {e}")


def maybe_fire_reminder() -> None:
    """Called when the alarm fires (via ReminderReceiver in java-src).
    Checks today's goal progress and posts a reminder if not yet hit."""
    from rask.services.notifications import show_reminder

    today = du.today_iso()
    goals = repos.GoalRepository.all()
    hit_all = True
    for g in goals:
        if g.period != cfg.PERIOD_DAILY:
            continue
        total = repos.ActivityRepository.total_seconds_on(
            today, g.category_id
        )
        if total < g.target_minutes * 60:
            hit_all = False
            break

    if not hit_all:
        show_reminder(
            "Don't forget your daily goal!",
            "هدف روزانه‌ات را فراموش نکن!",
            lang="fa",
        )


def cancel_all() -> None:
    try:
        from jnius import autoclass  # type: ignore
        Context = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        AlarmManager = autoclass("android.app.AlarmManager")

        ctx = Context.mActivity.getApplicationContext()
        am = ctx.getSystemService(ctx.ALARM_SERVICE)
        intent = Intent("com.rask.REMINDER_FIRE")
        intent.setPackage(ctx.getPackageName())
        pi = PendingIntent.getBroadcast(
            ctx, 2001, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        )
        am.cancel(pi)
    except Exception:
        pass
