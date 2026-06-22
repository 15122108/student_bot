"""
🎓 TALABA AI BOT — Balans tizimi + Haqiqiy PowerPoint generatsiya
Har bir ish = 5000 so'm (balansdan yechiladi)
To'lov: Kartaga o'tkazma + chek + Admin tasdiqlaydi
"""

import asyncio
import logging
import json
import os
import re
import httpx
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from pptx_generator import create_presentation
from data_store import (
    load_data, save_data, get_user, save_user,
    approve_topup as _approve_topup, reject_topup as _reject_topup
)

# ══════════════════════════════════════════
#  CONFIG — Environment Variables orqali olinadi
#  (Render/Railway'da "Environment" bo'limida qo'shiladi,
#   localhost'da sinash uchun pastdagi os.environ.get(...) ichidagi
#   ikkinchi qiymatni vaqtincha to'ldirishingiz mumkin)
# ══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "YOUR_ANTHROPIC_API_KEY")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))
CARD_NUMBER = os.environ.get("CARD_NUMBER", "8600 1234 5678 9012")
CARD_OWNER = os.environ.get("CARD_OWNER", "ISMINGIZ FAMILIYANGIZ")
PRICE_PER_TASK = int(os.environ.get("PRICE_PER_TASK", "5000"))
WEBAPP_URL = os.environ.get("WEBAPP_URL", "https://YOUR_DOMAIN.com/webapp/")
# ══════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TMP_DIR = "tmp_files"
os.makedirs(TMP_DIR, exist_ok=True)

def lang(uid):
    return get_user(uid).get("lang", "uz")

def fmt(n):
    return f"{n:,}".replace(",", " ")

# ── AI API calls ───────────────────────────
async def ask_claude(system_prompt: str, user_message: str, history: list = None) -> str:
    messages = []
    if history:
        for h in history[-6:]:
            messages.append(h)
    messages.append({"role": "user", "content": user_message})

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 2000,
                "system": system_prompt,
                "messages": messages
            }
        )
        result = resp.json()
        if "content" in result:
            return result["content"][0]["text"]
        logger.error(f"API error: {result}")
        return None

async def generate_slides_json(topic: str, num_slides: int, lang_code: str) -> dict:
    """AI dan slayd tarkibini JSON formatda olish"""
    lang_name = "o'zbek" if lang_code == "uz" else "rus"
    system = f"""Sen prezentatsiya tarkibi yaratuvchi AI san. Faqat JSON formatda javob ber, boshqa hech narsa yozma — preambula yo'q, markdown belgilar (```json) yo'q, faqat toza JSON.

Talab qilingan format:
{{
  "title": "Prezentatsiya nomi",
  "subtitle": "Qisqa tavsif (5-8 so'z)",
  "slides": [
    {{"heading": "Slayd sarlavhasi", "bullets": ["nuqta 1", "nuqta 2", "nuqta 3"]}},
    ...
  ],
  "conclusion": {{"heading": "Xulosa", "bullets": ["xulosa nuqtasi 1", "xulosa nuqtasi 2", "xulosa nuqtasi 3"]}}
}}

Qoidalar:
- Aniq {num_slides} ta "slides" elementi bo'lsin (title va conclusion bundan tashqari)
- Har bir slayd uchun 3-4 ta bullet, har biri 5-15 so'z
- Mazmun {lang_name} tilida, ANIQ va FAKTGA ASOSLANGAN bo'lsin
- Agar mavzu haqida ishonchli ma'lumotga ega bo'lmasang, umumiy va to'g'ri ma'lumot ber, hech narsani to'qima
- Mantiqiy ketma-ketlik: kirish → asosiy qismlar → amaliy/yakuniy qism
"""
    raw = await ask_claude(system, f"Mavzu: {topic}\nSlaydlar soni: {num_slides}")
    if raw is None:
        return None
    # Clean potential markdown fences
    raw = re.sub(r'^```json\s*|\s*```$', '', raw.strip())
    raw = re.sub(r'^```\s*|\s*```$', '', raw.strip())
    try:
        return json.loads(raw)
    except Exception as e:
        logger.error(f"JSON parse error: {e}, raw: {raw[:500]}")
        return None

async def read_receipt_image(file_bytes: bytes) -> str:
    import base64
    b64 = base64.b64encode(file_bytes).decode("utf-8")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 500,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                        {"type": "text", "text": (
                            "Bu to'lov cheki rasmi. Quyidagi ma'lumotlarni JSON formatda chiqar, boshqa hech narsa yozma:\n"
                            '{"summa": <raqam yoki null>, "sana": "<sana yoki null>", "karta_oxiri": "<oxirgi 4 raqam yoki null>", "vaqt": "<vaqt yoki null>"}\n'
                            "Agar bu chek emasligini aniqlasang yoki o'qiy olmasang, hammasini null qil."
                        )}
                    ]
                }]
            }
        )
        result = resp.json()
        if "content" in result:
            return result["content"][0]["text"]
        return None

# ── System prompt (faqat o'quv mavzulari) ─
SYSTEM_BASE = """Sen faqat O'QUV/TA'LIM mavzulari bo'yicha yordam beruvchi qattiq cheklangan AI yordamchisan.
Faqat shu mavzularda javob ber: maktab/universitet fanlari, matematika, fizika, kimyo, biologiya, tarix,
geografiya, tilshunoslik, dasturlash, adabiyot, referat/esse yozish, test/konspekt.

QATTIQ QOIDALAR:
1. Agar savol o'qish bilan bog'liq bo'lmasa — javob berma, "Bu mavzu o'quv yordamchisi doirasidan tashqarida" deb yoz.
2. HECH QACHON noaniq yoki o'zing bilmagan faktni to'qima. Ishonchli bo'lmasang: "Bu haqda aniq ma'lumotim yo'q, ishonchli manbadan tekshiring" deb yoz.
3. Qaysi tilda savol berilsa o'sha tilda javob ber (o'zbek yoki rus).
4. Aniq, tushunarli va TO'LIQ javob ber.
5. Matematik formulalarni TO'G'RI yoz, hisobni QAYTA TEKSHIR.
"""

