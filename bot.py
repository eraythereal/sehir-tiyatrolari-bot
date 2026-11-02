"""İBB Şehir Tiyatroları koltuk takip botu.

Her çalıştırmada (GitHub Actions) belirli bir süre boyunca döngüde seansları kontrol eder.
Bir seans 'TÜKENDİ' iken satışa açılırsa (veya yeni bir seans satışa çıkarsa) Telegram'dan haber verir.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import scraper

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config.json"
STATE_PATH = ROOT / "state.json"

_TR = str.maketrans({"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"})


def norm(s):
    """Türkçe-uyumlu, aksan/büyük-küçük harf farkını yok sayan karşılaştırma anahtarı."""
    s = s.translate(_TR).lower()
    return s.translate(str.maketrans("ıöüşğç", "iousgc"))


def load_json(path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def telegram(text, photo=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chats = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chats:
        print("[TELEGRAM YOK] " + text)
        return
    for chat in [c.strip() for c in chats.split(",") if c.strip()]:
        attempts = [("sendPhoto", {"chat_id": chat, "photo": photo, "caption": text, "parse_mode": "HTML"})] if photo else []
        attempts.append(("sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML",
                                         "disable_web_page_preview": "true"}))
        for method, fields in attempts:
            try:
                urllib.request.urlopen(
                    urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}",
                                           data=urllib.parse.urlencode(fields).encode()), timeout=20).read()
                break
            except Exception as e:  # noqa
                print("Telegram hatası:", method, e)


def watched(name, patterns):
    if not patterns:
        return True
    n = norm(name)
    return any(norm(p) in n for p in patterns)


def check_once(cfg, state):
    """Bir tur kontrol. state: {session_id: bool(available)}. Döner: değişti mi."""
    changed = False
    baseline = not state.get("_init")
    seen = state.setdefault("sessions", {})
    try:
        plays = scraper.list_plays()
    except Exception as e:  # noqa
        print("Mekan sayfası alınamadı:", e)
        return False
    for url, name in plays.items():
        if not watched(name, cfg.get("watch", [])):
            continue
        try:
            sessions = scraper.list_sessions(url)
        except Exception as e:  # noqa
            print("Oyun sayfası alınamadı:", name, e)
            continue
        for s in sessions:
            prev = seen.get(s["id"])
            if prev != s["available"]:
                seen[s["id"]] = s["available"]
                changed = True
            if s["available"] and not prev and not baseline:
                kind = "Koltuk açıldı" if prev is False else "Yeni seans satışta"
                if prev is None and not cfg.get("notify_new_sessions", True):
                    continue
                telegram(
                    f"🎭 <b>{kind}!</b>\n"
                    f"🎭 <b>Oyun:</b> {name}\n"
                    f"👥 <b>Ekip:</b> {s['org']}\n"
                    f"📍 <b>Sahne:</b> {s['venue']}\n"
                    f"📅 <b>Tarih:</b> {s['date']}, {s['time']}\n"
                    f"🔗 <a href=\"{s['url']}\">Koltuk Seçimi İçin Tıkla</a>",
                    photo=s["poster"] or None)
    if baseline:
        state["_init"] = True
        changed = True
    return changed


def main():
    cfg = load_json(CONFIG_PATH, {})
    state = load_json(STATE_PATH, {})
    run_minutes = float(os.environ.get("RUN_MINUTES", cfg.get("run_minutes", 9)))
    interval = int(cfg.get("interval_seconds", 30))
    deadline = time.time() + run_minutes * 60
    if not state.get("_init") and os.environ.get("TELEGRAM_BOT_TOKEN"):
        w = ", ".join(cfg.get("watch", [])) or "tüm oyunlar"
        telegram(f"✅ Şehir Tiyatroları botu başladı.\nTakip: {w}")
    while True:
        if check_once(cfg, state):
            STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        if time.time() + interval >= deadline:
            break
        time.sleep(interval)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
