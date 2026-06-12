import logging
import json
import os
import sys
import fcntl
from datetime import datetime, date, timedelta
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# ── CONFIG ──────────────────────────────────────────────────────────────────
TOKEN = "8849559349:AAFQLKPjpVqfM-jLYWoB9j1f7Q4QbKNptDg"
CHAT_ID = 6456736085
TZ = pytz.timezone("Asia/Tashkent")
LOCK_FILE = "/tmp/dailybot.lock"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# ── LOCK (ikki marta ishga tushmaslik) ──────────────────────────────────────
def acquire_lock():
    try:
        lf = open(LOCK_FILE, "w")
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lf
    except IOError:
        log.warning("Bot allaqachon ishlamoqda!")
        sys.exit(0)

# ── AVTOMATIK KUNLIK TASKLAR (yakshanba=6 dan tashqari) ─────────────────────
AUTO_TASKS = [
    {"label": "CRM check",                  "time": "10:00"},
    {"label": "Instagram directga qarash",  "time": "10:15"},
    {"label": "Lead report on Marketing",   "time": "19:00"},
    {"label": "Check Youtube Leads",        "time": None},
    {"label": "Read 5 pages book",          "time": None},
    {"label": "Do tasks given by 4prep",    "time": None},
]

# ── DATA ────────────────────────────────────────────────────────────────────
DATA_FILE = "data.json"

def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "report": [], "state": {}, "last_date": ""}

def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def today_str():
    return str(date.today())

def is_sunday():
    return date.today().weekday() == 6

def next_id(tasks):
    return max((t["id"] for t in tasks), default=0) + 1

# ── KEYBOARD ────────────────────────────────────────────────────────────────
MAIN_KB = ReplyKeyboardMarkup([
    ["📋 Rejalar", "✅ Bajarildi"],
    ["➕ Task qo'sh", "📊 Daily Report"],
], resize_keyboard=True)

# ── HELPERS ─────────────────────────────────────────────────────────────────
def esc(text):
    text = str(text)
    for ch in r"\.!-()_+=#|{}~`>[]":
        text = text.replace(ch, "\\" + ch)
    return text

def task_line(t):
    icon = "✅" if t.get("done") else "⬜"
    time_str = " ⏰`{}`".format(t["time"]) if t.get("time") else ""
    label = esc(t["label"])
    if t.get("done"):
        return "{}{} ~{}~".format(icon, time_str, label)
    return "{}{} {}".format(icon, time_str, label)

def progress_bar(done, total):
    if total == 0:
        return "⬜⬜⬜⬜⬜"
    filled = round(done / total * 5)
    return "🟩" * filled + "⬜" * (5 - filled)

# ── DAILY RESET ─────────────────────────────────────────────────────────────
def reset_daily(data):
    today = today_str()
    if data.get("last_date") == today:
        return data

    # Kecha bajarilmagan tasklarni o'chirish
    data["tasks"] = []

    # Avtomatik tasklarni qo'shish (yakshanba bo'lmasa)
    if not is_sunday():
        for i, at in enumerate(AUTO_TASKS):
            data["tasks"].append({
                "id": i + 1,
                "label": at["label"],
                "time": at["time"],
                "done": False,
                "auto": True,
                "reminded_30": False,
            })

    data["last_date"] = today
    save(data)
    return data

# ── HANDLERS ────────────────────────────────────────────────────────────────
user_state = {}

async def cmd_start(update: Update, ctx):
    data = load()
    data = reset_daily(data)
    await update.message.reply_text(
        "👋 *Salom\\!* Kunlik rejalashtiruvchi botman\\.\n\n"
        "📋 *Rejalar* — bugungi tasklarni ko'rish\n"
        "✅ *Bajarildi* — task belgilash\n"
        "➕ *Task qo'sh* — yangi task\n"
        "📊 *Daily Report* — bugungi hisobot",
        parse_mode="MarkdownV2",
        reply_markup=MAIN_KB
    )

async def show_tasks(update: Update, ctx=None):
    data = load()
    data = reset_daily(data)
    tasks = data["tasks"]

    if not tasks:
        msg = "📭 _Bugun hech qanday task yo'q\\._"
        if update.message:
            await update.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return

    done = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    pct = round(done / total * 100)
    bar = progress_bar(done, total)

    lines = [
        "📋 *Bugungi rejalar*\n",
        "{} `{}/{}` — *{}%*\n".format(bar, done, total, pct),
    ]
    for t in tasks:
        lines.append(task_line(t))

    if update.message:
        await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def show_done_menu(update: Update, ctx):
    data = load()
    undone = [t for t in data["tasks"] if not t.get("done")]
    if not undone:
        await update.message.reply_text("🎉 *Barcha tasklar bajarildi\\!*", parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    kb = []
    for t in undone:
        time_str = " ({})".format(t["time"]) if t.get("time") else ""
        kb.append([InlineKeyboardButton("⬜ {}{}".format(t["label"], time_str), callback_data="done_{}".format(t["id"]))])
    await update.message.reply_text("☑️ *Qaysi taskni bajardingiz?*", parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))