MODE_PROMPTS = {
    "ai_free": {"uz": "🤖 Xohlagan o'quv savolingizni yozing:", "ru": "🤖 Напишите учебный вопрос:", "system": SYSTEM_BASE},
    "ai_essay": {
        "uz": "📝 Referat/esse mavzusini yozing:\n\nMasalan: *'Globallashuv va uning oqibatlari'*",
        "ru": "📝 Напишите тему реферата:\n\nНапример: *'Глобализация и её последствия'*",
        "system": SYSTEM_BASE + "\n\nReferat: 1.KIRISH 2.ASOSIY QISM (kichik bo'limlar bilan) 3.XULOSA 4.ADABIYOTLAR tuzilmasida yoz."
    },
    "ai_math": {
        "uz": "🧮 Masalangizni yozing:\n\nMasalan: *'2x + 5 = 15, x=?'*",
        "ru": "🧮 Напишите задачу:\n\nНапример: *'2x + 5 = 15, x=?'*",
        "system": SYSTEM_BASE + "\n\nMasala yechishda: 1.Berilganlar 2.Formula 3.Qadamba-qadam yechim 4.Aniq javob. Hisobni IKKI MARTA tekshir."
    },
    "ai_translate": {
        "uz": "🌐 Tarjima qilinadigan matnni va tilni yozing:\n\nMasalan: *'Hello world — o'zbekchaga'*",
        "ru": "🌐 Отправьте текст и язык перевода:\n\nНапример: *'Hello world — на русский'*",
        "system": SYSTEM_BASE + "\n\nTarjima: faqat aniq, grammatik to'g'ri tarjima ber."
    },
    "ai_konspekt": {
        "uz": "📋 Konspekt mavzusini yozing:\n\nMasalan: *'Fotosintez jarayoni'*",
        "ru": "📋 Напишите тему конспекта:\n\nНапример: *'Процесс фотосинтеза'*",
        "system": SYSTEM_BASE + "\n\nKonspekt: 🔑 Asosiy tushunchalar, 📌 Muhim faktlar, 📐 Formulalar, ✅ Eslab qolish kerak bo'limlari bilan."
    },
    "ai_quiz": {
        "uz": "🧪 Test mavzusini yozing:\n\nMasalan: *'Ikkinchi jahon urushi — 10 ta test'*",
        "ru": "🧪 Напишите тему теста:\n\nНапример: *'Вторая мировая — 10 вопросов'*",
        "system": SYSTEM_BASE + "\n\nTest: har savol uchun A)B)C)D) variant + ✅ to'g'ri javob ko'rsat."
    },
    "ai_code": {
        "uz": "💻 Kod topshirig'ini yozing:\n\nMasalan: *'Python kalkulyator yoz'*",
        "ru": "💻 Напишите задание для кода:\n\nНапример: *'Калькулятор на Python'*",
        "system": SYSTEM_BASE + "\n\nKod: ``` blokida, izohlar bilan, ishlatish yo'riqnomasi bilan yoz."
    },
}

SLIDE_COUNT_OPTIONS = [5, 8, 10, 12, 15, 20]
TOPUP_AMOUNTS = [5000, 10000, 20000, 50000, 100000, 200000]

# ── Keyboards ─────────────────────────────
def main_kb(uid):
    L = lang(uid)
    uz = L == "uz"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Prezentatsiya (PPTX)" if uz else "📊 Презентация (PPTX)", callback_data="ai_presentation")],
        [InlineKeyboardButton("🤖 AI Yordamchi" if uz else "🤖 ИИ Помощник", callback_data="ai_free")],
        [
            InlineKeyboardButton("📝 Referat/Esse" if uz else "📝 Реферат/Эссе", callback_data="ai_essay"),
            InlineKeyboardButton("🧮 Masala yechish" if uz else "🧮 Решить задачу", callback_data="ai_math"),
        ],
        [
            InlineKeyboardButton("🌐 Tarjima" if uz else "🌐 Перевод", callback_data="ai_translate"),
            InlineKeyboardButton("📋 Konspekt" if uz else "📋 Конспект", callback_data="ai_konspekt"),
        ],
        [
            InlineKeyboardButton("🧪 Test yaratish" if uz else "🧪 Создать тест", callback_data="ai_quiz"),
            InlineKeyboardButton("💻 Kod yozish" if uz else "💻 Написать код", callback_data="ai_code"),
        ],
        [InlineKeyboardButton("💰 Balans" if uz else "💰 Баланс", callback_data="balance")],
        [InlineKeyboardButton("🌐 " + ("Русский" if uz else "O'zbek"), callback_data="switch_lang")],
    ])

def back_kb(uid, cb="main_menu"):
    L = lang(uid)
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga" if L == "uz" else "⬅️ Назад", callback_data=cb)]])

