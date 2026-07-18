// date-utils.js — Gregorian + Jalali (Persian) calendar helpers
window.DateUtils = (function () {
  function todayISO() { return new Date().toISOString().slice(0, 10); }
  function nowISO() { return new Date().toISOString().slice(0, 19); }
  function parseISO(s) { return new Date(s); }
  function isLeap(y) { return (y % 4 === 0 && y % 100 !== 0) || (y % 400 === 0); }
  function startOfDay(d) { const x = new Date(d); x.setHours(0,0,0,0); return x; }
  function endOfDay(d) { const x = new Date(d); x.setHours(23,59,59,999); return x; }
  function startOfWeek(d) {
    const x = startOfDay(d);
    const day = (x.getDay() + 1) % 7; // Sunday=0
    x.setDate(x.getDate() - day);
    return x;
  }
  function endOfWeek(d) {
    const s = startOfWeek(d);
    s.setDate(s.getDate() + 6);
    return endOfDay(s);
  }
  function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }
  function endOfMonth(d) { return new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59, 999); }
  function startOfYear(d) { return new Date(d.getFullYear(), 0, 1); }
  function endOfYear(d) { return new Date(d.getFullYear(), 11, 31, 23, 59, 59, 999); }
  function* dateRange(start, end) {
    let cur = new Date(start);
    cur.setHours(0,0,0,0);
    const stop = new Date(end); stop.setHours(0,0,0,0);
    while (cur <= stop) {
      yield new Date(cur);
      cur.setDate(cur.getDate() + 1);
    }
  }
  function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
  function diffDays(a, b) {
    const ms = startOfDay(a).getTime() - startOfDay(b).getTime();
    return Math.round(ms / 86400000);
  }

  // Jalali conversion (Borkowski algorithm)
  function gregorianToJalali(gy, gm, gd) {
    if (gm <= 2) { gy -= 1; }
    const days = 365 * gy + Math.floor((gy + 3) / 4) - Math.floor((gy + 99) / 100) +
                 Math.floor((gy + 399) / 400) + gd +
                 (gm <= 2 ? [0,31,59,90,120,151,181,212,243,273,304,334][gm - 1]
                          : [0,31,60,91,121,152,182,213,244,274,305,335][gm - 1]);
    const jDays = days - 79;
    const jNp = Math.floor(jDays / 12053);
    let rem = jDays % 12053;
    let jy = 979 + 33 * jNp + 4 * Math.floor(rem / 1461);
    rem = rem % 1461;
    if (rem >= 366) {
      jy += Math.floor((rem - 1) / 365);
      rem = (rem - 1) % 365;
    }
    let jm, jd;
    if (rem < 186) { jm = 1 + Math.floor(rem / 31); jd = 1 + (rem % 31); }
    else { jm = 7 + Math.floor((rem - 186) / 30); jd = 1 + ((rem - 186) % 30); }
    return [jy, jm, jd];
  }
  function jalaliToGregorian(jy, jm, jd) {
    jy -= 979;
    let jDays = 365 * jy + Math.floor(jy / 33) * 8 + Math.floor(((jy % 33) + 3) / 4) + jd;
    jDays += (jm < 7) ? (jm - 1) * 31 : (jm - 7) * 30 + 186;
    let gDays = jDays + 79;
    let gy = 1600 + 400 * Math.floor(gDays / 146097);
    gDays = gDays % 146097;
    if (gDays >= 36525) { gDays -= 1; gy += 100 * Math.floor(gDays / 36524); gDays = gDays % 36524; if (gDays >= 365) gDays += 1; }
    gy += 4 * Math.floor(gDays / 1461);
    gDays = gDays % 1461;
    if (gDays >= 366) { gy += Math.floor((gDays - 1) / 365); gDays = (gDays - 1) % 365; }
    const salA = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (isLeap(gy)) salA[2] = 29;
    let gm = 0;
    while (gm < 13 && gDays > salA[gm]) { gDays -= salA[gm]; gm += 1; }
    return [gy, gm, gDays];
  }

  function fmtDate(d, lang) {
    if (lang === "fa") {
      const [jy, jm, jd] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
      return `${window.toFaDigits(jd)} ${window.t("jMonth" + jm, lang)} ${window.toFaDigits(jy)}`;
    }
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear()}`;
  }
  function fmtShortDate(d, lang) {
    if (lang === "fa") {
      const [jy, jm, jd] = gregorianToJalali(d.getFullYear(), d.getMonth() + 1, d.getDate());
      return `${window.toFaDigits(jd)}/${window.toFaDigits(jm)}/${window.toFaDigits(jy)}`;
    }
    return `${String(d.getDate()).padStart(2,"0")}/${String(d.getMonth()+1).padStart(2,"0")}/${d.getFullYear()}`;
  }
  function fmtWeekday(d, lang) {
    const idx = (d.getDay() + 6) % 7; // Mon=0
    const keys = ["weekdayMon","weekdayTue","weekdayWed","weekdayThu","weekdayFri","weekdaySat","weekdaySun"];
    return window.t(keys[idx], lang);
  }
  function fmtRelative(iso, lang) {
    const d = parseISO(iso);
    const today = new Date(); today.setHours(0,0,0,0);
    d.setHours(0,0,0,0);
    const diff = Math.round((today - d) / 86400000);
    if (diff === 0) return window.t("today_", lang);
    if (diff === 1) return window.t("yesterday", lang);
    if (diff < 7) return lang === "fa"
      ? `${window.toFaDigits(diff)} ${window.t("days", lang)} ${window.t("ago", lang)}`
      : `${diff} ${window.t("days", lang)} ${window.t("ago", lang)}`;
    if (diff < 30) { const w = Math.floor(diff / 7); return `${window.toFaDigits(w)} ${window.t("week", lang)}${lang==="fa"?"":"s"} ${window.t("ago", lang)}`; }
    if (diff < 365) { const m = Math.floor(diff / 30); return `${window.toFaDigits(m)} ${window.t("month", lang)}${lang==="fa"?"":"s"} ${window.t("ago", lang)}`; }
    const y = Math.floor(diff / 365);
    return `${window.toFaDigits(y)} ${window.t("year", lang)}${lang==="fa"?"":"s"} ${window.t("ago", lang)}`;
  }
  function fmtDuration(sec) {
    sec = Math.max(0, Math.floor(sec));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = sec % 60;
    if (h) return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
    return `${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
  }
  function fmtHuman(sec, lang) {
    sec = Math.max(0, Math.floor(sec));
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    if (lang === "fa") {
      const parts = [];
      if (h) parts.push(`${window.toFaDigits(h)} ${window.t("hour", lang)}`);
      if (m) parts.push(`${window.toFaDigits(m)} ${window.t("minute", lang)}`);
      return parts.join(" ") || `${window.toFaDigits(0)} ${window.t("minute", lang)}`;
    }
    const parts = [];
    if (h) parts.push(`${h}h`);
    if (m) parts.push(`${m}m`);
    return parts.join(" ") || "0m";
  }

  return {
    todayISO, nowISO, parseISO, isLeap,
    startOfDay, endOfDay, startOfWeek, endOfWeek,
    startOfMonth, endOfMonth, startOfYear, endOfYear,
    dateRange, addDays, diffDays,
    gregorianToJalali, jalaliToGregorian,
    fmtDate, fmtShortDate, fmtWeekday, fmtRelative,
    fmtDuration, fmtHuman,
  };
})();
