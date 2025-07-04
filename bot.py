# --- ধাপ ১: প্রয়োজনীয় লাইব্রেরি ইম্পোর্ট ---
import os
import uuid
from flask import Flask, request, Response, send_from_directory, jsonify
from flask_cors import CORS
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ParseMode
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
from dateutil.parser import parse

# --- ধাপ ২: এনভায়রনমেন্ট ভেরিয়েবল এবং ক্লায়েন্ট ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
# Render.com স্বয়ংক্রিয়ভাবে RENDER_EXTERNAL_URL ভেরিয়েবল সেট করে
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL") 
PORT = int(os.environ.get('PORT', 5000)) # Render-এর জন্য পোর্ট

bot = Bot(token=TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# static_folder='frontend' যোগ করা হয়েছে যাতে CSS/JS ফাইলগুলো সঠিকভাবে সার্ভ হয়
app = Flask(__name__, static_folder='frontend')
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- ধাপ ৩: গেমের নিয়ম ---
NEW_USER_BONUS = 2000
REFERRAL_BONUS = 1000
TASK_REWARD = 200
DAILY_TASK_LIMIT = 100
MINING_REWARD = 500
MINING_COOLDOWN_HOURS = 8

# --- ধাপ ৪: সহায়ক ফাংশন ---
def generate_referral_code(): return str(uuid.uuid4())[:8]

def update_rix_balance(user_id, amount_to_add):
    try:
        user_data_res = supabase.table('users').select('rix_balance').eq('user_id', user_id).limit(1).execute()
        if user_data_res.data:
            current_balance = user_data_res.data[0].get('rix_balance', 0)
            new_balance = current_balance + amount_to_add
            supabase.table('users').update({'rix_balance': new_balance}).eq('user_id', user_id).execute()
    except Exception as e: print(f"Balance update error for {user_id}: {e}")

def get_main_menu_keyboard(is_new_user=False):
    mini_app_url = f"{RENDER_URL}/app" if RENDER_URL else ""
    keyboard = [[InlineKeyboardButton("💎 ওপেন RiX Earn অ্যাপ", web_app={'url': mini_app_url})]]
    if is_new_user:
        keyboard.append([InlineKeyboardButton("🎁 ইনপুট রেফারেল কোড", callback_data="enter_referral_code")])
    return InlineKeyboardMarkup(keyboard)

# --- ধাপ ৫: মূল সিঙ্ক্রোনাস লজিক (বটের জন্য) ---
def handle_update(update_data):
    update = Update.de_json(update_data, bot)
    
    # Callback Query (বাটন ক্লিক) হ্যান্ডলার
    if update.callback_query:
        query = update.callback_query; chat_id = query.message.chat_id
        if query.data == "enter_referral_code":
            query.answer(); bot.send_message(chat_id=chat_id, text="🔑 আপনার বন্ধুর রেফারেল কোডটি এখানে পাঠান:")
        return

    if not (update.message and update.message.text): return

    user = update.message.from_user; chat_id = update.message.chat_id; text = update.message.text
    
    # /start কমান্ড হ্যান্ডলিং
    if text.startswith('/start'):
        try:
            command_parts = text.split(); referrer_id = None
            if len(command_parts) > 1 and len(command_parts[1]) > 5:
                referral_code = command_parts[1]
                referrer_res = supabase.table('users').select('user_id').eq('referral_code', referral_code).limit(1).execute()
                if referrer_res.data: referrer_id = int(referrer_res.data[0]['user_id'])
            
            existing_user = supabase.table('users').select('user_id').eq('user_id', user.id).limit(1).execute()
            
            if not existing_user.data:
                initial_balance = NEW_USER_BONUS
                if referrer_id and referrer_id != user.id:
                    initial_balance += REFERRAL_BONUS
                    update_rix_balance(referrer_id, REFERRAL_BONUS)
                    bot.send_message(chat_id=referrer_id, text=f"🎉 অভিনন্দন! {user.first_name} আপনার রেফারেলে যোগ দিয়েছেন। আপনারা দুজনেই বোনাস পেয়েছেন!")
                
                supabase.table('users').insert({'user_id': user.id, 'first_name': user.first_name, 'username': user.username or '', 'referral_code': generate_referral_code(), 'rix_balance': initial_balance, 'referred_by': referrer_id}).execute()
                welcome_message = f"🎉 **স্বাগতম, {user.first_name}!**\n\nRiX Earn-এ যোগ দেওয়ার জন্য আপনাকে **{initial_balance} RiX** বোনাস দেওয়া হয়েছে!"
                is_new = not bool(referrer_id)
                bot.send_message(chat_id=chat_id, text=welcome_message, reply_markup=get_main_menu_keyboard(is_new_user=is_new), parse_mode=ParseMode.MARKDOWN)
            else:
                welcome_message = f"👋 **ফিরে আসার জন্য ধন্যবাদ, {user.first_name}!**"
                bot.send_message(chat_id=chat_id, text=welcome_message, reply_markup=get_main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)
        except Exception as e: print(f"Error in /start: {e}")
        return

    # রেফারেল কোড ইনপুট হ্যান্ডলিং
    try:
        user_profile_res = supabase.table('users').select('referred_by').eq('user_id', user.id).limit(1).execute()
        if user_profile_res.data and user_profile_res.data[0].get('referred_by') is not None:
            bot.send_message(chat_id=chat_id, text="আপনি ইতিমধ্যেই একটি রেফারেল কোড ব্যবহার করেছেন।"); return
        
        referral_code = text.strip()
        referrer_response = supabase.table('users').select('user_id, first_name').eq('referral_code', referral_code).limit(1).execute()
        if referrer_response.data:
            referrer = referrer_response.data[0]; referrer_id = referrer['user_id']
            if referrer_id == user.id: bot.send_message(chat_id=chat_id, text="আপনি নিজের রেফারেল কোড ব্যবহার করতে পারবেন না।"); return
            update_rix_balance(user.id, REFERRAL_BONUS); update_rix_balance(referrer_id, REFERRAL_BONUS)
            supabase.table('users').update({'referred_by': referrer_id}).eq('user_id', user.id).execute()
            bot.send_message(chat_id=chat_id, text=f"সফল! আপনি {referrer['first_name']}-এর রেফারেলে যোগ দিয়েছেন এবং {REFERRAL_BONUS} RiX বোনাস পেয়েছেন।")
            bot.send_message(chat_id=referrer_id, text=f"🎉 অভিনন্দন! {user.first_name} আপনার রেফারেল কোড ব্যবহার করেছে। আপনারা দুজনেই বোনাস পেয়েছেন!")
        else:
            bot.send_message(chat_id=chat_id, text="দুঃখিত, এই রেফারেল কোডটি সঠিক নয়।")
    except Exception as e: print(f"Error processing referral code: {e}")

# --- ধাপ ৬: ওয়েব সার্ভার এবং API এন্ডপয়েন্টস ---
@app.route('/app')
def mini_app_handler():
    return send_from_directory('frontend', 'index.html')

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    # ... (অপরিবর্তিত) ...
    pass
# ... (আপনার অন্যান্য সব API এন্ডপয়েন্ট অপরিবর্তিত থাকবে) ...

# --- Webhook সেটআপ এবং অ্যাপ রান ---
@app.route('/', methods=['POST'])
def webhook_handler():
    handle_update(request.json)
    return Response(status=200)

def set_webhook():
    # শুধুমাত্র একবার চালু করার জন্য
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/"
        is_set = bot.set_webhook(url=webhook_url, allowed_updates=['message', 'callback_query'])
        if is_set:
            print(f"Webhook set successfully to {webhook_url}")
        else:
            print("Webhook setup failed.")

if __name__ == "__main__":
    # Render.com এই ব্লকটি ব্যবহার করে না, এটি Gunicorn থেকে অ্যাপ চালায়।
    # কিন্তু প্রথমবার Webhook সেট করার জন্য এটি কার্যকর হতে পারে।
    set_webhook()
    app.run(host='0.0.0.0', port=PORT)
