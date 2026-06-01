import logging
import json
import os
from datetime import datetime, date
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

TOKEN = "8849559349:AAFQLKPjpVqfM-jLYWoB9j1f7Q4QbKNptDg"
CHAT_ID = 6456736085
TIMEZONE = pytz.timezone("Asia/Tashkent")
DATA_FILE = "tasks.json"
PRAYER_FILE = "prayers.json"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOTIVATSION = [
    "🔥 Har kuni bir qadam oldinga\\! Siz buni uddalay olasiz\\!",
    "⚡ Kichik harakatlar katta natijalarga olib boradi\\. Davom eting\\!",
    "🚀 Eng qiyin — boshlash\\. Boshlang, qolganini o'zingiz qilasiz\\!",
    "🎯 Maqsad aniq, yo'l ma'lum\\. Faqat harakat kerak\\!",
    "🌟 Bugun qilingan ish — ertangi o'zingizga sovg'a\\!",
    "💡 Hozir qiyin tuyulsa ham, natija siz uchun kutmoqda\\!",
    "🏆 Har kuni ozgina harakat — katta muvaffaqiyatga olib boradi\\!",
    "💪 Siz kuchli odamsiz\\. Bugun ham isbotlang\\!",
    "⏰ Dangasalik vaqtinchalik, muvaffaqiyat abadiy\\!",
]

NAMOZ_NOMLAR = ["Bomdod", "Peshin", "Asr", "Shom", "Xufton"]
NAMOZ_EMOJIS = ["🌅", "☀️", "🌤", "🌇", "🌙"]

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

def load_prayers():
    if os.path.exists(PRAYER_FILE):
        with open(PRAYER_FILE, "r") as f:
            return json.load(f)
    return {}

def save_prayers(data):
    with open(PRAYER_FILE, "w") as f:
        json.dump(data, f)

async def fetch_prayer_times():
    today = date.today()
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://api.aladhan.com/v1/timingsByCity/{}-{}-{}?city=Tashkent&country=Uzbekistan&method=3".format(
                today.day, today.month, today.year
            )
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                timings = data["data"]["timings"]
                prayers = {
                    "Bomdod": timings["Fajr"][:5],
                    "Peshin": timings["Dhuhr"][:5],
                    "Asr": timings["Asr"][:5],
                    "Shom": timings["Maghrib"][:5],
                    "Xufton": timings["Isha"][:5],
                    "date": str(today)
                }
                save_prayers(prayers)
                return prayers
    except Exception as e:
        logger.error("Namoz vaqtlari olishda xato: {}".format(e))
        return None

def get_prayers():
    prayers = load_prayers()
    today = str(date.today())
    if prayers.get("date") == today:
        return prayers
    return None

user_state = {}

MAIN_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("📋 Rejalar"), KeyboardButton("✅ Bajardim")],
    [KeyboardButton("➕ Vazifa qosh"), KeyboardButton("📊 Tahlil")],
    [KeyboardButton("🕌 Namoz vaqtlari"), KeyboardButton("💪 Motivatsiya")],
    [KeyboardButton("🗑 Tozala")],
], resize_keyboard=True)

VAQT_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("⏰ Vaqt qosham"), KeyboardButton("⏭ Shartmas")],
], resize_keyboard=True)

def escape_md(text):
    for ch in [".", "!", "-", "(", ")", "_", "+", "=", "|", "{", "}", "#"]:
        text = text.replace(ch, "\\" + ch)
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Salom\\!* Men sizning kunlik rejalashtiruvchi yordamchingizman\\.\n\n"
        "🌙 Har kuni kechqurun ertangi rejaingizni so'rayman\\!\n"
        "🕌 Namoz vaqtlari avtomatik eslatiladi\\!\n"
        "📌 Quyidagi tugmalardan foydalaning:",
        parse_mode="MarkdownV2",
        reply_markup=MAIN_KEYBOARD
    )

async def reja_korsatish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = data.get("tasks", [])
    if not tasks:
        await update.message.reply_text(
            "📭 _Bugun hech qanday vazifa yo'q\\._\n\n➕ *Vazifa qosh* tugmasini bosing\\!",
            parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD
        )
        return
    done = sum(1 for t in tasks if t.get("done"))
    total = len(tasks)
    pct = round(done / total * 100) if total else 0
    bars = ["⬜"] * 5
    for i in range(min(5, round(pct / 20))):
        bars[i] = "🟩"
    bar = "".join(bars)
    lines = ["📋 *Bugungi vazifalar*\n", "{} `{}/{}` — *{}%*\n".format(bar, done, total, pct)]
    for i, t in enumerate(tasks, 1):
        icon = "✅" if t.get("done") else "⬜"
        vaqt_str = "" if t.get("no_time") else "⏰`{}` — ".format(t["time"])
        label = escape_md(t["label"])
        if t.get("done"):
            lines.append("{} {}~{}~".format(icon, vaqt_str, label))
        else:
            lines.append("{} {}*{}*".format(icon, vaqt_str, label))
    if pct == 100:
        lines.append("\n🎉 *Barcha vazifalar bajarildi\\! Ajoyib\\!*")
    elif pct >= 50:
        lines.append("\n" + motivatsiya())
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)

