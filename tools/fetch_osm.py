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
RAW_NAMES = {"город": "city", "районы": "districts", "точки": "pois", "дороги": "roads", "застройка": "landuse"}


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


# ---------- застройка → тип клетки игры ----------
# Сетка должна совпадать с index.html: CELL_REAL, LAT0, BOUNDS. Игра проверяет lu.cell.
import math
CELL_REAL, LAT0 = 125, 43.25
BOUNDS = (76.73, 43.13, 77.11, 43.43)
R_EARTH = 6378137
CELL_M = CELL_REAL / math.cos(math.radians(LAT0))
def merc(lon, lat):
    return R_EARTH * math.radians(lon), R_EARTH * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
OX, OY = merc(BOUNDS[0], BOUNDS[1]); EX, EY = merc(BOUNDS[2], BOUNDS[3])
GW, GH = math.ceil((EX - OX) / CELL_M), math.ceil((EY - OY) / CELL_M)

LANDUSE_Q = """[out:json][timeout:600][maxsize:1073741824];area(AREA)->.a;(
way(area.a)["landuse"~"^(residential|industrial|commercial|retail|garages|military|cemetery|construction|brownfield|farmland|orchard|allotments|forest|recreation_ground|railway)$"];
rel(area.a)["landuse"~"^(residential|industrial|military|cemetery|forest|commercial|retail)$"];
way(area.a)["leisure"~"^(park|garden)$"];rel(area.a)["leisure"="park"];
way(area.a)["natural"~"^(water|wood)$"];rel(area.a)["natural"~"^(water|wood)$"];
);out geom qt;"""
# код клетки: W вода, M военные, I промзона, G гаражи, C торговля/офисы, P парк, L лес, X кладбище, S стройка, F сады/дачи, R жильё
LU_PRI = "WMIGCPLXSFR"
def lu_code(t):
    lu, le, na = t.get("landuse"), t.get("leisure"), t.get("natural")
    if na == "water": return "W"
    if lu == "military": return "M"
    if lu in ("industrial", "railway"): return "I"
    if lu == "garages": return "G"
    if lu in ("commercial", "retail"): return "C"
    if le in ("park", "garden") or lu == "recreation_ground": return "P"  # газоны (grass) не считаем: дробят жилые кварталы
    if lu == "forest" or na == "wood": return "L"
    if lu == "cemetery": return "X"
    if lu in ("construction", "brownfield"): return "S"
    if lu in ("farmland", "orchard", "allotments"): return "F"
    if lu == "residential": return "R"
    return None

def rasterize_landuse(elements):
    grid = bytearray(b"." * (GW * GH)); stat = {}
    for el in elements:
        code = lu_code(el.get("tags", {}))
        if not code:
            continue
        if el["type"] == "way":
            g = el.get("geometry") or []
            rings = [[[p["lon"], p["lat"]] for p in g if p]] if len(g) >= 4 else []
        else:
            rings = rings_from_relation(el)
        cr = []
        for r in rings:  # в координаты сетки
            pts = [((mx - OX) / CELL_M, (my - OY) / CELL_M) for mx, my in (merc(x, y) for x, y in r)]
            if len(pts) >= 3: cr.append(pts)
        if not cr:
            continue
        xs = [p[0] for r in cr for p in r]; ys = [p[1] for r in cr for p in r]
        i0, i1 = max(0, int(min(xs))), min(GW - 1, int(max(xs))); j0, j1 = max(0, int(min(ys))), min(GH - 1, int(max(ys)))
        pr = LU_PRI.index(code)
        for j in range(j0, j1 + 1):
            cy = j + .5
            for i in range(i0, i1 + 1):
                cx = i + .5; inside = False
                for r in cr:  # чётно-нечётно по всем кольцам
                    n = len(r)
                    for k in range(n):
                        (x1, y1), (x2, y2) = r[k], r[k - 1]
                        if (y1 > cy) != (y2 > cy) and cx < (x2 - x1) * (cy - y1) / (y2 - y1) + x1:
                            inside = not inside
                if inside:
                    cur = chr(grid[j * GW + i])
                    if cur == "." or LU_PRI.index(cur) > pr:
                        grid[j * GW + i] = ord(code)
    out, k = [], 0  # RLE: «число+символ»
    while k < len(grid):
        c, n = grid[k], 1
        while k + n < len(grid) and grid[k + n] == c: n += 1
        out.append((str(n) if n > 1 else "") + chr(c)); k += n
    for c in grid: stat[chr(c)] = stat.get(chr(c), 0) + 1
    print("  клетки: " + ", ".join(f"{k}:{v}" for k, v in sorted(stat.items())))
    return {"cell": CELL_REAL, "w": GW, "h": GH, "s": "".join(out)}


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
    print("1/5 Ищу границу Алматы…")
    js = overpass('[out:json][timeout:60];rel["boundary"="administrative"]["name"="Алматы"];out tags;', "город")
    rels = js["elements"]
    if not rels:
        sys.exit("Граница Алматы не найдена")
    rels.sort(key=lambda r: {"4": 0, "5": 1, "6": 2}.get(r["tags"].get("admin_level"), 9))
    city_id = rels[0]["id"]
    area = 3600000000 + city_id
    print(f"  relation {city_id}, admin_level={rels[0]['tags'].get('admin_level')}")

    print("2/5 Граница города и районы…")
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

    print("3/5 Точки лута (магазины, аптеки, больницы…)… это самый долгий запрос")
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

    print("4/5 Главные дороги и реки…")
    js = overpass(f"""[out:json][timeout:240];
area({area})->.a;
(way(area.a)["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"];way(area.a)["waterway"="river"];);
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
            rank = {"motorway": 0, "trunk": 0, "primary": 1, "secondary": 2, "tertiary": 3}.get(t.get("highway"), 3)
            roads.append([t.get("name:ru") or t.get("name") or "", rank, line])
    print(f"  дорог: {len(roads)}, рек: {len(rivers)}")

    print("5/5 Застройка и вода (сетка игры)… большой запрос")
    js = overpass(LANDUSE_Q.replace("AREA", str(area)), "застройка")
    lu = rasterize_landuse(js["elements"])

    data = {"v": 1, "date": time.strftime("%Y-%m-%d"), "city": city, "districts": districts,
            "pois": pois, "roads": roads, "rivers": rivers, "lu": lu}
    out = os.path.abspath(OUT)
    with open(out, "w", encoding="utf-8") as f:
        f.write("/* Данные © OpenStreetMap contributors, ODbL. Сгенерировано fetch_osm.py */\n")
        f.write("window.OSM=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print(f"\nГотово: {out} ({os.path.getsize(out) // 1024} КБ)")
    print("Положи osm_almaty.js в корень игры рядом с index.html.")


if __name__ == "__main__":
    main()
