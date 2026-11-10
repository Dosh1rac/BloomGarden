from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime, timedelta, date
import sqlite3
import os
import random

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "garden.db")

app = FastAPI(title="Цветущий сад")


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


# ---------------------------------------------------------------- каталог
SPECIES = {
    "tulip":      {"name": "Тюльпан",       "rarity": "Обычный",     "color": "#ff6f91", "petals": 5, "cost": 20,  "emoji": "🌷"},
    "crocus":     {"name": "Крокус",        "rarity": "Обычный",     "color": "#a67fe0", "petals": 5, "cost": 15,  "emoji": "🌱"},
    "iris":       {"name": "Ирис",          "rarity": "Редкий",      "color": "#7b6fd0", "petals": 6, "cost": 30,  "emoji": "🪻"},
    "eustoma":    {"name": "Эустома",       "rarity": "Редкий",      "color": "#f0c7dd", "petals": 6, "cost": 40,  "emoji": "🎀"},
    "rosebush":   {"name": "Кустовая роза", "rarity": "Редкий",      "color": "#e75480", "petals": 6, "cost": 45,  "emoji": "🌹"},
    "freesia":    {"name": "Фрезия",        "rarity": "Редкий",      "color": "#f7d154", "petals": 6, "cost": 35,  "emoji": "🌼"},
    "peony":      {"name": "Пион",          "rarity": "Особенный",   "color": "#f2a0bd", "petals": 8, "cost": 60,  "emoji": "🌸"},
    "ranunculus": {"name": "Ранункулюс",    "rarity": "Особенный",   "color": "#f49e8c", "petals": 8, "cost": 70,  "emoji": "🌺"},
    "lilac":      {"name": "Сирень",        "rarity": "Особенный",   "color": "#b39ddb", "petals": 8, "cost": 65,  "emoji": "💜"},
    "calla":      {"name": "Калла",         "rarity": "Легендарный", "color": "#fbf7f2", "petals": 9, "cost": 120, "emoji": "🤍"},
    "gypsophila": {"name": "Гипсофила",     "rarity": "Мифический",  "color": "#f7f4f8", "petals": 10, "cost": 250, "emoji": "☁️"},
    "secret":     {"name": "Цветок любви",  "rarity": "Мифический",  "color": "#ff9ec7", "petals": 10, "cost": 0,   "emoji": "💗"},
}

# старые ключи и русские названия -> новые виды
LEGACY_SPECIES = {
    "rose": "rosebush", "Роза": "rosebush",
    "lavender": "lilac", "Лаванда": "lilac",
    "cactus": "crocus", "Кактус": "crocus",
    "sakura": "eustoma", "Сакура": "eustoma",
    "orchid": "freesia", "Орхидея": "freesia",
    "sun": "ranunculus", "Подсолнух": "ranunculus",
    "lotus": "iris", "Лотос": "iris",
    "moon": "gypsophila", "Лунный цветок": "gypsophila",
}

DECOR = {
    "lantern":  {"name": "Фонарик",   "price": 60,  "emoji": "🏮"},
    "bench":    {"name": "Скамейка",  "price": 80,  "emoji": "🪑"},
    "butterfly":{"name": "Бабочка",   "price": 50,  "emoji": "🦋"},
    "path":     {"name": "Дорожка",   "price": 70,  "emoji": "🪨"},
    "statue":   {"name": "Статуэтка", "price": 150, "emoji": "🗿"},
    "fountain": {"name": "Фонтан",    "price": 300, "emoji": "⛲"},
    "swing":    {"name": "Качели",    "price": 250, "emoji": "🎠"},
    "moonlamp": {"name": "Лунная лампа", "price": 500, "emoji": "🌜"},
}