async def reja_sarala(update_or_app, is_scheduled=False):
    data = load_data()
    tasks = [t for t in data.get("tasks", []) if not t.get("done") and not t.get("is_prayer")]
    if not tasks:
        msg = "📭 _Bugun bajarilmagan vazifalar yo'q\\._"
        if is_scheduled:
            await update_or_app.bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="MarkdownV2")
        else:
            await update_or_app.message.reply_text(msg, parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        return

    keyboard = []
    lines = ["📋 *Bugungi rejani ko'rib chiqing\\!*\n_Keraksiz vazifalarni ❌ bosib o'chiring:_\n"]
    for t in tasks:
        vaqt_str = "" if t.get("no_time") else "⏰`{}` — ".format(t["time"])
        label = escape_md(t["label"])
        lines.append("• {}*{}*".format(vaqt_str, label))
        keyboard.append([InlineKeyboardButton(
            "❌ {}{}".format("" if t.get("no_time") else "{} - ".format(t["time"]), t["label"]),
            callback_data="del_{}".format(t["id"])
        )])
    keyboard.append([InlineKeyboardButton("✅ Tayyor, barchasi to'g'ri!", callback_data="sarala_done")])

    if is_scheduled:
        await update_or_app.bot.send_message(
            chat_id=CHAT_ID,
            text="\n".join(lines),
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update_or_app.message.reply_text(
            "\n".join(lines),
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def namoz_vaqtlari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prayers = get_prayers()
    if not prayers:
        prayers = await fetch_prayer_times()
    if not prayers:
        await update.message.reply_text("❌ _Namoz vaqtlarini olishda xato\\. Internet tekshiring\\._", parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        return
    lines = ["🕌 *Bugungi namoz vaqtlari*\n_Toshkent shahari_\n"]
    for nom, emoji in zip(NAMOZ_NOMLAR, NAMOZ_EMOJIS):
        vaqt = prayers.get(nom, "—")
        lines.append("{} *{}:* `{}`".format(emoji, nom, vaqt))
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)

async def qosh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 1:
        await update.message.reply_text("📌 Format: `/qosh Vazifa nomi`\nYoki: `/qosh 09:00 Vazifa nomi`", parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        return
    try:
        datetime.strptime(args[0], "%H:%M")
        vaqt = args[0]
        label = " ".join(args[1:]) if len(args) > 1 else "Vazifa"
        no_time = False
    except ValueError:
        vaqt = "--:--"
        label = " ".join(args)
        no_time = True
    data = load_data()
    task = {"id": len(data["tasks"]) + 1, "time": vaqt, "label": label, "done": False, "no_time": no_time}
    data["tasks"].append(task)
    data["tasks"].sort(key=lambda x: x["time"])
    save_data(data)
    label_esc = escape_md(label)
    if no_time:
        await update.message.reply_text("✅ Vazifa qo'shildi\\!\n\n📌 *{}* \\(vaqtsiz\\)".format(label_esc), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("✅ Vazifa qo'shildi\\!\n\n⏰ `{}` — *{}*".format(vaqt, label_esc), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)

async def vazifa_qosh_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_state[update.effective_chat.id] = "adding_task_label"
    await update.message.reply_text("✏️ *Vazifa nomini yozing:*", parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)

async def bajardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    tasks = [t for t in data["tasks"] if not t.get("done")]
    if not tasks:
        await update.message.reply_text("🎉 *Barcha vazifalar bajarilgan\\!*", parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        return
    keyboard = []
    for t in tasks:
        vaqt_str = "" if t.get("no_time") else "{} - ".format(t["time"])
        keyboard.append([InlineKeyboardButton("⬜ {}{}".format(vaqt_str, t["label"]), callback_data="done_{}".format(t["id"]))])
    await update.message.reply_text("☑️ *Qaysi vazifani bajardingiz?*", parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(keyboard))

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("done_"):
        task_id = int(query.data.split("_")[1])
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
        label_esc = escape_md(label)
        msg = "✅ *{}* — bajarildi\\!\n\n".format(label_esc)
        if done == total:
            msg += "🏆 *Barcha vazifalar bajarildi\\! Ajoyib kun\\!*"
        else:
            msg += "📊 Bajarildi: `{}/{}`\n\n{}".format(done, total, motivatsiya())
        await query.edit_message_text(msg, parse_mode="MarkdownV2")

    elif query.data.startswith("del_"):
        task_id = int(query.data.split("_")[1])
        data = load_data()
        data["tasks"] = [t for t in data["tasks"] if t["id"] != task_id]
        save_data(data)
        # Ro'yxatni yangilash
        tasks = [t for t in data["tasks"] if not t.get("done") and not t.get("is_prayer")]
        if not tasks:
            await query.edit_message_text("✅ *Ro'yxat tozalandi\\! Yaxshi kun\\!*", parse_mode="MarkdownV2")
            return
        keyboard = []
        lines = ["📋 *Bugungi rejani ko'rib chiqing\\!*\n_Keraksiz vazifalarni ❌ bosib o'chiring:_\n"]
        for t in tasks:
            vaqt_str = "" if t.get("no_time") else "⏰`{}` — ".format(t["time"])
            label = escape_md(t["label"])
            lines.append("• {}*{}*".format(vaqt_str, label))
            keyboard.append([InlineKeyboardButton("❌ {}{}".format("" if t.get("no_time") else "{} - ".format(t["time"]), t["label"]), callback_data="del_{}".format(t["id"]))])
        keyboard.append([InlineKeyboardButton("✅ Tayyor, barchasi to'g'ri!", callback_data="sarala_done")])
        await query.edit_message_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "sarala_done":
        await query.edit_message_text("✅ *Ajoyib\\! Bugungi rejangiz tasdiqlandi\\.*\n\n💪 _Muvaffaqiyat\\!_", parse_mode="MarkdownV2")

async def tahlil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    all_tasks = data.get("tasks", [])
    tasks = [t for t in all_tasks if not t.get("is_prayer")]
    prayers = [t for t in all_tasks if t.get("is_prayer")]
    if not tasks and not prayers:
        await update.message.reply_text("📭 _Tahlil qilish uchun vazifalar yo'q\\._", parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        return
    done = [t for t in tasks if t.get("done")]
    undone = [t for t in tasks if not t.get("done")]
    p_done = [t for t in prayers if t.get("done")]
    pct = round(len(done) / len(tasks) * 100) if tasks else 0
    lines = ["📊 *Kunlik tahlil*\n"]
    lines.append("📈 Samaradorlik: *{}%*".format(pct))
    lines.append("✅ Bajarildi: *{} ta*".format(len(done)))
    lines.append("❌ Bajarilmadi: *{} ta*".format(len(undone)))
    lines.append("🕌 Namoz: *{}/5*\n".format(len(p_done)))
    if done:
        lines.append("*✅ Bajarilgan:*")
        for t in done:
            vaqt_str = "" if t.get("no_time") else "⏰`{}` ".format(t["time"])
            lines.append("  ~{}{}~".format(vaqt_str, escape_md(t["label"])))
    if undone:
        lines.append("\n*❌ Bajarilmagan:*")
        for t in undone:
            vaqt_str = "" if t.get("no_time") else "⏰`{}` ".format(t["time"])
            lines.append("  • {}{}".format(vaqt_str, escape_md(t["label"])))
    if pct == 100:
        lines.append("\n🏆 *Ajoyib\\! Barcha rejalar bajarildi\\!*")
    elif pct >= 70:
        lines.append("\n👍 *Yaxshi natija\\!*")
    else:
        lines.append("\n💡 _Ertaga yangi imkoniyat\\!_")
    await update.message.reply_text("\n".join(lines), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)

async def motivatsiya_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💪 *Bugungi rag'bat:*\n\n{}".format(motivatsiya()), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)

async def tozala(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    data["tasks"] = []
    save_data(data)
    await update.message.reply_text("🗑 _Barcha vazifalar o'chirildi\\._", parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text

    if text == "📋 Rejalar":
        await reja_korsatish(update, context)
    elif text == "✅ Bajardim":
        await bajardim(update, context)
    elif text == "➕ Vazifa qosh":
        await vazifa_qosh_start(update, context)
    elif text == "📊 Tahlil":
        await tahlil(update, context)
    elif text == "🕌 Namoz vaqtlari":
        await namoz_vaqtlari(update, context)
    elif text == "💪 Motivatsiya":
        await motivatsiya_cmd(update, context)
    elif text == "🗑 Tozala":
        await tozala(update, context)
    elif user_state.get(chat_id) == "adding_task_label":
        user_state[chat_id] = "adding_task_time:" + text
        await update.message.reply_text("🕐 *Vaqt qo'shmoqchimisiz?*", parse_mode="MarkdownV2", reply_markup=VAQT_KEYBOARD)
    elif user_state.get(chat_id, "").startswith("adding_task_time:"):
        label = user_state[chat_id].replace("adding_task_time:", "")
        if text == "⏭ Shartmas":
            data = load_data()
            task = {"id": len(data["tasks"]) + 1, "time": "--:--", "label": label, "done": False, "no_time": True}
            data["tasks"].append(task)
            save_data(data)
            user_state[chat_id] = None
            await update.message.reply_text("✅ Vazifa qo'shildi\\!\n\n📌 *{}* \\(vaqtsiz\\)".format(escape_md(label)), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        elif text == "⏰ Vaqt qosham":
            user_state[chat_id] = "entering_time:" + label
            await update.message.reply_text("⏰ *Vaqtni yozing* \\(masalan `09:00`\\):", parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        else:
            await update.message.reply_text("Iltimos tugmani bosing:", reply_markup=VAQT_KEYBOARD)
    elif user_state.get(chat_id, "").startswith("entering_time:"):
        label = user_state[chat_id].replace("entering_time:", "")
        try:
            datetime.strptime(text.strip(), "%H:%M")
            data = load_data()
            task = {"id": len(data["tasks"]) + 1, "time": text.strip(), "label": label, "done": False, "no_time": False}
            data["tasks"].append(task)
            data["tasks"].sort(key=lambda x: x["time"])
            save_data(data)
            user_state[chat_id] = None
            await update.message.reply_text("✅ Vazifa qo'shildi\\!\n\n⏰ `{}` — *{}*".format(text.strip(), escape_md(label)), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        except ValueError:
            await update.message.reply_text("❌ _Vaqt formati noto'g'ri\\. Qaytadan yozing_ \\(misol: `09:00`\\):", parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
    elif user_state.get(chat_id) == "adding_tomorrow":
        if text.lower() in ["tayyor", "boldi", "hammasi"]:
            user_state[chat_id] = None
            data = load_data()
            data["tasks"] = data.get("tomorrow_tasks", [])
            data["tomorrow_tasks"] = []
            save_data(data)
            await update.message.reply_text("✅ *{} ta vazifa saqlandi\\!*\n\n🌙 _Yaxshi tun\\!_".format(len(data["tasks"])), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
        else:
            parts = text.strip().split(" ", 1)
            try:
                datetime.strptime(parts[0], "%H:%M")
                vaqt = parts[0]
                label = parts[1] if len(parts) > 1 else "Vazifa"
                no_time = False
            except (ValueError, IndexError):
                vaqt = "--:--"
                label = text
                no_time = True
            data = load_data()
            if "tomorrow_tasks" not in data:
                data["tomorrow_tasks"] = []
            data["tomorrow_tasks"].append({"id": len(data["tomorrow_tasks"]) + 1, "time": vaqt, "label": label, "done": False, "no_time": no_time})
            save_data(data)
            vaqt_str = "" if no_time else "⏰ `{}` — ".format(vaqt)
            await update.message.reply_text("➕ Qo'shildi: {}{}\n\n_Yana qo'shing yoki_ *Tayyor* _deb yozing\\._".format(vaqt_str, escape_md(label)), parse_mode="MarkdownV2", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text("📌 Quyidagi tugmalardan foydalaning:", reply_markup=MAIN_KEYBOARD)

# --- SCHEDULED JOBS ---

async def ertalab_eslatma(app):
    data = load_data()
    tasks = data.get("tasks", [])
    # Namozlarni yangidan qo'shish
    prayers = await fetch_prayer_times()
    if prayers:
        # Eski namozlarni o'chirish
        data["tasks"] = [t for t in data["tasks"] if not t.get("is_prayer")]
        for nom, emoji in zip(NAMOZ_NOMLAR, NAMOZ_EMOJIS):
            vaqt = prayers.get(nom, "00:00")
            max_id = max((t["id"] for t in data["tasks"]), default=0)
            data["tasks"].append({
                "id": max_id + 1,
                "time": vaqt,
                "label": "{} {} namozi".format(emoji, nom),
                "done": False,
                "no_time": False,
                "is_prayer": True
            })
        data["tasks"].sort(key=lambda x: x["time"])
        save_data(data)

    # Saralash xabari
    await reja_sarala(app, is_scheduled=True)

async def kechki_eslatma(app):
    user_state[CHAT_ID] = "adding_tomorrow"
    data = load_data()
    data["tomorrow_tasks"] = []
    save_data(data)
    await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
        text="🌙 *Kechqurun eslatmasi\\!*\n\nErtangi kunlik rejangizni kiriting\\.\n\n📝 Format: `09:00 Vazifa nomi`\nYoki faqat: `Vazifa nomi` \\(vaqtsiz\\)\n\n_Barcha vazifalarni kiritib bo'lgach_ *Tayyor* _deb yozing\\._")

async def vazifa_eslatmalari(app):
    now = datetime.now(TIMEZONE).strftime("%H:%M")
    data = load_data()
    tasks = data.get("tasks", [])
    changed = False
    for t in tasks:
        if not t.get("no_time") and t.get("time") == now and not t.get("done") and not t.get("reminded"):
            if t.get("is_prayer"):
                nom = t["label"]
                nom_esc = escape_md(nom)
                await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
                    text="🕌 *Namoz vaqti\\!*\n\n*{}* — `{}`\n\n_Alloh qabul qilsin\\!_".format(nom_esc, t["time"]))
            else:
                label_esc = escape_md(t["label"])
                await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
                    text="⏰ *Vaqt keldi\\!*\n\n📌 `{}` — *{}*\n\n{}\n\n_Bajargach_ ✅ *Bajardim* _tugmasini bosing\\!_".format(t["time"], label_esc, motivatsiya()))
            t["reminded"] = True
            changed = True
    if changed:
        save_data(data)

async def avto_motivatsiya(app):
    await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
        text="💪 *Kunlik rag'bat\\!*\n\n{}".format(motivatsiya()))

async def dangasa_tekshirish(app):
    now = datetime.now(TIMEZONE)
    if now.hour < 9 or now.hour > 22:
        return
    data = load_data()
    undone = [t for t in data.get("tasks", []) if not t.get("done") and not t.get("is_prayer")]
    if len(undone) >= 2:
        await app.bot.send_message(chat_id=CHAT_ID, parse_mode="MarkdownV2",
            text="🔔 *Eslatma\\!*\n\nHali *{} ta* vazifa bajarilmagan\\.\n\n{}\n\n_Hoziroq boshlang\\!_ 🚀".format(len(undone), motivatsiya()))

async def kechki_tahlil(app):
    data = load_data()
    tasks = [t for t in data.get("tasks", []) if not t.get("is_prayer")]
    prayers = [t for t in data.get("tasks", []) if t.get("is_prayer")]
    if not tasks:
        return
    done = [t for t in tasks if t.get("done")]
    p_done = [t for t in prayers if t.get("done")]
    pct = round(len(done) / len(tasks) * 100) if tasks else 0
    lines = ["🌙 *Kunlik yakuniy tahlil*\n",
             "📈 Samaradorlik: *{}%*".format(pct),
             "✅ Bajarildi: *{}/{}*".format(len(done), len(tasks)),
             "🕌 Namoz: *{}/5*\n".format(len(p_done))]
    if pct == 100:
        lines.append("🏆 *Mukammal kun\\!*")
    elif pct >= 70:
        lines.append("👍 *Yaxshi natija\\!*")
    else:
        lines.append("💡 _Ertaga yangi imkoniyat\\!_")
    lines.append("\n📅 _Ertangi rejalaringiz uchun 21:00 da yana yozaman\\!_")
    await app.bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="MarkdownV2")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reja", reja_korsatish))
    app.add_handler(CommandHandler("qosh", qosh))
    app.add_handler(CommandHandler("bajardim", bajardim))
    app.add_handler(CommandHandler("tahlil", tahlil))
    app.add_handler(CommandHandler("motivatsiya", motivatsiya_cmd))
    app.add_handler(CommandHandler("tozala", tozala))
    app.add_handler(CommandHandler("namoz", namoz_vaqtlari))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    scheduler = AsyncIOScheduler(timezone=TIMEZONE)
    scheduler.add_job(ertalab_eslatma, "cron", hour=7, minute=0, args=[app])
    scheduler.add_job(kechki_eslatma, "cron", hour=21, minute=0, args=[app])
    scheduler.add_job(vazifa_eslatmalari, "cron", minute="*", args=[app])
    scheduler.add_job(dangasa_tekshirish, "cron", hour="10,14,18", minute=0, args=[app])
    scheduler.add_job(kechki_tahlil, "cron", hour=22, minute=0, args=[app])
    scheduler.add_job(avto_motivatsiya, "cron", hour=9, minute=0, args=[app])
    scheduler.add_job(avto_motivatsiya, "cron", hour=13, minute=0, args=[app])
    scheduler.add_job(avto_motivatsiya, "cron", hour=19, minute=0, args=[app])
    scheduler.start()

    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
