"""biletinial.com üzerinden İBB Şehir Tiyatroları oyun/seans bilgilerini çeker."""
import html
import json
import re
import urllib.request

VENUE_URL = "https://biletinial.com/tr-tr/mekan/istanbul-bb-sehir-tiyatrolari"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


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


def list_sessions(play_url):
    """Bir oyunun seanslarını döner: [{id, date, time, venue, available, button}]."""
    page = fetch(play_url)
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
        sold_out = "sold-out" in tag or "disabled" in tag
        sessions.append({
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
