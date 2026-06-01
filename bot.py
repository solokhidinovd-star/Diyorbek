import logging
import json
import os
from datetime import datetime
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
import random

TOKEN = "8849559349:AAFQLKPjpVqfM-jLYWoB9j1f7Q4QbKNptDg"
CHAT_ID = 6456736085
TIMEZONE = pytz.timezone("Asia/Tashkent")
DATA_FILE = "tasks.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOTIVATSION = [
    "Har bir qadam oldinga! Siz buni uddalay olasiz!",
    "Kichik harakatlar katta natijalarga olib boradi. Davom eting!",
    "Eng qiyin boshlash. Boshlang, qolganini o'zingiz qilasiz!",
    "Maqsad aniq, yo'l ma'lum. Faqat harakat kerak!",
    "Bugun qilingan ish ertangi o'zingizga sovg'a!",
]

def motivatsiya():
    return random.choice(MOTIVATSION)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "tomorrow_tasks": [], "state": "idle"}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Salom! Men sizning kunlik rejalashtiruvchi yordamchingizman.\n\n"
        "Buyruqlar:\n"
        "/reja - bugungi vazifalarni korish\n"
        "/qosh 09:00 Vazifa nomi - vazifa qoshish\n"
        "/bajardim - vazifani bajarildi deb belgilash\n"
        "/tahlil - kunlik tahlil\n"
        "/tozala - barcha vazifalarni ochirish\n"
        "/motivatsiya - ragbatlantiruvchi xabar\n\n"
        "Har kuni kechqurun ertangi rejaingizni soraman!"
    )
    await update.message.reply_text(text)

async def reja_korsatish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = data.get("tasks", [])
    if not tasks:
        await update.message.reply_text(
            "Bugun hech qanday vazifa yoq.\n\nQoshish uchun: /qosh 09:00 Vazifa nomi"
        )
        return
    done = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    pct = round(done / total * 100) if total else 0
    lines = ["Bugungi vazifalar ({}/{} - {}%):\n".format(done, total, pct)]
    for i, t in enumerate(tasks, 1):
        icon = "✅" if t.get("done") else "⬜"
        lines.append("{} {}. {} - {}".format(icon, i, t["time"], t["label"]))
    if pct == 100:
        lines.append("\nBarcha vazifalar bajarildi! Ajoyib!")
    elif pct >= 50:
        lines.append("\n" + motivatsiya())
    await update.message.reply_text("\n".join(lines))

async def qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Format: /qosh 09:00 Vazifa nomi")
        return
    vaqt = args[0]
    label = " ".join(args[1:])
    try:
        datetime.strptime(vaqt, "%H:%M")
    except ValueError:
        await update.message.reply_text("Vaqt formati notogri. Misol: 09:00")
        return
    data = load_data()
    task = {"id": len(data["tasks"]) + 1, "time": vaqt, "label": label, "done": False}
    data["tasks"].append(task)
    data["tasks"].sort(key=lambda x: x["time"])
    save_data(data)
    await update.message.reply_text("Vazifa qoshildi: {} - {}".format(vaqt, label))

async def bajardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = [t for t in data["tasks"] if not t.get("done")]
    if not tasks:
        await update.message.reply_text("Barcha vazifalar allaqachon bajarilgan!")
        return
    keyboard = []
    for t in tasks:
        keyboard.append([InlineKeyboardButton(
            "{} - {}".format(t["time"], t["label"]),
            callback_data="done_{}".format(t["id"])
        )])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Qaysi vazifani bajardingiz?", reply_markup=reply_markup)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_str = query.data
    if data_str.startswith("done_"):
        task_id = int(data_str.split("_")[1])
        data = load_data()
        label = ""
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["done"] = True
                label = t["label"]
                break
        save_data(data)
        done = sum(1 for t in data["tasks"] if t.get("done"))
        total = len(data["tasks"])
        msg = "{} - bajarildi!\n\n".format(label)
        if done == total:
            msg += "Barcha vazifalar bajarildi! Ajoyib kun!"
        else:
            msg += "Bajarildi: {}/{}\n{}".format(done, total, motivatsiya())
        await query.edit_message_text(msg)

async def tahlil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = data.get("tasks", [])
    if not tasks:
        await update.message.reply_text("Tahlil qilish uchun vazifalar yoq.")
        return
    done = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct = round(len(done) / len(tasks) * 100) if tasks else 0
    lines = ["Kunlik tahlil\n"]
    lines.append("Samaradorlik: {}%".format(pct))
    lines.append("Bajarildi: {} ta".format(len(done)))
    lines.append("Bajarilmadi: {} ta\n".format(len(undone)))
    if done:
        lines.append("Bajarilgan:")
        for t in done:
            lines.append("  {} - {}".format(t["time"], t["label"]))
    if undone:
        lines.append("\nBajarilmagan:")
        for t in undone:
            lines.append("  {} - {}".format(t["time"], t["label"]))
    if pct == 100:
        lines.append("\nAjoyib! Barcha rejalar bajarildi!")
    elif pct >= 70:
        lines.append("\nYaxshi natija! Ertaga yanada yaxshiroq bolasiz!")
    else:
        lines.append("\nErtaga yangi imkoniyat! Bugungi tajribadan organing.")
    await update.message.reply_text("\n".join(lines))

