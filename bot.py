import logging
import json
import os
import fcntl
import sys
from datetime import datetime, date, timedelta
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import random

# Ikki marta ishga tushmaslik uchun lock
LOCK_FILE = "/tmp/dailybot.lock"
def acquire_lock():
    try:
        lf = open(LOCK_FILE, 'w')
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lf
    except IOError:
        print("Bot allaqachon ishlamoqda. Chiqilmoqda.")
        sys.exit(0)

TOKEN = "8849559349:AAFQLKPjpVqfM-jLYWoB9j1f7Q4QbKNptDg"
CHAT_ID = 6456736085
TIMEZONE = pytz.timezone("Asia/Tashkent")

FILES = {
    "tasks": "tasks.json",
    "prayers": "prayers.json",
    "streak": "streak.json",
    "goals": "goals.json",
    "journal": "journal.json",
    "books": "books.json",
    "expenses": "expenses.json",
    "kpi": "kpi.json",
    "prayer_stats": "prayer_stats.json",
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOTIVATSION = [
    "🔥 Har bir qadam oldinga\\! Siz buni uddalay olasiz\\!",
    "⚡ Kichik harakatlar katta natijalarga olib boradi\\.",
    "🚀 Eng qiyin — boshlash\\. Boshlang, qolganini o'zingiz qilasiz\\!",
    "🎯 Maqsad aniq, yo'l ma'lum\\. Faqat harakat kerak\\!",
    "🌟 Bugun qilingan ish — ertangi o'zingizga sovg'a\\!",
    "💡 Hozir qiyin tuyulsa ham, natija kutmoqda\\!",
    "🏆 Har kuni ozgina harakat — katta muvaffaqiyatga olib boradi\\!",
    "💪 Siz kuchli odamsiz\\. Bugun ham isbotlang\\!",
]
NAMOZ_NOMLAR = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]
NAMOZ_EMOJIS = ["🌅", "☀️", "🌤", "🌇", "🌙"]
NAMOZ_BALLS = {"Bomdod": 15, "Peshin": 10, "Asr": 10, "Shom": 10, "Xufton": 10}

def motivatsiya():
    return random.choice(MOTIVATSION)

def load(key):
    f = FILES.get(key, key)
    if os.path.exists(f):
        with open(f, "r", encoding="utf-8") as fp:
            return json.load(fp)
    defaults = {
        "tasks": {"tasks": [], "tomorrow_tasks": []},
        "prayers": {},
        "streak": {},
        "goals": [],
        "journal": [],
        "books": {"current": None, "log": []},
        "expenses": {"today": [], "history": []},
        "kpi": {"items": [], "history": []},
        "prayer_stats": {},
    }
    return defaults.get(key, {})

def save(key, data):
    f = FILES.get(key, key)
    with open(f, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)

def escape_md(text):
    text = str(text)
    for ch in [".", "!", "-", "(", ")", "_", "+", "=", "|", "{", "}", "#", "*", "~", "`", ">"]:
        text = text.replace(ch, "\\" + ch)
    return text

def fix_utc(time_str):
    try:
        t = datetime.strptime(time_str[:5], "%H:%M") + timedelta(hours=5)
        return t.strftime("%H:%M")
    except:
        return time_str[:5]

async def fetch_prayer_times():
    today = date.today()
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.aladhan.com/v1/timingsByCity/{}-{}-{}?city=Tashkent&country=Uzbekistan&method=3".format(today.day, today.month, today.year)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                d = await resp.json()
                t = d["data"]["timings"]
                prayers = {
                    "Bomdod": fix_utc(t["Fajr"]),
                    "Peshin": fix_utc(t["Dhuhr"]),
                    "Asr": fix_utc(t["Asr"]),
                    "Shom": fix_utc(t["Maghrib"]),
                    "Xufton": fix_utc(t["Isha"]),
                    "date": str(today)
                }
                save("prayers", prayers)
                return prayers
    except Exception as e:
        logger.error("Prayer fetch error: {}".format(e))
        return None

def get_prayers():
    p = load("prayers")
    return p if p.get("date") == str(date.today()) else None

user_state = {}

MAIN_KB = ReplyKeyboardMarkup([
    [KeyboardButton("📋 Rejalar"), KeyboardButton("✅ Bajardim")],
    [KeyboardButton("➕ Vazifa qosh"), KeyboardButton("📊 Tahlil")],
    [KeyboardButton("🕌 Namoz"), KeyboardButton("📚 Kitob")],
    [KeyboardButton("🎯 Maqsadlar"), KeyboardButton("💰 Xarajatlar")],
    [KeyboardButton("📖 Jurnal"), KeyboardButton("🏆 Reyting")],
    [KeyboardButton("📈 Streak"), KeyboardButton("🤖 AI Coach")],
    [KeyboardButton("🗑 Tozala")],
], resize_keyboard=True)

ANTHROPIC_TOKEN = "sk-ant-api03-placeholder"  # Bu yerga Anthropic API key kiriting

VAQT_KB = ReplyKeyboardMarkup([[KeyboardButton("⏰ Vaqt qosham"), KeyboardButton("⏭ Shartmas")]], resize_keyboard=True)

# ─── TASKS ───────────────────────────────────────────────────────────────────