def balance_kb(uid):
    L = lang(uid)
    uz = L == "uz"
    rows = []
    for i in range(0, len(TOPUP_AMOUNTS), 2):
        row = [InlineKeyboardButton(f"{fmt(TOPUP_AMOUNTS[i])} so'm", callback_data=f"topup_{TOPUP_AMOUNTS[i]}")]
        if i+1 < len(TOPUP_AMOUNTS):
            row.append(InlineKeyboardButton(f"{fmt(TOPUP_AMOUNTS[i+1])} so'm", callback_data=f"topup_{TOPUP_AMOUNTS[i+1]}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Orqaga" if uz else "⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

def slide_count_kb(uid):
    L = lang(uid)
    uz = L == "uz"
    rows = []
    for i in range(0, len(SLIDE_COUNT_OPTIONS), 3):
        row = [InlineKeyboardButton(f"{n} ta" if uz else f"{n} шт", callback_data=f"slidecount_{n}")
               for n in SLIDE_COUNT_OPTIONS[i:i+3]]
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ Orqaga" if uz else "⬅️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)

# ══════════════════════════════════════════
#  HANDLERS
# ══════════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    get_user(u.id, u.username, u.first_name)
    L = lang(u.id)
    uz = L == "uz"
    display_name = u.first_name or (f"@{u.username}" if u.username else "")
    greeting = f"Assalomu alaykum, {display_name}!" if uz else f"Здравствуйте, {display_name}!"
    text = (
        f"👋 *{greeting}*\n"
        "Men sizning AI talaba yordamchingizman!\n\n"
        "🎓 Men qila oladigan ishlar:\n"
        "• 📊 *Haqiqiy PowerPoint (.pptx)* prezentatsiya yaratish\n"
        "• 📝 Referat va esse yozish\n• 🧮 Masala yechish\n• 🌐 Tarjima\n"
        "• 📋 Konspekt\n• 🧪 Test yaratish\n• 💻 Kod yozish\n\n"
        "⚠️ *Eslatma:* Men faqat o'quv mavzulari bo'yicha yordam beraman.\n\n"
        "👇 Quyidan tanlang, yoki pastdagi *Menyu* tugmasidan tezkor buyruqlardan foydalaning:"
    ) if uz else (
        f"👋 *{greeting}*\n"
        "Я ваш AI учебный помощник!\n\n"
        "🎓 Что я умею:\n"
        "• 📊 Создавать настоящие *PowerPoint (.pptx)* презентации\n"
        "• 📝 Писать рефераты\n• 🧮 Решать задачи\n• 🌐 Переводить\n"
        "• 📋 Конспекты\n• 🧪 Создавать тесты\n• 💻 Писать код\n\n"
        "⚠️ *Важно:* Я помогаю только по учебным темам.\n\n"
        "👇 Выберите ниже, или используйте кнопку *Меню* внизу для быстрых команд:"
    )
    await update.message.reply_text(text, reply_markup=main_kb(u.id), parse_mode="Markdown")

# ── Tezkor buyruqlar (Menyu tugmasidan) ───
async def _start_text_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, mode_key: str):
    """Matnli AI rejimini to'g'ridan-to'g'ri buyruq orqali boshlash (masalan /referat)."""
    uid = update.effective_user.id
    L = lang(uid)
    uz = L == "uz"
    ud = get_user(uid)
    bal = ud.get("balance", 0)
    if bal < PRICE_PER_TASK:
        text_err = f"❌ *Balansingiz yetarli emas!*\n\n💰 Mavjud: {fmt(bal)} so'm\n💲 Kerak: {fmt(PRICE_PER_TASK)} so'm" if uz else \
                   f"❌ *Недостаточно баланса!*\n\n💰 Доступно: {fmt(bal)} сум\n💲 Нужно: {fmt(PRICE_PER_TASK)} сум"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💰 Balans" if uz else "💰 Баланс", callback_data="balance")]])
        await update.message.reply_text(text_err, reply_markup=kb, parse_mode="Markdown")
        return
    ud["mode"] = mode_key
    ud["history"] = []
    save_user(uid, ud)
    mode = MODE_PROMPTS[mode_key]
    prompt = mode["uz"] if uz else mode["ru"]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Menyu" if uz else "⬅️ Меню", callback_data="main_menu")]])
    note = f"\n\n💰 Balans: {fmt(bal)} so'm (1 ish = {fmt(PRICE_PER_TASK)} so'm)" if uz else \
           f"\n\n💰 Баланс: {fmt(bal)} сум (1 работа = {fmt(PRICE_PER_TASK)} сум)"
    await update.message.reply_text(f"{prompt}{note}", reply_markup=kb, parse_mode="Markdown")

async def cmd_presentation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    L = lang(uid)
    uz = L == "uz"
    ud = get_user(uid)
    bal = ud.get("balance", 0)
    if bal < PRICE_PER_TASK:
        text_err = f"❌ *Balansingiz yetarli emas!*\n\n💰 Mavjud: {fmt(bal)} so'm\n💲 Kerak: {fmt(PRICE_PER_TASK)} so'm" if uz else \
                   f"❌ *Недостаточно баланса!*\n\n💰 Доступно: {fmt(bal)} сум\n💲 Нужно: {fmt(PRICE_PER_TASK)} сум"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💰 Balans" if uz else "💰 Баланс", callback_data="balance")]])
        await update.message.reply_text(text_err, reply_markup=kb, parse_mode="Markdown")
        return
    ud["mode"] = "waiting_pptx_topic"
    save_user(uid, ud)
    text = (
        f"📊 *Prezentatsiya mavzusini yozing:*\n\nMasalan: _'Sun'iy intellekt tarixi'_\n\n💰 Balans: {fmt(bal)} so'm"
    ) if uz else (
        f"📊 *Напишите тему презентации:*\n\nНапример: _'История ИИ'_\n\n💰 Баланс: {fmt(bal)} сум"
    )
    await update.message.reply_text(text, reply_markup=back_kb(uid), parse_mode="Markdown")