async def motivatsiya_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(motivatsiya())

async def tozala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    data["tasks"] = []
    save_data(data)
    await update.message.reply_text("Barcha vazifalar ochirildi.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    if user_state.get(chat_id) == "adding_tomorrow":
        if text.lower() in ["tayyor", "boldi", "hammasi"]:
            user_state[chat_id] = None
            data = load_data()
            tomorrow = data.get("tomorrow_tasks", [])
            data["tasks"] = tomorrow
            data["tomorrow_tasks"] = []
            save_data(data)
            await update.message.reply_text(
                "{} ta vazifa saqlandi! Yaxshi tun!".format(len(data["tasks"]))
            )
        else:
            parts = text.strip().split(" ", 1)
            try:
                datetime.strptime(parts[0], "%H:%M")
                vaqt = parts[0]
                label = parts[1] if len(parts) > 1 else "Vazifa"
            except (ValueError, IndexError):
                vaqt = "09:00"
                label = text
            data = load_data()
            if "tomorrow_tasks" not in data:
                data["tomorrow_tasks"] = []
            data["tomorrow_tasks"].append({
                "id": len(data["tomorrow_tasks"]) + 1,
                "time": vaqt,
                "label": label,
                "done": False
            })
            save_data(data)
            await update.message.reply_text(
                "Qoshildi: {} - {}\n\nYana qoshing yoki Tayyor deb yozing.".format(vaqt, label)
            )
    else:
        await update.message.reply_text("Buyruqlar uchun /start ni bosing.")

async def kechki_eslatma(app):
    user_state[CHAT_ID] = "adding_tomorrow"
    data = load_data()
    data["tomorrow_tasks"] = []
    save_data(data)
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=(
            "Kechqurun eslatmasi!\n\n"
            "Ertangi kunlik rejangizni kiriting.\n"
            "Format: 09:00 Vazifa nomi\n\n"
            "Barcha vazifalarni kiritib bolgach Tayyor deb yozing."
        )
    )

async def ertalab_eslatma(app):
    data = load_data()
    tasks = data.get("tasks", [])
    if not tasks:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="Xayrli tong!\n\nBugun hech qanday reja yoq. /qosh buyrug'i bilan qoshing!"
        )
        return
    lines = ["Xayrli tong! Bugungi rejangiz:\n"]
    for i, t in enumerate(tasks, 1):
        lines.append("{}. {} - {}".format(i, t["time"], t["label"]))
    lines.append("\nBugun hammasi siz uchun! Muvaffaqiyat!")
    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines))

async def vazifa_eslatmalari(app):
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    data = load_data()
    tasks = data.get("tasks", [])
    changed = False
    for t in tasks:
        if t.get("time") == now and not t.get("done") and not t.get("reminded"):
            await app.bot.send_message(
                chat_id=CHAT_ID,
                text="Vaqt keldi!\n\n{} - {}\n\n{}\n\nBajargach /bajardim ni bosing!".format(
                    t["time"], t["label"], motivatsiya()
                )
            )
            t["reminded"] = True
            changed = True
    if changed:
        save_data(data)

async def dangasa_tekshirish(app):
    now = datetime.now(TIMEZONE)
    if now.hour < 9 or now.hour > 22:
        return
    data = load_data()
    undone = [t for t in data.get("tasks", []) if not t.get("done")]
    if len(undone) >= 3:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="Eslatma!\n\nHali {} ta vazifa bajarilmagan.\n\n{}\n\nHoziroq boshlang! /reja".format(
                len(undone), motivatsiya()
            )
        )

async def kechki_tahlil(app):
    data = load_data()
    tasks = data.get("tasks", [])
    if not tasks:
        return
    done = [t for t in tasks if t.get("done")]
    pct = round(len(done) / len(tasks) * 100)
    lines = ["Kunlik tahlil\n"]
    lines.append("Samaradorlik: {}%".format(pct))
    lines.append("Bajarildi: {}/{}".format(len(done), len(tasks)))
    if pct == 100:
        lines.append("\nMukammal kun! Barcha rejalar bajarildi!")
    elif pct >= 70:
        lines.append("\nYaxshi natija! Ertaga yanada yaxshiroq bolasiz!")
    else:
        lines.append("\nErtaga yangi imkoniyat! Bugungi tajribadan organing.")
    lines.append("\n\nErtangi rejalaringiz uchun 21:00 da yana yozaman!")
    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines))

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reja", reja_korsatish))
    app.add_handler(CommandHandler("qosh", qosh))
    app.add_handler(CommandHandler("bajardim", bajardim))
    app.add_handler(CommandHandler("tahlil", tahlil))
    app.add_handler(CommandHandler("motivatsiya", motivatsiya_cmd))
    app.add_handler(CommandHandler("tozala", tozala))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(kechki_eslatma, "cron", hour=21, minute=0, args=[app])
    scheduler.add_job(ertalab_eslatma, "cron", hour=7, minute=0, args=[app])
    scheduler.add_job(vazifa_eslatmalari, "cron", minute="*", args=[app])
    scheduler.add_job(dangasa_tekshirish, "cron", hour="10,12,14,16,18,20", minute=0, args=[app])
    scheduler.add_job(kechki_tahlil, "cron", hour=22, minute=0, args=[app])
    scheduler.start()

    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