async def ensure_prayers_in_tasks():
    data = load("tasks")
    prayers = get_prayers()
    if not prayers:
        prayers = await fetch_prayer_times()
    if prayers:
        existing = {t["label"] for t in data["tasks"] if t.get("is_prayer")}
        for nom, emoji in zip(NAMOZ_NOMLAR, NAMOZ_EMOJIS):
            label = "{} {} namozi".format(emoji, nom)
            if label not in existing:
                mid = max((t["id"] for t in data["tasks"]), default=0) + 1
                data["tasks"].append({"id": mid, "time": prayers.get(nom, "00:00"), "label": label, "done": False, "no_time": False, "is_prayer": True, "prayer_name": nom})
        data["tasks"].sort(key=lambda x: x["time"])
        save("tasks", data)
    return data

async def cmd_start(update: Update, ctx):
    await ensure_prayers_in_tasks()
    await update.message.reply_text(
        "👋 *Salom\\!* Kunlik rejalashtiruvchi yordamchingizman\\.\n\n"
        "🕌 5 vaqt namoz avtomatik eslatiladi\n"
        "🔥 Streak, KPI, Maqsadlar va boshqalar\\!\n"
        "📌 Quyidagi tugmalardan foydalaning:",
        parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def cmd_reja(update: Update, ctx):
    data = await ensure_prayers_in_tasks()
    tasks = data["tasks"]
    regular = [t for t in tasks if not t.get("is_prayer")]
    prayers = [t for t in tasks if t.get("is_prayer")]
    if not tasks:
        await update.message.reply_text("📭 _Vazifalar yo'q\\._", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    done_r = sum(1 for t in regular if t.get("done"))
    done_p = sum(1 for t in prayers if t.get("done"))
    pct = round(done_r / len(regular) * 100) if regular else 0
    bars = "🟩" * round(pct/20) + "⬜" * (5 - round(pct/20))
    lines = ["📋 *Bugungi rejalar*\n",
             "{} `{}/{}` — *{}%*".format(bars, done_r, len(regular), pct),
             "🕌 Namoz: *{}/5*\n".format(done_p)]
    if regular:
        lines.append("*📌 Vazifalar:*")
        for t in regular:
            icon = "✅" if t.get("done") else "⬜"
            vs = "" if t.get("no_time") else "⏰`{}` — ".format(t["time"])
            lb = escape_md(t["label"])
            lines.append("{} {}{}{}".format(icon, vs, "~" if t.get("done") else "*", lb + ("~" if t.get("done") else "*")))
    if prayers:
        lines.append("\n*🕌 Namozlar:*")
        for t in prayers:
            icon = "✅" if t.get("done") else "⬜"
            lines.append("{} ⏰`{}` — {}".format(icon, t["time"], escape_md(t["label"])))
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def cmd_bajardim(update: Update, ctx):
    data = await ensure_prayers_in_tasks()
    undone = [t for t in data["tasks"] if not t.get("done")]
    if not undone:
        await update.message.reply_text("🎉 *Barcha vazifalar bajarildi\\!*", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    kb = []
    reg = [t for t in undone if not t.get("is_prayer")]
    prays = [t for t in undone if t.get("is_prayer")]
    if reg:
        kb.append([InlineKeyboardButton("── 📌 Vazifalar ──", callback_data="noop")])
        for t in reg:
            vs = "" if t.get("no_time") else "{} - ".format(t["time"])
            kb.append([InlineKeyboardButton("⬜ {}{}".format(vs, t["label"]), callback_data="done_{}".format(t["id"]))])
    if prays:
        kb.append([InlineKeyboardButton("── 🕌 Namozlar ──", callback_data="noop")])
        for t in prays:
            kb.append([InlineKeyboardButton("⬜ {} - {}".format(t["time"], t["label"]), callback_data="done_{}".format(t["id"]))])
    await update.message.reply_text("☑️ *Qaysi vazifani bajardingiz?*", parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))

async def cmd_vazifa_qosh_start(update: Update, ctx):
    user_state[update.effective_chat.id] = "task_label"
    await update.message.reply_text("✏️ *Vazifa nomini yozing:*", parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def cmd_tahlil(update: Update, ctx):
    data = load("tasks")
    regular = [t for t in data["tasks"] if not t.get("is_prayer")]
    prayers = [t for t in data["tasks"] if t.get("is_prayer")]
    done_r = [t for t in regular if t.get("done")]
    done_p = [t for t in prayers if t.get("done")]
    pct = round(len(done_r)/len(regular)*100) if regular else 0
    lines = ["📊 *Kunlik tahlil*\n",
             "📈 Samaradorlik: *{}%*".format(pct),
             "✅ Vazifa: *{}/{}*".format(len(done_r), len(regular)),
             "🕌 Namoz: *{}/5*\n".format(len(done_p))]
    if done_r:
        lines.append("*✅ Bajarilgan:*")
        for t in done_r:
            vs = "" if t.get("no_time") else "⏰`{}` ".format(t["time"])
            lines.append("  ~{}{}~".format(vs, escape_md(t["label"])))
    undone_r = [t for t in regular if not t.get("done")]
    if undone_r:
        lines.append("\n*❌ Bajarilmagan:*")
        for t in undone_r:
            vs = "" if t.get("no_time") else "⏰`{}` ".format(t["time"])
            lines.append("  • {}{}".format(vs, escape_md(t["label"])))
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def cmd_tozala(update: Update, ctx):
    data = load("tasks")
    data["tasks"] = [t for t in data["tasks"] if t.get("is_prayer")]
    save("tasks", data)
    await update.message.reply_text("🗑 _Vazifalar o'chirildi\\. Namozlar saqlanib qoldi\\._", parse_mode="MarkdownV2", reply_markup=MAIN_KB)

# ─── NAMOZ ───────────────────────────────────────────────────────────────────

async def cmd_namoz(update: Update, ctx):
    prayers = get_prayers()
    if not prayers:
        prayers = await fetch_prayer_times()
    if not prayers:
        await update.message.reply_text("❌ _Namoz vaqtlarini olishda xato\\._", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    # Statistika
    stats = load("prayer_stats")
    month_key = date.today().strftime("%Y-%m")
    month_stats = stats.get(month_key, {n: 0 for n in NAMOZ_NOMLAR})
    days_in_month = date.today().day
    lines = ["🕌 *Namoz vaqtlari* \\— _Toshkent_\n"]
    for nom, emoji in zip(NAMOZ_NOMLAR, NAMOZ_EMOJIS):
        vaqt = prayers.get(nom, "—")
        count = month_stats.get(nom, 0)
        lines.append("{} *{}:* `{}` — _{}/{} kun_".format(emoji, nom, vaqt, count, days_in_month))
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

# ─── STREAK ──────────────────────────────────────────────────────────────────

async def cmd_streak(update: Update, ctx):
    streak = load("streak")
    if not streak:
        await update.message.reply_text("📈 _Hozircha streak ma'lumotlari yo'q\\._\n\nVazifalarni bajaring, streak avtomatik hisoblanadi\\!", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    lines = ["📈 *Streak tizimi* 🔥\n"]
    for key, val in streak.items():
        days = val.get("days", 0)
        emoji = "🔥" if days >= 7 else "⚡"
        lines.append("{} *{}:* `{} kun`".format(emoji, escape_md(key), days))
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

# ─── MAQSADLAR ───────────────────────────────────────────────────────────────

async def cmd_maqsadlar(update: Update, ctx):
    goals = load("goals")
    if not goals:
        user_state[update.effective_chat.id] = "goal_add"
        await update.message.reply_text(
            "🎯 *Maqsadlar bo'limi*\n\n_Hozircha maqsad yo'q\\._\n\nYangi maqsad nomini yozing:",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    kb = []
    lines = ["🎯 *Maqsadlar*\n"]
    for i, g in enumerate(goals):
        pct = round(g.get("progress", 0))
        bar = "🟩" * round(pct/20) + "⬜" * (5 - round(pct/20))
        lines.append("{} *{}*".format(bar, escape_md(g["name"])))
        lines.append("   Progress: *{}%*\n".format(pct))
        kb.append([
            InlineKeyboardButton("📈 +10% — {}".format(g["name"][:20]), callback_data="goal_up_{}".format(i)),
            InlineKeyboardButton("❌", callback_data="goal_del_{}".format(i))
        ])
    kb.append([InlineKeyboardButton("➕ Yangi maqsad", callback_data="goal_new")])
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))

# ─── KITOB ───────────────────────────────────────────────────────────────────

async def cmd_kitob(update: Update, ctx):
    books = load("books")
    current = books.get("current")
    if not current:
        user_state[update.effective_chat.id] = "book_name"
        await update.message.reply_text("📚 *Kitob kuzatuvi*\n\n_Hozircha kitob yo'q\\._\n\nKitob nomini yozing:", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    read = current.get("read", 0)
    total = current.get("total", 100)
    pct = round(read/total*100) if total else 0
    bar = "🟩" * round(pct/20) + "⬜" * (5 - round(pct/20))
    kb = [
        [InlineKeyboardButton("📖 +5 sahifa", callback_data="book_+5"),
         InlineKeyboardButton("📖 +10 sahifa", callback_data="book_+10")],
        [InlineKeyboardButton("📖 +20 sahifa", callback_data="book_+20"),
         InlineKeyboardButton("✅ Tugatdim", callback_data="book_done")],
        [InlineKeyboardButton("🔄 Kitob o'zgartirish", callback_data="book_change")]
    ]
    name_esc = escape_md(current["name"])
    lines = ["📚 *Kitob kuzatuvi*\n",
             "📖 *{}*\n".format(name_esc),
             "{} `{}/{}` sahifa — *{}%*".format(bar, read, total, pct)]
    today_log = [l for l in books.get("log", []) if l.get("date") == str(date.today())]
    today_read = sum(l.get("pages", 0) for l in today_log)
    if today_read:
        lines.append("📅 _Bugun: {} sahifa_".format(today_read))
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))

# ─── XARAJATLAR ──────────────────────────────────────────────────────────────

async def cmd_xarajatlar(update: Update, ctx):
    exp = load("expenses")
    today_items = [e for e in exp.get("today", []) if e.get("date") == str(date.today())]
    total = sum(e.get("amount", 0) for e in today_items)
    lines = ["💰 *Bugungi xarajatlar*\n"]
    if today_items:
        for e in today_items:
            lines.append("• {}: *{:,} so'm*".format(escape_md(e["name"]), e["amount"]))
        lines.append("\n💳 *Jami: {:,} so'm*".format(total))
    else:
        lines.append("_Bugun hali xarajat yo'q\\._")
    kb = [[InlineKeyboardButton("➕ Xarajat qo'shish", callback_data="exp_add"),
           InlineKeyboardButton("📊 Oy hisoboti", callback_data="exp_month")]]
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))

# ─── JURNAL ──────────────────────────────────────────────────────────────────

async def cmd_jurnal(update: Update, ctx):
    journal = load("journal")
    today = str(date.today())
    today_entry = next((j for j in journal if j.get("date") == today), None)
    if today_entry:
        lines = ["📖 *Bugungi jurnal*\n",
                 "✨ *Eng yaxshi:* {}".format(escape_md(today_entry.get("best", "—"))),
                 "❌ *Xato:* {}".format(escape_md(today_entry.get("mistake", "—"))),
                 "🔄 *Ertaga:* {}".format(escape_md(today_entry.get("tomorrow", "—")))]
        kb = [[InlineKeyboardButton("✏️ Tahrirlash", callback_data="journal_edit")]]
        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))
    else:
        user_state[update.effective_chat.id] = "journal_best"
        await update.message.reply_text("📖 *Kunlik jurnal*\n\n✨ *Bugungi eng yaxshi ishingiz nima bo'ldi?*", parse_mode="MarkdownV2", reply_markup=MAIN_KB)

