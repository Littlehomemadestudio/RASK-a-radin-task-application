package com.rask;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.content.Intent;
import android.widget.RemoteViews;

/**
 * Home-screen widget showing today's total tracked time + a quick-log button.
 *
 * The widget is a simple TextView + Button (RemoteViews) — we update it via
 * a Python-triggered AppWidgetManager.updateAppWidget() call whenever a new
 * activity is saved.
 */
public class RaskWidgetProvider extends AppWidgetProvider {

    @Override
    public void onUpdate(Context ctx, AppWidgetManager mgr, int[] ids) {
        for (int id : ids) {
            RemoteViews views = new RemoteViews(ctx.getPackageName(),
                R.id.widget_root != 0 ? R.id.widget_root
                                      : ctx.getResources().getIdentifier(
                                          "widget_rask", "layout",
                                          ctx.getPackageName()));

            views.setTextViewText(
                ctx.getResources().getIdentifier("widget_total", "id",
                                                  ctx.getPackageName()),
                "Rask — 0m");

            // Quick-log button
            Intent intent = new Intent(ctx, RaskWidgetProvider.class)
                .setAction("com.rask.WIDGET_QUICK_LOG");
            PendingIntent pi = PendingIntent.getBroadcast(ctx, 0, intent,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            int btnId = ctx.getResources().getIdentifier("widget_fab", "id",
                                                          ctx.getPackageName());
            if (btnId != 0) {
                views.setOnClickPendingIntent(btnId, pi);
            }
            mgr.updateAppWidget(id, views);
        }
    }

    @Override
    public void onReceive(Context ctx, Intent intent) {
        super.onReceive(ctx, intent);
        if ("com.rask.WIDGET_QUICK_LOG".equals(intent.getAction())) {
            // Launch the app with a quick-log flag
            Intent launch = ctx.getPackageManager()
                .getLaunchIntentForPackage(ctx.getPackageName());
            if (launch != null) {
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                launch.putExtra("quick_log", true);
                ctx.startActivity(launch);
            }
        }
    }
}
