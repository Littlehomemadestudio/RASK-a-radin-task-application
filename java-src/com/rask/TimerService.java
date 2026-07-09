package com.rask;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.IBinder;
import android.os.Handler;
import android.os.Looper;
import androidx.core.app.NotificationCompat;

/**
 * Foreground service that keeps the stopwatch alive while the app is
 * backgrounded. Also keeps the persistent timer notification up-to-date.
 *
 * The actual elapsed-time state lives in Python (kv_store); this service
 * just keeps the process alive and ticks the notification once per second.
 */
public class TimerService extends Service {
    public static final String CHANNEL_ID = "rask_timer";
    public static final int NOTIF_ID = 1001;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private String currentTitle = "Recording";
    private int elapsed = 0;

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            elapsed += 1;
            updateNotification();
            handler.postDelayed(this, 1000);
        }
    };

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null) {
            currentTitle = intent.getStringExtra("title");
            if (currentTitle == null) currentTitle = "Recording";
            elapsed = intent.getIntExtra("elapsed", 0);
        }
        Notification n = buildNotification(elapsed, true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIF_ID, n,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(NOTIF_ID, n);
        }
        handler.postDelayed(tick, 1000);
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(tick);
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void updateNotification() {
        Notification n = buildNotification(elapsed, true);
        NotificationManager nm = (NotificationManager)
            getSystemService(Context.NOTIFICATION_SERVICE);
        nm.notify(NOTIF_ID, n);
    }

    private Notification buildNotification(int sec, boolean running) {
        int h = sec / 3600;
        int m = (sec % 3600) / 60;
        int s = sec % 60;
        String text = String.format("%02d:%02d:%02d — %s", h, m, s, currentTitle);

        NotificationCompat.Builder b = new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(getApplicationInfo().icon)
            .setContentTitle("Rask Timer")
            .setContentText(text)
            .setOngoing(running)
            .setSilent(true)
            .setOnlyAlertOnce(true);

        // Pause action
        Intent pauseIntent = new Intent(this, TimerActionReceiver.class)
            .setAction("com.rask.TIMER_PAUSE");
        PendingIntent pausePi = PendingIntent.getBroadcast(this, 0, pauseIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        b.addAction(0, "Pause", pausePi);

        // Stop action
        Intent stopIntent = new Intent(this, TimerActionReceiver.class)
            .setAction("com.rask.TIMER_STOP");
        PendingIntent stopPi = PendingIntent.getBroadcast(this, 1, stopIntent,
            PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        b.addAction(0, "Stop & save", stopPi);

        return b.build();
    }
}