# ─── REYTING ─────────────────────────────────────────────────────────────────

def calculate_rating():
    data = load("tasks")
    balls = 0
    for t in data["tasks"]:
        if t.get("done"):
            if t.get("is_prayer"):
                nom = t.get("prayer_name", "")
                balls += NAMOZ_BALLS.get(nom, 10)
            else:
                balls += 5
    return balls

async def cmd_reyting(update: Update, ctx):
    balls = calculate_rating()
    if balls >= 150:
        daraja = "👑 Elite"
    elif balls >= 100:
        daraja = "🥇 Gold"
    elif balls >= 60:
        daraja = "🥈 Silver"
    else:
        daraja = "🥉 Bronze"
    data = load("tasks")
    lines = ["🏆 *Bugungi reyting*\n",
             "🎯 *{} ball*\n".format(balls),
             "Daraja: *{}*\n".format(escape_md(daraja)),
             "_Ball hisoblash:_",
             "🕌 Namoz: 10\\-15 ball",
             "📌 Vazifa: 5 ball",
             "📊 Namoz ball: *{}*".format(sum(NAMOZ_BALLS.get(t.get("prayer_name",""), 10) for t in data["tasks"] if t.get("done") and t.get("is_prayer"))),
             "📌 Vazifa ball: *{}*".format(sum(5 for t in data["tasks"] if t.get("done") and not t.get("is_prayer")))]
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

