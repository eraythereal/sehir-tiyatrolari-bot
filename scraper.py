"""biletinial.com üzerinden İBB Şehir Tiyatroları oyun/seans bilgilerini çeker."""
import html
import json
import re
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

VENUE_URL = "https://biletinial.com/tr-tr/mekan/istanbul-bb-sehir-tiyatrolari"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


TR = timezone(timedelta(hours=3))


def page_age(page):
    """Sayfadaki cachedDate'e göre sayfanın yaşı (sn). Bulunamazsa None."""
    m = re.search(r"cachedDate = '(\d+)\.(\d+)\.(\d+) (\d+):(\d+):(\d+)'", page)
    if not m:
        return None
    d, mo, y, h, mi, s = map(int, m.groups())
    return (datetime.now(TR) - datetime(y, mo, d, h, mi, s, tzinfo=TR)).total_seconds()


def fetch_fresh(url, max_age=90, attempts=6):
    """Site sayfaları önbelleğe alıyor (bazen 40+ dk eski). Her denemede rastgele çerezle farklı
    bir önbellek kopyası isteyip en tazesini döner."""
    best, best_age = None, None
    for _ in range(attempts):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9", "Cookie": "cb=" + uuid.uuid4().hex})
        with urllib.request.urlopen(req, timeout=30) as r:
            page = r.read().decode("utf-8", errors="replace")
        age = page_age(page)
        if age is None:
            return page
        if best is None or age < best_age:
            best, best_age = page, age
        if age <= max_age:
            break
        time.sleep(0.5)
    return best



def list_plays():
    """Mekan sayfasındaki JSON-LD'den {url: ad} döner."""
    page = fetch(VENUE_URL)
    plays = {}
    for m in re.finditer(r'<script type="application/ld\+json">(.*?)</script>', page, re.S):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for ev in data.get("event", []) if isinstance(data, dict) else []:
            plays[ev["url"]] = ev["name"]
    return plays


def search_plays(term):
    """biletinial aramasından oyun adresleri döner: {url: slug-adı}. Mekan sayfası yalnızca 20 oyun gösterdiği için gerekli."""
    page = fetch("https://biletinial.com/tr-tr/search?q=" + urllib.parse.quote(term))
    out = {}
    for slug in re.findall(r'/tr-tr/tiyatro/([a-z0-9-]+)', page):
        out[f"https://biletinial.com/tr-tr/tiyatro/{slug}"] = slug.replace("-", " ")
    return out


def list_sessions(play_url):
    """Bir oyunun seanslarını döner: [{id, date, time, venue, available, button}]."""
    page = fetch_fresh(play_url)
    title = re.search(r'<h1 class="hero-v3__title">(.*?)</h1>', page, re.S)
    title = html.unescape(title.group(1)).strip() if title else ""
    poster = re.search(r'<meta property="og:image" content="([^"]+)"', page)
    poster = html.unescape(poster.group(1)) if poster else ""
    sessions = []
    rows = re.finditer(
        r'<div class="row" id="seans-(\d+)">(.*?)(?=<div class="row" id="seans-|</section>)', page, re.S)
    for m in rows:
        body = m.group(2)
        d = re.search(r'class="d">(.*?)<', body)
        tm = re.search(r'class="tm">(.*?)<', body)
        venue = re.search(r'class="vl">.*?<a[^>]*>(.*?)</a>', body, re.S)
        btn = re.search(r'<button[^>]*class="[^"]*\bcta\b[^"]*"[^>]*>(.*?)</button>', body, re.S)
        btn_tag = re.search(r'<button[^>]*class="[^"]*\bcta\b[^"]*"[^>]*>', body, re.S)
        tag = btn_tag.group(0) if btn_tag else ""
        label = html.unescape(re.sub(r"\s+", " ", btn.group(1))).strip() if btn else ""
        org = re.search(r'class="td">Organizasyon:\s*(.*?)<', body)
        sold_out = "sold-out" in tag or "disabled" in tag
        sessions.append({
            "poster": poster,
            "name": title,
            "org": html.unescape(org.group(1)).strip() if org else "",
            "id": m.group(1),
            "date": html.unescape(d.group(1)) if d else "",
            "time": tm.group(1) if tm else "",
            "venue": html.unescape(venue.group(1)).strip() if venue else "",
            "available": not sold_out,
            "button": label,
            "tag": re.sub(r"\s+", " ", tag),
            "url": f"{play_url}/{m.group(1)}",
        })
    return sessions


if __name__ == "__main__":
    import sys
    plays = list_plays()
    print(len(plays), "oyun")
    for url, name in plays.items():
        try:
            ss = list_sessions(url)
        except Exception as e:  # noqa
            print("HATA", name, e)
            continue
        av = [s for s in ss if s["available"]]
        print(f"{name}: {len(ss)} seans, {len(av)} satışta")
        for s in av:
            print("   ", s["date"], s["time"], s["button"], "|", s["tag"])
