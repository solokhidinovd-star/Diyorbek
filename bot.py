import logging
import json
import os
import sys
import fcntl
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# ── CONFIG ──────────────────────────────────────────────────────────────────
TOKEN = "8849559349:AAFQLKPjpVqfM-jLYWoB9j1f7Q4QbKNptDg"
CHAT_ID = 6456736085
TZ = pytz.timezone("Asia/Tashkent")
LOCK_FILE = "/tmp/dailybot.lock"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

def acquire_lock():
    try:
        lf = open(LOCK_FILE, "w")
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lf
    except IOError:
        log.warning("Bot is already running!")
        sys.exit(0)

AUTO_TASKS = [
    {"label": "CRM check",                     "time": "10:00"},
    {"label": "Check Instagram DMs",           "time": "10:15"},
    {"label": "Lead report on Marketing group","time": "19:00"},
    {"label": "Check YouTube Leads",           "time": None},
    {"label": "Read 5 pages of a book",        "time": None},
    {"label": "Do tasks given by 4prep",       "time": None},
]

DATA_FILE = "data.json"

def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "last_date": ""}

def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def today_str():
    return str(date.today())

def is_sunday():
    return date.today().weekday() == 6

def next_id(tasks):
    return max((t["id"] for t in tasks), default=0) + 1

MAIN_KB = ReplyKeyboardMarkup([
    ["📋 My Tasks", "✅ Mark Done"],
    ["➕ Add Task",  "📊 Daily Report"],
], resize_keyboard=True)

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
    return "{}{} *{}*".format(icon, time_str, label)

def progress_bar(done, total):
    if total == 0:
        return "⬜⬜⬜⬜⬜"
    filled = round(done / total * 5)
    return "🟩" * filled + "⬜" * (5 - filled)

def reset_daily(data):
    today = today_str()
    if data.get("last_date") == today:
        return data
    data["tasks"] = []
    if not is_sunday():
        for i, at in enumerate(AUTO_TASKS):
            data["tasks"].append({
                "id": i + 1,
                "label": at["label"],
                "time": at["time"],
                "done": False,
                "auto": True,
                "reminded": False,
                "reminded_30": False,
                "reminded_at": None,
            })
    data["last_date"] = today
    save(data)
    return data

user_state = {}

async def cmd_start(update, ctx):
    data = load()
    data = reset_daily(data)
    await update.message.reply_text(
        "👋 *Hello\\!* I'm your Daily Planner Bot\\.\n\n"
        "📋 *My Tasks* — view today's tasks\n"
        "✅ *Mark Done* — mark a task as completed\n"
        "➕ *Add Task* — add a new task\n"
        "📊 *Daily Report* — today's summary\n\n"
        "_Tasks reset automatically every day at 7:00 AM\\._\n"
        "_Daily report sent at 11:00 PM\\._",
        parse_mode="MarkdownV2",
        reply_markup=MAIN_KB
    )