async def show_daily_report(update: Update, ctx):
    data = load()
    tasks = data["tasks"]
    done = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct = round(len(done) / len(tasks) * 100) if tasks else 0

    lines = [
        "📊 *Daily Report — {}*\n".format(esc(today_str())),
        "📈 Samaradorlik: *{}%*".format(pct),
        "✅ Bajarildi: *{} ta*".format(len(done)),
        "❌ Bajarilmadi: *{} ta*\n".format(len(undone)),
    ]
    if done:
        lines.append("*✅ Bajarilgan:*")
        for t in done:
            lines.append("  • {}".format(esc(t["label"])))
    if undone:
        lines.append("\n*❌ Bajarilmagan:*")
        for t in undone:
            lines.append("  • {}".format(esc(t["label"])))

    if pct == 100:
        lines.append("\n🏆 *Mukammal kun\\!*")
    elif pct >= 70:
        lines.append("\n👍 *Yaxshi natija\\!*")
    else:
        lines.append("\n💡 _Ertaga yanada yaxshiroq qilasiz\\!_")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def start_add_task(update: Update, ctx):
    user_state[update.effective_chat.id] = "add_label"
    await update.message.reply_text("✏️ *Task nomini yozing:*", parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def callback_handler(update: Update, ctx):
    q = update.callback_query
    await q.answer()

    if q.data.startswith("done_"):
        task_id = int(q.data.split("_")[1])
        data = load()
        label = ""
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["done"] = True
                label = t["label"]
                break
        save(data)

        done = sum(1 for t in data["tasks"] if t.get("done"))
        total = len(data["tasks"])
        pct = round(done / total * 100)

        msg = "✅ *{}* — bajarildi\\!\n\n📊 `{}/{}` — *{}%*".format(esc(label), done, total, pct)
        if done == total:
            msg += "\n\n🏆 *Barcha tasklar bajarildi\\! Zo'r\\!*"
        await q.edit_message_text(msg, parse_mode="MarkdownV2")

    elif q.data.startswith("check30_"):
        task_id = int(q.data.split("_")[1])
        data = load()
        task = next((t for t in data["tasks"] if t["id"] == task_id), None)
        if task and not task.get("done"):
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Ha, bajardim", callback_data="done_{}".format(task_id)),
                InlineKeyboardButton("⏰ Keyinroq", callback_data="later_{}".format(task_id)),
            ]])
            await q.edit_message_text(
                "❓ *{}* taskinni bajardingizmi?".format(esc(task["label"])),
                parse_mode="MarkdownV2",
                reply_markup=kb
            )
        else:
            await q.edit_message_text("✅ _Task allaqachon bajarilgan\\._", parse_mode="MarkdownV2")

    elif q.data.startswith("later_"):
        await q.edit_message_text("⏰ _Keyinroq eslataman\\._", parse_mode="MarkdownV2")

async def message_handler(update: Update, ctx):
    chat_id = update.effective_chat.id
    text = update.message.text
    state = user_state.get(chat_id, "")

    if text == "📋 Rejalar":
        await show_tasks(update, ctx)
    elif text == "✅ Bajarildi":
        await show_done_menu(update, ctx)
    elif text == "➕ Task qo'sh":
        await start_add_task(update, ctx)
    elif text == "📊 Daily Report":
        await show_daily_report(update, ctx)

    elif state == "add_label":
        user_state[chat_id] = "add_time:" + text
        await update.message.reply_text(
            "⏰ *Vaqt bormi?* Yozing \\(masalan `14:30`\\) yoki *Yo'q* deb yozing:",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB
        )

    elif state.startswith("add_time:"):
        label = state.replace("add_time:", "")
        vaqt = None
        if text.strip().lower() not in ["yoq", "yo'q", "yok", "-", "skip"]:
            try:
                datetime.strptime(text.strip(), "%H:%M")
                vaqt = text.strip()
            except ValueError:
                await update.message.reply_text("❌ Format noto'g'ri\\. Qaytadan: `14:30` yoki *Yo'q*", parse_mode="MarkdownV2")
                return

        data = load()
        new_task = {
            "id": next_id(data["tasks"]),
            "label": label,
            "time": vaqt,
            "done": False,
            "auto": False,
            "reminded_30": False,
        }
        data["tasks"].append(new_task)
        if vaqt:
            data["tasks"].sort(key=lambda x: x["time"] or "99:99")
        save(data)
        user_state[chat_id] = None

        time_str = " ⏰ `{}`".format(vaqt) if vaqt else " \\(vaqtsiz\\)"
        await update.message.reply_text(
            "✅ Task qo'shildi\\!\n\n📌 *{}*{}".format(esc(label), time_str),
            parse_mode="MarkdownV2", reply_markup=MAIN_KB
        )
    else:
        await update.message.reply_text("📌 Tugmalardan foydalaning:", reply_markup=MAIN_KB)

