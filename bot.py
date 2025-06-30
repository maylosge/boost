import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiosend import CryptoPay

# === Конфигурация ===
BOT_TOKEN = "BOT_TOKEN"
CRYPTOBOT_API_TOKEN = "CRYPTOBOT_API_TOKEN"
ADMIN_ID = "860728574"

bot = Bot(BOT_TOKEN)
dp = Dispatcher()
cryptopay = CryptoPay(CRYPTOBOT_API_TOKEN)
user_states = {}

# === Цены ===
SOLO_PRICES = {
    (1, 1000): 15,
    (1000, 2000): 25,
    (2000, 3000): 35,
    (3000, 4000): 50,
    (4000, 5000): 75,
    (5000, 6000): 120,
    (6000, 7000): 160,
}
DUO_MULTIPLIER = 1.5

def get_price_per_win(mode, mmr):
    for (lo, hi), price in SOLO_PRICES.items():
        if lo <= mmr < hi:
            return price * DUO_MULTIPLIER if mode == "duo" else price
    return 160 * (DUO_MULTIPLIER if mode == "duo" else 1)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Solo🎯", callback_data="boost_solo"),
         InlineKeyboardButton(text="Duo🤝", callback_data="boost_duo")]
    ])
    await message.answer(f"👋Привет, {message.from_user.first_name or 'друг'}! 🔥Выбери режим буста.\n🥴Основной канал @hat3meepo", reply_markup=kb)

@dp.callback_query()
async def process_callback(call: types.CallbackQuery):
    await call.answer()
    data = call.data
    ranges = [("😂1‑1000",1,1000),("😁1000‑2000",1000,2000),("😆2000‑3000",2000,3000),
              ("🙁3000‑4000",3000,4000),("😩4000‑5000",4000,5000),("😭5000‑6000",5000,6000),
              ("😤6000‑7000",6000,7000)]

    if data.startswith("boost_"):
        mode = "solo" if data == "boost_solo" else "duo"
        ranges = ranges if mode == "solo" else ranges[:-1]
        markup = []
        for i in range(0, len(ranges), 2):
            row = []
            for j in range(i, min(i+2, len(ranges))):
                label, lo, hi = ranges[j]
                row.append(InlineKeyboardButton(text=label, callback_data=f"{mode}_{lo}_{hi}"))
            markup.append(row)
        await call.message.edit_text("🤪Выбирай диапазон рейтинга:", reply_markup=InlineKeyboardMarkup(inline_keyboard=markup))

    elif data.startswith("solo_") or data.startswith("duo_"):
        mode, lo, hi = data.split("_")
        lo, hi = int(lo), int(hi)
        user_states[call.from_user.id] = {"mode": mode, "range": (lo, hi), "step": "current_mmr"}
        await call.message.answer(f"📊Введи текущий MMR ({lo}–{hi}):")

@dp.message()
async def handle_input(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_states:
        return

    state = user_states[user_id]
    step = state["step"]

    try:
        val = int(message.text)
    except ValueError:
        await message.answer("❌ Введите нормальное число.")
        return

    if step == "current_mmr":
        lo, hi = state["range"]
        if lo <= val <= hi:
            state["current_mmr"] = val
            state["step"] = "boost_amount"
            await message.answer(f"📈Сколько MMR нужно апнуть (итог ≤{hi})?\n📝 (1 победа=25 ммр).")
        else:
            await message.answer(f"❌ Введите число в диапазоне {lo}–{hi}.")

    elif step == "boost_amount":
        cur = state["current_mmr"]
        target = cur + val
        if val <= 0 or target > state["range"][1] or val % 25 != 0:
            await message.answer("❌ Введите MMR, кратный 25, не превышающий максимума.")
        else:
            state["boost"] = val
            state["total"] = target
            state["step"] = "games"
            await message.answer("🎬Сколько игр на аккаунте?")

    elif step == "games":
        if val <= 0 or val > 20000:
            await message.answer("❌ Введите число от 1 до 20000.")
        else:
            state["games"] = val
            state["step"] = "honesty"
            await message.answer("🤬Укажи порядочность (не более 12000):")

    elif step == "honesty":
        if val <= 0 or val > 12000:
            await message.answer("❌ Введите порядочность от 1 до 12000.")
        else:
            state["honesty"] = val
            state["step"] = "tokens"
            await message.answer("👮🏻‍♂️Сколько у тебя жетонов рейтинга? (не более 60):")

    elif step == "tokens":
        if val < 0 or val > 60:
            await message.answer("❌ Введите количество жетонов от 0 до 60.")
            return

        state["tokens"] = val
        boost = state["boost"]
        total = state["total"]
        games = state["games"]
        honesty = state["honesty"]
        tokens = state["tokens"]
        mode = state["mode"]

        price_pw = get_price_per_win(mode, total)
        wins = boost / 25
        base = wins * price_pw

        p = 0
        if games < 1000: p += 0.25
        if honesty < 6000: p += 0.35
        elif honesty < 8000: p += 0.20
        if tokens < 10: p += 0.20

        final_rub = round(base * (1 + p), 2)
        final_usd = round(final_rub / 78.22, 2)
        final_uah = round(final_usd * 41.67, 2)
        emoji = "😊" if honesty > 10000 else "☹️" if honesty > 8000 else "😡" if honesty > 6000 else "🤬"

        await message.answer(
            f"⌨️Итог: {total} MMR\n"
            f"📖Информация📖\n"
            f"{emoji} Порядочность: {honesty}\n"
            f"🎬 Игр на аккаунте: {games}\n"
            f"🎟 Жетоны: {tokens}\n"
            f"💵 Цена: {final_rub}₽ (~💎{final_usd}$)"
        )

        invoice = await cryptopay.create_invoice(
            amount=final_usd,
            asset="USDT",
            description="Оплачивай за буст и связывайся через ссылку в сообщении после оплаты.",
            hidden_message="📱Связь: t.me/hat3pain",
            allow_comments=True
        )

        pay_markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="💳 Оплатить CryptoBot", url=invoice.bot_invoice_url)],
                [InlineKeyboardButton(text="🆘 Другие способы оплаты", url="https://t.me/mayloseg")]
            ]
        )

        await message.answer("💴Выбери оплату💶:", reply_markup=pay_markup)

        await bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"🆕 Заказ от @{message.from_user.username or message.from_user.id}\n"
                f"MMR: {state['current_mmr']} → {total} (+{boost})\n"
                f"Игры: {games}, Порядочность: {honesty}, Жетоны: {tokens}\n"
                f"Цена: {final_rub}₽ (~{final_usd}$)({final_uah}₴)"
            )
        )

        del user_states[user_id]

# === Запуск ===
async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"I'm alive!")

    def run_web_server():
        port = int(os.environ.get("PORT", 8000))
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        print(f"Dummy web server running on port {port}")
        server.serve_forever()

    threading.Thread(target=run_web_server, daemon=True).start()
    asyncio.run(main())