# ─── CALLBACKS ───────────────────────────────────────────────────────────────

async def callback_handler(update: Update, ctx):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d == "noop":
        return

    # Vazifa bajarildi
    elif d.startswith("done_"):
        task_id = int(d.split("_")[1])
        data = load("tasks")
        label = ""
        is_prayer = False
        prayer_name = ""
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["done"] = True
                label = t["label"]
                is_prayer = t.get("is_prayer", False)
                prayer_name = t.get("prayer_name", "")
                break
        save("tasks", data)

        # Prayer stats yangilash
        if is_prayer and prayer_name:
            stats = load("prayer_stats")
            month_key = date.today().strftime("%Y-%m")
            if month_key not in stats:
                stats[month_key] = {n: 0 for n in NAMOZ_NOMLAR}
            stats[month_key][prayer_name] = stats[month_key].get(prayer_name, 0) + 1
            save("prayer_stats", stats)
            # Streak yangilash
            streak = load("streak")
            sk = "Namoz"
            today = str(date.today())
            yesterday = str(date.today() - timedelta(days=1))
            if sk not in streak:
                streak[sk] = {"days": 1, "last": today}
            elif streak[sk].get("last") == today:
                pass
            elif streak[sk].get("last") == yesterday:
                streak[sk]["days"] += 1
                streak[sk]["last"] = today
            else:
                streak[sk] = {"days": 1, "last": today}
            save("streak", streak)

        done_r = sum(1 for t in data["tasks"] if t.get("done") and not t.get("is_prayer"))
        total_r = len([t for t in data["tasks"] if not t.get("is_prayer")])
        done_p = sum(1 for t in data["tasks"] if t.get("done") and t.get("is_prayer"))
        balls = calculate_rating()
        label_esc = escape_md(label)

        if is_prayer:
            msg = "🕌 *{}* — o'qildi\\!\n\n_Alloh qabul qilsin\\!_ 🤲\n\nNamoz: `{}/5` \\| 🏆 *{} ball*".format(label_esc, done_p, balls)
        else:
            msg = "✅ *{}* — bajarildi\\!\n\n".format(label_esc)
            if done_r == total_r:
                msg += "🏆 *Barcha vazifalar bajarildi\\!*\n🎯 Bugungi ball: *{}*".format(balls)
            else:
                msg += "📊 `{}/{}` \\| 🏆 *{} ball*\n\n{}".format(done_r, total_r, balls, motivatsiya())
        await q.edit_message_text(msg, parse_mode="MarkdownV2")

    # Saralash
    elif d.startswith("del_"):
        task_id = int(d.split("_")[1])
        data = load("tasks")
        data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
        save("tasks", data)
        undone = [t for t in data["tasks"] if not t.get("done") and not t.get("is_prayer")]
        if not undone:
            await q.edit_message_text("✅ *Ro'yxat tayyor\\! Yaxshi kun\\!*", parse_mode="MarkdownV2")
            return
        kb = []
        lines = ["📋 *Rejani ko'rib chiqing* — ❌ keraksizlarni o'chiring:\n"]
        for t in undone:
            vs = "" if t.get("no_time") else "⏰`{}` — ".format(t["time"])
            lines.append("• {}{}".format(vs, escape_md(t["label"])))
            kb.append([InlineKeyboardButton("❌ {}{}".format("" if t.get("no_time") else "{} - ".format(t["time"]), t["label"]), callback_data="del_{}".format(t["id"]))])
        kb.append([InlineKeyboardButton("✅ Tayyor!", callback_data="sarala_done")])
        await q.edit_message_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))

    elif d == "sarala_done":
        await q.edit_message_text("✅ *Bugungi rejangiz tasdiqlandi\\.*\n\n💪 _Muvaffaqiyat\\!_", parse_mode="MarkdownV2")

    # Maqsadlar
    elif d == "goal_new":
        user_state[CHAT_ID] = "goal_add"
        await q.edit_message_text("🎯 Yangi maqsad nomini yozing:")
    elif d.startswith("goal_up_"):
        i = int(d.split("_")[2])
        goals = load("goals")
        if i < len(goals):
            goals[i]["progress"] = min(100, goals[i].get("progress", 0) + 10)
            save("goals", goals)
            g = goals[i]
            pct = round(g["progress"])
            bar = "🟩" * round(pct/20) + "⬜" * (5 - round(pct/20))
            await q.edit_message_text("🎯 *{}*\n\n{} *{}%*".format(escape_md(g["name"]), bar, pct), parse_mode="MarkdownV2")
    elif d.startswith("goal_del_"):
        i = int(d.split("_")[2])
        goals = load("goals")
        if i < len(goals):
            goals.pop(i)
            save("goals", goals)
            await q.edit_message_text("🗑 _Maqsad o'chirildi\\._", parse_mode="MarkdownV2")

    # Kitob
    elif d.startswith("book_+"):
        pages = int(d.replace("book_+", ""))
        books = load("books")
        if books.get("current"):
            books["current"]["read"] = books["current"].get("read", 0) + pages
            books.setdefault("log", []).append({"date": str(date.today()), "pages": pages})
            save("books", books)
            # Streak
            streak = load("streak")
            sk = "Kitob"
            today = str(date.today())
            yesterday = str(date.today() - timedelta(days=1))
            if sk not in streak:
                streak[sk] = {"days": 1, "last": today}
            elif streak[sk].get("last") != today:
                if streak[sk].get("last") == yesterday:
                    streak[sk]["days"] += 1
                else:
                    streak[sk] = {"days": 1, "last": today}
                streak[sk]["last"] = today
            save("streak", streak)
            read = books["current"]["read"]
            total = books["current"]["total"]
            pct = round(read/total*100) if total else 0
            await q.edit_message_text("📖 *\\+{} sahifa\\!*\n\nJami: `{}/{}` — *{}%*".format(pages, read, total, pct), parse_mode="MarkdownV2")
    elif d == "book_done":
        books = load("books")
        if books.get("current"):
            books.setdefault("finished", []).append(books["current"])
            books["current"] = None
            save("books", books)
            await q.edit_message_text("🎉 *Kitob tugatildi\\! Tabriklaymiz\\!*", parse_mode="MarkdownV2")
    elif d == "book_change":
        user_state[CHAT_ID] = "book_name"
        await q.edit_message_text("📚 Yangi kitob nomini yozing:")

    # Xarajatlar
    elif d == "exp_add":
        user_state[CHAT_ID] = "exp_name"
        await q.edit_message_text("💰 Xarajat nomini yozing \\(masalan: Ovqat\\):", parse_mode="MarkdownV2")
    elif d == "exp_month":
        exp = load("expenses")
        month = date.today().strftime("%Y-%m")
        month_items = [e for e in exp.get("today", []) if e.get("date", "").startswith(month)]
        total = sum(e.get("amount", 0) for e in month_items)
        await q.edit_message_text("📊 *Oylik xarajat: {:,} so'm*".format(total), parse_mode="MarkdownV2")

    # Jurnal
    elif d == "journal_edit":
        user_state[CHAT_ID] = "journal_best"
        await q.edit_message_text("✨ *Bugungi eng yaxshi ishingiz nima bo'ldi?*", parse_mode="MarkdownV2")

