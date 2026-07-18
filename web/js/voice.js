// voice.js — Voice input via Web Speech API.
window.RaskVoice = (function () {
  function supported() {
    return ("SpeechRecognition" in window) || ("webkitSpeechRecognition" in window);
  }
  function listen(lang, onResult, onError, onEnd) {
    if (!supported()) {
      if (onError) onError("Speech recognition not supported in this browser.");
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = lang === "fa" ? "fa-IR" : "en-US";
    rec.interimResults = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      const text = e.results[0][0].transcript;
      if (onResult) onResult(text);
    };
    rec.onerror = (e) => { if (onError) onError(e.error || "voice error"); };
    rec.onend = () => { if (onEnd) onEnd(); };
    try { rec.start(); } catch (e) { if (onError) onError(e.message); }
    return rec;
  }
  return { supported, listen };
})();
