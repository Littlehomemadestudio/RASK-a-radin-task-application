"""i18n.py — Persian + English string catalog (1:1 mirror of web/js/i18n.js).

Provides:
  - t(key, lang): translate a key
  - to_fa_digits(s): convert ASCII digits to Persian
  - to_en_digits(s): convert Persian digits back to ASCII
  - fa_num(n): format a number with Persian digits and thousands separators
  - format_list(items, lang): join a list with proper conjunctions

Mirrors the web i18n.js catalog and extends it with desktop-only keys.
"""
from __future__ import annotations
import re

# =====================================================================
# === PERSIAN + ENGLISH STRING CATALOG ===
# =====================================================================
I18N: dict[str, dict[str, str]] = {
    "fa": {
        # ---- App identity ----
        "appName": "رَسک",
        "tagline": "زمان، ظریف.",
        "welcome": "خوش آمدی",

        # ---- Onboarding ----
        "slide1Title": "زمان را زیبا پیگیری کن",
        "slide1Body": "فعالیت‌ها را با یک ضربه ثبت کن، کرنومتر پس‌زمینه را اجرا کن و روزت را شکل بده.",
        "slide2Title": "هدف تعیین کن. زنجیره بساز.",
        "slide2Body": "اهداف روزانه، هفتگی و ماهانه. زنجیره‌ات را زنده نگه‌دار و نشان‌های قدم‌به‌قدم بگیر.",
        "slide3Title": "۱۰۰٪ آفلاین. خصوصی.",
        "slide3Body": "داده‌هایت روی دستگاهت می‌مانند. پشتیبان رمزنگاری‌شده هر وقت بخواهی. بدون حساب، بدون سرور، بدون ردیابی.",
        "skip": "رد شدن",
        "next": "بعدی",
        "start": "شروع",
        "prev": "قبلی",
        "done": "تمام",
        "finish": "پایان",

        # ---- Navigation ----
        "home": "خانه",
        "goals": "اهداف",
        "stats": "آمار",
        "settings": "تنظیمات",

        # ---- Greetings ----
        "goodMorning": "صبح بخیر",
        "goodAfternoon": "عصر بخیر",
        "goodEvening": "شب بخیر",
        "goodNight": "شب بخیر",

        # ---- Home screen ----
        "today": "امروز",
        "yesterday": "دیروز",
        "tomorrow": "فردا",
        "goal": "هدف",
        "streak": "زنجیره",
        "days": "روز",
        "day": "روز",
        "quickTemplates": "قالب‌های سریع",
        "recentActivities": "فعالیت‌های اخیر",
        "noActivities": "هنوز فعالیتی ثبت نشده",
        "noActivitiesHint": "برای شروع، دکمه + را بزن",
        "noTemplates": "هنوز قالبی ساخته نشده",
        "noTemplatesHint": "برای ساخت قالب کلیک کن",
        "recording": "در حال ثبت",
        "recordingFor": "در حال ثبت: {0}",
        "pause": "توقف",
        "resume": "ادامه",
        "stopSave": "ذخیره و پایان",
        "cancelTimer": "لغو تایمر",
        "best": "رکورد",
        "of": "از",
        "thisWeek": "این هفته",
        "thisMonth": "این ماه",
        "thisYear": "این سال",
        "allTime": "همه زمان‌ها",
        "liveTimer": "تایمر زنده",
        "elapsedTime": "زمان گذشته",
        "todayProgress": "پیشرفت امروز",
        "weeklyProgress": "پیشرفت هفتگی",
        "monthlyProgress": "پیشرفت ماهانه",
        "viewAll": "همه را ببین",
        "showMore": "بیشتر",
        "showLess": "کمتر",

        # ---- Quick log modal ----
        "quickLog": "ثبت سریع",
        "activityTitle": "عنوان فعالیت",
        "voiceInput": "ورودی صوتی",
        "listening": "در حال شنیدن...",
        "voiceNotAvailable": "ورودی صوتی در دسترس نیست",
        "voiceError": "خطا در شنیدن صدا",
        "category": "دسته‌بندی",
        "duration": "مدت زمان",
        "hours": "ساعت",
        "minutes": "دقیقه",
        "seconds": "ثانیه",
        "startStopwatch": "شروع کرنومتر به‌جای مدت ثابت",
        "cancel": "انصراف",
        "save": "ذخیره",
        "saved": "ذخیره شد ✓",
        "saveFailed": "ذخیره ناموفق",
        "quickLogSaved": "فعالیت ثبت شد",
        "stopwatchStarted": "کرنومتر شروع شد",
        "selectCategory": "دسته را انتخاب کن",
        "selectDuration": "مدت را وارد کن",
        "enterTitle": "عنوان را وارد کن",
        "titleOptional": "عنوان (اختیاری)",

        # ---- Templates ----
        "addTemplate": "قالب جدید",
        "templateTitle": "عنوان قالب",
        "templateDuration": "مدت پیش‌فرض (دقیقه)",
        "create": "ساخت",
        "editTemplate": "ویرایش قالب",
        "deleteTemplate": "حذف قالب",
        "noTemplatesYet": "قالبی وجود ندارد",
        "templateCreated": "قالب ساخته شد",
        "templateDeleted": "قالب حذف شد",
        "templateUpdated": "قالب به‌روز شد",
        "confirmDeleteTemplate": "این قالب حذف شود؟",

        # ---- Goals ----
        "goalsStreaks": "اهداف و زنجیره‌ها",
        "newGoal": "هدف جدید",
        "noGoals": "هنوز هدفی تعیین نکرده‌ای",
        "noGoalsHint": "برای ساخت اولین هدف کلیک کن",
        "daily": "روزانه",
        "weekly": "هفتگی",
        "monthly": "ماهانه",
        "all": "همه",
        "delete": "حذف",
        "edit": "ویرایش",
        "editGoal": "ویرایش هدف",
        "deleteGoal": "حذف هدف",
        "confirmDeleteGoal": "این هدف حذف شود؟",
        "targetMinutes": "هدف (دقیقه)",
        "targetHours": "هدف (ساعت)",
        "badges": "نشان‌ها",
        "noBadges": "هنوز نشان‌ای گرفته نشده",
        "noBadgesHint": "با حفظ زنجیره نشان بگیر",
        "goalProgress": "پیشرفت هدف",
        "goalAchieved": "هدف محقق شد! 🎉",
        "goalAlmostThere": "نزدیک هدف",
        "goalBehind": "عقب از هدف",
        "goalAhead": "جلوتر از هدف",
        "streakCurrent": "زنجیره فعلی",
        "streakLongest": "طولانی‌ترین زنجیره",
        "streakDays": "{0} روز",
        "streakDay": "{0} روز",
        "keepStreakAlive": "زنجیره را زنده نگه‌دار!",
        "streakInDanger": "زنجیره در خطر!",
        "streakBroken": "زنجیره شکست",
        "goalPeriod": "دوره",
        "goalCategory": "دسته",

        # ---- Statistics ----
        "statistics": "آمار و بینش",
        "total": "مجموع زمان",
        "totalActivities": "تعداد فعالیت",
        "totalCategories": "تعداد دسته‌ها",
        "activeDays": "روز فعال",
        "todayPreset": "امروز",
        "sevenDays": "۷ روز",
        "thirtyDays": "۳۰ روز",
        "thisMonth": "این ماه",
        "thisYear": "این سال",
        "customRange": "بازه دلخواه",
        "dailyTrend": "روند روزانه",
        "weeklyTrend": "روند هفتگی",
        "monthlyTrend": "روند ماهانه",
        "categoryShare": "سهم دسته‌ها",
        "yearHeatmap": "نقشه فعالیت سال",
        "trends": "روند و نقاط اوج",
        "bestDay": "بهترین روز",
        "peakHour": "ساعت اوج",
        "peakDay": "روز اوج",
        "dailyAvg": "میانگین روزانه",
        "weeklyAvg": "میانگین هفتگی",
        "monthlyAvg": "میانگین ماهانه",
        "noData": "داده‌ای در این بازه نیست",
        "noDataHint": "فعالیتی ثبت کن تا آمار ببینی",
        "exportPdf": "خروجی PDF",
        "exportCsv": "خروجی CSV",
        "exportJson": "خروجی JSON",
        "pdfSaved": "گزارش PDF ذخیره شد",
        "csvSaved": "خروجی CSV ذخیره شد",
        "jsonSaved": "خروجی JSON ذخیره شد",
        "exportFailed": "خروجی ناموفق",
        "comparison": "مقایسه با دوره قبل",
        "vsLastPeriod": "در برابر دوره قبل",
        "improvement": "بهبود",
        "decline": "افت",
        "noChange": "بدون تغییر",
        "percentChange": "{0}٪",
        "insights": "بینش‌ها",
        "insightMostProductiveDay": "پرکارترین روزت: {0}",
        "insightMostUsedCategory": "پراستفاده‌ترین دسته: {0}",
        "insightStreakAdvice": "برای حفظ زنجیره امروز فعالیت ثبت کن",
        "insightGoalProgress": "به هدف امروز {0} رسیدی",
        "insightPeakHour": "بیشترین فعالیت در ساعت {0}",
        "topCategories": "دسته‌های برتر",
        "topActivities": "فعالیت‌های برتر",
        "averageSession": "میانگین هر جلسه",
        "longestSession": "طولانی‌ترین جلسه",
        "shortestSession": "کوتاه‌ترین جلسه",
        "medianSession": "میانه جلسه‌ها",
        "p25Session": "صدک ۲۵",
        "p75Session": "صدک ۷۵",
        "p90Session": "صدک ۹۰",
        "activitiesCount": "تعداد فعالیت",
        "stdevSession": "انحراف معیار",
        "histogram": "توزیع مدت‌ها",
        "hourlyDistribution": "توزیع ساعتی",
        "weekdayDistribution": "توزیع روزهای هفته",
        "weekdayActivity": "فعالیت بر اساس روز هفته",
        "weekendVsWeekday": "آخر هفته در برابر روزهای هفته",
        "weekendActivity": "فعالیت آخر هفته",
        "weekdayActivityLabel": "روزهای هفته",
        "productivityScore": "امتیاز بهره‌وری",
        "consistencyScore": "امتیاز پیوستگی",
        "balanceScore": "امتیاز تعادل",
        "scoreOutOf100": "{0} از ۱۰۰",

        # ---- Settings ----
        "settingsTitle": "تنظیمات",
        "appearance": "ظاهر",
        "language": "زبان",
        "persian": "فارسی",
        "english": "انگلیسی",
        "appLock": "قفل برنامه",
        "currentMode": "حالت فعلی",
        "newPin": "پین جدید (۴-۶ رقم)",
        "confirmPin": "تکرار پین",
        "setPin": "تنظیم پین",
        "changePin": "تغییر پین",
        "enableBiometric": "فعال‌سازی اثر انگشت",
        "clearLock": "حذف قفل",
        "backupRestore": "پشتیبان و بازیابی",
        "backupPassword": "رمز پشتیبان",
        "confirmPassword": "تکرار رمز",
        "exportBackup": "خروجی پشتیبان",
        "restoreBackup": "بازیابی پشتیبان",
        "autoBackup": "پشتیبان خودکار",
        "autoBackupDaily": "هر روز",
        "autoBackupWeekly": "هر هفته",
        "autoBackupOff": "خاموش",
        "reminders": "یادآوری‌ها",
        "enableReminders": "فعال‌سازی یادآور",
        "reminderTime": "ساعت یادآور",
        "reminderMessage": "متن یادآور",
        "defaultReminderMessage": "هدف روزانه‌ات را فراموش نکن!",
        "dataManagement": "مدیریت داده",
        "clearAllData": "پاک کردن همه داده‌ها",
        "confirmClearAllData": "همه داده‌ها پاک شوند؟ این عمل برگشت‌ناپذیر است.",
        "exportAllData": "خروجی همه داده‌ها (JSON)",
        "importData": "وروردی داده‌ها",
        "about": "درباره",
        "aboutTagline": "آفلاین. خصوصی. زیبا.",
        "aboutVersion": "نسخه",
        "aboutStudio": "استودیو",
        "aboutCopyright": "© ۲۰۲۶ Littlehomemade Studio",
        "aboutDescription": "پیگیری‌گر زمان و فعالیت، آفلاین و خصوصی",
        "keyboardShortcuts": "میانبرهای صفحه‌کلید",
        "showShortcuts": "نمایش میانبرها",
        "categories": "دسته‌ها",
        "manageCategories": "مدیریت دسته‌ها",
        "addCategory": "دسته جدید",
        "editCategory": "ویرایش دسته",
        "deleteCategory": "حذف دسته",
        "confirmDeleteCategory": "این دسته حذف شود؟",
        "categoryName": "نام دسته",
        "categoryColor": "رنگ دسته",
        "categoryIcon": "آیکن دسته",
        "archiveCategory": "آرشیو دسته",
        "unarchiveCategory": "برگرداندن از آرشیو",
        "archived": "آرشیو شده",
        "active": "فعال",
        "recurringActivities": "فعالیت‌های تکرارشونده",
        "addRecurring": "فعالیت تکرارشونده جدید",
        "noRecurring": "هیچ فعالیت تکرارشونده‌ای نیست",
        "recurringDaily": "هر روز",
        "recurringWeekly": "هر هفته",
        "recurringMonthly": "هر ماه",
        "recurringWeekdays": "روزهای هفته",
        "recurringWeekends": "آخر هفته‌ها",
        "recurringCustom": "سفارشی",
        "search": "جستجو",
        "searchActivities": "جستجوی فعالیت‌ها...",
        "searchResults": "نتایج جستجو",
        "noResults": "نتیجه‌ای پیدا نشد",
        "filter": "فیلتر",
        "filterByCategory": "فیلتر بر اساس دسته",
        "filterByDate": "فیلتر بر اساس تاریخ",
        "filterByDuration": "فیلتر بر اساس مدت",
        "sortBy": "مرتب بر اساس",
        "sortNewest": "جدیدترین",
        "sortOldest": "قدیمی‌ترین",
        "sortLongest": "بلندترین",
        "sortShortest": "کوتاه‌ترین",
        "sortAlphabetical": "الفبایی",
        "sortDuration": "مدت",
        "editActivity": "ویرایش فعالیت",
        "deleteActivity": "حذف فعالیت",
        "confirmDeleteActivity": "این فعالیت حذف شود؟",
        "activityNote": "یادداشت",
        "activityNotePlaceholder": "یادداشت (اختیاری)",
        "activityDate": "تاریخ",
        "activityStartTime": "ساعت شروع",
        "activityEndTime": "ساعت پایان",
        "activityDuration": "مدت",
        "activityCategory": "دسته",
        "activityKind": "نوع",
        "kindManual": "دستی",
        "kindStopwatch": "کرنومتر",
        "kindTemplate": "از قالب",
        "kindRecurring": "تکرارشونده",
        "kindVoice": "صوتی",
        "undoLastActivity": "برگرداندن آخرین فعالیت",
        "undo": "برگردان",
        "undone": "برگردانده شد",
        "cannotUndo": "برگرداندن ممکن نیست",
        "confirmUndo": "آخرین فعالیت برگردانده شود؟",

        # ---- Lock screen ----
        "pinTooShort": "پین کوتاه است",
        "pinTooLong": "پین بلند است",
        "pinMismatch": "پین مطابقت ندارد",
        "pinSet": "پین تنظیم شد",
        "pinChanged": "پین تغییر کرد",
        "pinIncorrect": "پین نادرست",
        "biometricEnabled": "اثر انگشت فعال شد",
        "biometricUnavailable": "اثر انگشت در دسترس نیست",
        "biometricFailed": "اثر انگشت ناموفق بود",
        "lockCleared": "قفل حذف شد",
        "passwordTooShort": "رمز کوتاه است (حداقل ۶)",
        "passwordMismatch": "رمز مطابقت ندارد",
        "backupSaved": "پشتیبان ذخیره شد",
        "backupFailed": "پشتیبان‌گیری ناموفق",
        "noBackupFound": "پشتیبانی پیدا نشد",
        "restoreFailed": "بازیابی ناموفق",
        "restored": "بازیابی شد",
        "restoreConfirm": "بازیابی، داده‌های فعلی را جایگزین می‌کند. ادامه؟",
        "enterPassword": "رمز را وارد کن",
        "unlockRask": "قفل را باز کنید",
        "enterPin": "پین خود را وارد کنید",
        "unlock": "باز کردن",
        "useBiometric": "استفاده از اثر انگشت",
        "wrongPin": "پین نادرست",
        "none": "هیچ",
        "pin": "پین",
        "biometric": "اثر انگشت",

        # ---- Time units ----
        "hour": "ساعت",
        "minute": "دقیقه",
        "second": "ثانیه",
        "hours": "ساعت",
        "minutes": "دقیقه",
        "seconds": "ثانیه",

        # ---- Relative dates ----
        "today_": "امروز",
        "yesterday": "دیروز",
        "tomorrow": "فردا",
        "ago": "پیش",
        "in": "در",
        "now": "اکنون",
        "just_now": "همین حالا",
        "week": "هفته",
        "month": "ماه",
        "year": "سال",

        # ---- Weekdays (Monday=0) ----
        "weekdayMon": "دوشنبه",
        "weekdayTue": "سه‌شنبه",
        "weekdayWed": "چهارشنبه",
        "weekdayThu": "پنجشنبه",
        "weekdayFri": "جمعه",
        "weekdaySat": "شنبه",
        "weekdaySun": "یکشنبه",
        "weekdayMonShort": "ش",
        "weekdayTueShort": "ی",
        "weekdayWedShort": "د",
        "weekdayThuShort": "س",
        "weekdayFriShort": "چ",
        "weekdaySatShort": "پ",
        "weekdaySunShort": "ج",

        # ---- Jalali months ----
        "jMonth1": "فروردین",  "jMonth2": "اردیبهشت", "jMonth3": "خرداد",
        "jMonth4": "تیر",      "jMonth5": "مرداد",    "jMonth6": "شهریور",
        "jMonth7": "مهر",      "jMonth8": "آبان",     "jMonth9": "آذر",
        "jMonth10": "دی",      "jMonth11": "بهمن",    "jMonth12": "اسفند",

        # ---- Category labels ----
        "catFocus": "تمرکز",
        "catLearn": "یادگیری",
        "catWork": "کار",
        "catHealth": "سلامتی",
        "catCreative": "خلاقیت",
        "catSocial": "اجتماعی",
        "catRest": "استراحت",

        # ---- Streak badge labels ----
        "streak3": "۳ روز پیاپی",
        "streak7": "۷ روز پیاپی",
        "streak30": "۳۰ روز پیاپی",
        "streak100": "۱۰۰ روز پیاپی",
        "first_activity": "اولین فعالیت",
        "ten_activities": "۱۰ فعالیت",
        "hundred_activities": "۱۰۰ فعالیت",
        "thousand_activities": "۱۰۰۰ فعالیت",
        "first_goal": "اولین هدف",
        "first_streak": "اولین زنجیره",
        "week_streak": "زنجیره هفته",
        "month_streak": "زنجیره ماه",
        "year_streak": "زنجیره ۱۰۰ روزه",
        "early_bird": "سحرگاهان",
        "night_owl": "شب‌بیدار",
        "weekend_warrior": "قهرمان آخر هفته",
        "perfectionist": "کمال‌گرا",
        "consistency_king": "پادشاه پیوستگی",
        "marathon": "ماراتن",
        "explorer": "کاوشگر",

        # ---- Notifications ----
        "notifReminderTitle": "رسک",
        "notifReminderBody": "هدف روزانه‌ات را فراموش نکن!",
        "notifTimerTitle": "کرنومتر رسک",
        "notifTimerPaused": "متوقف",
        "notifTimerRunning": "در حال اجرا",
        "notifGoalAchieved": "هدف امروز محقق شد! 🎉",
        "notifStreakInDanger": "زنجیره‌ات در خطر است!",
        "notifBadgeEarned": "نشان جدید گرفتید! 🏅",

        # ---- PWA install (kept for parity, unused on desktop) ----
        "installApp": "نصب برنامه",
        "installPrompt": "برای استفاده آفلاین، رسک را روی دستگاهت نصب کن.",
        "dismiss": "بستن",

        # ---- Toast messages ----
        "toastSaved": "ذخیره شد ✓",
        "toastDeleted": "حذف شد",
        "toastError": "خطا",
        "toastCopied": "کپی شد",
        "toastExported": "خروجی گرفته شد",
        "toastImported": "وروردی شد",
        "toastCleared": "پاک شد",
        "toastLockSet": "قفل فعال شد",
        "toastLockCleared": "قفل حذف شد",

        # ---- Empty states ----
        "emptyHome": "هنوز فعالیتی ثبت نکرده‌ای. دکمه + را بزن تا شروع کنی.",
        "emptyGoals": "هیچ هدفی تعیین نکرده‌ای. هدف اولت را بساز.",
        "emptyStats": "داده‌ای برای نمایش نیست. چند فعالیت ثبت کن.",
        "emptySearch": "جستجو نتیجه‌ای نداشت.",
        "emptyBadges": "هنوز نشان‌ای نگرفته‌ای.",

        # ---- Misc ----
        "yes": "بله",
        "no": "خیر",
        "ok": "باشه",
        "confirm": "تأیید",
        "continue": "ادامه",
        "back": "بازگشت",
        "close": "بستن",
        "apply": "اعمال",
        "reset": "بازنشانی",
        "refresh": "تازه‌سازی",
        "loading": "در حال بارگذاری...",
        "syncing": "در حال همگام‌سازی...",
        "saving": "در حال ذخیره...",
        "deleting": "در حال حذف...",
        "exporting": "در حال خروجی...",
        "importing": "در حال وروردی...",
        "computing": "در حال محاسبه...",
        "draft": "پیش‌نویس",
        "optional": "اختیاری",
        "required": "اجباری",
        "allCategories": "همه دسته‌ها",
        "allActivities": "همه فعالیت‌ها",
        "selectCategory": "دسته را انتخاب کن",
        "selectAll": "انتخاب همه",
        "selectNone": "خالی کردن انتخاب",
        "invertSelection": "برعکس کردن انتخاب",
        "moreOptions": "گزینه‌های بیشتر",
        "lessOptions": "گزینه‌های کمتر",
        "advanced": "پیشرفته",
        "basic": "ساده",
        "compact": "فشرده",
        "comfortable": "راحت",
        "spacious": "جادار",

        # ---- Desktop-specific ----
        "menuFile": "فایل",
        "menuEdit": "ویرایش",
        "menuView": "نمایش",
        "menuHelp": "راهنما",
        "menuQuit": "خروج",
        "menuNewActivity": "فعالیت جدید",
        "menuNewGoal": "هدف جدید",
        "menuNewTemplate": "قالب جدید",
        "menuExportPdf": "خروجی PDF...",
        "menuExportCsv": "خروجی CSV...",
        "menuExportBackup": "پشتیبان...",
        "menuImportBackup": "بازیابی پشتیبان...",
        "menuLock": "قفل برنامه",
        "menuSettings": "تنظیمات",
        "menuAbout": "درباره رسک",
        "menuShortcuts": "میانبرهای صفحه‌کلید",
        "menuRefresh": "تازه‌سازی",
        "menuUndo": "برگرداندن",
        "menuSearch": "جستجو",
        "menuZoomIn": "بزرگ‌نمایی",
        "menuZoomOut": "کوچک‌نمایی",
        "menuZoomReset": "بازنشانی بزرگ‌نمایی",
        "menuToggleFullscreen": "تمام صفحه",
        "menuToggleDevTools": "ابزار توسعه‌دهنده",

        # ---- Keyboard shortcuts descriptions ----
        "shortcut_switch_home": "رفتن به خانه",
        "shortcut_switch_goals": "رفتن به اهداف",
        "shortcut_switch_stats": "رفتن به آمار",
        "shortcut_switch_settings": "رفتن به تنظیمات",
        "shortcut_quick_log": "ثبت سریع",
        "shortcut_toggle_timer": "شروع/توقف تایمر",
        "shortcut_stop_save_timer": "توقف و ذخیره تایمر",
        "shortcut_export_csv": "خروجی CSV",
        "shortcut_export_pdf": "خروجی PDF",
        "shortcut_export_backup": "خروجی پشتیبان",
        "shortcut_lock_app": "قفل برنامه",
        "shortcut_settings": "تنظیمات",
        "shortcut_close_modal": "بستن پنجره",
        "shortcut_undo_last": "برگرداندن آخرین فعالیت",
        "shortcut_search": "جستجوی فعالیت‌ها",
        "shortcut_refresh": "تازه‌سازی صفحه",
        "shortcut_show_shortcuts": "نمایش میانبرها",

        # ---- Errors ----
        "err_db_open": "خطا در باز کردن پایگاه داده",
        "err_db_query": "خطا در پرس‌وجو",
        "err_db_write": "خطا در نوشتن",
        "err_crypto_unavailable": "کتابخانه رمزنگاری در دسترس نیست",
        "err_invalid_backup": "فایل پشتیبان نامعتبر است",
        "err_wrong_password": "رمز اشتباه است",
        "err_corrupted_data": "داده خراب شده",
        "err_file_not_found": "فایل پیدا نشد",
        "err_permission": "خطای دسترسی",
        "err_unknown": "خطای ناشناخته",

        # ---- Onboarding slides (extended) ----
        "slide4Title": "همه چیز روی دستگاه تو",
        "slide4Body": "داده‌ها روی همون دستگاهی که استفاده می‌کنی می‌مانند. هیچ سروری، هیچ ابری، هیچ ردیابی.",
        "slide5Title": "آماده شروع؟",
        "slide5Body": "بیا با اولین فعالیت شروع کنیم. فقط دکمه + را بزن.",

        # ---- Activity list ----
        "todayActivities": "فعالیت‌های امروز",
        "yesterdayActivities": "فعالیت‌های دیروز",
        "thisWeekActivities": "فعالیت‌های این هفته",
        "earlierActivities": "فعالیت‌های قدیمی‌تر",
        "untitled": "بدون عنوان",
        "noCategory": "بدون دسته",
        "durationFormat": "{0} ساعت {1} دقیقه",
        "durationFormatShort": "{0}h {1}m",

        # ---- CSV/PDF exports ----
        "exportTitle": "گزارش فعالیت‌های رسک",
        "exportDateRange": "بازه تاریخ",
        "exportGeneratedAt": "تاریخ تولید",
        "exportTotalDuration": "مجموع مدت",
        "exportActivityCount": "تعداد فعالیت",
        "exportColumnTitle": "عنوان",
        "exportColumnCategory": "دسته",
        "exportColumnDate": "تاریخ",
        "exportColumnStart": "شروع",
        "exportColumnEnd": "پایان",
        "exportColumnDuration": "مدت",
        "exportColumnNote": "یادداشت",
        "exportColumnKind": "نوع",

        # ---- Settings: theme ----
        "themeMode": "حالت تم",
        "themeDark": "تیره",
        "themeLight": "روشن",
        "themeAuto": "خودکار",
        "accentColor": "رنگ تأکید",
        "fontFamily": "خانواده فونت",
        "fontSize": "اندازه فونت",

        # ---- Settings: data ----
        "dataLocation": "محل ذخیره داده",
        "dbSize": "اندازه پایگاه داده",
        "openDataFolder": "باز کردن پوشه داده",
        "activitiesCount": "تعداد فعالیت‌ها",
        "categoriesCount": "تعداد دسته‌ها",
        "goalsCount": "تعداد اهداف",
        "templatesCount": "تعداد قالب‌ها",
        "badgesCount": "تعداد نشان‌ها",
        "firstActivityDate": "تاریخ اولین فعالیت",
        "lastActivityDate": "تاریخ آخرین فعالیت",
        "dataAge": "سن داده‌ها",
    },

    "en": {
        # ---- App identity ----
        "appName": "Rask",
        "tagline": "Time, refined.",
        "welcome": "Welcome",

        # ---- Onboarding ----
        "slide1Title": "Track time beautifully",
        "slide1Body": "Log activities with a tap, run a background stopwatch, and watch your day take shape.",
        "slide2Title": "Set goals. Build streaks.",
        "slide2Body": "Daily, weekly, monthly goals. Keep your streak alive and earn milestone badges.",
        "slide3Title": "100% offline. Private.",
        "slide3Body": "Your data lives on your device. Encrypted backups when you want them. No accounts, no servers, no tracking.",
        "skip": "Skip",
        "next": "Next",
        "start": "Get started",
        "prev": "Previous",
        "done": "Done",
        "finish": "Finish",

        # ---- Navigation ----
        "home": "Home",
        "goals": "Goals",
        "stats": "Stats",
        "settings": "Settings",

        # ---- Greetings ----
        "goodMorning": "Good morning",
        "goodAfternoon": "Good afternoon",
        "goodEvening": "Good evening",
        "goodNight": "Good night",

        # ---- Home screen ----
        "today": "Today",
        "yesterday": "Yesterday",
        "tomorrow": "Tomorrow",
        "goal": "Goal",
        "streak": "Streak",
        "days": "days",
        "day": "day",
        "quickTemplates": "Quick templates",
        "recentActivities": "Recent activities",
        "noActivities": "No activities yet",
        "noActivitiesHint": "Press + to start",
        "noTemplates": "No templates yet",
        "noTemplatesHint": "Click to create one",
        "recording": "Recording",
        "recordingFor": "Recording: {0}",
        "pause": "Pause",
        "resume": "Resume",
        "stopSave": "Stop & save",
        "cancelTimer": "Cancel timer",
        "best": "Best",
        "of": "of",
        "thisWeek": "This week",
        "thisMonth": "This month",
        "thisYear": "This year",
        "allTime": "All time",
        "liveTimer": "Live timer",
        "elapsedTime": "Elapsed time",
        "todayProgress": "Today's progress",
        "weeklyProgress": "Weekly progress",
        "monthlyProgress": "Monthly progress",
        "viewAll": "View all",
        "showMore": "Show more",
        "showLess": "Show less",

        # ---- Quick log modal ----
        "quickLog": "Quick log",
        "activityTitle": "Activity title",
        "voiceInput": "Voice input",
        "listening": "Listening...",
        "voiceNotAvailable": "Voice input unavailable",
        "voiceError": "Voice recognition error",
        "category": "Category",
        "duration": "Duration",
        "hours": "hours",
        "minutes": "minutes",
        "seconds": "seconds",
        "startStopwatch": "Start stopwatch instead",
        "cancel": "Cancel",
        "save": "Save",
        "saved": "Saved ✓",
        "saveFailed": "Save failed",
        "quickLogSaved": "Activity logged",
        "stopwatchStarted": "Stopwatch started",
        "selectCategory": "Select a category",
        "selectDuration": "Enter duration",
        "enterTitle": "Enter a title",
        "titleOptional": "Title (optional)",

        # ---- Templates ----
        "addTemplate": "+ New template",
        "templateTitle": "Template title",
        "templateDuration": "Default duration (min)",
        "create": "Create",
        "editTemplate": "Edit template",
        "deleteTemplate": "Delete template",
        "noTemplatesYet": "No templates",
        "templateCreated": "Template created",
        "templateDeleted": "Template deleted",
        "templateUpdated": "Template updated",
        "confirmDeleteTemplate": "Delete this template?",

        # ---- Goals ----
        "goalsStreaks": "Goals & streaks",
        "newGoal": "+ New goal",
        "noGoals": "No goals yet",
        "noGoalsHint": "Click to create your first goal",
        "daily": "Daily",
        "weekly": "Weekly",
        "monthly": "Monthly",
        "all": "All",
        "delete": "Delete",
        "edit": "Edit",
        "editGoal": "Edit goal",
        "deleteGoal": "Delete goal",
        "confirmDeleteGoal": "Delete this goal?",
        "targetMinutes": "Target (minutes)",
        "targetHours": "Target (hours)",
        "badges": "Badges",
        "noBadges": "No badges earned yet",
        "noBadgesHint": "Keep your streak alive to earn badges",
        "goalProgress": "Goal progress",
        "goalAchieved": "Goal achieved! 🎉",
        "goalAlmostThere": "Almost there",
        "goalBehind": "Behind goal",
        "goalAhead": "Ahead of goal",
        "streakCurrent": "Current streak",
        "streakLongest": "Longest streak",
        "streakDays": "{0} days",
        "streakDay": "{0} day",
        "keepStreakAlive": "Keep your streak alive!",
        "streakInDanger": "Streak in danger!",
        "streakBroken": "Streak broken",
        "goalPeriod": "Period",
        "goalCategory": "Category",

        # ---- Statistics ----
        "statistics": "Statistics",
        "total": "Total time",
        "totalActivities": "Activity count",
        "totalCategories": "Category count",
        "activeDays": "Active days",
        "todayPreset": "Today",
        "sevenDays": "7 days",
        "thirtyDays": "30 days",
        "thisMonth": "This month",
        "thisYear": "This year",
        "customRange": "Custom range",
        "dailyTrend": "Daily trend",
        "weeklyTrend": "Weekly trend",
        "monthlyTrend": "Monthly trend",
        "categoryShare": "Category share",
        "yearHeatmap": "Year heatmap",
        "trends": "Trends & peaks",
        "bestDay": "Best day",
        "peakHour": "Peak hour",
        "peakDay": "Peak day",
        "dailyAvg": "Daily average",
        "weeklyAvg": "Weekly average",
        "monthlyAvg": "Monthly average",
        "noData": "No data in this range",
        "noDataHint": "Log activities to see stats",
        "exportPdf": "Export PDF",
        "exportCsv": "Export CSV",
        "exportJson": "Export JSON",
        "pdfSaved": "PDF report saved",
        "csvSaved": "CSV export saved",
        "jsonSaved": "JSON export saved",
        "exportFailed": "Export failed",
        "comparison": "Comparison vs previous period",
        "vsLastPeriod": "vs last period",
        "improvement": "Improvement",
        "decline": "Decline",
        "noChange": "No change",
        "percentChange": "{0}%",
        "insights": "Insights",
        "insightMostProductiveDay": "Most productive day: {0}",
        "insightMostUsedCategory": "Most used category: {0}",
        "insightStreakAdvice": "Log an activity today to keep your streak",
        "insightGoalProgress": "You're {0} to today's goal",
        "insightPeakHour": "Most activity at hour {0}",
        "topCategories": "Top categories",
        "topActivities": "Top activities",
        "averageSession": "Average session",
        "longestSession": "Longest session",
        "shortestSession": "Shortest session",
        "medianSession": "Median session",
        "p25Session": "25th percentile",
        "p75Session": "75th percentile",
        "p90Session": "90th percentile",
        "activitiesCount": "Activities",
        "stdevSession": "Standard deviation",
        "histogram": "Duration distribution",
        "hourlyDistribution": "Hourly distribution",
        "weekdayDistribution": "Weekday distribution",
        "weekdayActivity": "Activity by weekday",
        "weekendVsWeekday": "Weekend vs weekday",
        "weekendActivity": "Weekend activity",
        "weekdayActivityLabel": "Weekday activity",
        "productivityScore": "Productivity score",
        "consistencyScore": "Consistency score",
        "balanceScore": "Balance score",
        "scoreOutOf100": "{0} / 100",

        # ---- Settings ----
        "settingsTitle": "Settings",
        "appearance": "Appearance",
        "language": "Language",
        "persian": "Persian",
        "english": "English",
        "appLock": "App lock",
        "currentMode": "Current mode",
        "newPin": "New PIN (4-6 digits)",
        "confirmPin": "Confirm PIN",
        "setPin": "Set PIN",
        "changePin": "Change PIN",
        "enableBiometric": "Enable biometric",
        "clearLock": "Clear lock",
        "backupRestore": "Backup & restore",
        "backupPassword": "Backup password",
        "confirmPassword": "Confirm password",
        "exportBackup": "Export backup",
        "restoreBackup": "Restore backup",
        "autoBackup": "Auto backup",
        "autoBackupDaily": "Daily",
        "autoBackupWeekly": "Weekly",
        "autoBackupOff": "Off",
        "reminders": "Reminders",
        "enableReminders": "Enable reminders",
        "reminderTime": "Reminder time",
        "reminderMessage": "Reminder message",
        "defaultReminderMessage": "Don't forget your daily goal!",
        "dataManagement": "Data management",
        "clearAllData": "Clear all data",
        "confirmClearAllData": "Clear all data? This is irreversible.",
        "exportAllData": "Export all data (JSON)",
        "importData": "Import data",
        "about": "About",
        "aboutTagline": "Offline. Private. Beautiful.",
        "aboutVersion": "Version",
        "aboutStudio": "Studio",
        "aboutCopyright": "© 2026 Littlehomemade Studio",
        "aboutDescription": "Time & activity tracker, offline and private",
        "keyboardShortcuts": "Keyboard shortcuts",
        "showShortcuts": "Show shortcuts",
        "categories": "Categories",
        "manageCategories": "Manage categories",
        "addCategory": "+ New category",
        "editCategory": "Edit category",
        "deleteCategory": "Delete category",
        "confirmDeleteCategory": "Delete this category?",
        "categoryName": "Category name",
        "categoryColor": "Category color",
        "categoryIcon": "Category icon",
        "archiveCategory": "Archive category",
        "unarchiveCategory": "Unarchive category",
        "archived": "Archived",
        "active": "Active",
        "recurringActivities": "Recurring activities",
        "addRecurring": "+ New recurring activity",
        "noRecurring": "No recurring activities",
        "recurringDaily": "Every day",
        "recurringWeekly": "Every week",
        "recurringMonthly": "Every month",
        "recurringWeekdays": "Weekdays",
        "recurringWeekends": "Weekends",
        "recurringCustom": "Custom",
        "search": "Search",
        "searchActivities": "Search activities...",
        "searchResults": "Search results",
        "noResults": "No results found",
        "filter": "Filter",
        "filterByCategory": "Filter by category",
        "filterByDate": "Filter by date",
        "filterByDuration": "Filter by duration",
        "sortBy": "Sort by",
        "sortNewest": "Newest",
        "sortOldest": "Oldest",
        "sortLongest": "Longest",
        "sortShortest": "Shortest",
        "sortAlphabetical": "Alphabetical",
        "sortDuration": "Duration",
        "editActivity": "Edit activity",
        "deleteActivity": "Delete activity",
        "confirmDeleteActivity": "Delete this activity?",
        "activityNote": "Note",
        "activityNotePlaceholder": "Note (optional)",
        "activityDate": "Date",
        "activityStartTime": "Start time",
        "activityEndTime": "End time",
        "activityDuration": "Duration",
        "activityCategory": "Category",
        "activityKind": "Kind",
        "kindManual": "Manual",
        "kindStopwatch": "Stopwatch",
        "kindTemplate": "Template",
        "kindRecurring": "Recurring",
        "kindVoice": "Voice",
        "undoLastActivity": "Undo last activity",
        "undo": "Undo",
        "undone": "Undone",
        "cannotUndo": "Cannot undo",
        "confirmUndo": "Undo the last activity?",

        # ---- Lock screen ----
        "pinTooShort": "PIN too short",
        "pinTooLong": "PIN too long",
        "pinMismatch": "PINs don't match",
        "pinSet": "PIN set",
        "pinChanged": "PIN changed",
        "pinIncorrect": "Incorrect PIN",
        "biometricEnabled": "Biometric enabled",
        "biometricUnavailable": "Biometric unavailable",
        "biometricFailed": "Biometric failed",
        "lockCleared": "Lock cleared",
        "passwordTooShort": "Password too short (≥6)",
        "passwordMismatch": "Passwords don't match",
        "backupSaved": "Backup saved",
        "backupFailed": "Backup failed",
        "noBackupFound": "No backup file found",
        "restoreFailed": "Restore failed",
        "restored": "Restored",
        "restoreConfirm": "Restoring will replace current data. Continue?",
        "enterPassword": "Enter password",
        "unlockRask": "Unlock Rask",
        "enterPin": "Enter your PIN",
        "unlock": "Unlock",
        "useBiometric": "Use biometric",
        "wrongPin": "Incorrect PIN",
        "none": "None",
        "pin": "PIN",
        "biometric": "Biometric",

        # ---- Time units ----
        "hour": "h",
        "minute": "m",
        "second": "s",
        "hours": "h",
        "minutes": "m",
        "seconds": "s",

        # ---- Relative dates ----
        "today_": "Today",
        "yesterday": "Yesterday",
        "tomorrow": "Tomorrow",
        "ago": "ago",
        "in": "in",
        "now": "now",
        "just_now": "just now",
        "week": "week",
        "month": "month",
        "year": "year",

        # ---- Weekdays ----
        "weekdayMon": "Monday",
        "weekdayTue": "Tuesday",
        "weekdayWed": "Wednesday",
        "weekdayThu": "Thursday",
        "weekdayFri": "Friday",
        "weekdaySat": "Saturday",
        "weekdaySun": "Sunday",
        "weekdayMonShort": "Mo",
        "weekdayTueShort": "Tu",
        "weekdayWedShort": "We",
        "weekdayThuShort": "Th",
        "weekdayFriShort": "Fr",
        "weekdaySatShort": "Sa",
        "weekdaySunShort": "Su",

        # ---- Months (English) ----
        "jMonth1": "Jan",  "jMonth2": "Feb",  "jMonth3": "Mar",
        "jMonth4": "Apr",  "jMonth5": "May",  "jMonth6": "Jun",
        "jMonth7": "Jul",  "jMonth8": "Aug",  "jMonth9": "Sep",
        "jMonth10": "Oct", "jMonth11": "Nov", "jMonth12": "Dec",

        # ---- Category labels ----
        "catFocus": "Focus",
        "catLearn": "Learn",
        "catWork": "Work",
        "catHealth": "Health",
        "catCreative": "Creative",
        "catSocial": "Social",
        "catRest": "Rest",

        # ---- Streak badge labels ----
        "streak3": "3-day streak",
        "streak7": "7-day streak",
        "streak30": "30-day streak",
        "streak100": "100-day streak",
        "first_activity": "First activity",
        "ten_activities": "10 activities",
        "hundred_activities": "100 activities",
        "thousand_activities": "1000 activities",
        "first_goal": "First goal",
        "first_streak": "First streak",
        "week_streak": "Week streak",
        "month_streak": "Month streak",
        "year_streak": "100-day streak",
        "early_bird": "Early bird",
        "night_owl": "Night owl",
        "weekend_warrior": "Weekend warrior",
        "perfectionist": "Perfectionist",
        "consistency_king": "Consistency king",
        "marathon": "Marathon",
        "explorer": "Explorer",

        # ---- Notifications ----
        "notifReminderTitle": "Rask",
        "notifReminderBody": "Don't forget your daily goal!",
        "notifTimerTitle": "Rask Timer",
        "notifTimerPaused": "Paused",
        "notifTimerRunning": "Running",
        "notifGoalAchieved": "Today's goal achieved! 🎉",
        "notifStreakInDanger": "Your streak is in danger!",
        "notifBadgeEarned": "New badge earned! 🏅",

        # ---- PWA install ----
        "installApp": "Install app",
        "installPrompt": "Install Rask on your device for offline use.",
        "dismiss": "Dismiss",

        # ---- Toast messages ----
        "toastSaved": "Saved ✓",
        "toastDeleted": "Deleted",
        "toastError": "Error",
        "toastCopied": "Copied",
        "toastExported": "Exported",
        "toastImported": "Imported",
        "toastCleared": "Cleared",
        "toastLockSet": "Lock enabled",
        "toastLockCleared": "Lock removed",

        # ---- Empty states ----
        "emptyHome": "No activities yet. Tap + to get started.",
        "emptyGoals": "No goals set. Create your first goal.",
        "emptyStats": "No data to display. Log a few activities.",
        "emptySearch": "Search returned no results.",
        "emptyBadges": "No badges earned yet.",

        # ---- Misc ----
        "yes": "Yes",
        "no": "No",
        "ok": "OK",
        "confirm": "Confirm",
        "continue": "Continue",
        "back": "Back",
        "close": "Close",
        "apply": "Apply",
        "reset": "Reset",
        "refresh": "Refresh",
        "loading": "Loading...",
        "syncing": "Syncing...",
        "saving": "Saving...",
        "deleting": "Deleting...",
        "exporting": "Exporting...",
        "importing": "Importing...",
        "computing": "Computing...",
        "draft": "Draft",
        "optional": "optional",
        "required": "required",
        "allCategories": "All categories",
        "allActivities": "All activities",
        "selectAll": "Select all",
        "selectNone": "Select none",
        "invertSelection": "Invert selection",
        "moreOptions": "More options",
        "lessOptions": "Fewer options",
        "advanced": "Advanced",
        "basic": "Basic",
        "compact": "Compact",
        "comfortable": "Comfortable",
        "spacious": "Spacious",

        # ---- Desktop-specific ----
        "menuFile": "File",
        "menuEdit": "Edit",
        "menuView": "View",
        "menuHelp": "Help",
        "menuQuit": "Quit",
        "menuNewActivity": "New activity",
        "menuNewGoal": "New goal",
        "menuNewTemplate": "New template",
        "menuExportPdf": "Export PDF...",
        "menuExportCsv": "Export CSV...",
        "menuExportBackup": "Export backup...",
        "menuImportBackup": "Restore backup...",
        "menuLock": "Lock app",
        "menuSettings": "Settings",
        "menuAbout": "About Rask",
        "menuShortcuts": "Keyboard shortcuts",
        "menuRefresh": "Refresh",
        "menuUndo": "Undo",
        "menuSearch": "Search",
        "menuZoomIn": "Zoom in",
        "menuZoomOut": "Zoom out",
        "menuZoomReset": "Reset zoom",
        "menuToggleFullscreen": "Toggle fullscreen",
        "menuToggleDevTools": "Toggle dev tools",

        # ---- Keyboard shortcuts descriptions ----
        "shortcut_switch_home": "Go to Home",
        "shortcut_switch_goals": "Go to Goals",
        "shortcut_switch_stats": "Go to Stats",
        "shortcut_switch_settings": "Go to Settings",
        "shortcut_quick_log": "Quick log",
        "shortcut_toggle_timer": "Start/pause timer",
        "shortcut_stop_save_timer": "Stop & save timer",
        "shortcut_export_csv": "Export CSV",
        "shortcut_export_pdf": "Export PDF",
        "shortcut_export_backup": "Export backup",
        "shortcut_lock_app": "Lock app",
        "shortcut_settings": "Settings",
        "shortcut_close_modal": "Close modal",
        "shortcut_undo_last": "Undo last activity",
        "shortcut_search": "Search activities",
        "shortcut_refresh": "Refresh screen",
        "shortcut_show_shortcuts": "Show shortcuts",

        # ---- Errors ----
        "err_db_open": "Failed to open database",
        "err_db_query": "Database query failed",
        "err_db_write": "Database write failed",
        "err_crypto_unavailable": "Cryptography library unavailable",
        "err_invalid_backup": "Invalid backup file",
        "err_wrong_password": "Wrong password",
        "err_corrupted_data": "Data corrupted",
        "err_file_not_found": "File not found",
        "err_permission": "Permission denied",
        "err_unknown": "Unknown error",

        # ---- Extended onboarding ----
        "slide4Title": "Everything stays on your device",
        "slide4Body": "Your data lives on the device you use. No servers, no cloud, no tracking.",
        "slide5Title": "Ready to start?",
        "slide5Body": "Let's begin with your first activity. Just tap +.",

        # ---- Activity list ----
        "todayActivities": "Today's activities",
        "yesterdayActivities": "Yesterday's activities",
        "thisWeekActivities": "This week's activities",
        "earlierActivities": "Earlier activities",
        "untitled": "Untitled",
        "noCategory": "No category",
        "durationFormat": "{0}h {1}m",
        "durationFormatShort": "{0}h {1}m",

        # ---- CSV/PDF exports ----
        "exportTitle": "Rask Activity Report",
        "exportDateRange": "Date range",
        "exportGeneratedAt": "Generated at",
        "exportTotalDuration": "Total duration",
        "exportActivityCount": "Activity count",
        "exportColumnTitle": "Title",
        "exportColumnCategory": "Category",
        "exportColumnDate": "Date",
        "exportColumnStart": "Start",
        "exportColumnEnd": "End",
        "exportColumnDuration": "Duration",
        "exportColumnNote": "Note",
        "exportColumnKind": "Kind",

        # ---- Settings: theme ----
        "themeMode": "Theme mode",
        "themeDark": "Dark",
        "themeLight": "Light",
        "themeAuto": "Auto",
        "accentColor": "Accent color",
        "fontFamily": "Font family",
        "fontSize": "Font size",

        # ---- Settings: data ----
        "dataLocation": "Data location",
        "dbSize": "Database size",
        "openDataFolder": "Open data folder",
        "activitiesCount": "Activities",
        "categoriesCount": "Categories",
        "goalsCount": "Goals",
        "templatesCount": "Templates",
        "badgesCount": "Badges",
        "firstActivityDate": "First activity date",
        "lastActivityDate": "Last activity date",
        "dataAge": "Data age",
    },
}