# ---------------------------------------------------------------- база
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            name TEXT,
            petals INTEGER DEFAULT 120,
            last_daily TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS plants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            species TEXT,
            planted_at TEXT,
            last_watered TEXT,
            last_fed TEXT,
            harvested_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS decor (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT,
            added_at TEXT,
            pos_x REAL,
            pos_y REAL
        )
    """)
    # миграция декора: координаты для перетаскивания
    dcols = [r[1] for r in c.execute("PRAGMA table_info(decor)").fetchall()]
    for col in ("pos_x", "pos_y"):
        if col not in dcols:
            c.execute("ALTER TABLE decor ADD COLUMN %s REAL" % col)
    # старые координаты были в пикселях «травки» — переводим в проценты экрана
    c.execute("UPDATE decor SET pos_y = MIN(pos_y / 10.0, 15) WHERE pos_y > 30")
    c.execute("SELECT COUNT(*) FROM user")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO user (id, name, petals, last_daily) VALUES (1, ?, ?, NULL)",
                  ("Мой сад", 120))

    # миграция старой схемы
    cols = [r[1] for r in c.execute("PRAGMA table_info(plants)").fetchall()]
    for col in ("planted_at", "last_fed", "harvested_at"):
        if col not in cols:
            c.execute("ALTER TABLE plants ADD COLUMN %s TEXT" % col)
    c.execute("UPDATE plants SET planted_at = last_watered WHERE planted_at IS NULL")
    c.execute("SELECT COUNT(*) FROM plants")
    if c.fetchone()[0] == 0:
        now = datetime.now()
        c.execute("""INSERT INTO plants (name, species, planted_at, last_watered, last_fed)
                     VALUES (?, ?, ?, ?, NULL)""",
                  ("Первый тюльпан", "tulip",
                   now.isoformat(),
                   now.isoformat()))
    c.execute("UPDATE plants SET name = 'Нежность' WHERE name = 'Доширак'")
    conn.commit()
    conn.close()


SECRET_NOTE = (
    "Дорогая моя Юлечка! Я знаю, как много сил ты отдаешь работе и как сильно устаешь, "
    "когда времени на отдых и на саму себя почти не остается. 🌸\n\n"
    "Я создал этот сад специально для тебя — это твой личный островок тишины, красоты и спокойствия. "
    "Пусть здесь время замирает, а эти цветы дарят тебе только улыбку. Заходи сюда, чтобы просто выдохнуть "
    "и почувствовать мою заботу. 💌\n\n"
    "Ты у меня самая лучшая, самая любимая, близкая и родная. Помни об этом всегда. 💗"
)


init_db()


# ---------------------------------------------------------------- логика
STAGES = [
    ("семечко", 2),
    ("росток", 12),
    ("молодой цветок", 48),
    ("взрослый цветок", 10 ** 9),
]


def get_stage(planted_at, last_fed):
    try:
        planted = datetime.fromisoformat(planted_at)
    except Exception:
        return "семечко"
    hours = (datetime.now() - planted).total_seconds() / 3600
    # удобрение ускоряет рост на 12 часов
    if last_fed:
        try:
            fed = datetime.fromisoformat(last_fed)
            if datetime.now() - fed < timedelta(hours=12):
                hours += 12
        except Exception:
            pass
    for stage, limit in STAGES:
        if hours < limit:
            return stage
    return "взрослый цветок"


def get_status(last_watered):
    if not last_watered:
        return "увядает", 0.25
    try:
        watered = datetime.fromisoformat(last_watered)
    except Exception:
        return "отлично", 1.0
    hours = (datetime.now() - watered).total_seconds() / 3600
    if hours < 24:
        return "отлично", 1.0
    if hours < 48:
        return "подсыхает", 0.8
    if hours < 72:
        return "поник", 0.6
    return "увядает", 0.4


def fetch_user(c):
    row = c.execute("SELECT id, name, petals, last_daily FROM user WHERE id = 1").fetchone()
    return dict(row)


def plant_payload(row):
    status, health = get_status(row["last_watered"])
    stage = get_stage(row["planted_at"], row["last_fed"])
    key = row["species"]
    if key in LEGACY_SPECIES:
        key = LEGACY_SPECIES[key]
    if key not in SPECIES:
        # совместимость со старыми записями, где хранилось русское название
        for k, v in SPECIES.items():
            if v["name"].lower() == str(key).lower():
                key = k
                break
        else:
            key = "tulip"
    species = SPECIES[key]
    if key == "secret":
        can_harvest, next_harvest_at = False, None
    else:
        can_harvest, next_harvest_at = harvest_state(row, stage)
    return {
        "id": row["id"],
        "name": row["name"],
        "species": key,
        "species_name": species["name"],
        "rarity": species["rarity"],
        "color": species["color"],
        "emoji": species["emoji"],
        "is_secret": key == "secret",
        "stage": stage,
        "status": status,
        "health": health,
        "last_watered": row["last_watered"],
        "last_fed": row["last_fed"],
        "harvested_at": row["harvested_at"],
        "can_harvest": can_harvest,
        "next_harvest_at": next_harvest_at,
    }


HARVEST_REWARDS = {"Обычный": 12, "Редкий": 22, "Особенный": 35, "Легендарный": 60, "Мифический": 90}


def harvest_state(row, stage=None):
    if stage is None:
        stage = get_stage(row["planted_at"], row["last_fed"])
    if stage != "взрослый цветок":
        return False, None
    if not row["harvested_at"]:
        return True, None
    try:
        last = datetime.fromisoformat(row["harvested_at"])
    except Exception:
        return True, None
    nxt = last + timedelta(hours=24)
    if datetime.now() >= nxt:
        return True, None
    return False, nxt.isoformat()


def get_time_of_day():
    hour = datetime.now().hour
    if 5 <= hour < 11:
        return {"name": "утро", "icon": "🌅"}
    if 11 <= hour < 17:
        return {"name": "день", "icon": "☀️"}
    if 17 <= hour < 22:
        return {"name": "вечер", "icon": "🌆"}
    return {"name": "ночь", "icon": "🌙"}


def get_season():
    month = datetime.now().month
    if month in (3, 4, 5):
        return {"name": "весна", "icon": "🌷"}
    if month in (6, 7, 8):
        return {"name": "лето", "icon": "☀️"}
    if month in (9, 10, 11):
        return {"name": "осень", "icon": "🍂"}
    return {"name": "зима", "icon": "❄️"}


def daily_available(user):
    today = date.today().isoformat()
    return user.get("last_daily") != today


# ---------------------------------------------------------------- API
@app.get("/api/state")
def state():
    conn = db()
    c = conn.cursor()
    user = fetch_user(c)
    plants = [plant_payload(r) for r in c.execute(
        "SELECT * FROM plants ORDER BY id").fetchall()]
    decor_rows = c.execute("SELECT id, item, pos_x, pos_y FROM decor").fetchall()
    conn.close()

    mood = "сияет" if all(p["health"] >= 0.8 for p in plants) else (
        "немного грустит" if any(p["health"] < 0.6 for p in plants) else "спокоен")

    return {
        "user": user,
        "plants": plants,
        "decor": [{
            "id": d["id"],
            "item": d["item"],
            "pos_x": d["pos_x"],
            "pos_y": d["pos_y"],
            **DECOR.get(d["item"], {"name": d["item"], "emoji": "✨"}),
        } for d in decor_rows],
        "shop": {
            "seeds": [{"id": k, **v} for k, v in SPECIES.items() if k != "secret"],
            "decor": [{"id": k, **v} for k, v in DECOR.items()],
        },
        "secret_note": SECRET_NOTE,
        "time_of_day": get_time_of_day(),
        "season": get_season(),
        "mood": mood,
        "daily_available": daily_available(user),
    }


class NameIn(BaseModel):
    name: str


class SpeciesIn(BaseModel):
    species: str


class PosIn(BaseModel):
    x: float
    y: float


@app.post("/api/water/{plant_id}")
def water(plant_id: int):
    conn = db()
    c = conn.cursor()
    row = c.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Растение не найдено")
    now = datetime.now().isoformat()
    c.execute("UPDATE plants SET last_watered = ? WHERE id = ?", (now, plant_id))
    c.execute("UPDATE user SET petals = petals + 2 WHERE id = 1")
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Полито! +2 🌸"}


@app.post("/api/feed/{plant_id}")
def feed(plant_id: int):
    conn = db()
    c = conn.cursor()
    row = c.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Растение не найдено")
    user = fetch_user(c)
    if user["petals"] < 10:
        conn.close()
        raise HTTPException(400, "Недостаточно лепестков (нужно 10)")
    now = datetime.now().isoformat()
    c.execute("UPDATE plants SET last_fed = ? WHERE id = ?", (now, plant_id))
    c.execute("UPDATE user SET petals = petals - 10 WHERE id = 1")
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Удобрено! Рост ускорился 🌿"}


@app.post("/api/rain")
def rain_all():
    conn = db()
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("UPDATE plants SET last_watered = ?", (now,))
    c.execute("UPDATE user SET petals = petals + 5 WHERE id = 1")
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Дождик полил весь сад! +5 🌸"}


@app.post("/api/rename/{plant_id}")
def rename(plant_id: int, data: NameIn):
    name = data.name.strip()[:24]
    if not name:
        raise HTTPException(400, "Имя не может быть пустым")
    conn = db()
    c = conn.cursor()
    c.execute("UPDATE plants SET name = ? WHERE id = ?", (name, plant_id))
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Теперь его зовут «%s»" % name}


@app.post("/api/plant")
def plant(data: SpeciesIn):
    if data.species not in SPECIES:
        raise HTTPException(400, "Неизвестный вид")
    sp = SPECIES[data.species]
    conn = db()
    c = conn.cursor()
    user = fetch_user(c)
    if user["petals"] < sp["cost"]:
        conn.close()
        raise HTTPException(400, "Недостаточно лепестков")
    now = datetime.now().isoformat()
    c.execute("""INSERT INTO plants (name, species, planted_at, last_watered, last_fed)
                 VALUES (?, ?, ?, ?, NULL)""",
              (sp["name"] + " 🌱", data.species, now, now))
    c.execute("UPDATE user SET petals = petals - ? WHERE id = 1", (sp["cost"],))
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Посажено! Теперь он будет расти 🌱"}


@app.post("/api/decor/{item_id}")
def buy_decor(item_id: str):
    if item_id not in DECOR:
        raise HTTPException(400, "Неизвестная декорация")
    d = DECOR[item_id]
    conn = db()
    c = conn.cursor()
    user = fetch_user(c)
    if user["petals"] < d["price"]:
        conn.close()
        raise HTTPException(400, "Недостаточно лепестков")
    c.execute("INSERT INTO decor (item, added_at) VALUES (?, ?)",
              (item_id, datetime.now().isoformat()))
    c.execute("UPDATE user SET petals = petals - ? WHERE id = 1", (d["price"],))
    conn.commit()
    conn.close()
    return {"ok": True, "message": "%s теперь в саду %s" % (d["name"], d["emoji"])}


@app.post("/api/decor/move/{decor_id}")
def move_decor(decor_id: int, data: PosIn):
    conn = db()
    c = conn.cursor()
    row = c.execute("SELECT id FROM decor WHERE id = ?", (decor_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Декорация не найдена")
    c.execute("UPDATE decor SET pos_x = ?, pos_y = ? WHERE id = ?",
              (max(0, min(100, data.x)), max(0, min(100, data.y)), decor_id))
    conn.commit()
    conn.close()
    return {"ok": True, "message": "Передвинуто ✨"}


@app.post("/api/harvest/{plant_id}")
def harvest(plant_id: int):
    conn = db()
    c = conn.cursor()
    row = c.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Растение не найдено")
    stage = get_stage(row["planted_at"], row["last_fed"])
    if stage != "взрослый цветок":
        conn.close()
        raise HTTPException(400, "Он ещё не вырос — чуть-чуть терпения 🌱")
    can_harvest, next_at = harvest_state(row, stage)
    if not can_harvest:
        left = ""
        if next_at:
            try:
                nxt = datetime.fromisoformat(next_at)
                hours = max(1, int((nxt - datetime.now()).total_seconds() // 3600) + 1)
                left = " Осталось около %d ч." % hours
            except Exception:
                pass
        conn.close()
        raise HTTPException(400, "Урожай уже собран." + left)
    species_key = row["species"]
    species_key = LEGACY_SPECIES.get(species_key, species_key)
    if species_key not in SPECIES:
        species_key = "tulip"
    rarity = SPECIES[species_key]["rarity"]
    amount = HARVEST_REWARDS.get(rarity, 12)
    now = datetime.now().isoformat()
    c.execute("UPDATE plants SET harvested_at = ? WHERE id = ?", (now, plant_id))
    c.execute("UPDATE user SET petals = petals + ? WHERE id = 1", (amount,))
    conn.commit()
    conn.close()
    return {"ok": True, "petals": amount, "rarity": rarity,
            "message": "Урожай собран! +%d 🌸" % amount}


@app.post("/api/daily")
def daily():
    conn = db()
    c = conn.cursor()
    user = fetch_user(c)
    today = date.today().isoformat()
    if user["last_daily"] == today:
        conn.close()
        raise HTTPException(400, "Сегодня подарок уже получен")
    petals = random.choice([15, 20, 25, 30, 40])
    c.execute("UPDATE user SET petals = petals + ?, last_daily = ? WHERE id = 1",
              (petals, today))
    conn.commit()
    conn.close()
    return {"ok": True, "petals": petals,
            "message": "Ежедневный подарок: +%d 🌸" % petals}


@app.get("/favicon.ico")
def favicon():
    return {"ok": True}


frontend_path = os.path.join(BASE_DIR, "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