async def show_tasks(update, ctx=None):
    data = load()
    data = reset_daily(data)
    tasks = data["tasks"]

    if not tasks:
        await update.message.reply_text(
            "📭 _No tasks for today\\._\n\nUse ➕ *Add Task* to add one\\!",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB
        )
        return

    done = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    pct = round(done / total * 100)
    bar = progress_bar(done, total)

    lines = [
        "📋 *Today's Tasks*\n",
        "{} `{}/{}` — *{}%* completed\n".format(bar, done, total, pct),
    ]
    for t in tasks:
        lines.append(task_line(t))

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def show_done_menu(update, ctx):
    data = load()
    undone = [t for t in data["tasks"] if not t.get("done")]
    if not undone:
        await update.message.reply_text(
            "🎉 *All tasks are completed\\! Great job\\!*",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB
        )
        return
    kb = []
    for t in undone:
        time_str = " ({})".format(t["time"]) if t.get("time") else ""
        kb.append([InlineKeyboardButton(
            "⬜ {}{}".format(t["label"], time_str),
            callback_data="done_{}".format(t["id"])
        )])
    await update.message.reply_text(
        "☑️ *Which task did you complete?*",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def show_daily_report(update, ctx):
    data = load()
    tasks = data["tasks"]

    if not tasks:
        await update.message.reply_text(
            "📭 _No tasks recorded for today\\._",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB
        )
        return

    done = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct = round(len(done) / len(tasks) * 100)
    bar = progress_bar(len(done), len(tasks))

    lines = [
        "📊 *Daily Report — {}*\n".format(esc(today_str())),
        "{} *{}%* completed".format(bar, pct),
        "✅ Done: *{}*   ❌ Remaining: *{}*\n".format(len(done), len(undone)),
    ]
    if done:
        lines.append("*✅ Completed:*")
        for t in done:
            time_str = " `{}`".format(t["time"]) if t.get("time") else ""
            lines.append("  • {}{}".format(time_str, esc(t["label"])))
    if undone:
        lines.append("\n*❌ Not completed:*")
        for t in undone:
            time_str = " `{}`".format(t["time"]) if t.get("time") else ""
            lines.append("  • {}{}".format(time_str, esc(t["label"])))

    if pct == 100:
        lines.append("\n🏆 *Perfect day\\! You crushed it\\!*")
    elif pct >= 70:
        lines.append("\n👍 *Good job\\! Keep it up\\!*")
    elif pct >= 40:
        lines.append("\n💪 *You can do better tomorrow\\!*")
    else:
        lines.append("\n💡 _Tomorrow is a fresh start\\!_")

    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def start_add_task(update, ctx):
    user_state[update.effective_chat.id] = "add_label"
    await update.message.reply_text(
        "✏️ *Enter the task name:*",
        parse_mode="MarkdownV2", reply_markup=MAIN_KB
    )

async def callback_handler(update, ctx):
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
        bar = progress_bar(done, total)

        msg = "✅ *{}* — marked as done\\!\n\n{} `{}/{}` — *{}%*".format(esc(label), bar, done, total, pct)
        if done == total:
            msg += "\n\n🏆 *All tasks completed\\! Excellent work\\!*"
        await q.edit_message_text(msg, parse_mode="MarkdownV2")

    elif q.data.startswith("check30_"):
        task_id = int(q.data.split("_")[1])
        data = load()
        task = next((t for t in data["tasks"] if t["id"] == task_id), None)
        if task and not task.get("done"):
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, done!", callback_data="done_{}".format(task_id)),
                InlineKeyboardButton("⏰ Not yet", callback_data="later_{}".format(task_id)),
            ]])
            await q.edit_message_text(
                "❓ Did you complete *{}*?".format(esc(task["label"])),
                parse_mode="MarkdownV2",
                reply_markup=kb
            )
        else:
            await q.edit_message_text("✅ _Task already completed\\._", parse_mode="MarkdownV2")

    elif q.data.startswith("later_"):
        await q.edit_message_text("⏰ _Got it\\. I'll remind you later\\._", parse_mode="MarkdownV2")

async def message_handler(update, ctx):
    chat_id = update.effective_chat.id
    text = update.message.text
    state = user_state.get(chat_id, "")

    if text == "📋 My Tasks":
        await show_tasks(update, ctx)
    elif text == "✅ Mark Done":
        await show_done_menu(update, ctx)
    elif text == "➕ Add Task":
        await start_add_task(update, ctx)
    elif text == "📊 Daily Report":
        await show_daily_report(update, ctx)

    elif state == "add_label":
        user_state[chat_id] = "add_time:" + text
        await update.message.reply_text(
            "⏰ *Does this task have a specific time?*\n\nType the time \\(e\\.g\\. `14:30`\\) or type *No*:",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB
        )

    elif state.startswith("add_time:"):
        label = state.replace("add_time:", "")
        vaqt = None
        if text.strip().lower() not in ["no", "n", "-", "skip", "none"]:
            try:
                datetime.strptime(text.strip(), "%H:%M")
                vaqt = text.strip()
            except ValueError:
                await update.message.reply_text(
                    "❌ Wrong format\\. Use `14:30` or type *No*:",
                    parse_mode="MarkdownV2"
                )
                return

        data = load()
        new_task = {
            "id": next_id(data["tasks"]),
            "label": label,
            "time": vaqt,
            "done": False,
            "auto": False,
            "reminded": False,
            "reminded_30": False,
            "reminded_at": None,
        }
        data["tasks"].append(new_task)
        data["tasks"].sort(key=lambda x: (x["time"] or "99:99"))
        save(data)
        user_state[chat_id] = None

        time_str = " at ⏰ `{}`".format(vaqt) if vaqt else " \\(no time set\\)"
        await update.message.reply_text(
            "✅ Task added\\!\n\n📌 *{}*{}".format(esc(label), time_str),
            parse_mode="MarkdownV2", reply_markup=MAIN_KB
        )
    else:
        await update.message.reply_text("📌 Use the buttons below:", reply_markup=MAIN_KB)