# ── SCHEDULED JOBS ───────────────────────────────────────────────────────────

async def job_ertalab(app):
    """Har kuni 07:00 da reset va ertalabki salom"""
    data = load()
    data = reset_daily(data)

    tasks = data["tasks"]
    if not tasks:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="☀️ *Xayrli tong\\!*\n\n_Bugun yakshanba — dam oling\\!_",
            parse_mode="MarkdownV2"
        )
        return

    done = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    bar = progress_bar(done, total)

    lines = [
        "☀️ *Xayrli tong\\!* Bugungi rejalar:\n",
        "{} `{}/{}` — *{}%*\n".format(bar, done, total, round(done/total*100) if total else 0),
    ]
    for t in tasks:
        lines.append(task_line(t))

    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="MarkdownV2")

async def job_vaqt_eslatma(app):
    """Har daqiqada vaqtli tasklarni tekshirish"""
    now = datetime.now(TZ).strftime("%H:%M")
    data = load()
    changed = False

    for t in data["tasks"]:
        if t.get("time") == now and not t.get("done") and not t.get("reminded"):
            await app.bot.send_message(
                chat_id=CHAT_ID,
                parse_mode="MarkdownV2",
                text="⏰ *Vaqt keldi\\!*\n\n📌 *{}* — `{}`\n\n_Bajaring va ✅ Bajarildi tugmasini bosing\\!_".format(
                    esc(t["label"]), t["time"]
                )
            )
            t["reminded"] = True
            t["reminded_at"] = now
            changed = True

    if changed:
        save(data)

async def job_30min_tekshirish(app):
    """Har daqiqada: vaqti kelgan va bajarilmagan task 30 daqiqadan o'tganmi?"""
    now = datetime.now(TZ)
    now_str = now.strftime("%H:%M")
    data = load()
    changed = False

    for t in data["tasks"]:
        if (t.get("reminded") and
            not t.get("done") and
            not t.get("reminded_30") and
            t.get("reminded_at")):
            try:
                reminded_time = datetime.strptime(t["reminded_at"], "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day, tzinfo=TZ
                )
                diff = (now - reminded_time).total_seconds() / 60
                if diff >= 30:
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Ha, bajardim", callback_data="done_{}".format(t["id"])),
                        InlineKeyboardButton("⏰ Keyinroq", callback_data="later_{}".format(t["id"])),
                    ]])
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        parse_mode="MarkdownV2",
                        text="🔔 *Eslatma\\!*\n\n_{}_  taskini bajardingizmi?".format(esc(t["label"])),
                        reply_markup=kb
                    )
                    t["reminded_30"] = True
                    changed = True
            except Exception as e:
                log.error("30min check error: {}".format(e))

    if changed:
        save(data)

async def job_kechki_report(app):
    """22:00 da kunlik yakuniy report"""
    data = load()
    tasks = data["tasks"]
    if not tasks:
        return

    done = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct = round(len(done) / len(tasks) * 100)

    lines = [
        "🌙 *Kunlik yakuniy hisobot*\n",
        "📈 Samaradorlik: *{}%*".format(pct),
        "✅ Bajarildi: *{}/{}*\n".format(len(done), len(tasks)),
    ]
    if done:
        lines.append("*✅ Bajarilgan:*")
        for t in done:
            lines.append("  • {}".format(esc(t["label"])))
    if undone:
        lines.append("\n*❌ Bajarilmagan:*")
        for t in undone:
            lines.append("  • {}".format(esc(t["label"])))

    if pct == 100:
        lines.append("\n🏆 *Mukammal kun\\! Zo'r\\!*")
    elif pct >= 70:
        lines.append("\n👍 *Yaxshi natija\\!*")
    else:
        lines.append("\n💡 _Ertaga yanada yaxshiroq qilasiz\\!_")

    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="MarkdownV2")

# ── MAIN ────────────────────────────────────────────────────────────────────

def main():
    lock = acquire_lock()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("rejalar", show_tasks))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(job_ertalab,          "cron", hour=7,  minute=0,  args=[app])
    scheduler.add_job(job_vaqt_eslatma,     "cron", minute="*",         args=[app])
    scheduler.add_job(job_30min_tekshirish, "cron", minute="*",         args=[app])
    scheduler.add_job(job_kechki_report,    "cron", hour=22, minute=0,  args=[app])
    scheduler.start()

    log.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
