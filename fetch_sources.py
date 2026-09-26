#!/usr/bin/env python3
"""Spike: pull public Thai flood/rain/road/news sources with stdlib only and
write latest.json + latest.md (3 layers). Designed to run in a cloud routine
(no browser, no local MCP). Every value carries source url + fetched time; a
source that fails is recorded as unavailable, never silently blank."""
import json, re, html, ssl, sys, datetime, urllib.request
from collections import defaultdict

TZ = datetime.timezone(datetime.timedelta(hours=7))
NOW = datetime.datetime.now(TZ)
UA = {"User-Agent": "Mozilla/5.0 (watch-kb spike)"}
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE  # tmd.go.th cert chain broken

METRO = ["กรุงเทพมหานคร", "ปทุมธานี", "สมุทรปราการ", "สมุทรสาคร", "นนทบุรี"]
WATCH = ["สงขลา", "สุราษฎร์ธานี", "เชียงใหม่", "นครสวรรค์", "ชลบุรี", "ขอนแก่น", "นครราชสีมา"]
KEYS = re.compile(r"น้ำท่วม|น้ำล้น|ฝนตกหนัก|ปภ\.|อุทกภัย|ดินถล่ม|ระบายน้ำ|จราจรติดขัด|ผ่านไม่ได้")

def get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read().decode("utf-8", "ignore")

def text(h):
    h = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h))

def src(name, url, fn):
    out = {"name": name, "url": url, "fetched_at": NOW.isoformat(timespec="minutes"), "ok": False, "data": None, "error": None}
    try:
        out["data"] = fn(url); out["ok"] = True
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:200]
    print(f"[{'ok ' if out['ok'] else 'ERR'}] {name}: {out['error'] or ''}", file=sys.stderr)
    return out

# ---------- ThaiWater (HII) ----------
def tw_rain(url):
    d = json.loads(get(url))["data"]
    def prov(x): return ((x.get("geocode") or {}).get("province_name") or {}).get("th", "")
    rows = [x for x in d if x.get("rain_24h") is not None]
    by = defaultdict(list)
    for x in rows: by[prov(x)].append(x)
    def top(xs, n):
        xs = sorted(xs, key=lambda x: -x["rain_24h"])[:n]
        return [{"province": prov(x), "station": (x.get("station") or {}).get("tele_station_name", {}).get("th", ""),
                 "rain_24h": x["rain_24h"], "at": x.get("rainfall_datetime")} for x in xs]
    return {"stations": len(rows), "top_national": top(rows, 5),
            "by_province": {p: {"n": len(by[p]), "max": top(by[p], 1)[0] if by[p] else None} for p in METRO + WATCH}}

def tw_level(url):
    d = json.loads(get(url))["waterlevel_data"]["data"]
    def prov(x): return ((x.get("geocode") or {}).get("province_name") or {}).get("th", "")
    lv = defaultdict(int); byp = defaultdict(lambda: defaultdict(int)); crit = []
    for x in d:
        s = x.get("situation_level")
        if s is None: continue
        lv[str(s)] += 1; byp[prov(x)][str(s)] += 1
        if s >= 4:
            crit.append({"province": prov(x), "station": (x.get("station") or {}).get("tele_station_name", {}).get("th", ""),
                         "level": s, "storage_percent": x.get("storage_percent"), "at": x.get("waterlevel_datetime")})
    crit.sort(key=lambda c: (-c["level"], -(float(c["storage_percent"] or 0))))
    return {"stations": len(d), "levels": dict(lv), "critical_top": crit[:8],
            "by_province": {p: dict(byp[p]) for p in METRO + WATCH}}

def tw_warn(url):
    d = json.loads(get(url))["data"]
    return [{"at": x.get("datetime"), "msg": re.sub(r"\s+", " ", x.get("message", ""))[:220]} for x in d[:10]]

# ---------- TMD ----------
def tmd_daily(url):
    t = text(get(url)); i = t.find("พยากรณ์อากาศ 24 ชั่วโมงข้างหน้า")
    if i < 0: raise ValueError("anchor not found")
    return t[i:i + 700]

