"""
notifications.py — Android notifications via pyjnius.

Creates notification channels and posts:
  - The persistent foreground timer notification (with Pause/Stop actions).
  - Goal reminder notifications (scheduled by ReminderWorker).
  - General info notifications.

On desktop this is a no-op that silently logs.
"""
from __future__ import annotations

from typing import Optional


def _on_android() -> bool:
    try:
        import jnius  # noqa
        return True
    except ImportError:
        return False


def ensure_channels() -> None:
    if not _on_android():
        return
    try:
        from jnius import autoclass  # type: ignore
        Context = autoclass("org.kivy.android.PythonActivity")
        NotificationManager = autoclass("android.app.NotificationManager")
        NotificationChannel = autoclass("android.app.NotificationChannel")
        Importance = autoclass("android.app.NotificationManager$Importance")

        ctx = Context.mActivity.getApplicationContext()
        mgr = ctx.getSystemService(ctx.NOTIFICATION_SERVICE)

        channels = [
            ("rask_timer", "Rask Timer", "Live stopwatch", Importance.HIGH),
            ("rask_reminders", "Rask Reminders", "Goal reminders", Importance.DEFAULT),
            ("rask_general", "Rask", "General", Importance.LOW),
        ]
        for cid, name, desc, imp in channels:
            ch = NotificationChannel(cid, name, imp)
            ch.setDescription(desc)
            mgr.createNotificationChannel(ch)
    except Exception as e:
        print(f"[notifications] ensure_channels: {e}")


def show_reminder(text_en: str, text_fa: str, lang: str = "fa") -> None:
    if not _on_android():
        print(f"[reminder] {text_fa if lang == 'fa' else text_en}")
        return
    try:
        from jnius import autoclass  # type: ignore
        Context = autoclass("org.kivy.android.PythonActivity")
        NotificationCompat = autoclass("androidx.core.app.NotificationCompat")
        PendingIntent = autoclass("android.app.PendingIntent")
        Intent = autoclass("android.content.Intent")

        ctx = Context.mActivity.getApplicationContext()
        intent = Intent(ctx, Context.mActivity.getClass())
        pi = PendingIntent.getActivity(ctx, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE)

        b = NotificationCompat.Builder(ctx, "rask_reminders")
        b.setSmallIcon(ctx.getApplicationInfo().icon)
        b.setContentTitle("Rask")
        b.setContentText(text_fa if lang == "fa" else text_en)
        b.setContentIntent(pi)
        b.setAutoCancel(True)

        NotificationManagerCompat = autoclass("androidx.core.app.NotificationManagerCompat")
        # `from` is a Python keyword — use getattr
        getattr(NotificationManagerCompat, "from")(ctx).notify(2001, b.build())
    except Exception as e:
        print(f"[notifications] show_reminder: {e}")


def update_timer_notification(elapsed_sec: int, running: bool,
                              title: str = "") -> None:
    """Update the live timer notification. Called by TimerService (Java side)
    or by our Python ticker."""
    if not _on_android():
        return
    try:
        from jnius import autoclass  # type: ignore
        Context = autoclass("org.kivy.android.PythonActivity")
        NotificationCompat = autoclass("androidx.core.app.NotificationCompat")
        ctx = Context.mActivity.getApplicationContext()

        h, rem = divmod(elapsed_sec, 3600)
        m, s = divmod(rem, 60)
        text = f"{h:02d}:{m:02d}:{s:02d} — {title or 'Recording'}"
        if not running:
            text = f"Paused — {text}"

        b = NotificationCompat.Builder(ctx, "rask_timer")
        b.setSmallIcon(ctx.getApplicationInfo().icon)
        b.setContentTitle("Rask Timer")
        b.setContentText(text)
        b.setOngoing(running)
        b.setSilent(True)
        # TODO: add Pause/Stop actions via PendingIntent
        NotificationManagerCompat = autoclass("androidx.core.app.NotificationManagerCompat")
        getattr(NotificationManagerCompat, "from")(ctx).notify(1001, b.build())
    except Exception as e:
        print(f"[notifications] update_timer: {e}")
