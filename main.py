import ccxt
import pandas as pd
import asyncio
import json
import os
import nest_asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from keep_alive import keep_alive

BOT_TOKEN = "7744264751:AAEEzR7J54XcuiZO8tK4uH61jfrCWBG0sPw"
FAV_FILE = "favorites.json"

exchange = ccxt.binance()
markets = exchange.load_markets()
allowed_symbols = [s.replace("/", "") for s in markets if "/USDT" in s and "spot" not in str(markets[s].get("type", ""))]

# Favorite system
if not os.path.exists(FAV_FILE):
    with open(FAV_FILE, "w") as f:
        json.dump([], f)

def get_signal(symbol="BTC/USDT"):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe='5m', limit=100)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["ema"] = EMAIndicator(df["close"], window=20).ema_indicator()
        df["macd"] = MACD(df["close"]).macd_diff()
        df["rsi"] = RSIIndicator(df["close"]).rsi()

        latest = df.iloc[-1]
        price = latest["close"]
        rsi = latest["rsi"]
        macd = latest["macd"]
        ema = latest["ema"]

        ob = exchange.fetch_order_book(symbol)
        buy_pressure = sum([b[1] for b in ob["bids"]])
        sell_pressure = sum([s[1] for s in ob["asks"]])
        pressure_pct = (buy_pressure / (buy_pressure + sell_pressure)) * 100

        if rsi < 30 and macd > 0 and price > ema and pressure_pct > 55:
            signal = "✅ BUY"
        elif rsi > 70 and macd < 0 and price < ema and pressure_pct < 45:
            signal = "🔻 SELL"
        else:
            signal = "🤝 HOLD"

        return {
            "signal": signal,
            "price": round(price, 4),
            "rsi": round(rsi, 2),
            "macd": round(macd, 4),
            "ema": round(ema, 4),
            "pressure": round(pressure_pct, 2)
        }

    except Exception as e:
        return {"error": str(e)}

def load_favorites():
    with open(FAV_FILE, "r") as f:
        return json.load(f)

def save_favorites(favs):
    with open(FAV_FILE, "w") as f:
        json.dump(favs, f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Send `/coin BTCUSDT` to get a signal.\n❤️ Send /favorites to see your list.")

async def coin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❗Use: /coin BTCUSDT")
        return

    coin = context.args[0].upper()
    if coin not in allowed_symbols:
        await update.message.reply_text("❌ Not a valid Binance Future symbol")
        return

    symbol = coin.replace("USDT", "/USDT")
    result = get_signal(symbol)
    await send_result(update, result, coin)

async def send_result(target, result, coin):
    favs = load_favorites()
    is_fav = coin in favs
    button_text = "❤️ Add to Favorites" if not is_fav else "❌ Remove Favorite"
    callback_data = f"addfav_{coin}" if not is_fav else f"removefav_{coin}"

    if "error" in result:
        await target.message.reply_text(f"⚠️ Error: {result['error']}")
    else:
        text = (
            f"📊 *Signal for {coin}* \[5m\]\n\n"
            f"{result['signal']}\n\n"
            f"Price: ${result['price']}\n"
            f"RSI: {result['rsi']}\n"
            f"MACD: {result['macd']}\n"
            f"EMA: {result['ema']}\n"
            f"Buy Pressure: {result['pressure']}%\n"
        )
        button = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data=callback_data)]])
        await target.message.reply_text(text, parse_mode="Markdown", reply_markup=button)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("addfav_"):
        coin = data.split("_")[1]
        favs = load_favorites()
        if coin not in favs:
            favs.append(coin)
            save_favorites(favs)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"✅ {coin} added to favorites.")

    elif data.startswith("removefav_"):
        coin = data.split("_")[1]
        favs = load_favorites()
        if coin in favs:
            favs.remove(coin)
            save_favorites(favs)
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(f"❌ {coin} removed from favorites.")

async def favorites_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    favs = load_favorites()
    if not favs:
        await update.message.reply_text("📭 No favorites added yet.")
        return

    for coin in favs:
        symbol = coin.replace("USDT", "/USDT")
        result = get_signal(symbol)
        await send_result(update, result, coin)

async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("coin", coin_handler))
    app.add_handler(CommandHandler("favorites", favorites_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    keep_alive()
    nest_asyncio.apply()
    asyncio.run(run_bot())
