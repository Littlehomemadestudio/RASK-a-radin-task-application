// app.js — Rask main controller.
// Wires up: splash → onboarding → lock → main app (home/goals/stats/settings),
// quick-log modal, template modal, goal modal, timer ticking, charts, exports,
// PWA install prompt, language switching, RTL.

(function () {
  const $ = (id) => document.getElementById(id);
  const $$ = (sel, root) => (root || document).querySelectorAll(sel);

  let LANG = "fa";
  let SELECTED_CATEGORY = null;     // for quick-log
  let SELECTED_TEMPLATE_CATEGORY = null;
  let SELECTED_GOAL_CATEGORY = null;
  let SELECTED_GOAL_PERIOD = "daily";
  let CURRENT_TAB = "home";
  let STATS_PRESET = "7d";
  let DEFERRED_INSTALL_PROMPT = null;
  let TIMER_TICK_INTERVAL = null;

  // === Entry point ===
  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    // Hide splash after 2.2s
    setTimeout(() => {
      $("splash").classList.add("hidden");
      proceedAfterSplash();
    }, 2200);

    // Pre-init DB so it's ready when splash ends
    try { await window.RaskDB.open(); } catch (e) { console.warn(e); }

    // Load language
    LANG = (await window.RaskDB.kvGet("lang", detectLang())) || "fa";
    window.RASK_LANG = LANG;
    applyLang();

    // Set up timer listener
    window.RaskTimer.addListener(onTimerTick);
  }

  function detectLang() {
    try {
      const nav = (navigator.language || "fa").toLowerCase();
      if (nav.startsWith("fa")) return "fa";
      if (nav.startsWith("en")) return "en";
    } catch (_) {}
    return "fa";
  }

  function applyLang() {
    document.documentElement.lang = LANG;
    document.documentElement.dir = LANG === "fa" ? "rtl" : "ltr";
    window.RASK_LANG = LANG;
    // Apply to all data-i18n elements
    $$("[data-i18n]").forEach((el) => {
      const key = el.getAttribute("data-i18n");
      el.textContent = window.t(key, LANG);
    });
    $$("[data-i18n-placeholder]").forEach((el) => {
      const key = el.getAttribute("data-i18n-placeholder");
      el.setAttribute("placeholder", window.t(key, LANG));
    });
  }

  async function proceedAfterSplash() {
    const onboarded = await window.RaskDB.kvGetBool("onboarded", false);
    if (!onboarded) {
      showOnboarding();
    } else {
      await maybeShowLock();
    }
  }

  // === Onboarding ===
  const SLIDES = [
    { titleKey: "slide1Title", bodyKey: "slide1Body" },
    { titleKey: "slide2Title", bodyKey: "slide2Body" },
    { titleKey: "slide3Title", bodyKey: "slide3Body" },
  ];
  let obIndex = 0;

  function showOnboarding() {
    $("onboarding").classList.remove("hidden");
    $("main").classList.add("hidden");
    $("lock").classList.add("hidden");
    $("obSkip").textContent = window.t("skip", LANG);
    $("obNext").textContent = window.t("next", LANG);
    $("obSkip").onclick = finishOnboarding;
    $("obNext").onclick = () => {
      obIndex++;
      if (obIndex >= SLIDES.length) finishOnboarding();
      else renderOnboarding();
    };
    renderOnboarding();
  }

  function renderOnboarding() {
    const s = SLIDES[obIndex];
    $("obTitle").textContent = window.t(s.titleKey, LANG);
    $("obBody").textContent = window.t(s.bodyKey, LANG);
    const dots = $("obDots");
    dots.innerHTML = "";
    SLIDES.forEach((_, i) => {
      const d = document.createElement("div");
      d.className = "onboarding-dot" + (i === obIndex ? " active" : "");
      dots.appendChild(d);
    });
    if (obIndex === SLIDES.length - 1) {
      $("obNext").textContent = window.t("start", LANG);
    } else {
      $("obNext").textContent = window.t("next", LANG);
    }
  }

  async function finishOnboarding() {
    await window.RaskDB.kvSet("onboarded", "1");
    $("onboarding").classList.add("hidden");
    await maybeShowLock();
  }

  // === Lock ===
  async function maybeShowLock() {
    const mode = await window.RaskLock.getMode();
    if (mode === "none") {
      showMain();
      return;
    }
    $("lock").classList.remove("hidden");
    $("main").classList.add("hidden");
    $("lockPin").value = "";
    $("unlockBtn").onclick = async () => {
      const pin = $("lockPin").value;
      if (!pin) return;
      if (await window.RaskLock.verifyPin(pin)) {
        $("lock").classList.add("hidden");
        showMain();
      } else {
        toast(window.t("wrongPin", LANG));
        $("lockPin").value = "";
      }
    };
    $("lockPin").onkeydown = (e) => { if (e.key === "Enter") $("unlockBtn").click(); };

    const bioBtn = $("biometricUnlockBtn");
    if (mode === "biometric" || await window.RaskLock.isBiometricAvailable()) {
      bioBtn.classList.remove("hidden");
      bioBtn.onclick = async () => {
        try {
          await window.RaskLock.authenticateBiometric();
          $("lock").classList.add("hidden");
          showMain();
        } catch (e) {
          toast(window.t("biometricFailed", LANG));
        }
      };
    } else {
      bioBtn.classList.add("hidden");
    }
  }

  // === Main ===
  function showMain() {
    $("main").classList.remove("hidden");
    setupNav();
    setupFAB();
    setupQuickLog();
    setupTemplateModal();
    setupGoalModal();
    setupSettings();
    setupStats();
    setupPWAInstall();
    switchTab("home");
    startTimerTick();
    // Handle URL shortcut (?action=quicklog or ?tab=stats)
    handleURLShortcut();
  }

  function handleURLShortcut() {
    const params = new URLSearchParams(location.search);
    const action = params.get("action");
    const tab = params.get("tab");
    if (tab && ["home", "goals", "stats", "settings"].includes(tab)) switchTab(tab);
    if (action === "quicklog") openQuickLog();
    if (action === "start-timer") {
      window.RaskTimer.start("Quick timer", null, null);
    }
  }

  function setupNav() {
    $$(".nav-btn").forEach((btn) => {
      btn.onclick = () => switchTab(btn.dataset.tab);
    });
  }

  function switchTab(tab) {
    CURRENT_TAB = tab;
    $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    ["home", "goals", "stats", "settings"].forEach((s) => {
      $("screen-" + s).classList.toggle("hidden", s !== tab);
    });
    if (tab === "home") renderHome();
    if (tab === "goals") renderGoals();
    if (tab === "stats") renderStats();
    if (tab === "settings") renderSettings();
  }

  function setupFAB() {
    $("fab").onclick = openQuickLog;
  }

  // === Home ===
  async function renderHome() {
    // Greeting
    const h = new Date().getHours();
    let gKey = "goodEvening";
    if (h < 12) gKey = "goodMorning";
    else if (h < 18) gKey = "goodAfternoon";
    $("greeting").textContent = window.t(gKey, LANG);
    $("dateLabel").textContent = window.DateUtils.fmtDate(new Date(), LANG);

    // Today total + goal
    const today = window.DateUtils.todayISO();
    const total = await window.RaskDB.totalSecondsOn(today);
    const goals = await window.RaskDB.allGoals(true);
    const dailyGoal = goals.find((g) => g.period === "daily" && !g.category_id) || goals[0];
    const targetSec = dailyGoal ? dailyGoal.target_minutes * 60 : 120 * 60;
    const progress = targetSec > 0 ? Math.min(1, total / targetSec) : 0;

    // Draw progress ring
    const canvas = $("todayRing");
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    canvas.width = 140 * dpr; canvas.height = 140 * dpr;
    canvas.style.width = "140px"; canvas.style.height = "140px";
    ctx.scale(dpr, dpr);
    window.RaskCharts.ProgressRing.draw(
      ctx, 70, 70, 140, progress,
      "#D4AF37", "#2C2C30",
      window.DateUtils.fmtHuman(total, LANG), "#E8E8E8"
    );

    $("todayTotal").textContent = window.DateUtils.fmtHuman(total, LANG);
    $("todayGoal").textContent = dailyGoal
      ? `${window.t("goal", LANG)}: ${window.DateUtils.fmtHuman(dailyGoal.target_minutes * 60, LANG)}`
      : "";

    // Streak
    const top = await window.RaskDB.topStreaks(1);
    if (top.length && top[0].current > 0) {
      $("todayStreak").textContent = `🔥 ${window.t("streak", LANG)}: ${LANG === "fa" ? window.toFaDigits(top[0].current) : top[0].current} ${window.t("days", LANG)}`;
    } else {
      $("todayStreak").textContent = "";
    }

    // Active timer card
    renderActiveTimer();

    // Templates
    const tpls = await window.RaskDB.allTemplates();
    const row = $("templatesRow");
    row.innerHTML = "";
    if (!tpls.length) {
      row.innerHTML = `<div class="empty-state" style="padding:8px 0">${window.t("noTemplates", LANG)} — <a href="#" id="addTplLink" style="color:var(--gold)">${window.t("addTemplate", LANG)}</a></div>`;
      const link = $("addTplLink");
      if (link) link.onclick = (e) => { e.preventDefault(); openTemplateModal(); };
    } else {
      tpls.forEach((t) => {
        const chip = document.createElement("button");
        chip.className = "chip";
        chip.textContent = t.title;
        chip.onclick = () => {
          window.RaskTimer.start(t.title, t.category_id, t.id);
          toast(`${window.t("recording", LANG)}: ${t.title}`);
        };
        row.appendChild(chip);
      });
    }

    // Recent activities
    const recent = await window.RaskDB.recentActivities(15);
    const cats = await window.RaskDB.allCategories();
    const catMap = {}; cats.forEach((c) => catMap[c.id] = c);
    const list = $("recentList");
    list.innerHTML = "";
    if (!recent.length) {
      list.innerHTML = `<div class="empty-state">${window.t("noActivities", LANG)}</div>`;
    } else {
      recent.forEach((a) => {
        const cat = a.category_id ? catMap[a.category_id] : null;
        const div = document.createElement("div");
        div.className = "activity-row";
        const catName = cat ? (LANG === "fa" ? cat.name_fa : cat.name_en) : "—";
        const catColor = cat ? cat.color : "#9A9A9F";
        div.innerHTML = `
          <div class="activity-top">
            <span class="activity-title">${escapeHtml(a.title || "(no title)")}</span>
            <span class="activity-cat" style="color:${catColor}">${escapeHtml(catName)}</span>
          </div>
          <div class="activity-bottom">
            <span class="activity-duration">${window.DateUtils.fmtHuman(a.duration_sec, LANG)}</span>
            <span class="activity-when">${window.DateUtils.fmtRelative(a.date_iso, LANG)}</span>
          </div>`;
        list.appendChild(div);
      });
    }
  }

  function renderActiveTimer() {
    const card = $("timerCard");
    if (!window.RaskTimer.isRunning() && window.RaskTimer.elapsedSec() === 0) {
      card.classList.add("hidden");
      return;
    }
    card.classList.remove("hidden");
    $("timerTitle").textContent = window.RaskTimer.currentTitle() || window.t("recording", LANG);
    $("timerTime").textContent = window.DateUtils.fmtDuration(window.RaskTimer.elapsedSec());
    $("timerPause").textContent = window.RaskTimer.isRunning()
      ? window.t("pause", LANG) : window.t("resume", LANG);
  }

  function onTimerTick() {
    if (CURRENT_TAB === "home") renderActiveTimer();
    if (CURRENT_TAB === "home" && window.RaskTimer.isRunning()) {
      // Refresh today total live
      const total = window.RaskTimer.elapsedSec();
      // Only redraw ring if there's an active stopwatch — manual activities don't change
    }
  }

  function startTimerTick() {
    if (TIMER_TICK_INTERVAL) clearInterval(TIMER_TICK_INTERVAL);
    TIMER_TICK_INTERVAL = setInterval(() => {
      if (window.RaskTimer.isRunning() && CURRENT_TAB === "home") {
        renderActiveTimer();
      }
    }, 1000);
  }

  // === Quick log modal ===
  function setupQuickLog() {
    $("qlCancel").onclick = () => closeQuickLog();
    $("qlVoice").onclick = onQuickLogVoice;
    $("qlStopwatch").onclick = () => {
      const title = $("qlTitle").value.trim();
      window.RaskTimer.start(title, SELECTED_CATEGORY, null);
      closeQuickLog();
      toast(`${window.t("recording", LANG)}: ${title || "—"}`);
    };
    $("qlSave").onclick = async () => {
      const title = $("qlTitle").value.trim() || "(no title)";
      const h = parseInt($("qlHours").value || "0", 10) || 0;
      const m = parseInt($("qlMinutes").value || "0", 10) || 0;
      const sec = h * 3600 + m * 60;
      if (sec <= 0) {
        window.RaskTimer.start(title, SELECTED_CATEGORY, null);
        closeQuickLog();
        toast(`${window.t("recording", LANG)}: ${title}`);
        return;
      }
      const now = new Date();
      await window.RaskDB.insertActivity({
        title, category_id: SELECTED_CATEGORY, kind: "manual",
        date_iso: now.toISOString().slice(0, 10),
        start_iso: null, end_iso: null,
        duration_sec: sec, note: "", voice_input: 0,
        created_at: now.toISOString(),
      });
      closeQuickLog();
      toast(window.t("save", LANG) + " ✓");
      if (CURRENT_TAB === "home") renderHome();
    };
    // Close on backdrop click
    $("quickLogModal").onclick = (e) => {
      if (e.target.id === "quickLogModal") closeQuickLog();
    };
  }

  async function openQuickLog() {
    $("quickLogModal").classList.remove("hidden");
    $("qlTitle").value = "";
    $("qlHours").value = "";
    $("qlMinutes").value = "";
    SELECTED_CATEGORY = null;
    // Render categories
    const cats = await window.RaskDB.allCategories();
    const row = $("qlCategories");
    row.innerHTML = "";
    cats.forEach((c) => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.textContent = LANG === "fa" ? c.name_fa : c.name_en;
      chip.onclick = () => {
        SELECTED_CATEGORY = c.id;
        row.querySelectorAll(".chip").forEach((x) => x.classList.remove("selected"));
        chip.classList.add("selected");
      };
      row.appendChild(chip);
    });
  }
  function closeQuickLog() {
    $("quickLogModal").classList.add("hidden");
  }
  function onQuickLogVoice() {
    if (!window.RaskVoice.supported()) {
      toast(window.t("voiceInput", LANG) + " ❌");
      return;
    }
    toast("🎤 ...");
    window.RaskVoice.listen(LANG, (text) => {
      $("qlTitle").value = text;
    }, (err) => toast(err), () => {});
  }

  // === Template modal ===
  function setupTemplateModal() {
    $("tplCancel").onclick = () => $("templateModal").classList.add("hidden");
    $("tplCreate").onclick = async () => {
      const title = $("tplTitle").value.trim();
      if (!title) return;
      const dur = parseInt($("tplDuration").value || "30", 10) || 30;
      await window.RaskDB.upsertTemplate({
        title, category_id: SELECTED_TEMPLATE_CATEGORY,
        default_duration_min: dur, icon: "",
      });
      $("templateModal").classList.add("hidden");
      toast(window.t("save", LANG) + " ✓");
      if (CURRENT_TAB === "home") renderHome();
    };
    $("templateModal").onclick = (e) => {
      if (e.target.id === "templateModal") $("templateModal").classList.add("hidden");
    };
  }
  async function openTemplateModal() {
    $("templateModal").classList.remove("hidden");
    $("tplTitle").value = "";
    $("tplDuration").value = "30";
    SELECTED_TEMPLATE_CATEGORY = null;
    const cats = await window.RaskDB.allCategories();
    const row = $("tplCategories");
    row.innerHTML = "";
    cats.forEach((c) => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.textContent = LANG === "fa" ? c.name_fa : c.name_en;
      chip.onclick = () => {
        SELECTED_TEMPLATE_CATEGORY = c.id;
        row.querySelectorAll(".chip").forEach((x) => x.classList.remove("selected"));
        chip.classList.add("selected");
      };
      row.appendChild(chip);
    });
  }

  // === Goal modal ===
  function setupGoalModal() {
    $("newGoalBtn").onclick = openGoalModal;
    $("goalCancel").onclick = () => $("goalModal").classList.add("hidden");
    $("goalModal").onclick = (e) => {
      if (e.target.id === "goalModal") $("goalModal").classList.add("hidden");
    };
    $$("#goalPeriods .chip").forEach((chip) => {
      chip.onclick = () => {
        SELECTED_GOAL_PERIOD = chip.dataset.period;
        $$("#goalPeriods .chip").forEach((x) => x.classList.remove("selected"));
        chip.classList.add("selected");
      };
    });
    $("goalCreate").onclick = async () => {
      const target = parseInt($("goalTarget").value || "60", 10) || 60;
      await window.RaskDB.upsertGoal({
        period: SELECTED_GOAL_PERIOD,
        category_id: SELECTED_GOAL_CATEGORY,
        target_minutes: target, active: 1,
      });
      $("goalModal").classList.add("hidden");
      toast(window.t("save", LANG) + " ✓");
      renderGoals();
    };
  }
  async function openGoalModal() {
    $("goalModal").classList.remove("hidden");
    $("goalTarget").value = "60";
    SELECTED_GOAL_PERIOD = "daily";
    SELECTED_GOAL_CATEGORY = null;
    $$("#goalPeriods .chip").forEach((c, i) => c.classList.toggle("selected", i === 0));
    const cats = await window.RaskDB.allCategories();
    const row = $("goalCategories");
    row.innerHTML = "";
    // "All" chip
    const allChip = document.createElement("button");
    allChip.className = "chip selected";
    allChip.textContent = window.t("all", LANG);
    allChip.onclick = () => {
      SELECTED_GOAL_CATEGORY = null;
      row.querySelectorAll(".chip").forEach((x) => x.classList.remove("selected"));
      allChip.classList.add("selected");
    };
    row.appendChild(allChip);
    cats.forEach((c) => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.textContent = LANG === "fa" ? c.name_fa : c.name_en;
      chip.onclick = () => {
        SELECTED_GOAL_CATEGORY = c.id;
        row.querySelectorAll(".chip").forEach((x) => x.classList.remove("selected"));
        chip.classList.add("selected");
      };
      row.appendChild(chip);
    });
  }

  // === Goals screen ===
  async function renderGoals() {
    const list = $("goalsList");
    list.innerHTML = "";
    const goals = await window.RaskDB.allGoals();
    const cats = await window.RaskDB.allCategories();
    const catMap = {}; cats.forEach((c) => catMap[c.id] = c);
    if (!goals.length) {
      list.innerHTML = `<div class="empty-state">${window.t("noGoals", LANG)}</div>`;
    } else {
      for (const g of goals) {
        const today = new Date();
        let start, end;
        if (g.period === "daily") { start = end = today; }
        else if (g.period === "weekly") {
          start = window.DateUtils.startOfWeek(today);
          end = window.DateUtils.endOfWeek(today);
        } else {
          start = window.DateUtils.startOfMonth(today);
          end = window.DateUtils.endOfMonth(today);
        }
        const total = await window.RaskDB.totalSecondsBetween(
          start.toISOString().slice(0,10), end.toISOString().slice(0,10), g.category_id
        );
        const target = g.target_minutes * 60;
        const progress = target > 0 ? Math.min(1, total / target) : 0;
        const cat = g.category_id ? catMap[g.category_id] : null;
        const catName = cat ? (LANG === "fa" ? cat.name_fa : cat.name_en) : window.t("all", LANG);
        const st = await window.RaskDB.streakForGoal(g.id);

        const card = document.createElement("div");
        card.className = "card goal-card";
        card.innerHTML = `
          <canvas class="ring-canvas" width="80" height="80"></canvas>
          <div class="goal-info">
            <div class="goal-period">${window.t(g.period, LANG)} — ${escapeHtml(catName)}</div>
            <div class="goal-progress">${window.DateUtils.fmtHuman(total, LANG)} / ${window.DateUtils.fmtHuman(target, LANG)}</div>
            ${st ? `<div class="goal-streak">${window.t("streak", LANG)}: ${LANG==="fa"?window.toFaDigits(st.current):st.current} ${window.t("days", LANG)} (${window.t("best", LANG)}: ${LANG==="fa"?window.toFaDigits(st.longest):st.longest})</div>` : ""}
          </div>
          <button class="goal-delete">${window.t("delete", LANG)}</button>`;
        list.appendChild(card);
        // Draw ring
        const canvas = card.querySelector("canvas");
        const ctx = canvas.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        canvas.width = 80 * dpr; canvas.height = 80 * dpr;
        canvas.style.width = "80px"; canvas.style.height = "80px";
        ctx.scale(dpr, dpr);
        window.RaskCharts.ProgressRing.draw(
          ctx, 40, 40, 80, progress, "#D4AF37", "#2C2C30",
          `${Math.floor(progress * 100)}%`, "#E8E8E8"
        );
        card.querySelector(".goal-delete").onclick = async () => {
          if (confirm(`${window.t("delete", LANG)}?`)) {
            await window.RaskDB.deleteGoal(g.id);
            renderGoals();
          }
        };
      }
    }

    // Badges
    const badges = await window.RaskDB.allBadges();
    const bList = $("badgesList");
    bList.innerHTML = "";
    if (!badges.length) {
      bList.innerHTML = `<div class="empty-state">${window.t("noBadges", LANG)}</div>`;
    } else {
      badges.forEach((b) => {
        const div = document.createElement("div");
        div.className = "card-row";
        div.style.padding = "8px 0";
        div.innerHTML = `<span style="font-size:24px">🏅</span>
          <span style="color:var(--gold);font-weight:700">${escapeHtml(LANG === "fa" ? b.title_fa : b.title_en)}</span>`;
        bList.appendChild(div);
      });
    }
  }

  // === Stats screen ===
  const PRESETS = [
    { key: "today", labelKey: "todayPreset" },
    { key: "7d", labelKey: "sevenDays" },
    { key: "30d", labelKey: "thirtyDays" },
    { key: "month", labelKey: "thisMonth" },
    { key: "year", labelKey: "thisYear" },
  ];

  function setupStats() {
    const row = $("statsPresets");
    row.innerHTML = "";
    PRESETS.forEach((p) => {
      const chip = document.createElement("button");
      chip.className = "chip" + (p.key === STATS_PRESET ? " selected" : "");
      chip.textContent = window.t(p.labelKey, LANG);
      chip.onclick = () => {
        STATS_PRESET = p.key;
        row.querySelectorAll(".chip").forEach((x) => x.classList.remove("selected"));
        chip.classList.add("selected");
        renderStats();
      };
      row.appendChild(chip);
    });
    $("exportPdfBtn").onclick = onExportPDF;
    $("exportCsvBtn").onclick = onExportCSV;
  }

  function statsRange() {
    const today = new Date();
    if (STATS_PRESET === "today") return [today, today];
    if (STATS_PRESET === "7d") return [window.DateUtils.addDays(today, -6), today];
    if (STATS_PRESET === "30d") return [window.DateUtils.addDays(today, -29), today];
    if (STATS_PRESET === "month") return [window.DateUtils.startOfMonth(today), window.DateUtils.endOfMonth(today)];
    if (STATS_PRESET === "year") return [window.DateUtils.startOfYear(today), window.DateUtils.endOfYear(today)];
    return [window.DateUtils.addDays(today, -6), today];
  }

  async function renderStats() {
    const [start, end] = statsRange();
    const sISO = start.toISOString().slice(0,10);
    const eISO = end.toISOString().slice(0,10);
    const content = $("statsContent");
    content.innerHTML = "";

    const acts = await window.RaskDB.activitiesByDateRange(sISO, eISO);
    const total = acts.reduce((s, a) => s + (a.duration_sec || 0), 0);

    // Total card
    const totalCard = document.createElement("div");
    totalCard.className = "card";
    totalCard.innerHTML = `
      <div class="card-subtitle" data-i18n="total">${window.t("total", LANG)}</div>
      <div class="stat-total">${window.DateUtils.fmtHuman(total, LANG)}</div>
      <div class="stat-period">${window.DateUtils.fmtShortDate(start, LANG)} → ${window.DateUtils.fmtShortDate(end, LANG)}</div>`;
    content.appendChild(totalCard);

    if (!acts.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = window.t("noData", LANG);
      content.appendChild(empty);
      return;
    }

    // Bar chart (daily trend, max 30 days)
    if ((end - start) / 86400000 <= 31) {
      const days = Array.from(window.DateUtils.dateRange(start, end));
      const perDay = await window.RaskDB.secondsPerDay(sISO, eISO);
      const barData = days.map((d) => ({
        label: LANG === "fa" ? window.toFaDigits(d.getDate()) : String(d.getDate()),
        value: perDay[d.toISOString().slice(0,10)] || 0,
        color: "#D4AF37",
      }));
      const barCard = document.createElement("div");
      barCard.className = "card chart-card";
      barCard.innerHTML = `<div class="section-header">${window.t("dailyTrend", LANG)}</div>`;
      const canvas = document.createElement("canvas");
      canvas.width = 460; canvas.height = 160;
      barCard.appendChild(canvas);
      content.appendChild(barCard);
      const ctx = canvas.getContext("2d");
      window.RaskCharts.BarChart.draw(ctx, 8, 8, 444, 144, barData);
    }

    // Donut chart (category share)
    const cats = await window.RaskDB.allCategories();
    const catMap = {}; cats.forEach((c) => catMap[c.id] = c);
    const perCat = await window.RaskDB.secondsPerCategory(sISO, eISO);
    const donutData = perCat.slice(0, 6).map(([cid, sec]) => {
      const c = catMap[cid];
      return {
        label: c ? (LANG === "fa" ? c.name_fa : c.name_en) : "—",
        value: sec, color: c ? c.color : "#9A9A9F",
      };
    });
    const donutCard = document.createElement("div");
    donutCard.className = "card chart-card";
    donutCard.innerHTML = `<div class="section-header">${window.t("categoryShare", LANG)}</div>`;
    const donutWrap = document.createElement("div");
    donutWrap.style.display = "flex";
    donutWrap.style.alignItems = "center";
    donutWrap.style.gap = "16px";
    const dcanvas = document.createElement("canvas");
    dcanvas.width = 140; dcanvas.height = 140;
    dcanvas.style.flexShrink = "0";
    donutWrap.appendChild(dcanvas);
    const legend = document.createElement("div");
    legend.style.flex = "1";
    legend.innerHTML = donutData.slice(0, 4).map((d) =>
      `<div style="display:flex;align-items:center;gap:6px;padding:2px 0">
        <span style="width:10px;height:10px;background:${d.color};border-radius:2px"></span>
        <span style="font-size:11px;color:var(--text-dim);flex:1">${escapeHtml(d.label)}</span>
        <span style="font-size:11px;color:var(--gold)">${window.DateUtils.fmtHuman(d.value, LANG)}</span>
      </div>`).join("");
    donutWrap.appendChild(legend);
    donutCard.appendChild(donutWrap);
    content.appendChild(donutCard);
    const dctx = dcanvas.getContext("2d");
    window.RaskCharts.DonutChart.draw(dctx, 70, 70, 50, donutData, 18);

    // Heatmap (year)
    const heatCard = document.createElement("div");
    heatCard.className = "card chart-card heatmap-card";
    heatCard.innerHTML = `<div class="section-header">${window.t("yearHeatmap", LANG)}</div>`;
    const hcanvas = document.createElement("canvas");
    hcanvas.width = 540; hcanvas.height = 110;
    hcanvas.style.overflowX = "auto";
    heatCard.appendChild(hcanvas);
    content.appendChild(heatCard);
    const hctx = hcanvas.getContext("2d");
    const yearStart = window.DateUtils.startOfYear(new Date());
    const yearEnd = window.DateUtils.endOfYear(new Date());
    const heatData = await window.RaskDB.secondsPerDay(
      yearStart.toISOString().slice(0,10), yearEnd.toISOString().slice(0,10)
    );
    window.RaskCharts.Heatmap.draw(hctx, 4, 4, 530, 100, new Date().getFullYear(), heatData, 11);

    // Trends
    const trendCard = document.createElement("div");
    trendCard.className = "card";
    trendCard.innerHTML = `<div class="section-header">${window.t("trends", LANG)}</div>`;
    // Best day
    const perDay = await window.RaskDB.secondsPerDay(sISO, eISO);
    let bestDay = null, bestSec = 0;
    Object.entries(perDay).forEach(([k, v]) => { if (v > bestSec) { bestSec = v; bestDay = k; } });
    // Peak hour (today only)
    let peakHour = -1, peakSec = 0;
    if ((end - start) / 86400000 <= 1) {
      const hours = await window.RaskDB.secondsPerHour(eISO);
      hours.forEach((s, h) => { if (s > peakSec) { peakSec = s; peakHour = h; } });
    }
    // Avg
    const nDays = Math.max(1, Math.round((end - start) / 86400000) + 1);
    const avg = total / nDays;
    const trends = [];
    if (bestDay) trends.push([window.t("bestDay", LANG),
      `${window.DateUtils.fmtShortDate(new Date(bestDay + "T00:00:00"), LANG)} — ${window.DateUtils.fmtHuman(bestSec, LANG)}`]);
    if (peakHour >= 0) trends.push([window.t("peakHour", LANG),
      `${LANG === "fa" ? window.toFaDigits(String(peakHour).padStart(2,"0")) : String(peakHour).padStart(2,"0")}:00 — ${window.DateUtils.fmtHuman(peakSec, LANG)}`]);
    trends.push([window.t("dailyAvg", LANG), window.DateUtils.fmtHuman(Math.floor(avg), LANG)]);
    trends.forEach(([k, v]) => {
      const row = document.createElement("div");
      row.className = "trend-row";
      row.innerHTML = `<span class="trend-label">${escapeHtml(k)}</span><span class="trend-value">${escapeHtml(v)}</span>`;
      trendCard.appendChild(row);
    });
    content.appendChild(trendCard);
  }

  async function onExportPDF() {
    const [s, e] = statsRange();
    try {
      await window.RaskPDF.exportReport(s.toISOString().slice(0,10), e.toISOString().slice(0,10), LANG);
      toast(window.t("pdfSaved", LANG));
    } catch (e) { toast("PDF error: " + e.message); }
  }
  async function onExportCSV() {
    const [s, e] = statsRange();
    try {
      const n = await window.RaskCSV.exportRange(s.toISOString().slice(0,10), e.toISOString().slice(0,10));
      toast(`${window.t("csvSaved", LANG)}: ${LANG === "fa" ? window.toFaDigits(n) : n}`);
    } catch (e) { toast("CSV error: " + e.message); }
  }

  // === Settings ===
  async function renderSettings() {
    const mode = await window.RaskLock.getMode();
    const modeLabel = mode === "pin" ? window.t("pin", LANG)
                    : mode === "biometric" ? window.t("biometric", LANG)
                    : window.t("none", LANG);
    $("lockModeLbl").textContent = modeLabel;

    // Language buttons
    $("langFa").classList.toggle("selected", LANG === "fa");
    $("langEn").classList.toggle("selected", LANG === "en");
    $("langFa").onclick = async () => {
      LANG = "fa"; window.RASK_LANG = "fa";
      await window.RaskDB.kvSet("lang", "fa");
      applyLang();
      switchTab("settings");
    };
    $("langEn").onclick = async () => {
      LANG = "en"; window.RASK_LANG = "en";
      await window.RaskDB.kvSet("lang", "en");
      applyLang();
      switchTab("settings");
    };

    // Lock
    $("setPinBtn").onclick = async () => {
      const pin = $("newPinInput").value;
      if (pin.length < 4) { toast(window.t("pinTooShort", LANG)); return; }
      await window.RaskLock.setupPin(pin);
      $("newPinInput").value = "";
      toast(window.t("pinSet", LANG));
      renderSettings();
    };
    $("enableBioBtn").onclick = async () => {
      try {
        await window.RaskLock.setupBiometric();
        toast(window.t("biometricEnabled", LANG));
        renderSettings();
      } catch (e) { toast(e.message || window.t("biometricUnavailable", LANG)); }
    };
    $("clearLockBtn").onclick = async () => {
      await window.RaskLock.clear();
      toast(window.t("lockCleared", LANG));
      renderSettings();
    };

    // Backup
    $("exportBackupBtn").onclick = async () => {
      const pwd = $("backupPwd").value;
      if (pwd.length < 6) { toast(window.t("passwordTooShort", LANG)); return; }
      try {
        await window.RaskBackup.exportToFile(`rask_backup.rask`, pwd);
        toast(window.t("backupSaved", LANG));
      } catch (e) { toast("Backup error: " + e.message); }
    };
    $("restoreBackupBtn").onclick = async () => {
      const pwd = $("backupPwd").value;
      if (!pwd) { toast(window.t("enterPassword", LANG)); return; }
      try {
        const ok = await window.RaskBackup.importFromFile(pwd);
        if (ok) {
          toast(window.t("restored", LANG));
          switchTab("home");
        }
      } catch (e) { toast("Restore error: " + e.message); }
    };
  }

  // === PWA install prompt ===
  function setupPWAInstall() {
    window.addEventListener("beforeinstallprompt", (e) => {
      e.preventDefault();
      DEFERRED_INSTALL_PROMPT = e;
      if (location.protocol === "https:" || location.hostname === "localhost") {
        $("installBanner").classList.remove("hidden");
      }
    });
    $("installBtn").onclick = async () => {
      if (!DEFERRED_INSTALL_PROMPT) return;
      DEFERRED_INSTALL_PROMPT.prompt();
      const { outcome } = await DEFERRED_INSTALL_PROMPT.userChoice;
      if (outcome === "accepted") {
        $("installBanner").classList.add("hidden");
      }
      DEFERRED_INSTALL_PROMPT = null;
    };
    $("dismissInstall").onclick = () => $("installBanner").classList.add("hidden");
  }

  // === Helpers ===
  function toast(text) {
    const t = document.createElement("div");
    t.className = "toast";
    t.textContent = text;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2600);
  }
  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, (c) => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    })[c]);
  }

  // Expose for debugging
  window.RaskApp = { renderHome, renderGoals, renderStats, renderSettings, switchTab, toast };
})();
