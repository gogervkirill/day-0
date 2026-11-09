#!/usr/bin/env python3
"""
Выгрузка данных OpenStreetMap по Алматы для игры «Алматы: Сбой».

Запуск:  python3 fetch_osm.py            (Windows: py fetch_osm.py)
Результат: osm_almaty.js рядом с index.html (положи в корень игры).

Нужен только Python 3.8+ и интернет. Сторонних библиотек нет.
Если Overpass недоступен из Python (например, антивирус перехватывает HTTPS),
можно сохранить ответы Overpass в папку (city.json, districts.json, pois.json, roads.json)
и запустить:  python fetch_osm.py --raw ПАПКА
Данные © OpenStreetMap contributors, лицензия ODbL.
"""
import json, os, sys, time, urllib.parse, urllib.request

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "osm_almaty.js")
UA = "almaty-sboy-game/1.0 (data fetch script)"


RAW = sys.argv[sys.argv.index("--raw") + 1] if "--raw" in sys.argv else None
RAW_NAMES = {"город": "city", "районы": "districts", "точки": "pois", "дороги": "roads"}


def overpass(query, label):
    if RAW:  # готовые ответы Overpass из папки
        with open(os.path.join(RAW, RAW_NAMES[label] + ".json"), encoding="utf-8") as f:
            js = json.load(f)
        print(f"  [{label}] из файла: {len(js.get('elements', []))} объектов")
        return js
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for attempt in range(2):
        for url in ENDPOINTS:
            try:
                print(f"  [{label}] {url} ...", flush=True)
                req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=300) as r:
                    js = json.loads(r.read().decode("utf-8"))
                print(f"  [{label}] ok: {len(js.get('elements', []))} объектов")
                return js
            except Exception as e:  # пробуем следующий сервер
                last = e
                print(f"  [{label}] ошибка: {e}")
                time.sleep(3)
        time.sleep(15)
    sys.exit(f"Не удалось получить данные ({label}): {last}")


# ---------- геометрия ----------
def rd(v):
    return round(v, 5)


