import logging
import json
import os
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
import pytz

TOKEN = "8849559349:AAEnn05gUAfsHHQlWpSZp606wOJX5iy57j8"
CHAT_ID = 6456736085
TZ = pytz.timezone("Asia/Tashkent")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_FILE = "data.json"

# ── DATA ────────────────────────────────────────────────────────────────────
def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "last_date": "", "scheduled": [], "custom_daily": [], "sent": {}}

def save(data):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)

def sent_check(data, key):
    """Mark key as sent. Returns True if this is the first time."""
    if data.get("sent", {}).get(key):
        return False
    data.setdefault("sent", {})[key] = True
    save(data)
    return True

def today_str():
    return str(date.today())

def is_sunday():
    return date.today().weekday() == 6

def nid(lst):
    return max((x["id"] for x in lst), default=0) + 1

# ── BASE TASKS ───────────────────────────────────────────────────────────────
BASE = [
    {"label": "CRM check",                      "time": "10:00"},
    {"label": "Check Instagram DMs",            "time": "10:15"},
    {"label": "Lead report on Marketing group", "time": "19:00"},
    {"label": "Check YouTube Leads",            "time": None},
    {"label": "Read 5 pages of a book",         "time": None},
    {"label": "Do tasks given by 4prep",        "time": None},
]

# ── KEYBOARDS ────────────────────────────────────────────────────────────────
MAIN_KB = ReplyKeyboardMarkup([
    ["📋 My Tasks",         "✅ Mark Done"],
    ["➕ Add Task",          "🔁 Daily Tasks"],
    ["🔔 Schedule Reminder", "📊 Daily Report"],
], resize_keyboard=True)

DAILY_KB = ReplyKeyboardMarkup([
    ["➕ Add Daily Task", "🗑 Remove Daily Task"],
    ["🔙 Back"],
], resize_keyboard=True)

# ── HELPERS ──────────────────────────────────────────────────────────────────
def esc(t):
    t = str(t)
    for c in r"\.!-()_+=#|{}~`>[]":
        t = t.replace(c, "\\" + c)
    return t

def pbar(done, total):
    if not total: return "⬜⬜⬜⬜⬜"
    n = round(done / total * 5)
    return "🟩" * n + "⬜" * (5 - n)

def tline(t):
    icon = "✅" if t.get("done") else "⬜"
    ts   = " ⏰`{}`".format(t["time"]) if t.get("time") else ""
    lb   = esc(t["label"])
    return "{}{} ~{}~".format(icon, ts, lb) if t.get("done") else "{}{} *{}*".format(icon, ts, lb)

def reset_daily(data):
    today = today_str()
    if data.get("last_date") == today:
        return data
    data["tasks"] = []
    # Clean old sent keys (keep only today's)
    data["sent"] = {k: v for k, v in data.get("sent", {}).items()
                    if today_str() in k}
    if not is_sunday():
        for bt in BASE:
            data["tasks"].append({
                "id": nid(data["tasks"]),
                "label": bt["label"], "time": bt["time"],
                "done": False, "reminded_at": None, "reminded_30": False,
            })
        for ct in data.get("custom_daily", []):
            data["tasks"].append({
                "id": nid(data["tasks"]),
                "label": ct["label"], "time": ct.get("time"),
                "done": False, "reminded_at": None, "reminded_30": False,
            })
        data["tasks"].sort(key=lambda x: x["time"] or "99:99")
    data["last_date"] = today
    save(data)
    return data

user_state = {}