# =====================================================================
# === DIGIT CONVERSION ===
# =====================================================================
_FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_EN_DIGITS = "0123456789"

_FA_TO_EN = str.maketrans(_FA_DIGITS, _EN_DIGITS)
_EN_TO_FA = str.maketrans(_EN_DIGITS, _FA_DIGITS)


def to_fa_digits(s) -> str:
    """Convert ASCII digits 0-9 to Persian digits."""
    return str(s).translate(_EN_TO_FA)


def to_en_digits(s) -> str:
    """Convert Persian digits to ASCII digits."""
    return str(s).translate(_FA_TO_EN)


def fa_num(n) -> str:
    """Format a number with thousands separators and Persian digits.
    
    Uses the Arabic thousands separator (٬, U+066C) per Persian convention.
    """
    if isinstance(n, float):
        if n.is_integer():
            n = int(n)
        else:
            # Format with ASCII commas first, then convert to Persian digits
            # and replace commas with Arabic thousands separator
            formatted = f"{n:,.2f}"
            return to_fa_digits(formatted.replace(",", "٬"))
    # Format with ASCII commas, then convert
    formatted = f"{n:,}"
    return to_fa_digits(formatted.replace(",", "٬"))


# =====================================================================
# === STRING FORMATTING ===
# =====================================================================
def t(key: str, lang: str = "fa", *args) -> str:
    """Translate a key for the given language (default fa).
    
    Supports positional placeholders: t("streakDays", "fa", 5) → "۵ روز".
    Falls back to English if key missing in requested lang, then to the key itself.
    """
    lang = lang or "fa"
    d = I18N.get(lang) or I18N["fa"]
    val = d.get(key)
    if val is None:
        val = I18N["en"].get(key, key)
    if args:
        try:
            # Convert args to Persian digits if lang is fa
            if lang == "fa":
                fa_args = tuple(to_fa_digits(a) if isinstance(a, (int, float)) else a for a in args)
                return val.format(*fa_args)
            return val.format(*args)
        except (IndexError, KeyError):
            return val
    return val