def simplify(pts, tol):
    """Дуглас-Пекер, pts = [[lon,lat],...]"""
    if len(pts) < 3:
        return pts
    def dist(p, a, b):
        (x, y), (x1, y1), (x2, y2) = p, a, b
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return ((x - x1) ** 2 + (y - y1) ** 2) ** .5
        t = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
        return ((x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2) ** .5
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        best, idx = 0, -1
        for i in range(a + 1, b):
            d = dist(pts[i], pts[a], pts[b])
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def rings_from_relation(rel):
    """Собирает замкнутые кольца из way-членов отношения (outer и inner вместе: игра считает чётно-нечётно)."""
    ways = []
    for m in rel.get("members", []):
        if m.get("type") == "way" and m.get("geometry"):
            ways.append([[g["lon"], g["lat"]] for g in m["geometry"] if g])
    rings = []
    while ways:
        ring = ways.pop(0)
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, w in enumerate(ways):
                if w[0] == ring[-1]:
                    ring += w[1:]
                elif w[-1] == ring[-1]:
                    ring += w[::-1][1:]
                elif w[-1] == ring[0]:
                    ring = w[:-1] + ring
                elif w[0] == ring[0]:
                    ring = w[::-1][:-1] + ring
                else:
                    continue
                ways.pop(i)
                changed = True
                break
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def pack_rings(rings, tol):
    out = []
    for r in rings:
        s = simplify(r, tol)
        if len(s) >= 4:
            out.append([[rd(x), rd(y)] for x, y in s])
    return out


# ---------- классификация точек ----------
def classify(t):
    a, s = t.get("amenity"), t.get("shop")
    if a == "pharmacy": return "pharm", "Аптека"
    if a == "hospital": return "hospital", "Больница"
    if a == "clinic": return "hospital", "Поликлиника"
    if a == "police": return "police", "Полиция"
    if a == "marketplace": return "market", "Рынок"
    if a == "fuel": return "garage", "АЗС"
    if s == "mall" or s == "department_store": return "mall", "ТЦ"
    if s in ("supermarket", "convenience", "grocery", "general"): return "shop", "Магазин"
    if s == "car_repair": return "garage", "Автосервис"
    if s in ("hardware", "doityourself"): return "garage", "Стройматериалы"
    if t.get("railway") == "station": return "station", "Станция"
    if t.get("leisure") == "park": return "park", "Парк"
    if t.get("landuse") == "garages": return "garage", "Гаражи"
    if t.get("power") == "plant": return "power", "Электростанция"
    if t.get("military"): return "military", "Военный объект"
    mm = t.get("man_made")
    if mm == "communications_tower" or (mm in ("mast", "tower") and t.get("tower:type") == "communication"):
        return "tower", "Вышка связи"
    return None, None


def main():
    print("1/4 Ищу границу Алматы…")
    js = overpass('[out:json][timeout:60];rel["boundary"="administrative"]["name"="Алматы"];out tags;', "город")
    rels = js["elements"]
    if not rels:
        sys.exit("Граница Алматы не найдена")
    rels.sort(key=lambda r: {"4": 0, "5": 1, "6": 2}.get(r["tags"].get("admin_level"), 9))
    city_id = rels[0]["id"]
    area = 3600000000 + city_id
    print(f"  relation {city_id}, admin_level={rels[0]['tags'].get('admin_level')}")

    print("2/4 Граница города и районы…")
    js = overpass(f"""[out:json][timeout:240];
rel({city_id});out geom;
area({area})->.a;
rel(area.a)["boundary"="administrative"]["admin_level"="6"];
out geom;""", "районы")
    city, districts, seen = [], [], set()
    for el in js["elements"]:
        if el["type"] != "relation":
            continue
        if el["id"] == city_id:
            city = pack_rings(rings_from_relation(el), 0.0004)
            continue
        name = (el["tags"].get("name:ru") or el["tags"].get("name", "")).replace(" район", "").strip()  # name — по-казахски
        if not name or name in seen:
            continue
        seen.add(name)
        rings = pack_rings(rings_from_relation(el), 0.0003)
        if rings:
            districts.append({"n": name, "r": rings})
    print(f"  город: {len(city)} колец, районов: {len(districts)} → {', '.join(d['n'] for d in districts)}")

    print("3/4 Точки лута (магазины, аптеки, больницы…)… это самый долгий запрос")
    js = overpass(f"""[out:json][timeout:300];
area({area})->.a;
(
 nwr(area.a)["amenity"~"^(pharmacy|hospital|clinic|police|marketplace|fuel)$"];
 nwr(area.a)["shop"~"^(supermarket|convenience|grocery|general|mall|department_store|car_repair|hardware|doityourself)$"];
 nwr(area.a)["railway"="station"];
 nwr(area.a)["leisure"="park"];
 nwr(area.a)["landuse"="garages"];
 nwr(area.a)["power"="plant"];
 nwr(area.a)["military"];
 nwr(area.a)["man_made"~"^(mast|tower|communications_tower)$"];
);
out center tags;""", "точки")
    pois, stat = [], {}
    for el in js["elements"]:
        t = el.get("tags", {})
        typ, label = classify(t)
        if not typ:
            continue
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None:
            continue
        name = (t.get("name:ru") or t.get("name") or "").strip()
        n = label + (f" «{name[:36]}»" if name and label not in ("Гаражи",) else "")
        pois.append([rd(lon), rd(lat), typ, n])
        stat[typ] = stat.get(typ, 0) + 1
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(stat.items())))

    print("4/4 Главные дороги и реки…")
    js = overpass(f"""[out:json][timeout:240];
area({area})->.a;
(way(area.a)["highway"~"^(motorway|trunk|primary|secondary)$"];way(area.a)["waterway"="river"];);
out geom tags;""", "дороги")
    roads, rivers = [], []
    for el in js["elements"]:
        g = el.get("geometry")
        if not g:
            continue
        line = [[rd(x), rd(y)] for x, y in simplify([[p["lon"], p["lat"]] for p in g], 0.00008)]
        if len(line) < 2:
            continue
        t = el.get("tags", {})
        if t.get("waterway"):
            rivers.append(line)
        else:
            rank = {"motorway": 0, "trunk": 0, "primary": 1, "secondary": 2}.get(t.get("highway"), 2)
            roads.append([t.get("name:ru") or t.get("name") or "", rank, line])
    print(f"  дорог: {len(roads)}, рек: {len(rivers)}")

    data = {"v": 1, "date": time.strftime("%Y-%m-%d"), "city": city, "districts": districts,
            "pois": pois, "roads": roads, "rivers": rivers}
    out = os.path.abspath(OUT)
    with open(out, "w", encoding="utf-8") as f:
        f.write("/* Данные © OpenStreetMap contributors, ODbL. Сгенерировано fetch_osm.py */\n")
        f.write("window.OSM=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"\nГотово: {out} ({os.path.getsize(out) // 1024} КБ)")
    print("Положи osm_almaty.js в корень игры рядом с index.html.")


if __name__ == "__main__":
    main()