# ── SCREENS ──────────────────────────────────────────────────────────────────
async def cmd_start(update, ctx):
    data = load()
    reset_daily(data)
    await update.message.reply_text(
        "👋 *Hello\\!* I'm your Daily Planner Bot\\.\n\n"
        "📋 *My Tasks* — view today's tasks\n"
        "✅ *Mark Done* — mark a task completed\n"
        "➕ *Add Task* — one\\-time task for today\n"
        "🔁 *Daily Tasks* — manage recurring tasks\n"
        "🔔 *Schedule Reminder* — reminder for any date\n"
        "📊 *Daily Report* — today's summary",
        parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def show_tasks(update, ctx=None):
    data = load()
    reset_daily(data)
    tasks = data["tasks"]
    if not tasks:
        await update.message.reply_text(
            "📭 _No tasks for today\\._\n\nUse ➕ *Add Task* to add one\\!",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    done  = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    pct   = round(done / total * 100)
    lines = ["📋 *Today's Tasks*\n",
             "{} `{}/{}` — *{}%* completed\n".format(pbar(done, total), done, total, pct)]
    for t in tasks:
        lines.append(tline(t))
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def show_done_menu(update, ctx):
    data   = load()
    undone = [t for t in data["tasks"] if not t.get("done")]
    if not undone:
        await update.message.reply_text(
            "🎉 *All tasks completed\\! Great job\\!*",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    kb = [[InlineKeyboardButton(
        "⬜ {}{}".format(t["label"], " ({})".format(t["time"]) if t.get("time") else ""),
        callback_data="done_{}".format(t["id"]))] for t in undone]
    await update.message.reply_text(
        "☑️ *Which task did you complete?*",
        parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(kb))

async def show_report(update, ctx):
    data  = load()
    tasks = data["tasks"]
    if not tasks:
        await update.message.reply_text(
            "📭 _No tasks recorded for today\\._",
            parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        return
    done   = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct    = round(len(done) / len(tasks) * 100)
    lines  = [
        "📊 *Daily Report — {}*\n".format(esc(today_str())),
        "{} *{}%* completed".format(pbar(len(done), len(tasks)), pct),
        "✅ Done: *{}*   ❌ Remaining: *{}*\n".format(len(done), len(undone)),
    ]
    if done:
        lines.append("*✅ Completed:*")
        for t in done:
            ts = "`{}` ".format(t["time"]) if t.get("time") else ""
            lines.append("  • {}{}".format(ts, esc(t["label"])))
    if undone:
        lines.append("\n*❌ Not completed:*")
        for t in undone:
            ts = "`{}` ".format(t["time"]) if t.get("time") else ""
            lines.append("  • {}{}".format(ts, esc(t["label"])))
    if pct == 100:   lines.append("\n🏆 *Perfect day\\! You crushed it\\!*")
    elif pct >= 70:  lines.append("\n👍 *Good job\\! Keep it up\\!*")
    elif pct >= 40:  lines.append("\n💪 *You can do better tomorrow\\!*")
    else:            lines.append("\n💡 _Tomorrow is a fresh start\\!_")
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KB)

async def show_daily_menu(update, ctx):
    data  = load()
    daily = data.get("custom_daily", [])
    lines = ["🔁 *Your Recurring Daily Tasks*\n"]
    if daily:
        for d in daily:
            ts = " ⏰`{}`".format(d["time"]) if d.get("time") else ""
            lines.append("• {}{}".format(esc(d["label"]), ts))
    else:
        lines.append("_No custom daily tasks yet\\._")
    lines.append("\n_Use buttons below to manage:_")
    await update.message.reply_text(
        "\n".join(lines), parse_mode="MarkdownV2", reply_markup=DAILY_KB)

async def show_remove_daily(update, ctx):
    data  = load()
    daily = data.get("custom_daily", [])
    if not daily:
        await update.message.reply_text(
            "📭 No custom daily tasks to remove.", reply_markup=DAILY_KB)
        return
    kb = [[InlineKeyboardButton(
        "🗑 {}{}".format(d["label"], " ({})".format(d["time"]) if d.get("time") else ""),
        callback_data="rmdaily_{}".format(d["id"]))] for d in daily]
    await update.message.reply_text(
        "Tap a task to remove it:", reply_markup=InlineKeyboardMarkup(kb))

# ── CALLBACKS ────────────────────────────────────────────────────────────────
async def cb(update, ctx):
    q = update.callback_query
    await q.answer()
    d = q.data

    if d.startswith("done_"):
        tid  = int(d.split("_")[1])
        data = load()
        label = ""
        for t in data["tasks"]:
            if t["id"] == tid:
                t["done"] = True
                label = t["label"]
                break
        save(data)
        done  = sum(1 for t in data["tasks"] if t.get("done"))
        total = len(data["tasks"])
        msg   = "✅ *{}* — marked as done\\!\n\n{} `{}/{}` — *{}%*".format(
            esc(label), pbar(done, total), done, total, round(done/total*100))
        if done == total:
            msg += "\n\n🏆 *All tasks completed\\!*"
        await q.edit_message_text(msg, parse_mode="MarkdownV2")

    elif d.startswith("check30_"):
        tid  = int(d.split("_")[1])
        data = load()
        task = next((t for t in data["tasks"] if t["id"] == tid), None)
        if task and not task.get("done"):
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, done!", callback_data="done_{}".format(tid)),
                InlineKeyboardButton("⏰ Not yet",    callback_data="later_{}".format(tid))]])
            await q.edit_message_text(
                "❓ Did you complete *{}*?".format(esc(task["label"])),
                parse_mode="MarkdownV2", reply_markup=kb)
        else:
            await q.edit_message_text("✅ _Task already completed\\._", parse_mode="MarkdownV2")

    elif d.startswith("later_"):
        await q.edit_message_text("⏰ _Got it\\. I'll remind you later\\._", parse_mode="MarkdownV2")

    elif d.startswith("rmdaily_"):
        rid  = int(d.split("_")[1])
        data = load()
        before = len(data.get("custom_daily", []))
        data["custom_daily"] = [x for x in data.get("custom_daily", []) if x["id"] != rid]
        after = len(data["custom_daily"])
        save(data)
        if after < before:
            await q.edit_message_text("🗑 Removed successfully!")
        else:
            await q.edit_message_text("❌ Task not found.")

