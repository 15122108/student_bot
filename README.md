# 🎓 TALABA AI BOT — PPTX + Balans + Admin Panel + Mini App

## 🆕 Bu versiyada nima yangi?

✅ **Telegram Mini App** — pastdagi "Menyu" tugmasi endi to'liq ekranli chiroyli sahifa ochadi
✅ Talaba u yerda: xizmat turini tanlaydi → mavzuni yozadi → (prezentatsiya bo'lsa) slayd soni va dizayn rangini tanlaydi → "Yaratish" bosadi
✅ Bot avtomatik ishlay boshlaydi — xuddi skrinshotdagi "Talaba Slide Bot" kabi tajriba

---

## 📁 Fayl tuzilmasi

```
finalbot3/
├── bot.py              # Telegram bot (asosiy)
├── admin_panel.py       # Web admin panel (to'lovlarni tasdiqlash)
├── webapp_server.py     # Mini App server (YANGI — talabalar uchun ochiq sahifa)
├── webapp/
│   └── index.html        # Mini App sahifasi (YANGI)
├── data_store.py         # Umumiy ma'lumot qatlami
├── pptx_generator.py     # PowerPoint generatsiya mexanizmi
├── requirements.txt
└── README.md
```

⚠️ Hammasi bitta papkada bo'lishi shart.

---

## ⚠️ MUHIM — Mini App uchun talab

Telegram Mini App ishlashi uchun sahifa **HTTPS bilan ochiq internetda** turishi SHART.
`http://localhost` ishlamaydi — Telegram uni rad etadi.

**Demak Mini App'ni sinab ko'rish uchun avval botni serverga joylashtirish kerak** (pastda yo'riqnoma bor).

Agar hali serverga joylashtirmagan bo'lsangiz — bot va admin panel **localhost'da ham ishlayveradi** (inline tugmalar orqali), faqat Mini App (Menyu tugmasi orqali to'liq ekranli sahifa) ishlamaydi.

---

## ⚡ Sozlash

### 1️⃣ O'rnatish
```bash
pip install -r requirements.txt
```

### 2️⃣ `bot.py` ni to'ldiring:
```python
BOT_TOKEN = "..."
ANTHROPIC_API_KEY = "..."
ADMIN_ID = 123456789
CARD_NUMBER = "8600 ..."
CARD_OWNER = "ISM FAMILIYA"
PRICE_PER_TASK = 5000
WEBAPP_URL = "https://sizning-domeningiz.com/webapp/"   # Serverga joylashtirgandan keyin to'ldirasiz
```

### 3️⃣ `admin_panel.py` ni to'ldiring:
```python
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "kuchli_parol"
SECRET_KEY = "tasodifiy_uzun_satr"
BOT_TOKEN = "..."   # bot.py dagi BIR XIL token
```

### 4️⃣ `webapp_server.py` ni to'ldiring:
```python
BOT_TOKEN = "..."   # bot.py dagi BIR XIL token
```

---

## 🚀 Localhost'da ishga tushirish (3 ta terminal)

**1-terminal — Bot:**
```bash
python bot.py
```

**2-terminal — Admin panel:**
```bash
python admin_panel.py
```
→ http://localhost:5000

**3-terminal — Mini App server:**
```bash
python webapp_server.py
```
→ http://localhost:8080/webapp/ (faqat ko'rinish uchun, Telegram ichida ishlamaydi)

> 💡 Mini App'ni **Telegram ichida sinash** uchun serverga joylashtirish va `WEBAPP_URL` ni to'ldirish kerak — pastga qarang.

---

## 🌐 Serverga joylashtirish (Mini App ishlashi uchun SHART)

### Railway.app orqali (tavsiya etiladi — bepul tarif bor)

1. **GitHub'da repository yarating**, barcha fayllarni yuklang (`bot.py`, `admin_panel.py`, `webapp_server.py`, `webapp/`, `data_store.py`, `pptx_generator.py`, `requirements.txt`)

2. **Railway.app**'ga kiring → "New Project" → "Deploy from GitHub repo"

3. **3 ta alohida xizmat (service)** yarating, bitta repodan:
   - **Bot xizmati**: Start Command → `python bot.py`
   - **Admin panel xizmati**: Start Command → `python admin_panel.py`
   - **Mini App xizmati**: Start Command → `python webapp_server.py`

4. Har bir xizmat uchun Railway **avtomatik HTTPS domen** beradi (masalan `https://mini-app-production.up.railway.app`)

5. Mini App xizmatining domenini nusxalab, `bot.py` dagi `WEBAPP_URL` ga qo'ying:
   ```python
   WEBAPP_URL = "https://mini-app-production.up.railway.app/webapp/"
   ```

6. Bot xizmatini qayta ishga tushiring (Railway avtomatik qayta deploy qiladi)

7. ⚠️ **Muhim**: barcha 3 xizmat **bir xil `users.json`** ga yozishi kerak — Railway'da **Volume** (doimiy disk) ulang va uni barcha xizmatlarga bog'lang, aks holda har birida alohida nusxa bo'lib qoladi.

> 💡 Agar bu qadamda yordam kerak bo'lsa — screenshot bilan birga ayting, men aniq ko'rsataman.

---

## 🛒 Mini App qanday ishlaydi

1. Talaba botda pastdagi **Menyu** tugmasini bosadi (yoki "🛒 Buyurtma" yozuvini)
2. To'liq ekranli sahifa ochiladi:
   - 8 ta xizmat kartasi (Prezentatsiya, Referat, Masala, Tarjima, Konspekt, Test, Kod, Erkin savol)
   - Tanlangach — forma ochiladi (mavzu, til, va prezentatsiya uchun slayd soni + dizayn rangi)
   - Joriy balans yuqorida ko'rinadi
3. "Yaratishni boshlash" tugmasi bosilganda — ma'lumot botga yuboriladi
4. Bot avtomatik AI'ni ishga tushiradi, natija (yoki tayyor `.pptx` fayl) chatga keladi
5. Balansdan 5000 so'm yechiladi

---

## 🛡️ Xavfsizlik

- Mini App'dan kelgan har bir so'rov **Telegram imzosi orqali tekshiriladi** (`initData` HMAC tekshiruvi) — soxtalashtirib bo'lmaydi
- Pul faqat siz admin panelda tasdiqlagandan keyin balansga qo'shiladi
- Bot faqat o'quv mavzulari bo'yicha javob beradi

## 🛠️ Muammolarni bartaraf etish

**"Menu tugmasi oddiy buyruqlar ro'yxatini ko'rsatmoqda, Mini App ochilmayapti":** `WEBAPP_URL` hali to'ldirilmagan yoki serverga joylashtirilmagan. Localhost manzili ishlamaydi.

**Mini App ochiladi, lekin balans ko'rinmaydi:** `webapp_server.py` dagi `BOT_TOKEN` ni tekshiring — u boshqa fayllardagi token bilan **bir xil** bo'lishi kerak.