async def cmd_essay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_text_mode(update, context, "ai_essay")

async def cmd_math(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_text_mode(update, context, "ai_math")

async def cmd_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_text_mode(update, context, "ai_translate")

async def cmd_konspekt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_text_mode(update, context, "ai_konspekt")

async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_text_mode(update, context, "ai_quiz")

async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_text_mode(update, context, "ai_code")

async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _start_text_mode(update, context, "ai_free")

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    L = lang(uid)
    uz = L == "uz"
    ud = get_user(uid)
    bal = ud.get("balance", 0)
    spent = ud.get("total_spent", 0)
    text = (
        f"💰 *Balansingiz*\n\n💵 Mavjud: *{fmt(bal)} so'm*\n📊 Jami sarflangan: {fmt(spent)} so'm\n"
        f"💲 1 ish narxi: {fmt(PRICE_PER_TASK)} so'm\n\n➕ Balansni to'ldirish uchun summani tanlang:"
    ) if uz else (
        f"💰 *Ваш баланс*\n\n💵 Доступно: *{fmt(bal)} сум*\n📊 Всего потрачено: {fmt(spent)} сум\n"
        f"💲 Цена за работу: {fmt(PRICE_PER_TASK)} сум\n\n➕ Выберите сумму пополнения:"
    )
    await update.message.reply_text(text, reply_markup=balance_kb(uid), parse_mode="Markdown")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data
    L = lang(uid)
    uz = L == "uz"
    ud = get_user(uid)

    if data == "main_menu":
        text = "🎓 *Asosiy menyu:*" if uz else "🎓 *Главное меню:*"
        await query.edit_message_text(text, reply_markup=main_kb(uid), parse_mode="Markdown")
        return

    if data == "switch_lang":
        ud["lang"] = "ru" if L == "uz" else "uz"
        ud["history"] = []
        save_user(uid, ud)
        msg = "✅ Til o'zbek tiliga o'zgartirildi!" if ud["lang"] == "uz" else "✅ Язык изменён на русский!"
        await query.edit_message_text(msg, reply_markup=main_kb(uid))
        return

    if data == "balance":
        bal = ud.get("balance", 0)
        spent = ud.get("total_spent", 0)
        text = (
            f"💰 *Balansingiz*\n\n💵 Mavjud: *{fmt(bal)} so'm*\n📊 Jami sarflangan: {fmt(spent)} so'm\n"
            f"💲 1 ish narxi: {fmt(PRICE_PER_TASK)} so'm\n\n➕ Balansni to'ldirish uchun summani tanlang:"
        ) if uz else (
            f"💰 *Ваш баланс*\n\n💵 Доступно: *{fmt(bal)} сум*\n📊 Всего потрачено: {fmt(spent)} сум\n"
            f"💲 Цена за работу: {fmt(PRICE_PER_TASK)} сум\n\n➕ Выберите сумму пополнения:"
        )
        await query.edit_message_text(text, reply_markup=balance_kb(uid), parse_mode="Markdown")
        return

    if data.startswith("topup_"):
        amount = int(data.split("_")[1])
        ud["pending_topup"] = amount
        save_user(uid, ud)
        text = (
            f"💳 *{fmt(amount)} so'm to'lash*\n\nQuyidagi kartaga o'tkazma qiling:\n\n"
            f"🏦 Karta: `{CARD_NUMBER}`\n👤 Egasi: {CARD_OWNER}\n💵 Summa: *{fmt(amount)} so'm*\n\n"
            f"✅ To'lov qilgach, *chek skrinshotini shu yerga yuboring*."
        ) if uz else (
            f"💳 *Оплата {fmt(amount)} сум*\n\nПереведите на карту:\n\n"
            f"🏦 Карта: `{CARD_NUMBER}`\n👤 Владелец: {CARD_OWNER}\n💵 Сумма: *{fmt(amount)} сум*\n\n"
            f"✅ После оплаты *отправьте скриншот чека сюда*."
        )
        await query.edit_message_text(text, reply_markup=back_kb(uid, "balance"), parse_mode="Markdown")
        return

    # ═══ PRESENTATION FLOW ═══
    if data == "ai_presentation":
        bal = ud.get("balance", 0)
        if bal < PRICE_PER_TASK:
            await _show_low_balance(query, uid, uz, bal)
            return
        ud["mode"] = "waiting_pptx_topic"
        save_user(uid, ud)
        text = (
            f"📊 *Prezentatsiya mavzusini yozing:*\n\nMasalan: _'Sun'iy intellekt tarixi'_\n\n💰 Balans: {fmt(bal)} so'm"
        ) if uz else (
            f"📊 *Напишите тему презентации:*\n\nНапример: _'История ИИ'_\n\n💰 Баланс: {fmt(bal)} сум"
        )
        await query.edit_message_text(text, reply_markup=back_kb(uid), parse_mode="Markdown")
        return

    if data.startswith("slidecount_"):
        n = int(data.split("_")[1])
        ud["pending_slide_count"] = n
        ud["mode"] = "generating_pptx"
        save_user(uid, ud)
        await query.edit_message_text(
            "⏳ *Prezentatsiya tayyorlanmoqda...*\n\nBu 30-60 soniya vaqt oladi." if uz else
            "⏳ *Презентация готовится...*\n\nЭто займёт 30-60 секунд.",
            parse_mode="Markdown"
        )
        await _generate_and_send_pptx(context, uid, query.message.chat_id, uz)
        return

    # AI text modes
    if data in MODE_PROMPTS:
        bal = ud.get("balance", 0)
        if bal < PRICE_PER_TASK:
            await _show_low_balance(query, uid, uz, bal)
            return
        ud["mode"] = data
        ud["history"] = []
        save_user(uid, ud)
        mode = MODE_PROMPTS[data]
        prompt = mode["uz"] if uz else mode["ru"]
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga" if uz else "⬅️ Назад", callback_data="main_menu")]])
        note = f"\n\n💰 Balans: {fmt(bal)} so'm (1 ish = {fmt(PRICE_PER_TASK)} so'm)" if uz else \
               f"\n\n💰 Баланс: {fmt(bal)} сум (1 работа = {fmt(PRICE_PER_TASK)} сум)"
        await query.edit_message_text(f"{prompt}{note}", reply_markup=kb, parse_mode="Markdown")
        return

    # ADMIN approve/reject
    if data.startswith("approve_") and uid == ADMIN_ID:
        target_uid = data.split("_")[1]
        tud_before = get_user(int(target_uid))
        t_uz = tud_before.get("lang", "uz") == "uz"
        amount = _approve_topup(int(target_uid))
        if amount:
            tud = get_user(int(target_uid))
            await context.bot.send_message(
                int(target_uid),
                f"✅ *To'lovingiz tasdiqlandi!*\n\n💰 +{fmt(amount)} so'm\n💵 Yangi balans: {fmt(tud['balance'])} so'm" if t_uz else
                f"✅ *Ваш платёж подтверждён!*\n\n💰 +{fmt(amount)} сум\n💵 Новый баланс: {fmt(tud['balance'])} сум",
                parse_mode="Markdown"
            )
            try:
                await query.edit_message_caption(caption=(query.message.caption or "") + "\n\n✅ TASDIQLANDI")
            except Exception:
                pass
        return

    if data.startswith("reject_") and uid == ADMIN_ID:
        target_uid = data.split("_")[1]
        tud = get_user(int(target_uid))
        t_uz = tud.get("lang", "uz") == "uz"
        _reject_topup(int(target_uid))
        await context.bot.send_message(
            int(target_uid),
            "❌ To'lovingiz tasdiqlanmadi. Qaytadan urinib ko'ring yoki admin bilan bog'laning." if t_uz else
            "❌ Ваш платёж не подтверждён. Попробуйте снова или свяжитесь с админом."
        )
        try:
            await query.edit_message_caption(caption=(query.message.caption or "") + "\n\n❌ RAD ETILDI")
        except Exception:
            pass
        return

async def _show_low_balance(query, uid, uz, bal):
    text = (
        f"❌ *Balansingiz yetarli emas!*\n\n💰 Mavjud: {fmt(bal)} so'm\n💲 Kerak: {fmt(PRICE_PER_TASK)} so'm\n\n➕ Balansni to'ldiring."
    ) if uz else (
        f"❌ *Недостаточно баланса!*\n\n💰 Доступно: {fmt(bal)} сум\n💲 Нужно: {fmt(PRICE_PER_TASK)} сум\n\n➕ Пополните баланс."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 " + ("Balansni to'ldirish" if uz else "Пополнить баланс"), callback_data="balance")],
        [InlineKeyboardButton("⬅️ Orqaga" if uz else "⬅️ Назад", callback_data="main_menu")],
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")

async def _generate_and_send_pptx(context, uid, chat_id, uz):
    ud = get_user(uid)
    topic = ud.get("pending_pptx_topic", "Mavzu")
    n_slides = ud.get("pending_slide_count", 10)
    bal = ud.get("balance", 0)

    if bal < PRICE_PER_TASK:
        await context.bot.send_message(chat_id, "❌ Balans yetarli emas." if uz else "❌ Недостаточно баланса.")
        return

    slides_json = await generate_slides_json(topic, n_slides, "uz" if uz else "ru")

    if not slides_json or "slides" not in slides_json:
        await context.bot.send_message(
            chat_id,
            "❌ Prezentatsiya yaratishda xatolik. Pul yechilmadi, qaytadan urinib ko'ring." if uz else
            "❌ Ошибка при создании презентации. Деньги не списаны, попробуйте снова.",
            reply_markup=main_kb(uid)
        )
        return

    try:
        slides_data = [{"subtitle": slides_json.get("subtitle", "Taqdimot")}]
        for s in slides_json["slides"]:
            slides_data.append({"heading": s["heading"], "bullets": s["bullets"]})
        if "conclusion" in slides_json:
            slides_data.append({"heading": slides_json["conclusion"]["heading"], "bullets": slides_json["conclusion"]["bullets"]})

        safe_topic = re.sub(r'[^\w\s-]', '', topic).strip().replace(' ', '_')[:40]
        filename = f"{TMP_DIR}/{safe_topic}_{uid}_{int(datetime.now().timestamp())}.pptx"
        create_presentation(slides_json.get("title", topic), slides_data, filename)

        # Charge balance only on success
        ud["balance"] = bal - PRICE_PER_TASK
        ud["total_spent"] = ud.get("total_spent", 0) + PRICE_PER_TASK
        ud["mode"] = None
        ud["pending_pptx_topic"] = None
        save_user(uid, ud)

        caption = (
            f"🎉 *Taqdimotingiz tayyor!*\n\n📌 Mavzu: _{topic}_\n📊 Slaydlar: {n_slides} ta\n"
            f"💳 To'langan: {fmt(PRICE_PER_TASK)} so'm\n💵 Qoldi: {fmt(ud['balance'])} so'm\n\nYuklab oling va tahrirlang. Omad! 🚀"
        ) if uz else (
            f"🎉 *Ваша презентация готова!*\n\n📌 Тема: _{topic}_\n📊 Слайдов: {n_slides}\n"
            f"💳 Оплачено: {fmt(PRICE_PER_TASK)} сум\n💵 Осталось: {fmt(ud['balance'])} сум\n\nСкачайте и редактируйте. Удачи! 🚀"
        )
        with open(filename, "rb") as f:
            await context.bot.send_document(chat_id, document=f, filename=os.path.basename(filename),
                                              caption=caption, parse_mode="Markdown",
                                              reply_markup=main_kb(uid))
        os.remove(filename)
    except Exception as e:
        logger.error(f"PPTX generation error: {e}")
        await context.bot.send_message(
            chat_id,
            "❌ Fayl yaratishda xatolik. Pul yechilmadi." if uz else "❌ Ошибка создания файла. Деньги не списаны.",
            reply_markup=main_kb(uid)
        )

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    L = lang(uid)
    uz = L == "uz"
    ud = get_user(uid)

    pending = ud.get("pending_topup")
    if not pending:
        await update.message.reply_text(
            "ℹ️ Avval 💰 Balans bo'limidan summa tanlang." if uz else "ℹ️ Сначала выберите сумму в разделе 💰 Баланс."
        )
        return

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()

    thinking = await update.message.reply_text("⏳ Chek tekshirilmoqda..." if uz else "⏳ Проверяю чек...")
    try:
        receipt_info = await read_receipt_image(bytes(file_bytes))
    except Exception:
        receipt_info = "AI o'qiy olmadi"
    await thinking.delete()

    # Save receipt details so the web admin panel can show them too
    ud["pending_receipt_file_id"] = photo.file_id
    ud["pending_receipt_info"] = receipt_info
    ud["pending_topup_time"] = datetime.now().isoformat()
    save_user(uid, ud)

    username = f"@{ud.get('username')}" if ud.get('username') else ud.get('first_name', "Noma'lum")

    await update.message.reply_text(
        f"✅ *Chekingiz qabul qilindi!*\n\n💰 Summa: {fmt(pending)} so'm\n⏳ Admin tasdiqlashini kuting (5-30 daqiqa)." if uz else
        f"✅ *Чек принят!*\n\n💰 Сумма: {fmt(pending)} сум\n⏳ Ожидайте подтверждения админа (5-30 минут).",
        parse_mode="Markdown"
    )

    admin_kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{uid}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{uid}"),
    ]])
    caption = (
        f"💳 *Yangi to'lov*\n\n👤 Foydalanuvchi: {username}\n🆔 ID: `{uid}`\n"
        f"💰 Talab qilingan summa: {fmt(pending)} so'm\n\n🤖 AI o'qigan ma'lumot:\n```\n{receipt_info}\n```"
    )
    await context.bot.send_photo(ADMIN_ID, photo.file_id, caption=caption, reply_markup=admin_kb, parse_mode="Markdown")