# ── MESSAGE HANDLER ──────────────────────────────────────────────────────────
async def msg_handler(update, ctx):
    cid   = update.effective_chat.id
    text  = update.message.text
    state = user_state.get(cid, "")

    # Main menu buttons
    if   text == "📋 My Tasks":           await show_tasks(update, ctx)
    elif text == "✅ Mark Done":           await show_done_menu(update, ctx)
    elif text == "➕ Add Task":
        user_state[cid] = "add_label"
        await update.message.reply_text("✏️ Enter the task name (today only):", reply_markup=MAIN_KB)
    elif text == "🔁 Daily Tasks":         await show_daily_menu(update, ctx)
    elif text == "📊 Daily Report":        await show_report(update, ctx)
    elif text == "🔔 Schedule Reminder":
        user_state[cid] = "sched_label"
        await update.message.reply_text("🔔 Enter the reminder text:", reply_markup=MAIN_KB)

    # Daily tasks submenu
    elif text == "➕ Add Daily Task":
        user_state[cid] = "daily_label"
        await update.message.reply_text(
            "🔁 Enter the name of the recurring task:", reply_markup=DAILY_KB)
    elif text == "🗑 Remove Daily Task":   await show_remove_daily(update, ctx)
    elif text == "🔙 Back":
        user_state[cid] = ""
        await update.message.reply_text("Main menu:", reply_markup=MAIN_KB)

    # ── Add daily task ──
    elif state == "daily_label":
        user_state[cid] = "daily_time:" + text
        await update.message.reply_text(
            "⏰ Set a time for notifications?\n\nType time (e.g. 09:00) or No:",
            reply_markup=DAILY_KB)

    elif state.startswith("daily_time:"):
        label = state.replace("daily_time:", "")
        vaqt  = None
        if text.strip().lower() not in ["no", "n", "-", "skip", "none"]:
            try:
                datetime.strptime(text.strip(), "%H:%M")
                vaqt = text.strip()
            except ValueError:
                await update.message.reply_text(
                    "❌ Wrong format. Use 09:00 or No:", reply_markup=DAILY_KB)
                return
        data = load()
        new_id = nid(data.get("custom_daily", []))
        data.setdefault("custom_daily", []).append(
            {"id": new_id, "label": label, "time": vaqt})
        # Add to today's list immediately
        data["tasks"].append({
            "id": nid(data["tasks"]),
            "label": label, "time": vaqt,
            "done": False, "reminded_at": None, "reminded_30": False,
        })
        data["tasks"].sort(key=lambda x: x["time"] or "99:99")
        save(data)
        user_state[cid] = ""
        reply = "✅ *Daily task added\\!*\n\n🔁 *{}*".format(esc(label))
        if vaqt:
            reply += " at ⏰`{}`".format(vaqt)
        reply += "\n\n_Repeats every day \\(except Sunday\\)\\._"
        await update.message.reply_text(reply, parse_mode="MarkdownV2", reply_markup=MAIN_KB)

    # ── Schedule one-time reminder ──
    elif state == "sched_label":
        user_state[cid] = "sched_dt:" + text
        await update.message.reply_text(
            "📅 When?\n\nFormat: DD.MM.YYYY HH:MM\nExample: 25.06.2026 14:30",
            reply_markup=MAIN_KB)

    elif state.startswith("sched_dt:"):
        label = state.replace("sched_dt:", "")
        try:
            dt = TZ.localize(datetime.strptime(text.strip(), "%d.%m.%Y %H:%M"))
            if dt <= datetime.now(TZ):
                await update.message.reply_text(
                    "❌ That time has already passed. Try again:", reply_markup=MAIN_KB)
                return
            data = load()
            data.setdefault("scheduled", []).append({
                "id": nid(data.get("scheduled", [])),
                "label": label,
                "datetime": dt.strftime("%Y-%m-%d %H:%M"),
                "sent": False,
            })
            save(data)
            user_state[cid] = ""
            await update.message.reply_text(
                "✅ Reminder set\\!\n\n🔔 *{}*\n📅 `{}`".format(esc(label), esc(text.strip())),
                parse_mode="MarkdownV2", reply_markup=MAIN_KB)
        except ValueError:
            await update.message.reply_text(
                "❌ Wrong format. Use: 25.06.2026 14:30", reply_markup=MAIN_KB)

    # ── Add one-time task ──
    elif state == "add_label":
        user_state[cid] = "add_time:" + text
        await update.message.reply_text(
            "⏰ Set a time? Type time (e.g. 14:30) or No:", reply_markup=MAIN_KB)

    elif state.startswith("add_time:"):
        label = state.replace("add_time:", "")
        vaqt  = None
        if text.strip().lower() not in ["no", "n", "-", "skip", "none"]:
            try:
                datetime.strptime(text.strip(), "%H:%M")
                vaqt = text.strip()
            except ValueError:
                await update.message.reply_text(
                    "❌ Wrong format. Use 14:30 or No:", reply_markup=MAIN_KB)
                return
        data = load()
        data["tasks"].append({
            "id": nid(data["tasks"]),
            "label": label, "time": vaqt,
            "done": False, "reminded_at": None, "reminded_30": False,
        })
        data["tasks"].sort(key=lambda x: x["time"] or "99:99")
        save(data)
        user_state[cid] = ""
        reply = "✅ Task added\\!\n\n📌 *{}*".format(esc(label))
        if vaqt:
            reply += " at ⏰`{}`".format(vaqt)
        await update.message.reply_text(reply, parse_mode="MarkdownV2", reply_markup=MAIN_KB)

    else:
        await update.message.reply_text("📌 Use the buttons below:", reply_markup=MAIN_KB)

