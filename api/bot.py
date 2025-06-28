import os
import asyncio
import uuid
import json
from flask import Flask, request
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
from dateutil.parser import parse
from urllib.parse import quote_plus

# --- প্রয়োজনীয় তথ্য যা Vercel থেকে আসবে ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
VERCEL_URL = f"https://{os.environ.get('VERCEL_URL')}"

# --- ক্লায়েন্ট এবং অ্যাপ ইনিশিয়ালাইজেশন ---
bot = Bot(token=TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = Flask(__name__)

# --- গেমের নিয়ম ---
NEW_USER_BONUS = 2000
REFERRAL_BONUS = 1000
MINING_REWARD = 200
MINING_INTERVAL_HOURS = 6

# ... (generate_referral_code এবং update_rix_balance ফাংশন আগের মতোই থাকবে) ...
def generate_referral_code(): return str(uuid.uuid4())[:8]
def update_rix_balance(user_id, amount_to_add):
    try:
        user_data = supabase.table('users').select('rix_balance').eq('user_id', user_id).single().execute()
        current_balance = user_data.data.get('rix_balance', 0)
        new_balance = current_balance + amount_to_add
        supabase.table('users').update({'rix_balance': new_balance}).eq('user_id', user_id).execute()
    except Exception as e: print(f"ব্যালেন্স আপডেট করতে সমস্যা: {e}")

# --- নতুন মেনু বাটন ---
def get_main_menu_keyboard():
    keyboard = [
        # মিনি অ্যাপ খোলার জন্য web_app বাটন
        [InlineKeyboardButton("💎 মাইনিং হাব (Mini App)", web_app={'url': VERCEL_URL})],
        [InlineKeyboardButton("🤝 রেফার করুন এবং আয় করুন", callback_data="refer_friend")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- মূল ফাংশন ---
async def handle_update(update_data):
    update = Update.de_json(update_data, bot)
    
    if update.message and update.message.web_app_data:
        # মিনি অ্যাপ থেকে আসা ডেটা হ্যান্ডেল করুন
        user = update.message.from_user
        web_app_data = json.loads(update.message.web_app_data.data)
        
        if web_app_data.get('action') == 'get_user_data':
            # মিনি অ্যাপকে ব্যবহারকারীর তথ্য পাঠান
            user_db_data = supabase.table('users').select('*').eq('user_id', user.id).single().execute().data
            if user_db_data:
                last_claim_str = user_db_data.get('last_mining_claim')
                can_claim = False
                next_claim_in_seconds = 0
                
                if not last_claim_str:
                    can_claim = True
                else:
                    last_claim_time = parse(last_claim_str)
                    next_claim_time = last_claim_time + timedelta(hours=MINING_INTERVAL_HOURS)
                    now_utc = datetime.now(timezone.utc)
                    if now_utc >= next_claim_time:
                        can_claim = True
                    else:
                        next_claim_in_seconds = (next_claim_time - now_utc).total_seconds()

                response_to_frontend = {
                    'rix_balance': user_db_data.get('rix_balance', 0),
                    'can_claim': can_claim,
                    'next_claim_in_seconds': int(next_claim_in_seconds),
                    'mining_reward': MINING_REWARD
                }
                # উত্তরটি মিনি অ্যাপে ফেরত পাঠান
                await bot.answer_web_app_query(update.message.web_app_data.query_id, json.dumps(response_to_frontend))

        elif web_app_data.get('action') == 'claim_from_mini_app':
            # মিনি অ্যাপ থেকে ক্লেইম রিকোয়েস্ট এসেছে
            update_rix_balance(user.id, MINING_REWARD)
            now_utc = datetime.now(timezone.utc).isoformat()
            supabase.table('users').update({'last_mining_claim': now_utc}).eq('user_id', user.id).execute()
            await bot.send_message(chat_id=user.id, text=f"🎉 অভিনন্দন! আপনি মিনি অ্যাপ থেকে {MINING_REWARD} RiX ক্লেইম করেছেন।")

    elif update.message and update.message.text and update.message.text.startswith('/start'):
        # ... (/start কমান্ডের লজিক আগের মতোই থাকবে, শুধু শেষে get_main_menu_keyboard() কল হবে) ...
        user = update.message.from_user
        # ... (বাকি কোড আগের মতো) ...
        await bot.send_message(chat_id=user.id, text=welcome_message, reply_markup=get_main_menu_keyboard())


    elif update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        
        if query.data == "refer_friend":
            # --- উন্নত রেফারেল লিঙ্ক ---
            user_data = supabase.table('users').select('referral_code').eq('user_id', user_id).single().execute()
            ref_code = user_data.data.get('referral_code', 'N/A')
            bot_username = (await bot.get_me()).username
            ref_link = f"https://t.me/{bot_username}?start={ref_code}"
            
            share_text = f"দারুণ একটি বট পেলাম! RiX Coin মাইনিং করা যাচ্ছে। আমার লিঙ্কে যোগ দিয়ে আপনিও {NEW_USER_BONUS} RiX বোনাস পান! 🚀"
            encoded_text = quote_plus(share_text)
            share_url = f"https://t.me/share/url?url={ref_link}&text={encoded_text}"
            
            keyboard = [
                [InlineKeyboardButton("📤 বন্ধুদের শেয়ার করুন", url=share_url)],
                [InlineKeyboardButton("⬅️ মেনুতে ফিরুন", callback_data="back_to_menu")]
            ]
            await query.edit_message_text(
                text=f"আপনার বন্ধুদের রেফার করে আয় করুন!\n\nআপনার লিঙ্ক:\n`{ref_link}`",
                parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif query.data == "back_to_menu":
            await query.edit_message_text(text="প্রধান মেনু:", reply_markup=get_main_menu_keyboard())

# --- Vercel এর জন্য রাউট (Route) ---
@app.route('/api/bot', methods=['POST'])
def webhook_handler():
    asyncio.run(handle_update(request.json))
    return 'ok'

# এই রাউটটি এখন আর দরকার নেই, কারণ vercel.json ফাইল রুট ডিরেক্টরিকে ফ্রন্টএন্ড হিসেবে দেখাবে
# @app.route('/', methods=['GET'])
# def index():
#     return "Bot is running..."

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    webhook_url = f"{VERCEL_URL}/api/bot" # Webhook URL পরিবর্তন হয়েছে
    is_set = asyncio.run(bot.set_webhook(url=webhook_url))
    if is_set:
        return "Webhook সফলভাবে সেট করা হয়েছে!"
    return "Webhook সেট করতে ব্যর্থ।"
