"""
locale_utils.py — Language detection + RTL helpers.

Tries pyjnius on Android; falls back to locale module on desktop.
"""
from __future__ import annotations

import locale
from typing import Optional

from rask import config as cfg


def detect_language() -> str:
    """Returns 'fa' or 'en'."""
    # 1) Try Android Locale via pyjnius
    try:
        from jnius import autoclass  # type: ignore
        Locale = autoclass("java.util.Locale")
        lang = Locale.getDefault().getLanguage()
        if lang and lang.startswith("fa"):
            return "fa"
        if lang and lang.startswith("en"):
            return "en"
    except Exception:
        pass
    # 2) Use Python locale
    try:
        loc = locale.getdefaultlocale()[0]
        if loc and loc.startswith("fa"):
            return "fa"
    except Exception:
        pass
    return cfg.DEFAULT_LANG


def is_rtl(lang: str) -> bool:
    return lang == "fa"


def t(en: str, fa: str, lang: Optional[str] = None) -> str:
    """Quick inline translator."""
    if lang is None:
        lang = cfg._active_lang  # set by app at startup
    return fa if lang == "fa" else en