def tmd_warning(url):
    t = text(get(url))
    m = re.search(r"([^|:]{10,160}?ฉบับที่\s*\d+\s*\(\d+/25\d{2}\).{0,500}?)(?=\s*(?:Tags:|หมวดหมู่:|$))", t)
    if not m: raise ValueError("no bulletin found")
    return re.sub(r"\s+", " ", m.group(1)).strip()[:700]

# ---------- DOH ----------
def doh_news(url):
    t = text(get(url)); items = re.findall(r"(\d{2}/\d{2}/25\d{2}) \| \d+ (.{10,220}?)(?= ข่าว|$)", t)
    return [{"date": d, "title": s.strip()} for d, s in items if KEYS.search(s)][:8]

# ---------- JS100 ----------
def js100(url):
    t = text(get(url)); items = re.findall(r"(.{15,220}?) (\d{1,2} \S+ 25\d{2}, \d{2}:\d{2}น\.)", t)
    out, seen = [], set()
    for s_, a in items:
        s_ = re.sub(r"^.*?(?:Tweet อ่านต่อ|POST & SHARE)\s*", "", s_).strip()
        if KEYS.search(s_) and s_ not in seen:
            seen.add(s_); out.append({"at": a, "title": s_})
    return out[:10]

sources = [
    src("ThaiWater ฝนสะสม 24 ชม.", "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/rain_24h", tw_rain),
    src("ThaiWater ระดับน้ำ", "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_load", tw_level),
    src("ThaiWater ประกาศเตือน", "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/warning", tw_warn),
    src("กรมอุตุฯ พยากรณ์ 24 ชม.", "https://www.tmd.go.th/forecast/daily", tmd_daily),
    src("กรมอุตุฯ ประกาศเตือนภัย", "https://www.tmd.go.th/warning-and-events/warning-storm", tmd_warning),
    src("กรมทางหลวง ข่าวน้ำท่วม", "https://www.doh.go.th/", doh_news),
    src("จส.100 ข่าว", "https://www.js100.com/en/site/news", js100),
    {"name": "Google Flood Hub", "url": "https://sites.research.google/floods", "fetched_at": NOW.isoformat(timespec="minutes"), "ok": False, "data": None, "error": "needs API key (floodforecasting.googleapis.com) or browser"},
    {"name": "ปภ. (disaster.go.th)", "url": "https://www.disaster.go.th/", "fetched_at": NOW.isoformat(timespec="minutes"), "ok": False, "data": None, "error": "Nuxt SPA, no public API found"},
]
S = {s["name"]: s for s in sources}
json.dump({"generated_at": NOW.isoformat(timespec="minutes"), "sources": sources}, open("latest.json", "w"), ensure_ascii=False, indent=1)

# ---------- markdown ----------
def L(name, body):
    s = S[name]
    head = f"**{name}** · [{s['url'].split('//')[1].split('/')[0]}]({s['url']}) · {s['fetched_at'][11:16]}"
    return head + ("\n" + body if s["ok"] else f"\n- ดึงไม่ได้: `{s['error']}`")