# ── SCHEDULED JOBS ───────────────────────────────────────────────────────────
async def job_morning(app):
    data = load()
    key  = "morning_{}".format(today_str())
    if not sent_check(data, key):
        return
    data = reset_daily(data)
    tasks = data["tasks"]
    if not tasks:
        await app.bot.send_message(CHAT_ID, "Good morning! Today is Sunday — rest and recharge! 🌿")
        return
    done  = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    lines = ["☀️ Good morning! Here are your tasks for today:\n",
             "{} {}/{} completed\n".format(pbar(done, total), done, total)]
    for t in tasks:
        ts = " [{}]".format(t["time"]) if t.get("time") else ""
        lines.append("{}{} {}".format("✅" if t.get("done") else "⬜", ts, t["label"]))
    lines.append("\n💪 Let's make today count!")
    await app.bot.send_message(CHAT_ID, "\n".join(lines))

async def job_reminders(app):
    now  = datetime.now(TZ).strftime("%H:%M")
    data = load()
    changed = False
    for t in data["tasks"]:
        if not t.get("time") or t.get("done") or t["time"] != now:
            continue
        key = "remind_{}_{}".format(t["id"], today_str())
        if not sent_check(data, key):
            continue
        await app.bot.send_message(
            CHAT_ID,
            "⏰ Time to do it!\n\n📌 {} — {}\n\nComplete it and tap ✅ Mark Done.".format(
                t["label"], t["time"]))
        t["reminded_at"] = now
        changed = True
    if changed:
        save(data)

