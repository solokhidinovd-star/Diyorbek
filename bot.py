import logging
import json
import os
from datetime import datetime, time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# --- SOZLAMALAR ---
TOKEN = "8849559349:AAFQLKPjpVqfM-jLYWoB9j1f7Q4QbKNptDg"
CHAT_ID = 6456736085
TIMEZONE = pytz.timezone("Asia/Tashkent")
DATA_FILE = "tasks.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MA'LUMOTLAR ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"tasks": [], "state": "idle", "tomorrow_tasks": []}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --- MOTIVATSION XABARLAR ---
MOTIVATSION = [
    "💪 Har bir qadam — oldinga! Siz buni uddalay olasiz!",
    "🔥 Kichik harakatlar katta natijalarga olib boradi. Davom eting!",
    "⚡ Eng qiyin boshlash. Boshlang — qolganini o'zingiz qilasiz!",
    "🎯 Maqsad aniq, yo'l ma'lum. Faqat harakat kerak!",
    "🌟 Bugun qilingan ish — ertangi o'zingizga sovg'a!",
]

import random
def motivatsiya():
    return random.choice(MOTIVATSION)

# --- KOMANDALAR ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 Salom! Men sizning kunlik rejalashtiruvchi yordamchingizman.\n\n"
        "📌 *Buyruqlar:*\n"
        "/reja — bugungi vazifalarni ko'rish\n"
        "/qosh — yangi vazifa qo'shish\n"
        "/bajardim — vazifani bajarildi deb belgilash\n"
        "/tahlil — kunlik tahlil\n"
        "/yordam — barcha buyruqlar\n\n"
        "Har kuni kechqurun ertangi rejaingizni so'rayman! 🌙"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def yordam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📋 *Barcha buyruqlar:*\n\n"
        "/start — botni boshlash\n"
        "/reja — bugungi vazifalar ro'yxati\n"
        "/qosh [vaqt] [vazifa] — vazifa qo'shish\n"
        "  Misol: `/qosh 09:00 Kitob o'qish`\n"
        "/bajardim — bajarilgan vazifani belgilash\n"
        "/tahlil — kunning AI tahlili\n"
        "/tozala — barcha vazifalarni o'chirish\n"
        "/motivatsiya — rag'batlantiruvchi xabar"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def reja_korsatish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = data.get("tasks", [])
    if not tasks:
        await update.message.reply_text(
            "📭 Bugun hech qanday vazifa yo'q.\n\n"
            "Qo'shish uchun: `/qosh 09:00 Vazifa nomi`",
            parse_mode="Markdown"
        )
        return

    done = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    pct = round(done / total * 100) if total else 0

    lines = [f"📋 *Bugungi vazifalar* ({done}/{total} — {pct}%):\n"]
    for i, t in enumerate(tasks, 1):
        icon = "✅" if t.get("done") else "⬜"
        lines.append(f"{icon} {i}. {t['time']} — {t['label']}")

    if pct == 100:
        lines.append("\n🎉 Barcha vazifalar bajarildi! Zo'r!")
    elif pct >= 50:
        lines.append(f"\n{motivatsiya()}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ To'g'ri format: `/qosh 09:00 Vazifa nomi`\nMisol: `/qosh 14:30 Ish yig'ilishi`",
            parse_mode="Markdown"
        )
        return

    vaqt = args[0]
    label = " ".join(args[1:])

    # Vaqt formatini tekshirish
    try:
        datetime.strptime(vaqt, "%H:%M")
    except ValueError:
        await update.message.reply_text("❌ Vaqt formati noto'g'ri. Misol: `09:00`", parse_mode="Markdown")
        return

    data = load_data()
    task = {"id": len(data["tasks"]) + 1, "time": vaqt, "label": label, "done": False}
    data["tasks"].append(task)
    # Vaqt bo'yicha saralash
    data["tasks"].sort(key=lambda x: x["time"])
    save_data(data)

    await update.message.reply_text(
        f"✅ Vazifa qo'shildi:\n⏰ {vaqt} — {label}",
        parse_mode="Markdown"
    )