def tf(key: str, lang: str = "fa", **kwargs) -> str:
    """Translate with named placeholders: tf("recordingFor", "fa", title="X")."""
    lang = lang or "fa"
    d = I18N.get(lang) or I18N["fa"]
    val = d.get(key) or I18N["en"].get(key, key)
    if kwargs:
        if lang == "fa":
            fa_kwargs = {k: (to_fa_digits(v) if isinstance(v, (int, float)) else v) for k, v in kwargs.items()}
            try:
                return val.format(**fa_kwargs)
            except (KeyError, IndexError):
                return val
        try:
            return val.format(**kwargs)
        except (KeyError, IndexError):
            return val
    return val


# =====================================================================
# === LIST FORMATTING ===
# =====================================================================
def format_list(items: list, lang: str = "fa") -> str:
    """Format a list with proper conjunctions.
    
    fa: ["a", "b", "c"] → "a، b و c"
    en: ["a", "b", "c"] → "a, b and c"
    """
    if not items:
        return ""
    items = [str(x) for x in items]
    if len(items) == 1:
        return items[0]
    if lang == "fa":
        if len(items) == 2:
            return f"{items[0]} و {items[1]}"
        return "، ".join(items[:-1]) + " و " + items[-1]
    else:
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return ", ".join(items[:-1]) + " and " + items[-1]


# =====================================================================
# === LANGUAGE DETECTION ===
# =====================================================================
def detect_lang() -> str:
    """Detect the user's preferred language from environment.
    
    Falls back to "fa" if detection fails (matches web default).
    """
    import locale
    try:
        loc = locale.getlocale()[0] or locale.getdefaultlocale()[0] or ""
        loc = loc.lower()
        if loc.startswith("fa"):
            return "fa"
        if loc.startswith("en"):
            return "en"
    except Exception:
        pass
    return "fa"


def is_rtl(lang: str) -> bool:
    """Return True if the language reads right-to-left."""
    return lang in ("fa", "ar", "he", "ur")


# =====================================================================
# === EXPORT ===
# =====================================================================
def available_langs() -> list[str]:
    """Return list of available language codes."""
    return list(I18N.keys())


def all_keys() -> list[str]:
    """Return all known translation keys (union of all languages)."""
    keys = set()
    for d in I18N.values():
        keys.update(d.keys())
    return sorted(keys)


def missing_keys(lang: str) -> list[str]:
    """Return keys present in English but missing in the given language."""
    return [k for k in I18N["en"] if k not in I18N.get(lang, {})]