async def job_30min(app):
    now  = datetime.now(TZ)
    data = load()
    changed = False
    for t in data["tasks"]:
        if not t.get("reminded_at") or t.get("done") or t.get("reminded_30"):
            continue
        try:
            rt   = TZ.localize(datetime.strptime(t["reminded_at"], "%H:%M").replace(
                year=now.year, month=now.month, day=now.day))
            diff = (now - rt).total_seconds() / 60
            if diff < 30:
                continue
            key = "check30_{}_{}".format(t["id"], today_str())
            if not sent_check(data, key):
                t["reminded_30"] = True
                changed = True
                continue
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Yes, done!", callback_data="done_{}".format(t["id"])),
                InlineKeyboardButton("⏰ Not yet",    callback_data="later_{}".format(t["id"]))]])
            await app.bot.send_message(
                CHAT_ID,
                "🔔 Did you complete {}?".format(t["label"]),
                reply_markup=kb)
            t["reminded_30"] = True
            changed = True
        except Exception as e:
            log.error("30min: {}".format(e))
    if changed:
        save(data)

async def job_scheduled(app):
    now  = datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    data = load()
    changed = False
    for r in data.get("scheduled", []):
        if r.get("sent") or r.get("datetime") != now:
            continue
        key = "sched_{}_{}".format(r["id"], r["datetime"])
        if not sent_check(data, key):
            r["sent"] = True
            changed = True
            continue
        await app.bot.send_message(
            CHAT_ID,
            "🔔 Reminder!\n\n📌 {}".format(r["label"]))
        r["sent"] = True
        changed = True
    if changed:
        save(data)

async def job_report(app):
    data = load()
    key  = "report_{}".format(today_str())
    if not sent_check(data, key):
        return
    tasks = data["tasks"]
    if not tasks:
        return
    done   = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct    = round(len(done) / len(tasks) * 100)
    lines  = [
        "🌙 Daily Report — {}\n".format(today_str()),
        "{} {}% completed".format(pbar(len(done), len(tasks)), pct),
        "✅ Done: {}   ❌ Remaining: {}\n".format(len(done), len(tasks)),
    ]
    if done:
        lines.append("✅ Completed:")
        for t in done:
            ts = " [{}]".format(t["time"]) if t.get("time") else ""
            lines.append("  •{} {}".format(ts, t["label"]))
    if undone:
        lines.append("\n❌ Not completed:")
        for t in undone:
            ts = " [{}]".format(t["time"]) if t.get("time") else ""
            lines.append("  •{} {}".format(ts, t["label"]))
    if pct == 100:  lines.append("\n🏆 Perfect day! You crushed it!")
    elif pct >= 70: lines.append("\n👍 Good job! Keep pushing!")
    elif pct >= 40: lines.append("\n💪 You can do better tomorrow!")
    else:           lines.append("\n💡 Tomorrow is a fresh start!")
    await app.bot.send_message(CHAT_ID, "\n".join(lines))

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("tasks", show_tasks))
    app.add_handler(CallbackQueryHandler(cb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))

    s = AsyncIOScheduler(
        timezone=TZ,
        jobstores={"default": MemoryJobStore()},
        job_defaults={"coalesce": True, "max_instances": 1})
    s.add_job(job_morning,   "cron", hour=7,  minute=0,  args=[app])
    s.add_job(job_reminders, "cron", minute="*",          args=[app])
    s.add_job(job_30min,     "cron", minute="*",          args=[app])
    s.add_job(job_scheduled, "cron", minute="*",          args=[app])
    s.add_job(job_report,    "cron", hour=23, minute=0,   args=[app])
    s.start()

    log.info("Bot started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