async def bajardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = [t for t in data["tasks"] if not t.get("done")]

    if not tasks:
        await update.message.reply_text("🎉 Barcha vazifalar allaqachon bajarilgan!")
        return

    keyboard = []
    for t in tasks:
        keyboard.append([InlineKeyboardButton(
            f"⬜ {t['time']} — {t['label']}",
            callback_data=f"done_{t['id']}"
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
        for t in data["tasks"]:
            if t["id"] == task_id:
                t["done"] = True
                label = t["label"]
                break
        save_data(data)

        done = sum(1 for t in data["tasks"] if t.get("done"))
        total = len(data["tasks"])

        msg = f"✅ *{label}* — bajarildi!\n\n"
        if done == total:
            msg += "🎉 Barcha vazifalar bajarildi! Ajoyib kun!"
        else:
            msg += f"Bajarildi: {done}/{total}\n{motivatsiya()}"

        await query.edit_message_text(msg, parse_mode="Markdown")

async def tahlil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = data.get("tasks", [])

    if not tasks:
        await update.message.reply_text("📭 Tahlil qilish uchun vazifalar yo'q.")
        return

    done = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct = round(len(done) / len(tasks) * 100) if tasks else 0

    lines = [f"📊 *Kunlik tahlil*\n"]
    lines.append(f"📈 Samaradorlik: *{pct}%*")
    lines.append(f"✅ Bajarildi: {len(done)} ta")
    lines.append(f"❌ Bajarilmadi: {len(undone)} ta\n")

    if done:
        lines.append("*✅ Bajarilgan:*")
        for t in done:
            lines.append(f"  • {t['time']} — {t['label']}")

    if undone:
        lines.append("\n*❌ Bajarilmagan:*")
        for t in undone:
            lines.append(f"  • {t['time']} — {t['label']}")

    if pct == 100:
        lines.append("\n🌟 *Ajoyib! Barcha rejalar bajarildi!*")
        lines.append("Ertaga ham xuddi shunday davom eting!")
    elif pct >= 70:
        lines.append(f"\n👍 *Yaxshi natija!* {len(undone)} ta vazifa ertaga o'tkazildi.")
    elif pct >= 40:
        lines.append(f"\n⚠️ O'rtacha natija. Ertaga yanada kuchliroq harakat qiling!")
    else:
        lines.append(f"\n💡 Bugun qiyin kun bo'ldi. Ertaga yangi imkoniyat!")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def motivatsiya_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(motivatsiya())

async def tozala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    data["tasks"] = []
    save_data(data)
    await update.message.reply_text("🗑️ Barcha vazifalar o'chirildi.")

# Ertangi reja kiritish holati
user_state = {}

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    if user_state.get(chat_id) == "adding_tomorrow":
        if text.lower() in ["tayyor", "bo'ldi", "hammasi", "✅"]:
            user_state[chat_id] = None
            data = load_data()
            # Ertangi vazifalarni bugungi qilib o'tkazish
            tomorrow = data.get("tomorrow_tasks", [])
            data["tasks"] = tomorrow
            data["tomorrow_tasks"] = []
            save_data(data)
            await update.message.reply_text(
                f"✅ {len(data['tasks'])} ta vazifa saqlandi!\nErtalab ko'rib chiqasiz. Yaxshi tun! 🌙"
            )
        else:
            # Vazifa formatini parse qilish
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
                f"➕ Qo'shildi: {vaqt} — {label}\n\nYana qo'shing yoki *Tayyor* deb yozing.",
                parse_mode="Markdown"
            )
    else:
        # Oddiy xabar
        await update.message.reply_text(
            "Buyruqlarni ishlatish uchun /yordam ni bosing.",
        )

# --- REJALASHTIRUVCHI FUNKSIYALAR ---
async def kechki_eslatma(app):
    """Har kuni 21:00 da ertangi reja so'rash"""
    user_state[CHAT_ID] = "adding_tomorrow"
    data = load_data()
    data["tomorrow_tasks"] = []
    save_data(data)
    await app.bot.send_message(
        chat_id=CHAT_ID,
        text=(
            "🌙 *Kechqurun eslatmasi!*\n\n"
            "Ertangi kunlik rejangizni kiriting.\n"
            "Format: `09:00 Vazifa nomi`\n\n"
            "Barcha vazifalarni kiritib bo'lgach *Tayyor* deb yozing."
        ),
        parse_mode="Markdown"
    )

async def ertalab_eslatma(app):
    """Har kuni 07:00 da rejalarni ko'rsatish"""
    data = load_data()
    tasks = data.get("tasks", [])
    if not tasks:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text="☀️ *Xayrli tong!*\n\nBugun hech qanday reja yo'q. /qosh buyrug'i bilan qo'shing!",
            parse_mode="Markdown"
        )
        return

    lines = ["☀️ *Xayrli tong! Bugungi rejangiz:*\n"]
    for i, t in enumerate(tasks, 1):
        lines.append(f"⬜ {i}. {t['time']} — {t['label']}")
    lines.append("\n💪 Bugun hammasi siz uchun! Muvaffaqiyat!")

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text="\n".join(lines),
        parse_mode="Markdown"
    )

