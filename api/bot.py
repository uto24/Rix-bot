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

# --- এনভায়রনমেন্ট ভেরিয়েবল থেকে প্রয়োজনীয় তথ্য লোড করা ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
# Vercel নিজে থেকেই VERCEL_URL ভেরিয়েবল সেট করে, আমরা সেটিকে ব্যবহার করব
VERCEL_URL = f"https://{os.environ.get('VERCEL_URL')}"

# --- টেলিগ্রাম বট, সুপাবেস ক্লায়েন্ট এবং ফ্ল্যাস্ক অ্যাপ ইনিশিয়ালাইজেশন ---
bot = Bot(token=TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = Flask(__name__)

# --- গেমের নিয়ম এবং কনস্ট্যান্টস (এগুলো সহজেই পরিবর্তন করতে পারবেন) ---
NEW_USER_BONUS = 2000
REFERRAL_BONUS = 1000
MINING_REWARD = 200
MINING_INTERVAL_HOURS = 6

# --- সহায়ক ফাংশন ---
def generate_referral_code():
    """একটি ইউনিক রেফারেল কোড তৈরি করে।"""
    return str(uuid.uuid4())[:8]

def update_rix_balance(user_id, amount_to_add):
    """নির্দিষ্ট ব্যবহারকারীর RiX ব্যালেন্স আপডেট করে।"""
    try:
        user_data = supabase.table('users').select('rix_balance').eq('user_id', user_id).single().execute()
        current_balance = user_data.data.get('rix_balance', 0) if user_data.data else 0
        new_balance = current_balance + amount_to_add
        supabase.table('users').update({'rix_balance': new_balance}).eq('user_id', user_id).execute()
    except Exception as e:
        print(f"ব্যালেন্স আপডেট করতে সমস্যা: user_id={user_id}, error={e}")

def get_main_menu_keyboard():
    """প্রধান মেনুর জন্য ইনলাইন কিবোর্ড তৈরি করে।"""
    keyboard = [
        # মিনি অ্যাপ খোলার জন্য web_app বাটন
        [InlineKeyboardButton("💎 মাইনিং হাব (Mini App)", web_app={'url': VERCEL_URL})],
        [InlineKeyboardButton("🤝 রেফার করুন এবং আয় করুন", callback_data="refer_friend")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- মূল আপডেট হ্যান্ডলিং ফাংশন ---
async def handle_update(update_data):
    """টেলিগ্রাম থেকে আসা সব ধরনের আপডেট (মেসেজ, বাটন ক্লিক, মিনি অ্যাপ ডেটা) পরিচালনা করে।"""
    update = Update.de_json(update_data, bot)
    
    # ১. মিনি অ্যাপ থেকে আসা ডেটা হ্যান্ডেল করা
    if update.message and update.message.web_app_data:
        user = update.message.from_user
        try:
            web_app_data = json.loads(update.message.web_app_data.data)
        except json.JSONDecodeError:
            print("Error decoding web_app_data")
            return

        action = web_app_data.get('action')

        if action == 'get_user_data':
            # মিনি অ্যাপকে ব্যবহারকারীর লেটেস্ট তথ্য পাঠান
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
                # answer_web_app_query ব্যবহার করে ডেটা মিনি অ্যাপে ফেরত পাঠান
                await bot.answer_web_app_query(update.message.web_app_data.query_id, json.dumps(response_to_frontend))

        elif action == 'claim_from_mini_app':
            # মিনি অ্যাপ থেকে ক্লেইম রিকোয়েস্ট এসেছে
            update_rix_balance(user.id, MINING_REWARD)
            now_utc = datetime.now(timezone.utc).isoformat()
            supabase.table('users').update({'last_mining_claim': now_utc}).eq('user_id', user.id).execute()
            await bot.send_message(chat_id=user.id, text=f"🎉 অভিনন্দন! আপনি মিনি অ্যাপ থেকে {MINING_REWARD} RiX ক্লেইম করেছেন।")

    # ২. সাধারণ মেসেজ বা /start কমান্ড হ্যান্ডেল করা
    elif update.message and update.message.text and update.message.text.startswith('/start'):
        user = update.message.from_user
        chat_id = update.message.chat_id
        
        # রেফারেল কোড চেক
        command_parts = update.message.text.split()
        referrer_id = None
        if len(command_parts) > 1:
            referral_code = command_parts[1]
            referrer_data = supabase.table('users').select('user_id').eq('referral_code', referral_code).single().execute()
            if referrer_data.data:
                referrer_id = referrer_data.data['user_id']
        
        # ব্যবহারকারী নতুন কিনা চেক
        existing_user = supabase.table('users').select('user_id').eq('user_id', user.id).single().execute()

        if not existing_user.data:
            new_referral_code = generate_referral_code()
            initial_balance = NEW_USER_BONUS
            
            # রেফারার থাকলে বোনাস দিন
            if referrer_id and referrer_id != user.id:
                update_rix_balance(referrer_id, REFERRAL_BONUS)
                await bot.send_message(chat_id=referrer_id, text=f"🎉 অভিনন্দন! {user.first_name} আপনার রেফারেলে যোগ দিয়েছেন। আপনি {REFERRAL_BONUS} RiX বোনাস পেয়েছেন!")
            
            supabase.table('users').insert({
                'user_id': user.id, 'first_name': user.first_name, 'referral_code': new_referral_code, 
                'rix_balance': initial_balance, 'referred_by': referrer_id, 'username': user.username
            }).execute()
            
            welcome_message = f"স্বাগতম, {user.first_name}! আপনি বোনাস হিসেবে {NEW_USER_BONUS} RiX পেয়েছেন!"
        else:
            welcome_message = f"ফিরে আসার জন্য ধন্যবাদ, {user.first_name}!"
        
        await bot.send_message(chat_id=chat_id, text=welcome_message, reply_markup=get_main_menu_keyboard())

    # ৩. ইনলাইন বাটন ক্লিক (Callback Query) হ্যান্ডেল করা
    elif update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        
        if query.data == "refer_friend":
            # উন্নত রেফারেল লিঙ্ক তৈরি এবং শেয়ার বাটন
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
    """টেলিগ্রাম থেকে আসা সব POST রিকোয়েস্ট এখানে আসে।"""
    try:
        asyncio.run(handle_update(request.json))
    except Exception as e:
        print(f"Error in webhook_handler: {e}")
    return 'ok'

@app.route('/setwebhook', methods=['GET'])
def set_webhook():
    """Webhook সেট করার জন্য এই রাউটটি ব্যবহার করা হয়।"""
    webhook_url = f"{VERCEL_URL}/api/bot" # Webhook URL হবে /api/bot
    is_set = asyncio.run(bot.set_webhook(url=webhook_url, allowed_updates=["message", "callback_query"]))
    if is_set:
        return "Webhook has been set successfully!"
    return "Failed to set webhook."