# ── SCHEDULED JOBS ───────────────────────────────────────────────────────────

async def job_morning(app):
    data = load()
    data = reset_daily(data)
    tasks = data["tasks"]

    if not tasks:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="☀️ *Good morning\\!*\n\n_Today is Sunday — rest and recharge\\! 🌿_",
            parse_mode="MarkdownV2"
        )
        return

    done = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    bar = progress_bar(done, total)

    lines = [
        "☀️ *Good morning\\!* Here are your tasks for today:\n",
        "{} `{}/{}` completed\n".format(bar, done, total),
    ]
    for t in tasks:
        lines.append(task_line(t))
    lines.append("\n💪 _Let's make today count\\!_")

    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="MarkdownV2")

async def job_time_reminder(app):
    now = datetime.now(TZ).strftime("%H:%M")
    data = load()
    changed = False

    for t in data["tasks"]:
        if t.get("time") == now and not t.get("done") and not t.get("reminded"):
            await app.bot.send_message(
                chat_id=CHAT_ID,
                parse_mode="MarkdownV2",
                text="⏰ *Time to do it\\!*\n\n📌 *{}* — `{}`\n\n_Complete it and tap ✅ Mark Done\\._".format(
                    esc(t["label"]), t["time"]
                )
            )
            t["reminded"] = True
            t["reminded_at"] = now
            changed = True

    if changed:
        save(data)

async def job_30min_check(app):
    now = datetime.now(TZ)
    data = load()
    changed = False

    for t in data["tasks"]:
        if (t.get("reminded") and
                not t.get("done") and
                not t.get("reminded_30") and
                t.get("reminded_at")):
            try:
                reminded_time = datetime.strptime(t["reminded_at"], "%H:%M").replace(
                    year=now.year, month=now.month, day=now.day
                )
                reminded_time = TZ.localize(reminded_time)
                diff = (now - reminded_time).total_seconds() / 60
                if diff >= 30:
                    kb = InlineKeyboardMarkup([[
                        InlineKeyboardButton("✅ Yes, done!", callback_data="done_{}".format(t["id"])),
                        InlineKeyboardButton("⏰ Not yet", callback_data="later_{}".format(t["id"])),
                    ]])
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        parse_mode="MarkdownV2",
                        text="🔔 *Reminder\\!*\n\nDid you complete *{}*?".format(esc(t["label"])),
                        reply_markup=kb
                    )
                    t["reminded_30"] = True
                    changed = True
            except Exception as e:
                log.error("30min check error: {}".format(e))

    if changed:
        save(data)

async def job_evening_report(app):
    data = load()
    tasks = data["tasks"]
    if not tasks:
        return

    done = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct = round(len(done) / len(tasks) * 100)
    bar = progress_bar(len(done), len(tasks))

    lines = [
        "🌙 *Daily Report — {}*\n".format(esc(today_str())),
        "{} *{}%* completed".format(bar, pct),
        "✅ Done: *{}*   ❌ Remaining: *{}*\n".format(len(done), len(tasks)),
    ]
    if done:
        lines.append("*✅ Completed:*")
        for t in done:
            time_str = " `{}`".format(t["time"]) if t.get("time") else ""
            lines.append("  • {}{}".format(time_str, esc(t["label"])))
    if undone:
        lines.append("\n*❌ Not completed:*")
        for t in undone:
            time_str = " `{}`".format(t["time"]) if t.get("time") else ""
            lines.append("  • {}{}".format(time_str, esc(t["label"])))

    if pct == 100:
        lines.append("\n🏆 *Perfect day\\! You crushed it\\!*")
    elif pct >= 70:
        lines.append("\n👍 *Good job\\! Keep pushing\\!*")
    elif pct >= 40:
        lines.append("\n💪 *You can do better tomorrow\\!*")
    else:
        lines.append("\n💡 _Tomorrow is a fresh start\\!_")

    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="MarkdownV2")

# ── MAIN ────────────────────────────────────────────────────────────────────
def main():
    lock = acquire_lock()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("tasks", show_tasks))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    scheduler = AsyncIOScheduler(timezone=TZ)
    scheduler.add_job(job_morning,        "cron", hour=7,  minute=0,  args=[app])
    scheduler.add_job(job_time_reminder,  "cron", minute="*",         args=[app])
    scheduler.add_job(job_30min_check,    "cron", minute="*",         args=[app])
    scheduler.add_job(job_evening_report, "cron", hour=23, minute=0,  args=[app])
    scheduler.start()

    log.info("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