async def webapp_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mini App (Web App) dan kelgan buyurtmani qabul qilish va bajarish."""
    uid = update.effective_user.id
    L = lang(uid)
    uz = L == "uz"
    ud = get_user(uid)

    try:
        payload = json.loads(update.effective_message.web_app_data.data)
    except Exception:
        await update.message.reply_text(
            "❌ Ma'lumotni o'qib bo'lmadi, qaytadan urinib ko'ring." if uz else
            "❌ Не удалось прочитать данные, попробуйте снова."
        )
        return

    service = payload.get("service")
    topic = (payload.get("topic") or "").strip()
    req_lang = payload.get("lang", "uz")
    if req_lang in ("uz", "ru"):
        ud["lang"] = req_lang
        uz = req_lang == "uz"
        save_user(uid, ud)

    if not topic:
        await update.message.reply_text("❌ Mavzu bo'sh." if uz else "❌ Тема пустая.")
        return

    bal = ud.get("balance", 0)
    if bal < PRICE_PER_TASK:
        await _show_low_balance_msg(update, uid, uz, bal)
        return

    service_to_mode = {
        "essay": "ai_essay", "math": "ai_math", "translate": "ai_translate",
        "konspekt": "ai_konspekt", "quiz": "ai_quiz", "code": "ai_code", "ask": "ai_free",
    }

    if service == "presentation":
        n_slides = int(payload.get("slideCount") or 10)
        ud["pending_pptx_topic"] = topic
        ud["pending_slide_count"] = n_slides
        save_user(uid, ud)
        await update.message.reply_text(
            f"📊 *'{topic}'*\n⏳ Prezentatsiya tayyorlanmoqda ({n_slides} ta slayd)..." if uz else
            f"📊 *'{topic}'*\n⏳ Презентация готовится ({n_slides} слайдов)...",
            parse_mode="Markdown"
        )
        await _generate_and_send_pptx(context, uid, update.effective_chat.id, uz)
        return

    mode_key = service_to_mode.get(service)
    if not mode_key:
        await update.message.reply_text("❌ Noma'lum xizmat turi." if uz else "❌ Неизвестный тип услуги.")
        return

    mode = MODE_PROMPTS[mode_key]
    system = mode["system"]
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    thinking = await update.message.reply_text("⏳ *Javob tayyorlanmoqda...*" if uz else "⏳ *Готовлю ответ...*", parse_mode="Markdown")

    try:
        history = []
        answer = await ask_claude(system, topic, history)
        if answer is None:
            await thinking.delete()
            await update.message.reply_text(
                "❌ AI xizmati hozir ishlamayapti. Pul yechilmadi." if uz else "❌ AI сервис не работает. Деньги не списаны.",
                reply_markup=main_kb(uid)
            )
            return

        ud["balance"] = bal - PRICE_PER_TASK
        ud["total_spent"] = ud.get("total_spent", 0) + PRICE_PER_TASK
        ud["history"] = [{"role": "user", "content": topic}, {"role": "assistant", "content": answer}]
        ud["mode"] = mode_key
        save_user(uid, ud)

        await thinking.delete()
        footer = f"\n\n💰 Yechildi: {fmt(PRICE_PER_TASK)} so'm | Qoldi: {fmt(ud['balance'])} so'm" if uz else \
                 f"\n\n💰 Списано: {fmt(PRICE_PER_TASK)} сум | Осталось: {fmt(ud['balance'])} сум"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 " + ("Yana" if uz else "Ещё"), callback_data=mode_key)],
            [InlineKeyboardButton("🏠 Menyu" if uz else "🏠 Меню", callback_data="main_menu")],
        ])
        MAX_LEN = 3800
        full_answer = answer + footer
        if len(full_answer) > MAX_LEN:
            parts = [answer[i:i+MAX_LEN] for i in range(0, len(answer), MAX_LEN)]
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    await update.message.reply_text(part + footer, reply_markup=kb, parse_mode="Markdown")
                else:
                    await update.message.reply_text(part, parse_mode="Markdown")
        else:
            await update.message.reply_text(full_answer, reply_markup=kb, parse_mode="Markdown")
    except Exception as e:
        await thinking.delete()
        logger.error(f"WebApp data error: {e}")
        await update.message.reply_text(
            "❌ Xatolik yuz berdi. Pul yechilmadi." if uz else "❌ Произошла ошибка. Деньги не списаны.",
            reply_markup=main_kb(uid)
        )

async def _show_low_balance_msg(update, uid, uz, bal):
    text_err = f"❌ *Balansingiz yetarli emas!*\n\n💰 Mavjud: {fmt(bal)} so'm\n💲 Kerak: {fmt(PRICE_PER_TASK)} so'm" if uz else \
               f"❌ *Недостаточно баланса!*\n\n💰 Доступно: {fmt(bal)} сум\n💲 Нужно: {fmt(PRICE_PER_TASK)} сум"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("💰 Balans" if uz else "💰 Баланс", callback_data="balance")]])
    await update.message.reply_text(text_err, reply_markup=kb, parse_mode="Markdown")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    L = lang(uid)
    uz = L == "uz"
    text = update.message.text.strip()
    ud = get_user(uid)

    mode_key = ud.get("mode")

    # PPTX topic input
    if mode_key == "waiting_pptx_topic":
        ud["pending_pptx_topic"] = text
        ud["mode"] = None
        save_user(uid, ud)
        msg = f"📊 *'{text}'*\n\n🔢 Nechta slayd bo'lsin?" if uz else f"📊 *'{text}'*\n\n🔢 Сколько слайдов?"
        await update.message.reply_text(msg, reply_markup=slide_count_kb(uid), parse_mode="Markdown")
        return

    if not mode_key or mode_key not in MODE_PROMPTS:
        await update.message.reply_text(
            "🎓 Iltimos menyudan funksiyani tanlang:" if uz else "🎓 Пожалуйста выберите функцию из меню:",
            reply_markup=main_kb(uid)
        )
        return

    bal = ud.get("balance", 0)
    if bal < PRICE_PER_TASK:
        text_err = f"❌ *Balansingiz yetarli emas!*\n\n💰 Mavjud: {fmt(bal)} so'm\n💲 Kerak: {fmt(PRICE_PER_TASK)} so'm" if uz else \
                   f"❌ *Недостаточно баланса!*\n\n💰 Доступно: {fmt(bal)} сум\n💲 Нужно: {fmt(PRICE_PER_TASK)} сум"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("💰 Balans" if uz else "💰 Баланс", callback_data="balance")]])
        await update.message.reply_text(text_err, reply_markup=kb, parse_mode="Markdown")
        return

    mode = MODE_PROMPTS[mode_key]
    system = mode["system"]

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    thinking = await update.message.reply_text("⏳ *Javob tayyorlanmoqda...*" if uz else "⏳ *Готовлю ответ...*", parse_mode="Markdown")

    try:
        history = ud.get("history", [])
        answer = await ask_claude(system, text, history)

        if answer is None:
            await thinking.delete()
            await update.message.reply_text(
                "❌ AI xizmati hozir ishlamayapti. Pul yechilmadi, qaytadan urinib ko'ring." if uz else
                "❌ AI сервис сейчас не работает. Деньги не списаны, попробуйте снова.",
                reply_markup=main_kb(uid)
            )
            return

        ud["balance"] = bal - PRICE_PER_TASK
        ud["total_spent"] = ud.get("total_spent", 0) + PRICE_PER_TASK
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
        if len(history) > 20:
            history = history[-20:]
        ud["history"] = history
        save_user(uid, ud)

        await thinking.delete()

        footer = f"\n\n💰 Yechildi: {fmt(PRICE_PER_TASK)} so'm | Qoldi: {fmt(ud['balance'])} so'm" if uz else \
                 f"\n\n💰 Списано: {fmt(PRICE_PER_TASK)} сум | Осталось: {fmt(ud['balance'])} сум"

        MAX_LEN = 3800
        full_answer = answer + footer
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 " + ("Yana" if uz else "Ещё"), callback_data=mode_key)],
            [InlineKeyboardButton("🏠 Menyu" if uz else "🏠 Меню", callback_data="main_menu")],
        ])
        if len(full_answer) > MAX_LEN:
            parts = [answer[i:i+MAX_LEN] for i in range(0, len(answer), MAX_LEN)]
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    await update.message.reply_text(part + footer, reply_markup=kb, parse_mode="Markdown")
                else:
                    await update.message.reply_text(part, parse_mode="Markdown")
        else:
            await update.message.reply_text(full_answer, reply_markup=kb, parse_mode="Markdown")

    except Exception as e:
        await thinking.delete()
        logger.error(f"Error: {e}")
        await update.message.reply_text(
            "❌ Xatolik yuz berdi. Pul yechilmadi, qaytadan urinib ko'ring." if uz else
            "❌ Произошла ошибка. Деньги не списаны, попробуйте снова.",
            reply_markup=main_kb(uid)
        )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    data = load_data()
    total_users = len(data)
    total_balance = sum(u.get("balance", 0) for u in data.values())
    total_spent = sum(u.get("total_spent", 0) for u in data.values())
    pending = sum(1 for u in data.values() if u.get("pending_topup"))
    await update.message.reply_text(
        f"📊 *Statistika*\n\n👥 Foydalanuvchilar: {total_users}\n💰 Jami balans: {fmt(total_balance)} so'm\n"
        f"💵 Jami sarflangan: {fmt(total_spent)} so'm\n⏳ Kutilayotgan to'lovlar: {pending} ta\n\n"
        f"🌐 Admin panel: /panel buyrug'ini yuboring",
        parse_mode="Markdown"
    )

async def admin_panel_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        f"🌐 *Web Admin Panel*\n\n"
        f"Brauzerda oching:\n`http://SIZNING_SERVER_MANZILI:5000`\n\n"
        f"(Kompyuteringizda ishga tushirgan bo'lsangiz: `http://localhost:5000`)\n\n"
        f"Login va parolni `admin_panel.py` faylida sozlagansiz.",
        parse_mode="Markdown"
    )

async def _setup_bot_commands(app):
    """Telegram 'Menyu' tugmasi ostida ko'rinadigan buyruqlar ro'yxatini o'rnatadi
    va pastdagi Menu Button'ni Mini App'ga ulaydi."""
    from telegram import BotCommand, MenuButtonWebApp, WebAppInfo, MenuButtonDefault
    commands = [
        BotCommand("start", "🏠 Botni boshlash / Asosiy menyu"),
        BotCommand("prezentatsiya", "📊 PowerPoint prezentatsiya yaratish"),
        BotCommand("referat", "📝 Referat yoki esse yozish"),
        BotCommand("masala", "🧮 Masala yoki misol yechish"),
        BotCommand("tarjima", "🌐 Matnni tarjima qilish"),
        BotCommand("konspekt", "📋 Konspekt tuzish"),
        BotCommand("test", "🧪 Test savollari yaratish"),
        BotCommand("kod", "💻 Dasturlash kodini yozish"),
        BotCommand("savol", "🤖 Erkin o'quv savoli berish"),
        BotCommand("balans", "💰 Balansni ko'rish / to'ldirish"),
    ]
    await app.bot.set_my_commands(commands)

    if WEBAPP_URL and not WEBAPP_URL.startswith("https://YOUR_DOMAIN"):
        try:
            await app.bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(text="🛒 Buyurtma", web_app=WebAppInfo(url=WEBAPP_URL))
            )
            logger.info(f"Menu Button Mini App'ga ulandi: {WEBAPP_URL}")
        except Exception as e:
            logger.error(f"Menu Button sozlashda xato: {e}")
    else:
        logger.warning("WEBAPP_URL sozlanmagan — Menu Button standart holatda qoladi (faqat buyruqlar ro'yxati).")

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("panel", admin_panel_link))
    app.add_handler(CommandHandler("prezentatsiya", cmd_presentation))
    app.add_handler(CommandHandler("referat", cmd_essay))
    app.add_handler(CommandHandler("masala", cmd_math))
    app.add_handler(CommandHandler("tarjima", cmd_translate))
    app.add_handler(CommandHandler("konspekt", cmd_konspekt))
    app.add_handler(CommandHandler("test", cmd_quiz))
    app.add_handler(CommandHandler("kod", cmd_code))
    app.add_handler(CommandHandler("savol", cmd_ask))
    app.add_handler(CommandHandler("balans", cmd_balance))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, webapp_data_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.post_init = _post_init
    print("🚀 Talaba AI Bot (PPTX + balans tizimi) ishga tushdi!")
    await app.run_polling(drop_pending_updates=True)

async def _post_init(app):
    await _setup_bot_commands(app)
    asyncio.create_task(_keepalive_server())
    external_url = os.environ.get("RENDER_EXTERNAL_URL")
    if external_url:
        asyncio.create_task(_self_ping(external_url))

async def _keepalive_server():
    port = int(os.environ.get("PORT", "10000"))

    async def _handler(reader, writer):
        try:
            await reader.read(1024)
        except Exception:
            pass
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "Content-Length: 22\r\n"
            "\r\n"
            "Bot ishlamoqda \u2705"
        )
        writer.write(response.encode("utf-8"))
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(_handler, "0.0.0.0", port)
    logger.info(f"Keep-alive server {port}-portda ishga tushdi.")
    async with server:
        await server.serve_forever()

async def _self_ping(url: str):
    await asyncio.sleep(60)
    while True:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.get(url)
            logger.info("Self-ping yuborildi.")
        except Exception as e:
            logger.warning(f"Self-ping xato: {e}")
        await asyncio.sleep(600)

if __name__ == "__main__":
    asyncio.run(main())
