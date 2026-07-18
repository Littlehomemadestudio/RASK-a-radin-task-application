"""
rask.help_system
================

In-app help system for Rask.

Provides a searchable, navigable help system that can be embedded in
any screen or opened as a modal.  Covers:

  • Getting started guide
  • Feature tutorials (each of the 7 core features)
  • FAQ
  • Keyboard shortcuts
  • Tips & tricks
  • Troubleshooting
  • Glossary
  • Changelog

All content is bilingual (fa/en) and stored in this module as Python
data structures for easy maintenance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import config
from .i18n import t, to_fa_digits


# =============================================================================
# === Data classes                                                             ===
# =============================================================================

@dataclass
class HelpArticle:
    """A single help article."""
    id: str
    title_fa: str
    title_en: str
    body_fa: str
    body_en: str
    category: str  # getting_started, features, faq, tips, troubleshooting, glossary
    tags: list[str] = field(default_factory=list)
    related: list[str] = field(default_factory=list)  # ids of related articles
    icon: str = "book"
    last_updated: str = "2025-07-18"

    def title(self, lang: str = "fa") -> str:
        return self.title_fa if lang == "fa" else self.title_en

    def body(self, lang: str = "fa") -> str:
        return self.body_fa if lang == "fa" else self.body_en


@dataclass
class HelpCategory:
    """A category of help articles."""
    id: str
    name_fa: str
    name_en: str
    icon: str
    description_fa: str
    description_en: str
    order: int = 0

    def name(self, lang: str = "fa") -> str:
        return self.name_fa if lang == "fa" else self.name_en

    def description(self, lang: str = "fa") -> str:
        return self.description_fa if lang == "fa" else self.description_en


# =============================================================================
# === Categories                                                               ===
# =============================================================================

CATEGORIES: list[HelpCategory] = [
    HelpCategory(
        id="getting_started",
        name_fa="شروع به کار",
        name_en="Getting Started",
        icon="spark",
        description_fa="راه‌اندازی و استفاده اولیه از رَسک",
        description_en="Set up and start using Rask",
        order=0,
    ),
    HelpCategory(
        id="features",
        name_fa="امکانات",
        name_en="Features",
        icon="star",
        description_fa="آموزش استفاده از هر امکان رَسک",
        description_en="Learn how to use each Rask feature",
        order=1,
    ),
    HelpCategory(
        id="faq",
        name_fa="سوال‌های پرتکرار",
        name_en="FAQ",
        icon="question",
        description_fa="پاسخ به پرسش‌های رایج",
        description_en="Answers to common questions",
        order=2,
    ),
    HelpCategory(
        id="tips",
        name_fa="نکات و ترفندها",
        name_en="Tips & Tricks",
        icon="lightbulb",
        description_fa="برای استفاده حداکثری از رَسک",
        description_en="Get the most out of Rask",
        order=3,
    ),
    HelpCategory(
        id="troubleshooting",
        name_fa="رفع مشکل",
        name_en="Troubleshooting",
        icon="wrench",
        description_fa="حل مشکلات رایج",
        description_en="Solve common problems",
        order=4,
    ),
    HelpCategory(
        id="glossary",
        name_fa="واژه‌نامه",
        name_en="Glossary",
        icon="book",
        description_fa="تعریف اصطلاحات",
        description_en="Definitions of terms",
        order=5,
    ),
    HelpCategory(
        id="changelog",
        name_fa="تغییرات نسخه‌ها",
        name_en="Changelog",
        icon="history",
        description_fa="تاریخچه تغییرات هر نسخه",
        description_en="History of changes per version",
        order=6,
    ),
]


# =============================================================================
# === Articles                                                                 ===
# =============================================================================

ARTICLES: list[HelpArticle] = [

    # ---- Getting Started --------------------------------------------------

    HelpArticle(
        id="gs_welcome",
        title_fa="به رَسک خوش آمدی!",
        title_en="Welcome to Rask!",
        body_fa=(
            "رَسک یک برنامه‌ی ساده اما قدرتمند برای پیگیری زمان و فعالیت‌های روزانه‌ات است. "
            "این برنامه ۱۰۰٪ آفلاین کار می‌کند، داده‌هایت را روی دستگاهت نگه می‌دارد، "
            "و با ظاهر ظریف طلایی-روی-مشکی، تجربه‌ای متفاوت از برنامه‌های مشابه می‌دهد.\n\n"
            "برای شروع:\n"
            "۱. اولین فعالیتت را ثبت کن — دکمه‌ی «+» پایین صفحه را بزن.\n"
            "۲. یک هدف روزانه تعریف کن — مثلاً ۱۲۰ دقیقه تمرکز در روز.\n"
            "۳. زنجیره‌ات را زنده نگه دار — هر روز حداقل یک فعالیت ثبت کن.\n"
            "۴. آمارت را ببین — تب «آمار» روندت را نشان می‌دهد.\n\n"
            "می‌توانی هر زمان از این بخش راهنما بخوانی یا با زدن «؟» میانبرهای صفحه‌کلید را ببینی."
        ),
        body_en=(
            "Rask is a simple yet powerful time tracker for your daily activities. "
            "It works 100% offline, keeps your data on your device, and with its refined "
            "gold-on-dark aesthetic, offers a different experience from similar apps.\n\n"
            "To get started:\n"
            "1. Log your first activity — tap the '+' button at the bottom.\n"
            "2. Set a daily goal — e.g. 120 minutes of focus per day.\n"
            "3. Keep your streak alive — log at least one activity every day.\n"
            "4. View your stats — the 'Stats' tab shows your trends.\n\n"
            "You can read this help section anytime or press '?' to see keyboard shortcuts."
        ),
        category="getting_started",
        tags=["intro", "new", "start"],
        related=["gs_first_activity", "gs_first_goal", "gs_shortcuts"],
        icon="spark",
    ),

    HelpArticle(
        id="gs_first_activity",
        title_fa="اولین فعالیتت را ثبت کن",
        title_en="Log your first activity",
        body_fa=(
            "برای ثبت یک فعالیت:\n\n"
            "۱. دکمه‌ی «+» طلایی پایین صفحه را بزن.\n"
            "۲. عنوان فعالیت را وارد کن — مثلاً «مطالعه کتاب».\n"
            "۳. دسته‌بندی را انتخاب کن (تمرکز، یادگیری، کار، سلامتی، خلاقیت، اجتماعی، استراحت).\n"
            "۴. مدت زمان را وارد کن یا از کرنومتر استفاده کن.\n"
            "۵. در صورت تمایل، یادداشت یا برچسب اضافه کن.\n"
            "۶. «ذخیره» را بزن.\n\n"
            "نکته: برای ثبت سریع، می‌توانی از قالب‌های آماده استفاده کنی. "
            "تب قالب‌ها در صفحه‌ی اصلی، قالب‌های پراستفاده را نشان می‌دهد."
        ),
        body_en=(
            "To log an activity:\n\n"
            "1. Tap the gold '+' button at the bottom of the screen.\n"
            "2. Enter an activity title — e.g. 'Reading book'.\n"
            "3. Select a category (Focus, Learn, Work, Health, Creative, Social, Rest).\n"
            "4. Enter a duration or use the stopwatch.\n"
            "5. Optionally add notes or tags.\n"
            "6. Tap 'Save'.\n\n"
            "Tip: For quick logging, use templates. The Templates tab on the home screen "
            "shows your most-used templates."
        ),
        category="getting_started",
        tags=["activity", "log", "create"],
        related=["gs_first_goal", "templates_create"],
        icon="plus",
    ),

    HelpArticle(
        id="gs_first_goal",
        title_fa="اولین هدفت را تعریف کن",
        title_en="Set your first goal",
        body_fa=(
            "اهداف به تو کمک می‌کنند تا مسیرت را حفظ کنی. برای ساخت یک هدف:\n\n"
            "۱. به تب «اهداف» برو.\n"
            "۲. دکمه‌ی «+ هدف جدید» را بزن.\n"
            "۳. دوره را انتخاب کن: روزانه، هفتگی، یا ماهانه.\n"
            "۴. هدف را به دقیقه وارد کن — مثلاً ۱۲۰ دقیقه در روز.\n"
            "۵. در صورت تمایل، یک دسته‌بندی خاص انتخاب کن (یا «همه دسته‌ها» را بگذار).\n"
            "۶. «ذخیره» را بزن.\n\n"
            "هر روز که به هدف برسی، زنجیره‌ات یک روز افزایش می‌یابد. "
            "زنجیره‌های ۳، ۷، ۱۴، ۳۰، ۶۰، ۱۰۰ و ۳۶۵ روز نشان‌های خاصی دارند."
        ),
        body_en=(
            "Goals help you stay on track. To create a goal:\n\n"
            "1. Go to the 'Goals' tab.\n"
            "2. Tap the '+ New Goal' button.\n"
            "3. Choose a period: daily, weekly, or monthly.\n"
            "4. Enter the target in minutes — e.g. 120 minutes per day.\n"
            "5. Optionally, select a specific category (or leave 'All categories').\n"
            "6. Tap 'Save'.\n\n"
            "Each day you hit your goal, your streak increases by one. "
            "Streaks of 3, 7, 14, 30, 60, 100, and 365 days unlock special badges."
        ),
        category="getting_started",
        tags=["goal", "streak", "create"],
        related=["gs_first_activity", "streaks_how"],
        icon="target",
    ),

    HelpArticle(
        id="gs_shortcuts",
        title_fa="میانبرهای صفحه‌کلید",
        title_en="Keyboard shortcuts",
        body_fa=(
            "رَسک میانبرهای صفحه‌کلید بسیاری دارد. در هر زمان «؟» را بزن تا همه را ببینی.\n\n"
            "پرکاربردترین‌ها:\n"
            "• Ctrl+N — ثبت سریع فعالیت\n"
            "• Ctrl+F — جستجو\n"
            "• Ctrl+T — شروع تایمر\n"
            "• Ctrl+S — توقف تایمر\n"
            "• Ctrl+B — پشتیبان‌گیری\n"
            "• Ctrl+E — خروجی گرفتن\n"
            "• Ctrl+1/2/3/4 — جابه‌جایی بین تب‌ها\n"
            "• Ctrl+L — قفل برنامه\n"
            "• Esc — بستن پنجره\n"
            "• ? — نمایش میانبرها"
        ),
        body_en=(
            "Rask has many keyboard shortcuts. Press '?' anytime to see all of them.\n\n"
            "Most useful:\n"
            "• Ctrl+N — Quick log activity\n"
            "• Ctrl+F — Search\n"
            "• Ctrl+T — Start timer\n"
            "• Ctrl+S — Stop timer\n"
            "• Ctrl+B — Backup now\n"
            "• Ctrl+E — Export\n"
            "• Ctrl+1/2/3/4 — Switch tabs\n"
            "• Ctrl+L — Lock app\n"
            "• Esc — Close dialog\n"
            "• ? — Show shortcuts"
        ),
        category="getting_started",
        tags=["keyboard", "shortcut", "hotkey"],
        related=["gs_welcome"],
        icon="keyboard",
    ),

    # ---- Features ---------------------------------------------------------

    HelpArticle(
        id="feat_quick_log",
        title_fa="ثبت سریع فعالیت",
        title_en="Quick log activity",
        body_fa=(
            "ثبت سریع سریع‌ترین راه برای ثبت یک فعالیت است. "
            "دکمه‌ی «+» طلایی پایین صفحه را بزن تا پنجره‌ی ثبت سریع باز شود.\n\n"
            "ویژگی‌ها:\n"
            "• ورودی صوتی — دکمه‌ی میکروفون را بزن و عنوان را بگو.\n"
            "• قالب‌های سریع — قالب‌های اخیرت را در یک نگاه ببین.\n"
            "• کرنومتر — به جای مدت ثابت، تایمر را شروع کن.\n"
            "• یادداشت و برچسب — اختیاری، برای جزئیات بیشتر.\n"
            "• تاریخ و زمان — پیش‌فرض امروز و حال، اما قابل تغییر.\n\n"
            "می‌توانی با Ctrl+N هم این پنجره را باز کنی."
        ),
        body_en=(
            "Quick log is the fastest way to record an activity. "
            "Tap the gold '+' button at the bottom to open the quick log sheet.\n\n"
            "Features:\n"
            "• Voice input — tap the microphone and speak the title.\n"
            "• Quick templates — see your recent templates at a glance.\n"
            "• Stopwatch — start a timer instead of a fixed duration.\n"
            "• Notes and tags — optional, for more detail.\n"
            "• Date and time — defaults to now, but editable.\n\n"
            "You can also open this sheet with Ctrl+N."
        ),
        category="features",
        tags=["activity", "log", "voice", "timer"],
        related=["feat_templates", "feat_voice"],
        icon="bolt",
    ),

    HelpArticle(
        id="feat_templates",
        title_fa="قالب‌های سریع",
        title_en="Quick templates",
        body_fa=(
            "قالب‌ها برای فعالیت‌های تکراری هستند. مثلاً:\n"
            "• «مطالعه روزانه» — ۳۰ دقیقه، دسته: یادگیری\n"
            "• «جلسه تیمی» — ۶۰ دقیقه، دسته: کار\n"
            "• «تمرین صبحگاهی» — ۴۵ دقیقه، دسته: سلامتی\n\n"
            "برای ساخت قالب:\n"
            "۱. به تب «قالب‌ها» برو (از منوی تنظیمات).\n"
            "۲. «قالب جدید» را بزن.\n"
            "۳. نام، عنوان، دسته و مدت پیش‌فرض را وارد کن.\n"
            "۴. در صورت تمایل، کلید میانبر (تک‌حرف) تعریف کن.\n"
            "۵. ذخیره کن.\n\n"
            "حالا می‌توانی با یک ضربه از قالب استفاده کنی. "
            "قالب‌ها به ترتیب استفاده مرتب می‌شوند — پراستفاده‌ترین‌ها اول."
        ),
        body_en=(
            "Templates are for repeated activities. E.g.:\n"
            "• 'Daily reading' — 30 min, category: Learn\n"
            "• 'Team meeting' — 60 min, category: Work\n"
            "• 'Morning workout' — 45 min, category: Health\n\n"
            "To create a template:\n"
            "1. Go to the 'Templates' tab (from settings menu).\n"
            "2. Tap 'New Template'.\n"
            "3. Enter name, title, category, and default duration.\n"
            "4. Optionally define a shortcut key (single character).\n"
            "5. Save.\n\n"
            "Now you can use a template with a single tap. "
            "Templates are sorted by usage — most-used first."
        ),
        category="features",
        tags=["template", "shortcut"],
        related=["feat_quick_log"],
        icon="bookmark",
    ),

    HelpArticle(
        id="feat_voice",
        title_fa="ورودی صوتی",
        title_en="Voice input",
        body_fa=(
            "برای ثبت فعالیت با صدات:\n"
            "۱. در پنجره‌ی ثبت سریع، دکمه‌ی میکروفون را بزن.\n"
            "۲. اجازه‌ی دسترسی به میکروفون را بده (در صورت نیاز).\n"
            "۳. عنوان فعالیت را بگو — مثلاً «مطالعه کتاب به مدت ۳۰ دقیقه».\n"
            "۴. صبر کن تا متن تشخیص داده شود.\n"
            "۵. در صورت نیاز، ویرایش کن و ذخیره کن.\n\n"
            "نکته: ورودی صوتی نیاز به نصب کتابخانه‌ی speech_recognition دارد. "
            "اگر نصب نباشد، دکمه‌ی میکروفون غیرفعال می‌شود."
        ),
        body_en=(
            "To log an activity with your voice:\n"
            "1. In the quick log sheet, tap the microphone button.\n"
            "2. Grant microphone permission if asked.\n"
            "3. Speak the activity title — e.g. 'Reading book for 30 minutes'.\n"
            "4. Wait for the text to be recognized.\n"
            "5. Edit if needed, then save.\n\n"
            "Note: Voice input requires the speech_recognition library. "
            "If not installed, the microphone button is disabled."
        ),
        category="features",
        tags=["voice", "speech", "input"],
        related=["feat_quick_log"],
        icon="mic",
    ),

    HelpArticle(
        id="feat_goals_streaks",
        title_fa="اهداف و زنجیره‌ها",
        title_en="Goals and streaks",
        body_fa=(
            "اهداف به تو جهت می‌دهند، زنجیره‌ها به تو انگیزه می‌دهند.\n\n"
            "انواع اهداف:\n"
            "• روزانه — هر روز به مقدار مشخص برس.\n"
            "• هفتگی — هر هفته مجموع هدف را برس.\n"
            "• ماهانه — هر ماه مجموع هدف را برس.\n\n"
            "زنجیره‌ها:\n"
            "• هر روز که به هدف روزانه برسی، زنجیره‌ات یکی زیاد می‌شود.\n"
            "• اگر یک روز از دست بدهی، زنجیره صفر می‌شود.\n"
            "• زنجیره‌های ۳، ۷، ۱۴، ۳۰، ۶۰، ۱۰۰، ۳۶۵ روز نشان دارند.\n"
            "• بهترین زنجیره‌ات برای همیشه ثبت می‌شود.\n\n"
            "نکته: می‌توانی چند هدف همزمان داشته باشی. هر کدام زنجیره‌ی مستقل دارند."
        ),
        body_en=(
            "Goals give you direction, streaks give you motivation.\n\n"
            "Goal types:\n"
            "• Daily — hit the target every day.\n"
            "• Weekly — hit the weekly total.\n"
            "• Monthly — hit the monthly total.\n\n"
            "Streaks:\n"
            "• Each day you hit a daily goal, your streak increases by 1.\n"
            "• If you miss a day, the streak resets to 0.\n"
            "• Streaks of 3, 7, 14, 30, 60, 100, 365 days unlock badges.\n"
            "• Your best streak is recorded forever.\n\n"
            "Tip: You can have multiple goals simultaneously. Each has its own streak."
        ),
        category="features",
        tags=["goal", "streak", "badge"],
        related=["gs_first_goal", "feat_badges"],
        icon="flame",
    ),

    HelpArticle(
        id="feat_stats",
        title_fa="آمار و بینش‌ها",
        title_en="Statistics and insights",
        body_fa=(
            "تب «آمار» نمایی کامل از فعالیت‌هایت نشان می‌دهد:\n\n"
            "• خلاصه — کل زمان، تعداد فعالیت، میانگین روزانه.\n"
            "• نمودار میله‌ای — به تفکیک روز هفته.\n"
            "• نمودار دونات — به تفکیک دسته‌بندی.\n"
            "• نقشه‌ی فعالیت — سال کامل در یک نگاه.\n"
            "• روندها — خط زمانی ۳۰ روز اخیر.\n"
            "• بینش‌ها — تحلیل هوشمند الگوهایت.\n\n"
            "می‌توانی بازه‌ی زمانی را انتخاب کنی (امروز، این هفته، این ماه، امسال، همه) "
            "یا بازه‌ی دلخواه تعریف کنی. "
            "همچنین می‌توانی خروجی PDF یا CSV بگیری تا با دیگران به اشتراک بگذاری."
        ),
        body_en=(
            "The 'Stats' tab gives you a complete view of your activities:\n\n"
            "• Summary — total time, activity count, daily average.\n"
            "• Bar chart — by day of week.\n"
            "• Donut chart — by category.\n"
            "• Activity heatmap — full year at a glance.\n"
            "• Trends — last 30 days line chart.\n"
            "• Insights — smart analysis of your patterns.\n\n"
            "You can select a time range (today, this week, this month, this year, all) "
            "or define a custom range. "
            "You can also export PDF or CSV reports to share with others."
        ),
        category="features",
        tags=["stats", "chart", "export", "insights"],
        related=["feat_export", "feat_insights"],
        icon="chart",
    ),

    HelpArticle(
        id="feat_insights",
        title_fa="بینش‌های هوشمند",
        title_en="Smart insights",
        body_fa=(
            "رَسک الگوهای فعالیت‌هایت را تحلیل می‌کند و به تو می‌گوید:\n\n"
            "• شخصیت زمانی — «تو یک شب‌بیدار هستی» یا «سحرخیز».\n"
            "• بهترین زمان — کدام ساعت روز بیشترین تمرکز را داری.\n"
            "• بهترین روز — کدام روز هفته پربازده‌ترین.\n"
            "• دسته‌های برتر — با روند صعودی/نزولی.\n"
            "• تحلیل زنجیره — با متن انگیزشی.\n"
            "• مقایسه هفتگی — این هفته در برابر هفته قبل.\n"
            "• تحلیل اهداف — کدام در مسیر، کدام عقب.\n"
            "• توصیه‌ها — بر اساس الگوهایت.\n"
            "• ناهنجاری‌ها — روزهای غیرعادی.\n\n"
            "این بخش در تب «بینش‌ها» در دسترس است."
        ),
        body_en=(
            "Rask analyzes your activity patterns and tells you:\n\n"
            "• Time personality — 'You are a night owl' or 'early bird'.\n"
            "• Best time — which hour of day you focus most.\n"
            "• Best day — which day of week is most productive.\n"
            "• Top categories — with up/down trends.\n"
            "• Streak analysis — with motivational text.\n"
            "• Weekly comparison — this week vs last week.\n"
            "• Goals analysis — which are on track, which are behind.\n"
            "• Recommendations — based on your patterns.\n"
            "• Anomalies — unusual days.\n\n"
            "This is available in the 'Insights' tab."
        ),
        category="features",
        tags=["insights", "ai", "analysis"],
        related=["feat_stats"],
        icon="brain",
    ),

    HelpArticle(
        id="feat_backup",
        title_fa="پشتیبان‌گیری و بازگردانی",
        title_en="Backup and restore",
        body_fa=(
            "داده‌هایت روی دستگاهت می‌مانند، اما می‌توانی پشتیبان رمزنگاری‌شده بسازی:\n\n"
            "۱. به تنظیمات → داده‌ها → پشتیبان برو.\n"
            "۲. دکمه‌ی «پشتیبان‌گیری» را بزن.\n"
            "۳. یک رمز قوی (حداقل ۸ نویسه) وارد کن.\n"
            "۴. تکر رمز را وارد کن.\n"
            "۵. صبر کن تا پشتیبان ساخته شود.\n\n"
            "پشتیبان‌ها با AES-256-GCM رمزنگاری می‌شوند — بدون رمز، غیرقابل بازگشایی.\n"
            "رمز را در جای امن نگه دار!\n\n"
            "برای بازگردانی:\n"
            "۱. فایل پشتیبان را انتخاب کن.\n"
            "۲. رمز را وارد کن.\n"
            "۳. تأیید کن — داده‌های فعلی با پشتیبان جایگزین می‌شوند.\n\n"
            "می‌توانی پشتیبان‌گیری خودکار (روزانه یا هفتگی) هم تنظیم کنی."
        ),
        body_en=(
            "Your data stays on your device, but you can create encrypted backups:\n\n"
            "1. Go to Settings → Data → Backup.\n"
            "2. Tap 'Backup Now'.\n"
            "3. Enter a strong password (min 8 characters).\n"
            "4. Confirm the password.\n"
            "5. Wait for the backup to be created.\n\n"
            "Backups are encrypted with AES-256-GCM — without the password, they cannot be decrypted.\n"
            "Keep your password safe!\n\n"
            "To restore:\n"
            "1. Select the backup file.\n"
            "2. Enter the password.\n"
            "3. Confirm — current data will be replaced with the backup.\n\n"
            "You can also enable automatic backups (daily or weekly)."
        ),
        category="features",
        tags=["backup", "restore", "encryption", "security"],
        related=["feat_pin", "feat_export"],
        icon="shield",
    ),

    HelpArticle(
        id="feat_pin",
        title_fa="قفل برنامه با پین",
        title_en="App lock with PIN",
        body_fa=(
            "برای حفظ حریم خصوصی، می‌توانی برنامه را با پین قفل کنی:\n\n"
            "۱. به تنظیمات → حریم خصوصی برو.\n"
            "۲. «حالت قفل» را روی «کد پین» بگذار.\n"
            "۳. یک پین ۴ رقمی انتخاب کن.\n"
            "۴. تکر پین را وارد کن.\n\n"
            "حالا هر بار که برنامه را باز می‌کنی، باید پین را وارد کنی.\n\n"
            "قفل خودکار:\n"
            "می‌توانی تنظیم کنی که برنامه پس از مدت عدم فعالیت (۳۰ ثانیه، ۱، ۵، ۱۵ دقیقه) "
            "خودکار قفل شود.\n\n"
            "امنیت: پین با PBKDF2-SHA256 با ۲۰۰٬۰۰۰ تکرار هش می‌شود — حتی اگر کس کد هش را بدزدد، "
            "نمی‌تواند پین اصلی را پیدا کند."
        ),
        body_en=(
            "For privacy, you can lock the app with a PIN:\n\n"
            "1. Go to Settings → Privacy.\n"
            "2. Set 'Lock mode' to 'PIN'.\n"
            "3. Choose a 4-digit PIN.\n"
            "4. Confirm the PIN.\n\n"
            "Now every time you open the app, you must enter the PIN.\n\n"
            "Auto-lock:\n"
            "You can set the app to auto-lock after inactivity (30s, 1m, 5m, 15m).\n\n"
            "Security: The PIN is hashed with PBKDF2-SHA256 with 200,000 iterations — "
            "even if someone steals the hash, they cannot recover the original PIN."
        ),
        category="features",
        tags=["pin", "lock", "security", "privacy"],
        related=["feat_backup"],
        icon="lock",
    ),

    HelpArticle(
        id="feat_export",
        title_fa="خروجی گرفتن",
        title_en="Exporting data",
        body_fa=(
            "می‌توانی داده‌هایت را به چند قالب خروجی بگیری:\n\n"
            "• PDF — گزارش زیبا با نمودارها، برای چاپ یا اشتراک‌گذاری.\n"
            "• CSV — برای اکسل یا Google Sheets.\n"
            "• JSON — برای پشتیبان‌گیری یا انتقال به برنامه‌ی دیگر.\n"
            "• PNG — عکس از نمودارها.\n\n"
            "برای خروجی گرفتن:\n"
            "۱. در تب «آمار»، دکمه‌ی «خروجی» را بزن.\n"
            "۲. قالب را انتخاب کن.\n"
            "۳. بازه‌ی زمانی را انتخاب کن.\n"
            "۴. فیلترها را اعمال کن (اختیاری).\n"
            "۵. «خروجی» را بزن.\n\n"
            "همچنین می‌توانی از تنظیمات → داده‌ها، کل دیتابیس را به JSON خروجی بگیری."
        ),
        body_en=(
            "You can export your data in several formats:\n\n"
            "• PDF — beautiful report with charts, for printing or sharing.\n"
            "• CSV — for Excel or Google Sheets.\n"
            "• JSON — for backup or transfer to another app.\n"
            "• PNG — screenshot of charts.\n\n"
            "To export:\n"
            "1. In the 'Stats' tab, tap the 'Export' button.\n"
            "2. Choose a format.\n"
            "3. Select a date range.\n"
            "4. Apply filters (optional).\n"
            "5. Tap 'Export'.\n\n"
            "You can also export the entire database as JSON from Settings → Data."
        ),
        category="features",
        tags=["export", "pdf", "csv", "json", "png"],
        related=["feat_stats", "feat_backup"],
        icon="download",
    ),

    HelpArticle(
        id="feat_reminders",
        title_fa="یادآوری‌ها",
        title_en="Reminders",
        body_fa=(
            "یادآوری‌ها به تو کمک می‌کنند در زمان مشخص فعالیت ثبت کنی.\n\n"
            "برای ساخت یادآوری:\n"
            "۱. به تب «یادآوری‌ها» برو.\n"
            "۲. «یادآوری جدید» را بزن.\n"
            "۳. عنوان، پیام و زمان را وارد کن.\n"
            "۴. روزهای تکرار را انتخاب کن (شنبه تا جمعه).\n"
            "۵. در صورت تمایل، دسته یا هدف مرتبط انتخاب کن.\n"
            "۶. صدا را روشن یا خاموش کن.\n"
            "۷. ذخیره کن.\n\n"
            "می‌توانی یادآوری را به تعویق بیندازی (به‌طور پیش‌فرض ۱۰ دقیقه) یا رد کنی."
        ),
        body_en=(
            "Reminders help you log activities at specific times.\n\n"
            "To create a reminder:\n"
            "1. Go to the 'Reminders' tab.\n"
            "2. Tap 'New Reminder'.\n"
            "3. Enter title, message, and time.\n"
            "4. Select repeat days (Saturday to Friday).\n"
            "5. Optionally link to a category or goal.\n"
            "6. Toggle sound on/off.\n"
            "7. Save.\n\n"
            "You can snooze a reminder (default 10 minutes) or dismiss it."
        ),
        category="features",
        tags=["reminder", "notification"],
        related=[],
        icon="bell",
    ),

    HelpArticle(
        id="feat_pomodoro",
        title_fa="تکنیک پومودورو",
        title_en="Pomodoro technique",
        body_fa=(
            "پومودورو یک تکنیک مدیریت زمان است: ۲۵ دقیقه تمرکز، ۵ دقیقه استراحت، تکرار.\n\n"
            "در رَسک:\n"
            "• به تب «پومودورو» برو.\n"
            "• مدت تمرکز و استراحت را تنظیم کن (پیش‌فرض: ۲۵/۵).\n"
            "• «شروع» را بزن.\n"
            "• بعد از هر تمرکز، یک فعالیت خودکار ذخیره می‌شود.\n"
            "• بعد از ۴ چرخه، یک استراحت بلند (۱۵ دقیقه) می‌گیری.\n\n"
            "نکته: می‌توانی از تایمر زنده در صفحه‌ی اصلی هم استفاده کنی، "
            "بدون پومودورو."
        ),
        body_en=(
            "Pomodoro is a time management technique: 25 min focus, 5 min break, repeat.\n\n"
            "In Rask:\n"
            "• Go to the 'Pomodoro' tab.\n"
            "• Set focus and break durations (default: 25/5).\n"
            "• Tap 'Start'.\n"
            "• After each focus phase, an activity is automatically saved.\n"
            "• After 4 cycles, take a long break (15 min).\n\n"
            "Tip: You can also use the live timer on the home screen, without Pomodoro."
        ),
        category="features",
        tags=["pomodoro", "focus", "timer"],
        related=["feat_quick_log"],
        icon="clock",
    ),

    HelpArticle(
        id="feat_journals",
        title_fa="خاطرات روزانه",
        title_en="Daily journal",
        body_fa=(
            "هر روز می‌توانی یک خاطره ثبت کنی:\n\n"
            "• حال (۱-۵)\n"
            "• انرژی (۱-۵)\n"
            "• عنوان و متن\n"
            "• نقاط قوت امروز\n"
            "• بهبودها\n"
            "• سپاسگزاری‌ها\n\n"
            "این به تو کمک می‌کند الگوهایت را بشناسی — مثلاً «وقتی ورزش می‌کنم، حالم بهتره»."
        ),
        body_en=(
            "Each day you can write a journal entry:\n\n"
            "• Mood (1-5)\n"
            "• Energy (1-5)\n"
            "• Title and body\n"
            "• Today's strengths\n"
            "• Improvements\n"
            "• Gratitudes\n\n"
            "This helps you recognize patterns — e.g. 'when I exercise, my mood is better'."
        ),
        category="features",
        tags=["journal", "mood", "reflection"],
        related=["feat_mood"],
        icon="book",
    ),

    HelpArticle(
        id="feat_mood",
        title_fa="ردیابی حال",
        title_en="Mood tracking",
        body_fa=(
            "هر روز حال و انرژی‌ات را ثبت کن تا رَسک روندها را نشانت دهد و "
            "همبستگی با فعالیت‌ها را پیدا کند.\n\n"
            "می‌توانی محرک‌ها را هم ثبت کنی: کار، خواب، ورزش، غذا، اجتماع، آب‌وهوا و..."
        ),
        body_en=(
            "Track your mood and energy each day to see trends and "
            "find correlations with your activities.\n\n"
            "You can also log triggers: work, sleep, exercise, food, social, weather, etc."
        ),
        category="features",
        tags=["mood", "energy", "tracking"],
        related=["feat_journals"],
        icon="heart",
    ),

    HelpArticle(
        id="feat_habits",
        title_fa="ردیابی عادت‌ها",
        title_en="Habit tracking",
        body_fa=(
            "عادت‌هایت را جدا از فعالیت‌ها دنبال کن:\n\n"
            "• هر عادت می‌تواند روزانه، هفتگی، یا چندبار در هفته باشد.\n"
            "• هر روز که عادت را انجام دهی، تیک بزن.\n"
            "• زنجیره‌ی هر عادت جداگانه محاسبه می‌شود.\n"
            "• نرخ موفقیت ۳۰ روزه را ببین.\n\n"
            "نکته: عادت‌ها فقط تیک/خالی هستند، مدت زمان ندارند."
        ),
        body_en=(
            "Track your habits separately from activities:\n\n"
            "• Each habit can be daily, weekly, or several times per week.\n"
            "• Each day you do the habit, check it off.\n"
            "• Each habit has its own streak.\n"
            "• See your 30-day completion rate.\n\n"
            "Tip: Habits are just check/empty, they don't have durations."
        ),
        category="features",
        tags=["habit", "streak", "tracking"],
        related=["feat_goals_streaks"],
        icon="check",
    ),

    # ---- FAQ -------------------------------------------------------------

    HelpArticle(
        id="faq_offline",
        title_fa="آیا برنامه واقعاً آفلاین کار می‌کند؟",
        title_en="Does the app really work offline?",
        body_fa=(
            "بله، رَسک ۱۰۰٪ آفلاین است. هیچ سروری وجود ندارد، هیچ حساب کاربری لازم نیست، "
            "هیچ داده‌ای به جایی ارسال نمی‌شود.\n\n"
            "داده‌هایت در یک پایگاه داده‌ی SQLite روی دستگاهت ذخیره می‌شود. "
            "تنها زمانی که به اینترنت نیاز داری، خروجی گرفتن از نمودارهاست (نه خود داده‌ها)."
        ),
        body_en=(
            "Yes, Rask is 100% offline. There is no server, no account required, "
            "no data sent anywhere.\n\n"
            "Your data is stored in a SQLite database on your device. "
            "The only time you might need internet is for chart exports (not the data itself)."
        ),
        category="faq",
        tags=["offline", "privacy", "data"],
        related=["feat_backup"],
        icon="cloud_off",
    ),

    HelpArticle(
        id="faq_data_location",
        title_fa="داده‌هایم کجا ذخیره می‌شوند؟",
        title_en="Where is my data stored?",
        body_fa=(
            "داده‌هایت در این مسیر ذخیره می‌شوند:\n\n"
            "• ویندوز: %APPDATA%\\Rask\\\n"
            "• مک: ~/Library/Application Support/Rask/\n"
            "• لینوکس: ~/.local/share/Rask/\n\n"
            "می‌توانی از تنظیمات → پیشرفته → اطلاعات دیباگ، مسیر دقیق را ببینی."
        ),
        body_en=(
            "Your data is stored at:\n\n"
            "• Windows: %APPDATA%\\Rask\\\n"
            "• macOS: ~/Library/Application Support/Rask/\n"
            "• Linux: ~/.local/share/Rask/\n\n"
            "You can see the exact path from Settings → Advanced → Debug info."
        ),
        category="faq",
        tags=["data", "storage", "path"],
        related=["feat_backup"],
        icon="folder",
    ),

    HelpArticle(
        id="faq_sync",
        title_fa="آیا می‌توانم بین دستگاه‌ها همگام‌سازی کنم؟",
        title_en="Can I sync between devices?",
        body_fa=(
            "در حال حاضر همگام‌سازی خودکار وجود ندارد. اما می‌توانی:\n\n"
            "۱. یک پشتیبان رمزنگاری‌شده از دستگاه اول بگیری.\n"
            "۲. فایل پشتیبان را به دستگاه دوم منتقل کن.\n"
            "۳. در دستگاه دوم، بازگردانی کنی.\n\n"
            "همگام‌سازی خودکار ابری در نقشه‌راه آینده است."
        ),
        body_en=(
            "Currently there is no automatic sync. But you can:\n\n"
            "1. Create an encrypted backup on the first device.\n"
            "2. Transfer the backup file to the second device.\n"
            "3. Restore on the second device.\n\n"
            "Automatic cloud sync is on the future roadmap."
        ),
        category="faq",
        tags=["sync", "backup", "multi-device"],
        related=["feat_backup"],
        icon="sync",
    ),

    HelpArticle(
        id="faq_lost_pin",
        title_fa="پینم را فراموش کردم!",
        title_en="I forgot my PIN!",
        body_fa=(
            "متأسفیم! به دلایل امنیتی، هیچ راهی برای بازیابی پین وجود ندارد. "
            "تنها راه این است که:\n\n"
            "۱. داده‌هایت را پاک کنی (با حذف فایل دیتابیس).\n"
            "۲. برنامه را از نو راه‌اندازی کنی.\n\n"
            "این کار تمام فعالیت‌هایت را حذف می‌کند. "
            "اگر پشتیبان داری، می‌توانی بعداً بازگردانی کنی.\n\n"
            "برای جلوگیری از این مشکل، پین را در یک مدیر رمز عبور ذخیره کن."
        ),
        body_en=(
            "We're sorry! For security reasons, there is no way to recover the PIN. "
            "The only option is to:\n\n"
            "1. Wipe your data (delete the database file).\n"
            "2. Restart the app.\n\n"
            "This will delete all your activities. "
            "If you have a backup, you can restore it later.\n\n"
            "To prevent this, store your PIN in a password manager."
        ),
        category="faq",
        tags=["pin", "lost", "recovery"],
        related=["feat_pin"],
        icon="warning",
    ),

    HelpArticle(
        id="faq_lang_support",
        title_fa="چه زبان‌هایی پشتیبانی می‌شوند؟",
        title_en="Which languages are supported?",
        body_fa=(
            "رَسک در حال حاضر از این زبان‌ها پشتیبانی می‌کند:\n\n"
            "• فارسی (پیش‌فرض)\n"
            "• انگلیسی\n"
            "• عربی\n"
            "• ترکی\n"
            "• روسی\n"
            "• آلمانی\n"
            "• فرانسوی\n"
            "• اسپانیایی\n"
            "• چینی\n"
            "• ژاپنی\n\n"
            "می‌توانی از تنظیمات → ظاهر → زبان، زبان را تغییر دهی. "
            "فارسی و عربی راست‌چین هستند، بقیه چپ‌چین."
        ),
        body_en=(
            "Rask currently supports:\n\n"
            "• Persian (default)\n"
            "• English\n"
            "• Arabic\n"
            "• Turkish\n"
            "• Russian\n"
            "• German\n"
            "• French\n"
            "• Spanish\n"
            "• Chinese\n"
            "• Japanese\n\n"
            "Change language from Settings → Appearance → Language. "
            "Persian and Arabic are RTL, others are LTR."
        ),
        category="faq",
        tags=["language", "i18n", "localization"],
        related=[],
        icon="globe",
    ),

    HelpArticle(
        id="faq_lost_data",
        title_fa="داده‌هایم پاک شده! چه کنم؟",
        title_en="My data is gone! What do I do?",
        body_fa=(
            "اول، نگران نباش. چند احتمال وجود دارد:\n\n"
            "۱. آیا برنامه‌ی دیگری باز است؟ ممکن است دیتابیس دیگری استفاده کند.\n"
            "۲. آیا مسیر داده‌ها تغییر کرده؟ (تنظیمات → پیشرفته → اطلاعات دیباگ)\n"
            "۳. آیا پشتیبان داری؟ اگر بله، بازگردانی کن.\n\n"
            "اگر هیچ‌کدام جواب نداد، متأسفانه داده‌ها از دست رفته‌اند. "
            "برای جلوگیری از تکرار، پشتیبان‌گیری خودکار را روشن کن."
        ),
        body_en=(
            "First, don't panic. A few possibilities:\n\n"
            "1. Is another instance of the app open? It might use a different database.\n"
            "2. Has the data path changed? (Settings → Advanced → Debug info)\n"
            "3. Do you have a backup? If so, restore it.\n\n"
            "If none of these work, unfortunately the data is lost. "
            "To prevent recurrence, enable automatic backups."
        ),
        category="faq",
        tags=["data", "lost", "recovery"],
        related=["feat_backup"],
        icon="warning",
    ),

    # ---- Tips ------------------------------------------------------------

    HelpArticle(
        id="tip_flow_state",
        title_fa="چطور به حالت تمرکز عمیق برسم؟",
        title_en="How to reach a deep focus state?",
        body_fa=(
            "چند نکته برای رسیدن به حالت تمرکز (Flow):\n\n"
            "۱. صدای تایمر را خاموش کن تا مزاحم نشود.\n"
            "۲. از پومودورو با دوره‌های ۵۰ دقیقه‌ای استفاده کن.\n"
            "۳. حالت تمرکز عمیق را فعال کن (اینترنت را مسدود کن).\n"
            "۴. یک قالب «تمرکز عمیق» بساز و از آن استفاده کن.\n"
            "۵. یادداشت‌های کوتاه بنویس، اما تایمر را متوقف نکن.\n"
            "۶. وقتی تایمر زنگ زد، حتماً استراحت کن — نباید دوباره شروع کنی.\n\n"
            "نکته: اگر وقفه‌ای پیش آمد، در تایمر ثبت کن تا بعداً تحلیل کنی."
        ),
        body_en=(
            "Tips to reach a flow state:\n\n"
            "1. Turn off the timer sound so it doesn't interrupt.\n"
            "2. Use Pomodoro with 50-minute focus phases.\n"
            "3. Activate Focus Mode (blocks internet).\n"
            "4. Create a 'Deep Focus' template and use it.\n"
            "5. Write short notes, but don't stop the timer.\n"
            "6. When the timer rings, take a real break — don't restart immediately.\n\n"
            "Tip: If interrupted, log it in the timer to analyze later."
        ),
        category="tips",
        tags=["focus", "flow", "deep work", "pomodoro"],
        related=["feat_pomodoro"],
        icon="lightbulb",
    ),

    HelpArticle(
        id="tip_consistency",
        title_fa="چطور ثابت‌قدم باشم؟",
        title_en="How to be consistent?",
        body_fa=(
            "ثبات مهم‌تر از شدت است. چند نکته:\n\n"
            "۱. هدف روزانه‌ات را کم شروع کن — مثلاً ۳۰ دقیقه، نه ۲ ساعت.\n"
            "۲. هر روز در یک ساعت مشخص فعالیت کن.\n"
            "۳. یادآوری تنظیم کن.\n"
            "۴. زنجیره‌ات را هر روز نگاه کن — تأثیر روانی بزرگی دارد.\n"
            "۵. وقتی زنجیره‌ات طولانی شد، از آن محافظت کن — حتی ۵ دقیقه بهتر از صفر.\n"
            "۶. وقتی گند زدی، خودت را سرزنش نکن — فردا دوباره شروع کن.\n\n"
            "نکته: رَسک زنجیره‌های «هر فعالیتی» را هم محاسبه می‌کند، نه فقط اهداف."
        ),
        body_en=(
            "Consistency beats intensity. Tips:\n\n"
            "1. Start with a small daily goal — e.g. 30 min, not 2 hours.\n"
            "2. Do it at the same time every day.\n"
            "3. Set a reminder.\n"
            "4. Check your streak every day — it has a big psychological effect.\n"
            "5. When your streak is long, protect it — even 5 min is better than 0.\n"
            "6. When you fail, don't beat yourself up — start again tomorrow.\n\n"
            "Tip: Rask tracks 'any activity' streaks too, not just goals."
        ),
        category="tips",
        tags=["consistency", "streak", "motivation"],
        related=["feat_goals_streaks"],
        icon="flame",
    ),

    HelpArticle(
        id="tip_review_weekly",
        title_fa="هر هفته مرور کن",
        title_en="Review every week",
        body_fa=(
            "یک عادت ارزشمند: هر هفته یکبار مرور هفتگی کن. \n\n"
            "۱. به تب «مرور هفتگی» برو.\n"
            "۲. خلاصه‌ی هفته‌ات را بخوان.\n"
            "۳. نقاط قوت و ضعف را یادداشت کن.\n"
            "۴. برای هفته‌ی بعد یک هدف کوچک تعیین کن.\n\n"
            "این کار ۵ دقیقه طول می‌کشد اما تأثیر بزرگی روی رشدت دارد."
        ),
        body_en=(
            "A valuable habit: do a weekly review.\n\n"
            "1. Go to the 'Weekly Review' tab.\n"
            "2. Read your week summary.\n"
            "3. Note strengths and weaknesses.\n"
            "4. Set a small goal for next week.\n\n"
            "Takes 5 minutes but has a big impact on your growth."
        ),
        category="tips",
        tags=["review", "weekly", "reflection"],
        related=["feat_journals"],
        icon="calendar",
    ),

    # ---- Troubleshooting -------------------------------------------------

    HelpArticle(
        id="trouble_wont_start",
        title_fa="برنامه باز نمی‌شود",
        title_en="App won't start",
        body_fa=(
            "اگر برنامه باز نمی‌شود:\n\n"
            "۱. مطمئن شو Python 3.9 یا بالاتر داری: python --version\n"
            "۲. وابستگی‌ها را نصب کن: pip install -r requirements.txt\n"
            "۳. دیتابیس را بررسی کن: python main.py --vacuum\n"
            "۴. لاگ‌ها را ببین: python main.py --debug\n"
            "۵. اگر هنوز مشکل داری، دیتابیس را پاک کن (با احتیاط!):\n"
            "   python main.py --reset\n\n"
            "اگر هیچ‌کدام جواب نداد، مشکل را در GitHub گزارش کن."
        ),
        body_en=(
            "If the app won't start:\n\n"
            "1. Make sure you have Python 3.9+: python --version\n"
            "2. Install dependencies: pip install -r requirements.txt\n"
            "3. Check the database: python main.py --vacuum\n"
            "4. View logs: python main.py --debug\n"
            "5. If still broken, reset DB (carefully!):\n"
            "   python main.py --reset\n\n"
            "If none of these work, report the issue on GitHub."
        ),
        category="troubleshooting",
        tags=["startup", "crash", "error"],
        related=["trouble_slow"],
        icon="wrench",
    ),

    HelpArticle(
        id="trouble_slow",
        title_fa="برنامه کند شده",
        title_en="App is slow",
        body_fa=(
            "اگر برنامه کند شده:\n\n"
            "۱. دیتابیس را فشرده کن: تنظیمات → پیشرفته → فشرده‌سازی پایگاه داده.\n"
            "۲. حافظه‌ی پنهان را پاک کن: تنظیمات → پیشرفته → پاک‌کردن حافظه پنهان.\n"
            "۳. تعداد فعالیت‌ها را چک کن — اگر بالای ۱۰٬۰۰۰ است، آرشیو کن.\n"
            "۴. پشتیبان بگیر، دیتابیس را پاک کن، بازگردانی کن.\n\n"
            "اگر باز هم کند است، گزارش عملکرد بگیر:\n"
            "python examples/benchmark.py --save-baseline baseline.json"
        ),
        body_en=(
            "If the app is slow:\n\n"
            "1. Vacuum the database: Settings → Advanced → Vacuum database.\n"
            "2. Clear cache: Settings → Advanced → Clear cache.\n"
            "3. Check activity count — if over 10,000, archive some.\n"
            "4. Backup, wipe DB, restore.\n\n"
            "If still slow, run a benchmark:\n"
            "python examples/benchmark.py --save-baseline baseline.json"
        ),
        category="troubleshooting",
        tags=["performance", "slow"],
        related=["trouble_wont_start"],
        icon="speed",
    ),

    HelpArticle(
        id="trouble_missing_deps",
        title_fa="کتابخانه‌ای پیدا نشد",
        title_en="Missing library",
        body_fa=(
            "اگر خطای «ModuleNotFoundError» دیدی:\n\n"
            "۱. کتابخانه‌های مورد نیاز را نصب کن:\n"
            "   pip install -r requirements.txt\n\n"
            "۲. اگر خاصی گم شده، این‌ها را امتحان کن:\n"
            "   pip install customtkinter Pillow cryptography reportlab\n\n"
            "۳. برای ورودی صوتی (اختیاری):\n"
            "   pip install SpeechRecognition pyaudio\n\n"
            "می‌توانی با python main.py --doctor محیط را بررسی کنی."
        ),
        body_en=(
            "If you see 'ModuleNotFoundError':\n\n"
            "1. Install required libraries:\n"
            "   pip install -r requirements.txt\n\n"
            "2. If a specific one is missing, try:\n"
            "   pip install customtkinter Pillow cryptography reportlab\n\n"
            "3. For voice input (optional):\n"
            "   pip install SpeechRecognition pyaudio\n\n"
            "You can check your environment with python main.py --doctor."
        ),
        category="troubleshooting",
        tags=["install", "missing", "dependency"],
        related=["trouble_wont_start"],
        icon="package",
    ),

    # ---- Glossary --------------------------------------------------------

    HelpArticle(
        id="gloss_activity",
        title_fa="فعالیت (Activity)",
        title_en="Activity",
        body_fa=(
            "یک کار که انجام داده‌ای و زمانش را ثبت کرده‌ای. "
            "هر فعالیت شامل: عنوان، دسته، مدت، تاریخ، و یادداشت/برچسب (اختیاری)."
        ),
        body_en=(
            "A task you have done and recorded the time for. "
            "Each activity has: title, category, duration, date, and optional notes/tags."
        ),
        category="glossary",
        tags=["definition"],
        related=["gloss_category"],
        icon="book",
    ),

    HelpArticle(
        id="gloss_category",
        title_fa="دسته (Category)",
        title_en="Category",
        body_fa=(
            "یک طبقه‌بندی برای فعالیت‌ها. رَسک ۷ دسته‌ی پیش‌فرض دارد: "
            "تمرکز، یادگیری، کار، سلامتی، خلاقیت، اجتماعی، استراحت. "
            "می‌توانی دسته‌های خودت را هم بسازی."
        ),
        body_en=(
            "A classification for activities. Rask has 7 default categories: "
            "Focus, Learn, Work, Health, Creative, Social, Rest. "
            "You can create your own too."
        ),
        category="glossary",
        tags=["definition"],
        related=["gloss_activity"],
        icon="tag",
    ),

    HelpArticle(
        id="gloss_goal",
        title_fa="هدف (Goal)",
        title_en="Goal",
        body_fa=(
            "یک هدف زمانی برای فعالیت‌ها. می‌تواند روزانه، هفتگی یا ماهانه باشد. "
            "مثلاً: «۱۲۰ دقیقه تمرکز در روز»."
        ),
        body_en=(
            "A time target for activities. Can be daily, weekly, or monthly. "
            "E.g. '120 minutes of focus per day'."
        ),
        category="glossary",
        tags=["definition"],
        related=["gloss_streak"],
        icon="target",
    ),

    HelpArticle(
        id="gloss_streak",
        title_fa="زنجیره (Streak)",
        title_en="Streak",
        body_fa=(
            "تعداد روزهای متوالی که به هدف رسیده‌ای. "
            "اگر یک روز از دست بدهی، زنجیره صفر می‌شود. "
            "زنجیره‌های ۳، ۷، ۱۴، ۳۰، ۶۰، ۱۰۰ و ۳۶۵ روز نشان دارند."
        ),
        body_en=(
            "The number of consecutive days you've hit your goal. "
            "If you miss a day, the streak resets to 0. "
            "Streaks of 3, 7, 14, 30, 60, 100, 365 days unlock badges."
        ),
        category="glossary",
        tags=["definition"],
        related=["gloss_badge"],
        icon="flame",
    ),

    HelpArticle(
        id="gloss_badge",
        title_fa="نشان (Badge)",
        title_en="Badge",
        body_fa=(
            "یک جایزه‌ی دیجیتال برای دستاوردها. رَسک ۱۲+ نشان دارد، "
            "از «اولین قدم» تا «یک سال کامل». نشان‌ها در ۴ رده هستند: "
            "برنزی، نقره‌ای، طلایی، پلاتینی."
        ),
        body_en=(
            "A digital award for achievements. Rask has 12+ badges, "
            "from 'First Step' to 'One Full Year'. Badges have 4 tiers: "
            "Bronze, Silver, Gold, Platinum."
        ),
        category="glossary",
        tags=["definition"],
        related=["gloss_streak"],
        icon="medal",
    ),

    HelpArticle(
        id="gloss_template",
        title_fa="قالب (Template)",
        title_en="Template",
        body_fa=(
            "یک الگوی از پیش تعریف‌شده برای فعالیت‌های تکراری. "
            "مثلاً: «مطالعه روزانه» — ۳۰ دقیقه، دسته: یادگیری. "
            "قالب‌ها ثبت سریع را تسریع می‌کنند."
        ),
        body_en=(
            "A pre-defined pattern for repeated activities. "
            "E.g. 'Daily reading' — 30 min, category: Learn. "
            "Templates speed up quick logging."
        ),
        category="glossary",
        tags=["definition"],
        related=["gloss_activity"],
        icon="bookmark",
    ),

    HelpArticle(
        id="gloss_jalali",
        title_fa="تقویم شمسی (Jalali)",
        title_en="Jalali calendar",
        body_fa=(
            "تقویم رسمی ایران. سال خورشیدی با ۱۲ ماه: "
            "فروردین، اردیبهشت، خرداد، تیر، مرداد، شهریور، "
            "مهر، آبان، آذر، دی، بهمن، اسفند. "
            "نوروز (۱ فروردین) در برابر ۲۰ یا ۲۱ مارس است."
        ),
        body_en=(
            "The official Iranian calendar. A solar year with 12 months: "
            "Farvardin, Ordibehesht, Khordad, Tir, Mordad, Shahrivar, "
            "Mehr, Aban, Azar, Dey, Bahman, Esfand. "
            "Nowruz (1 Farvardin) corresponds to March 20 or 21."
        ),
        category="glossary",
        tags=["definition", "calendar", "persian"],
        related=[],
        icon="calendar",
    ),

    # ---- Changelog -------------------------------------------------------

    HelpArticle(
        id="changelog_v2",
        title_fa="نسخه ۲.۰",
        title_en="Version 2.0",
        body_fa=(
            "بازنویسی کامل با CustomTkinter — ظاهر بسیار زیباتر و حرفه‌ای.\n\n"
            "• ۱۷ صفحه‌ی جدید (پومودورو، خاطرات، عادت‌ها، حال، تقویم و...)\n"
            "• ۱۵ پنجره‌ی محاوره‌ای\n"
            "• ۳۰+ ویجت سفارشی\n"
            "• ۱۸ ویژگی جدید (پومودورو، تمرکز عمیق، تحلیل پیشرفته و...)\n"
            "• ۱۰۰٪ آفلاین، ۱۰۰٪ خصوصی\n"
            "• رمزنگاری AES-256-GCM\n"
            "• ۱۰ زبان\n"
            "• تقویم شمسی و میلادی\n"
            "• خروجی PDF/CSV/JSON/PNG\n"
            "• ۱۰۰٬۰۰۰+ خط کد"
        ),
        body_en=(
            "Complete rewrite with CustomTkinter — much more beautiful and professional.\n\n"
            "• 17 new screens (Pomodoro, journal, habits, mood, calendar, etc.)\n"
            "• 15 dialog windows\n"
            "• 30+ custom widgets\n"
            "• 18 new features (Pomodoro, focus mode, advanced analytics, etc.)\n"
            "• 100% offline, 100% private\n"
            "• AES-256-GCM encryption\n"
            "• 10 languages\n"
            "• Jalali and Gregorian calendars\n"
            "• PDF/CSV/JSON/PNG export\n"
            "• 100,000+ lines of code"
        ),
        category="changelog",
        tags=["v2", "release"],
        related=[],
        icon="star",
    ),

    HelpArticle(
        id="changelog_v1",
        title_fa="نسخه ۱.۰",
        title_en="Version 1.0",
        body_fa=(
            "نسخه‌ی اولیه با Tkinter استاندارد.\n\n"
            "• ثبت فعالیت، هدف، زنجیره\n"
            "• آمار پایه\n"
            "• پشتیبان‌گیری رمزنگاری‌شده\n"
            "• ۲ زبان (فارسی، انگلیسی)"
        ),
        body_en=(
            "Initial release with standard Tkinter.\n\n"
            "• Activity, goal, streak logging\n"
            "• Basic statistics\n"
            "• Encrypted backups\n"
            "• 2 languages (Persian, English)"
        ),
        category="changelog",
        tags=["v1", "initial"],
        related=["changelog_v2"],
        icon="history",
    ),
]


# =============================================================================
# === Help system                                                              ===
# =============================================================================

class HelpSystem:
    """In-app help system singleton."""

    def __init__(self):
        self._articles: dict[str, HelpArticle] = {a.id: a for a in ARTICLES}
        self._categories: dict[str, HelpCategory] = {c.id: c for c in CATEGORIES}

    def get(self, article_id: str) -> Optional[HelpArticle]:
        return self._articles.get(article_id)

    def all_articles(self) -> list[HelpArticle]:
        return list(self._articles.values())

    def articles_by_category(self, category_id: str) -> list[HelpArticle]:
        return [a for a in ARTICLES if a.category == category_id]

    def all_categories(self) -> list[HelpCategory]:
        return sorted(CATEGORIES, key=lambda c: c.order)

    def search(self, query: str, lang: str = "fa") -> list[HelpArticle]:
        """Search articles by title, body, or tags."""
        if not query:
            return []
        q = query.lower().strip()
        results: list[tuple[int, HelpArticle]] = []
        for a in ARTICLES:
            score = 0
            title = a.title(lang).lower()
            body = a.body(lang).lower()
            tags = [t.lower() for t in a.tags]
            if q in title:
                score += 10
            if title.startswith(q):
                score += 5
            if q in body:
                score += 3
            if any(q in tag for tag in tags):
                score += 7
            if score > 0:
                results.append((score, a))
        results.sort(key=lambda x: x[0], reverse=True)
        return [a for _, a in results]

    def related(self, article_id: str) -> list[HelpArticle]:
        """Get articles related to the given one."""
        a = self._articles.get(article_id)
        if not a:
            return []
        return [self._articles[rid] for rid in a.related if rid in self._articles]

    def featured(self, lang: str = "fa") -> list[HelpArticle]:
        """Return 5 articles recommended for new users."""
        return [self._articles[aid] for aid in [
            "gs_welcome", "gs_first_activity", "gs_first_goal",
            "feat_quick_log", "tip_consistency",
        ] if aid in self._articles]

    def article_count(self) -> int:
        return len(self._articles)

    def category_count(self) -> int:
        return len(self._categories)


# Singleton
help_system = HelpSystem()


__all__ = [
    "HelpArticle", "HelpCategory", "HelpSystem", "help_system",
    "ARTICLES", "CATEGORIES",
]