md = [f"# สถานการณ์น้ำ/ฝน/ถนน — {NOW:%d %b %Y %H:%M} (Asia/Bangkok)", ""]
md += ["## 1. ภาพรวมทั้งประเทศ", ""]
r = S["ThaiWater ฝนสะสม 24 ชม."]; body = "\n".join(f"- {x['province']} {x['station']} **{x['rain_24h']} มม.** ({x['at'][11:]})" for x in (r["data"] or {}).get("top_national", []))
md += [L(r["name"], body), ""]
w = S["ThaiWater ระดับน้ำ"]; d = w["data"] or {}
body = f"- สถานี {d.get('stations')} แห่ง · ระดับ 5 (วิกฤต) {d.get('levels',{}).get('5',0)} · ระดับ 4 {d.get('levels',{}).get('4',0)}\n" + "\n".join(f"- L{c['level']} {c['province']} {c['station']} {c['storage_percent']}% ({c['at'][11:]})" for c in d.get("critical_top", []))
md += [L(w["name"], body), ""]
t = S["กรมอุตุฯ พยากรณ์ 24 ชม."]; md += [L(t["name"], f"> {t['data']}" if t["ok"] else ""), ""]
t = S["กรมอุตุฯ ประกาศเตือนภัย"]; md += [L(t["name"], f"> {t['data']}" if t["ok"] else ""), ""]
t = S["ThaiWater ประกาศเตือน"]; md += [L(t["name"], "\n".join(f"- {x['at'][11:16]} {x['msg']}" for x in (t["data"] or [])[:6])), ""]
t = S["กรมทางหลวง ข่าวน้ำท่วม"]; md += [L(t["name"], "\n".join(f"- {x['date']} {x['title']}" for x in (t["data"] or []))), ""]
t = S["จส.100 ข่าว"]; md += [L(t["name"], "\n".join(f"- {x['at']} {x['title']}" for x in (t["data"] or []))), ""]

def prov_table(provs):
    rows = ["| จังหวัด | ฝนสูงสุด 24 ชม. | สถานีน้ำ L4 / L5 |", "|---|---|---|"]
    rp = (r["data"] or {}).get("by_province", {}); wp = d.get("by_province", {})
    for p in provs:
        m = (rp.get(p) or {}).get("max"); lv = wp.get(p, {})
        rows.append(f"| {p} | {f'**{m['rain_24h']} มม.** {m['station']}' if m else '—'} | {lv.get('4',0)} / {lv.get('5',0)} |")
    return "\n".join(rows)
md += ["## 2. กรุงเทพฯ–ปริมณฑล", "", prov_table(METRO), ""]
md += ["## 3. จังหวัดที่เฝ้า", "", prov_table(WATCH), ""]
md += ["## แหล่งที่ดึงไม่ได้รอบนี้", ""] + [f"- {s['name']}: {s['error']}" for s in sources if not s["ok"]]
md += ["", "_ทุกค่า = ค่าที่แหล่งรายงาน ณ เวลาที่ระบุ ไม่มีค่าประมาณการของผู้สรุป_"]
import os
os.makedirs("daily", exist_ok=True)
open("latest.md", "w").write("\n".join(md))
open(f"daily/{NOW:%Y-%m-%d}.md", "w").write("\n".join(md))
json.dump({"generated_at": NOW.isoformat(timespec="minutes"), "sources": sources}, open(f"daily/{NOW:%Y-%m-%d}.json", "w"), ensure_ascii=False)
rp = (r["data"] or {}).get("by_province", {}); bkk = (rp.get("กรุงเทพมหานคร") or {}).get("max") or {}
doh = (S["กรมทางหลวง ข่าวน้ำท่วม"]["data"] or [{}])[:1]
brief = [f"ฝนสูงสุด: {(r['data'] or {}).get('top_national',[{}])[0].get('province','-')} {(r['data'] or {}).get('top_national',[{}])[0].get('rain_24h','-')} มม. | กทม. {bkk.get('rain_24h','-')} มม. {bkk.get('station','')}",
         f"น้ำ L5 {d.get('levels',{}).get('5',0)} สถานี / L4 {d.get('levels',{}).get('4',0)} | กทม.-ปริมณฑล L5 {sum(int(d.get('by_province',{}).get(p,{}).get('5',0)) for p in METRO)}",
         (doh[0].get("title","ทางหลวง: ไม่มีข่าวใหม่")[:90] if doh else "ทางหลวง: ไม่มีข่าวใหม่"),
         f"ดึงไม่ได้: {sum(1 for x in sources if not x['ok'])}/{len(sources)}"]
open("brief.txt", "w").write("\n".join(brief))
print("wrote latest.json latest.md daily/ brief.txt", file=sys.stderr)