async def vazifa_eslatmalari(app):
    """Har 1 daqiqada tekshirish — vaqti kelgan vazifalarni eslatish"""
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    data = load_data()
    tasks = data.get("tasks", [])

    for t in tasks:
        if t.get("time") == now and not t.get("done") and not t.get("reminded"):
            await app.bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    f"⏰ *Vaqt keldi!*\n\n"
                    f"📌 {t['time']} — *{t['label']}*\n\n"
                    f"{motivatsiya()}\n\n"
                    f"Bajargach /bajardim buyrug'ini bosing!"
                ),
                parse_mode="Markdown"
            )
            t["reminded"] = True

    save_data(data)

async def dangasa_tekshirish(app):
    """Har 2 soatda bajarilmagan vazifalarni tekshirish"""
    now = datetime.now(TIMEZONE)
    hour = now.hour
    if hour < 9 or hour > 22:
        return

    data = load_data()
    tasks = data.get("tasks", [])
    undone = [t for t in tasks if not t.get("done")]

    if len(undone) >= 3:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"🔔 *Eslatma!*\n\n"
                f"Hali {len(undone)} ta vazifa bajarilmagan.\n\n"
                f"{motivatsiya()}\n\n"
                f"Hoziroq boshlang! /reja"
            ),
            parse_mode="Markdown"
        )

async def kechki_tahlil(app):
    """Har kuni 22:00 da kunlik tahlil"""
    data = load_data()
    tasks = data.get("tasks", [])
    if not tasks:
        return

    done = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    pct = round(len(done) / len(tasks) * 100) if tasks else 0

    lines = [f"🌙 *Kunlik tahlil*\n"]
    lines.append(f"📈 Samaradorlik: *{pct}%*")
    lines.append(f"✅ Bajarildi: {len(done)}/{len(tasks)}\n")

    if pct == 100:
        lines.append("🏆 *Mukammal kun! Barcha rejalar bajarildi!*")
    elif pct >= 70:
        lines.append("👍 *Yaxshi natija!* Ertaga yanada yaxshiroq bo'lasiz!")
    else:
        lines.append("💡 *Ertaga yangi imkoniyat!* Bugungi tajribadan o'rganing.")

    lines.append("\n\nErtangi rejalaringiz uchun 21:00 da yana yozaman! 🌙")

    await app.bot.send_message(
        chat_id=CHAT_ID,
        text="\n".join(lines),
        parse_mode="Markdown"
    )

# --- ASOSIY FUNKSIYA ---
def main():
    app = Application.builder().token(TOKEN).build()

    # Komandalar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("yordam", yordam))
    app.add_handler(CommandHandler("reja", reja_korsatish))
    app.add_handler(CommandHandler("qosh", qosh))
    app.add_handler(CommandHandler("bajardim", bajardim))
    app.add_handler(CommandHandler("tahlil", tahlil))
    app.add_handler(CommandHandler("motivatsiya", motivatsiya_cmd))
    app.add_handler(CommandHandler("tozala", tozala))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # Scheduler
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