# ─── MESSAGE HANDLER ─────────────────────────────────────────────────────────

async def message_handler(update: Update, ctx):
    chat_id = update.effective_chat.id
    text = update.message.text
    state = user_state.get(chat_id, "")

    # Tugmalar
    if text == "📋 Rejalar": await cmd_reja(update, ctx); return
    elif text == "✅ Bajardim": await cmd_bajardim(update, ctx); return
    elif text == "➕ Vazifa qosh": await cmd_vazifa_qosh_start(update, ctx); return
    elif text == "📊 Tahlil": await cmd_tahlil(update, ctx); return
    elif text == "🕌 Namoz": await cmd_namoz(update, ctx); return
    elif text == "📈 Streak": await cmd_streak(update, ctx); return
    elif text == "🎯 Maqsadlar": await cmd_maqsadlar(update, ctx); return
    elif text == "📚 Kitob": await cmd_kitob(update, ctx); return
    elif text == "💰 Xarajatlar": await cmd_xarajatlar(update, ctx); return
    elif text == "📖 Jurnal": await cmd_jurnal(update, ctx); return
    elif text == "🏆 Reyting": await cmd_reyting(update, ctx); return
    elif text == "🤖 AI Coach": await cmd_ai_coach(update, ctx); return
    elif text == "🗑 Tozala": await cmd_tozala(update, ctx); return

    # Vazifa qo'shish
    elif state == "task_label":
        user_state[chat_id] = "task_time:" + text
        await update.message.reply_text("🕐 *Vaqt qo'shmoqchimisiz?*", parse_mode="MarkdownV2", reply_markup=VAQT_KB)
    elif state.startswith("task_time:"):
        label = state.replace("task_time:", "")
        if text == "⏭ Shartmas":
            data = load("tasks")
            mid = max((t["id"] for t in data["tasks"]), default=0) + 1
            data["tasks"].append({"id": mid, "time": "--:--", "label": label, "done": False, "no_time": True})
            save("tasks", data)
            user_state[chat_id] = None
            await update.message.reply_text("✅ *{}* qo'shildi \\(vaqtsiz\\)".format(escape_md(label)), parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        elif text == "⏰ Vaqt qosham":
            user_state[chat_id] = "task_time_enter:" + label
            await update.message.reply_text("⏰ Vaqtni yozing \\(masalan `09:00`\\):", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        else:
            await update.message.reply_text("Iltimos tugmani bosing:", reply_markup=VAQT_KB)
    elif state.startswith("task_time_enter:"):
        label = state.replace("task_time_enter:", "")
        try:
            datetime.strptime(text.strip(), "%H:%M")
            data = load("tasks")
            mid = max((t["id"] for t in data["tasks"]), default=0) + 1
            data["tasks"].append({"id": mid, "time": text.strip(), "label": label, "done": False, "no_time": False})
            data["tasks"].sort(key=lambda x: x["time"])
            save("tasks", data)
            user_state[chat_id] = None
            await update.message.reply_text("✅ ⏰`{}` — *{}*".format(text.strip(), escape_md(label)), parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        except ValueError:
            await update.message.reply_text("❌ Format noto'g'ri\\. Misol: `09:00`", parse_mode="MarkdownV2", reply_markup=MAIN_KB)

    # Ertangi reja
    elif state == "adding_tomorrow":
        if text.lower() in ["tayyor", "boldi"]:
            user_state[chat_id] = None
            data = load("tasks")
            tomorrow = data.get("tomorrow_tasks", [])
            prayers = get_prayers()
            if prayers:
                for nom, emoji in zip(NAMOZ_NOMLAR, NAMOZ_EMOJIS):
                    mid = max((t["id"] for t in tomorrow), default=0) + 1
                    tomorrow.append({"id": mid, "time": prayers.get(nom, "00:00"), "label": "{} {} namozi".format(emoji, nom), "done": False, "no_time": False, "is_prayer": True, "prayer_name": nom})
                tomorrow.sort(key=lambda x: x["time"])
            data["tasks"] = tomorrow
            data["tomorrow_tasks"] = []
            save("tasks", data)
            cnt = len([t for t in data["tasks"] if not t.get("is_prayer")])
            await update.message.reply_text("✅ *{} ta vazifa saqlandi\\!*\n\n🌙 _Yaxshi tun\\!_".format(cnt), parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        else:
            parts = text.strip().split(" ", 1)
            try:
                datetime.strptime(parts[0], "%H:%M")
                vaqt, label, no_time = parts[0], parts[1] if len(parts) > 1 else "Vazifa", False
            except (ValueError, IndexError):
                vaqt, label, no_time = "--:--", text, True
            data = load("tasks")
            data.setdefault("tomorrow_tasks", [])
            data["tomorrow_tasks"].append({"id": len(data["tomorrow_tasks"]) + 1, "time": vaqt, "label": label, "done": False, "no_time": no_time})
            save("tasks", data)
            vs = "" if no_time else "⏰`{}` — ".format(vaqt)
            await update.message.reply_text("➕ {}{}\n\n_Yana qo'shing yoki_ *Tayyor* _deb yozing\\._".format(vs, escape_md(label)), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

    # Maqsad qo'shish
    elif state == "goal_add":
        user_state[chat_id] = "goal_pct:" + text
        await update.message.reply_text("📊 Hozirgi progress \\(% da, masalan `0` yoki `40`\\):", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
    elif state.startswith("goal_pct:"):
        name = state.replace("goal_pct:", "")
        try:
            pct = max(0, min(100, int(text.strip())))
        except:
            pct = 0
        goals = load("goals")
        goals.append({"name": name, "progress": pct})
        save("goals", goals)
        user_state[chat_id] = None
        await update.message.reply_text("🎯 Maqsad qo'shildi: *{}* — *{}%*".format(escape_md(name), pct), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

    # Kitob
    elif state == "book_name":
        user_state[chat_id] = "book_total:" + text
        await update.message.reply_text("📄 Kitob necha sahifa?", reply_markup=MAIN_KB)
    elif state.startswith("book_total:"):
        name = state.replace("book_total:", "")
        try:
            total = int(text.strip())
        except:
            total = 100
        books = load("books")
        books["current"] = {"name": name, "total": total, "read": 0}
        save("books", books)
        user_state[chat_id] = None
        await update.message.reply_text("📚 *{}* boshlandi\\! {} sahifa".format(escape_md(name), total), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

    # Xarajat
    elif state == "exp_name":
        user_state[chat_id] = "exp_amount:" + text
        await update.message.reply_text("💵 Miqdorini yozing \\(so'mda\\):", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
    elif state.startswith("exp_amount:"):
        name = state.replace("exp_amount:", "")
        try:
            amount = int(text.strip().replace(" ", "").replace(",", ""))
        except:
            amount = 0
        exp = load("expenses")
        exp.setdefault("today", []).append({"name": name, "amount": amount, "date": str(date.today())})
        save("expenses", exp)
        user_state[chat_id] = None
        await update.message.reply_text("💰 *{}*: *{:,} so'm* qo'shildi".format(escape_md(name), amount), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

    # Jurnal
    elif state == "journal_best":
        user_state[chat_id] = "journal_mistake:" + text
        await update.message.reply_text("❌ *Bugungi xatongiz nima bo'ldi?*", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
    elif state.startswith("journal_mistake:"):
        best = state.replace("journal_mistake:", "")
        user_state[chat_id] = "journal_tomorrow:" + best + "|||" + text
        await update.message.reply_text("🔄 *Ertaga nimani yaxshiroq qilasiz?*", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
    elif state.startswith("journal_tomorrow:"):
        parts = state.replace("journal_tomorrow:", "").split("|||")
        best = parts[0] if len(parts) > 0 else ""
        mistake = parts[1] if len(parts) > 1 else ""
        journal = load("journal")
        today = str(date.today())
        journal = [j for j in journal if j.get("date") != today]
        journal.append({"date": today, "best": best, "mistake": mistake, "tomorrow": text})
        save("journal", journal)
        user_state[chat_id] = None
        await update.message.reply_text("📖 *Jurnal saqlandi\\!*\n\n✨ _{}_\n❌ _{}_\n🔄 _{}_".format(escape_md(best), escape_md(mistake), escape_md(text)), parse_mode="MarkdownV2", reply_markup=MAIN_KB)
    elif state == "ai_coach":
        await ask_ai_coach(update, text)
        user_state[chat_id] = None
    else:
        await update.message.reply_text("📌 Quyidagi tugmalardan foydalaning:", reply_markup=MAIN_KB)

# ─── SCHEDULED ───────────────────────────────────────────────────────────────

async def job_ertalab(app):
    prayers = await fetch_prayer_times()
    data = load("tasks")
    data["tasks"] = [t for t in data.get("tasks", []) if not t.get("is_prayer")]
    if prayers:
        for nom, emoji in zip(NAMOZ_NOMLAR, NAMOZ_EMOJIS):
            mid = max((t["id"] for t in data["tasks"]), default=0) + 1
            data["tasks"].append({"id": mid, "time": prayers.get(nom, "00:00"), "label": "{} {} namozi".format(emoji, nom), "done": False, "no_time": False, "is_prayer": True, "prayer_name": nom})
        data["tasks"].sort(key=lambda x: x["time"])
        save("tasks", data)
    regular = [t for t in data["tasks"] if not t.get("is_prayer") and not t.get("done")]
    if not regular:
        await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2", text="☀️ *Xayrli tong\\!*\n\n📭 _Bugun hech qanday vazifa yo'q\\._")
        return
    kb = []
    lines = ["☀️ *Xayrli tong\\!* Rejangizni ko'rib chiqing:\n"]
    for t in regular:
        vs = "" if t.get("no_time") else "⏰`{}` — ".format(t["time"])
        lines.append("• {}*{}*".format(vs, escape_md(t["label"])))
        kb.append([InlineKeyboardButton("❌ {}{}".format("" if t.get("no_time") else "{} - ".format(t["time"]), t["label"]), callback_data="del_{}".format(t["id"]))])
    kb.append([InlineKeyboardButton("✅ Tayyor, barchasi to'g'ri!", callback_data="sarala_done")])
    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))

async def job_kechki(app):
    user_state[CHAT_ID] = "adding_tomorrow"
    data = load("tasks")
    data["tomorrow_tasks"] = []
    save("tasks", data)
    await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
        text="🌙 *Kechqurun eslatmasi\\!*\n\nErtangi rejangizni kiriting\\.\n📝 `09:00 Vazifa nomi` yoki faqat `Vazifa nomi`\n\n_Tugatgach_ *Tayyor* _deb yozing\\._")

async def job_eslatma(app):
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    data = load("tasks")
    changed = False
    for t in data.get("tasks", []):
        if not t.get("no_time") and t.get("time") == now and not t.get("done") and not t.get("reminded"):
            if t.get("is_prayer"):
                await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
                    text="🕌 *Namoz vaqti\\!*\n\n*{}* — `{}`\n\n_Alloh qabul qilsin\\!_ 🤲".format(escape_md(t["label"]), t["time"]))
            else:
                await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
                    text="⏰ *Vaqt keldi\\!*\n\n📌 `{}` — *{}*\n\n{}\n\n_Bajargach_ ✅ *Bajardim* _tugmasini bosing\\!_".format(t["time"], escape_md(t["label"]), motivatsiya()))
            t["reminded"] = True
            changed = True
    if changed:
        save("tasks", data)

async def job_motivatsiya(app):
    await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2", text="💪 *Kunlik rag'bat\\!*\n\n{}".format(motivatsiya()))

async def job_dangasa(app):
    now = datetime.now(TIMEZONE)
    if now.hour < 9 or now.hour > 22:
        return
    data = load("tasks")
    undone = [t for t in data.get("tasks", []) if not t.get("done") and not t.get("is_prayer")]
    if len(undone) >= 2:
        await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
            text="🔔 *Eslatma\\!*\n\nHali *{} ta* vazifa bajarilmagan\\.\n\n{}\n\n🚀 _Hoziroq boshlang\\!_".format(len(undone), motivatsiya()))

async def job_kechki_tahlil(app):
    data = load("tasks")
    regular = [t for t in data.get("tasks", []) if not t.get("is_prayer")]
    prayers_list = [t for t in data.get("tasks", []) if t.get("is_prayer")]
    if not regular:
        return
    done_r = [t for t in regular if t.get("done")]
    done_p = [t for t in prayers_list if t.get("done")]
    balls = calculate_rating()
    pct = round(len(done_r)/len(regular)*100) if regular else 0
    if balls >= 150: daraja = "👑 Elite"
    elif balls >= 100: daraja = "🥇 Gold"
    elif balls >= 60: daraja = "🥈 Silver"
    else: daraja = "🥉 Bronze"
    lines = ["🌙 *Kunlik yakuniy tahlil*\n",
             "📈 Samaradorlik: *{}%*".format(pct),
             "✅ Vazifa: *{}/{}*".format(len(done_r), len(regular)),
             "🕌 Namoz: *{}/5*".format(len(done_p)),
             "🏆 Ball: *{}* — {}".format(balls, escape_md(daraja)),
             "\n📅 _Ertangi rejalar uchun 21:00 da yana yozaman\\!_"]
    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="MarkdownV2")

async def job_jurnal_eslatma(app):
    journal = load("journal")
    today = str(date.today())
    today_entry = next((j for j in journal if j.get("date") == today), None)
    if not today_entry:
        user_state[CHAT_ID] = "journal_best"
        await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
            text="📖 *Kunlik jurnal vaqti\\!*\n\n✨ *Bugungi eng yaxshi ishingiz nima bo'ldi?*")

# ─── MAIN ────────────────────────────────────────────────────────────────────


# ─── AI COACH ────────────────────────────────────────────────────────────────

ANTHROPIC_TOKEN = "YOUR_ANTHROPIC_API_KEY"  # Anthropic API key kiriting

async def cmd_ai_coach(update: Update, ctx):
    user_state[update.effective_chat.id] = "ai_coach"
    await update.message.reply_text(
        "🤖 *AI Coach*\n\n_Men sizning shaxsiy AI murabbiyingizman\\._ \nSavolingizni yozing \\— masalan:\n• _Bugun nima qilishim kerak?_\n• _IELTS uchun maslahat ber_\n• _Motivatsiya kerak_\n\nYoki xohlagan savolni bering\\!",
        parse_mode="MarkdownV2", reply_markup=MAIN_KB
    )

async def ask_ai_coach(update, question):
    data = load("tasks")
    regular = [t for t in data.get("tasks", []) if not t.get("is_prayer")]
    done_r = [t for t in regular if t.get("done")]
    undone_r = [t for t in regular if not t.get("done")]
    prayers = [t for t in data.get("tasks", []) if t.get("is_prayer")]
    done_p = [t for t in prayers if t.get("done")]
    streak = load("streak")
    goals = load("goals")
    books = load("books")
    balls = calculate_rating()

    context_info = """Foydalanuvchi:
- Bajarilgan: {}
- Bajarilmagan: {}
- Namoz: {}/5
- Ball: {}
- Streak: {}
- Maqsadlar: {}
- Kitob: {}""".format(
        ", ".join(t["label"] for t in done_r) or "yoq",
        ", ".join(t["label"] for t in undone_r) or "yoq",
        len(done_p), balls,
        ", ".join("{}: {} kun".format(k, v.get("days",0)) for k,v in streak.items()) or "yoq",
        ", ".join("{} ({}%)".format(g["name"], g.get("progress",0)) for g in goals) or "yoq",
        books.get("current", {}).get("name", "yoq") if books.get("current") else "yoq"
    )

    await update.message.reply_text("🤖 _Javob tayyorlanmoqda\\\.\.\._", parse_mode="MarkdownV2")

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 600,
                "messages": [{
                    "role": "user",
                    "content": "Sen o'zbek tilida gapiradigan shaxsiy AI murabbiysan.\n{}\n\nSavol: {}\n\nQisqa (3-5 gap), aniq va rag'batlantiruvchi javob ber. O'zbek tilida.".format(context_info, question)
                }]
            }
            headers = {
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_TOKEN,
                "anthropic-version": "2023-06-01"
            }
            async with session.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                result = await resp.json()
                answer = result["content"][0]["text"]
                answer_esc = escape_md(answer)
                await update.message.reply_text("🤖 *AI Coach:*\n\n{}".format(answer_esc), parse_mode="MarkdownV2", reply_markup=MAIN_KB)
    except Exception as e:
        logger.error("AI Coach xato: {}".format(e))
        await update.message.reply_text("❌ _AI Coach hozir ishlamayapti\\. Keyinroq urinib ko'ring\\._", parse_mode="MarkdownV2", reply_markup=MAIN_KB)


def main():
    lock = acquire_lock()
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reja", cmd_reja))
    app.add_handler(CommandHandler("bajardim", cmd_bajardim))
    app.add_handler(CommandHandler("tahlil", cmd_tahlil))
    app.add_handler(CommandHandler("namoz", cmd_namoz))
    app.add_handler(CommandHandler("streak", cmd_streak))
    app.add_handler(CommandHandler("maqsad", cmd_maqsadlar))
    app.add_handler(CommandHandler("kitob", cmd_kitob))
    app.add_handler(CommandHandler("xarajat", cmd_xarajatlar))
    app.add_handler(CommandHandler("jurnal", cmd_jurnal))
    app.add_handler(CommandHandler("reyting", cmd_reyting))
    app.add_handler(CommandHandler("coach", cmd_ai_coach))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(job_ertalab, "cron", hour=7, minute=0, args=[app])
    scheduler.add_job(job_kechki, "cron", hour=21, minute=0, args=[app])
    scheduler.add_job(job_eslatma, "cron", minute="*", args=[app])
    scheduler.add_job(job_dangasa, "cron", hour="10,14,18", minute=0, args=[app])
    scheduler.add_job(job_kechki_tahlil, "cron", hour=22, minute=0, args=[app])
    scheduler.add_job(job_motivatsiya, "cron", hour=9, minute=0, args=[app])
    scheduler.add_job(job_motivatsiya, "cron", hour=13, minute=0, args=[app])
    scheduler.add_job(job_motivatsiya, "cron", hour=19, minute=0, args=[app])
    scheduler.add_job(job_jurnal_eslatma, "cron", hour=21, minute=30, args=[app])
    scheduler.start()

    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
