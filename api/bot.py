# --- ধাপ ১: প্রয়োজনীয় লাইব্রেরি ইম্পোর্ট ---
import os
import uuid
from flask import Flask, request, Response, send_from_directory, jsonify
from flask_cors import CORS # CORS এর জন্য নতুন ইম্পোর্ট
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
from dateutil.parser import parse

# --- ধাপ ২: এনভায়রনমেন্ট ভেরিয়েবল এবং ক্লায়েন্ট ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
VERCEL_URL = os.environ.get("VERCEL_URL")

bot = Bot(token=TOKEN)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = Flask(__name__)

# --- CORS সক্রিয় করা (সবচেয়ে গুরুত্বপূর্ণ পরিবর্তন) ---
# এটি আপনার ফ্রন্টএন্ডকে ব্যাকএন্ড API থেকে ডেটা গ্রহণ করতে দেবে।
CORS(app, resources={r"/api/*": {"origins": "*"}})

# --- ধাপ ৩: গেমের নিয়ম এবং সহায়ক ফাংশন ---
NEW_USER_BONUS = 2000
REFERRAL_BONUS = 1000
TASK_REWARD = 200
DAILY_TASK_LIMIT = 100

def generate_referral_code():
    return str(uuid.uuid4())[:8]

def update_rix_balance(user_id, amount_to_add):
    try:
        user_data = supabase.table('users').select('rix_balance').eq('user_id', user_id).single().execute()
        current_balance = user_data.data.get('rix_balance', 0) if user_data.data else 0
        new_balance = current_balance + amount_to_add
        supabase.table('users').update({'rix_balance': new_balance}).eq('user_id', user_id).execute()
    except Exception as e:
        print(f"ব্যালেন্স আপডেট করতে সমস্যা (User ID: {user_id}): {e}")

def get_main_menu_keyboard():
    mini_app_url = f"https://{VERCEL_URL}/app" if VERCEL_URL else ""
    keyboard = [[InlineKeyboardButton("💎 ওপেন RiX Earn অ্যাপ", web_app={'url': mini_app_url})]]
    return InlineKeyboardMarkup(keyboard)

# --- ধাপ ৪: মূল সিঙ্ক্রোনাস লজিক (বটের জন্য) ---
def handle_update(update_data):
    update = Update.de_json(update_data, bot)
    
    if update.message and update.message.web_app_data:
        print(f"Received data from Mini App: {update.message.web_app_data.data}")
        return

    if update.message and update.message.text:
        user = update.message.from_user; chat_id = update.message.chat_id; text = update.message.text
        if text.startswith('/start'):
            command_parts = text.split(); referrer_id = None
            if len(command_parts) > 1:
                referrer_data = supabase.table('users').select('user_id').eq('referral_code', command_parts[1]).single().execute()
                if referrer_data.data: referrer_id = referrer_data.data['user_id']
            
            existing_user = supabase.table('users').select('user_id').eq('user_id', user.id).single().execute()
            if not existing_user.data:
                initial_balance = NEW_USER_BONUS
                if referrer_id and referrer_id != user.id:
                    update_rix_balance(referrer_id, REFERRAL_BONUS)
                    bot.send_message(chat_id=referrer_id, text=f"🎉 অভিনন্দন! {user.first_name} আপনার রেফারেলে যোগ দিয়েছেন। আপনি {REFERRAL_BONUS} RiX বোনাস পেয়েছেন!")
                supabase.table('users').insert({'user_id': user.id, 'first_name': user.first_name, 'username': user.username or '', 'referral_code': generate_referral_code(), 'rix_balance': initial_balance, 'referred_by': referrer_id}).execute()
                welcome_message = f"স্বাগতম, {user.first_name}! আপনি বোনাস হিসেবে {NEW_USER_BONUS} RiX পেয়েছেন!"
            else:
                welcome_message = f"ফিরে আসার জন্য ধন্যবাদ, {user.first_name}!"
            bot.send_message(chat_id=chat_id, text=welcome_message, reply_markup=get_main_menu_keyboard())

# --- ধাপ ৫: Vercel এর জন্য ওয়েব সার্ভার এবং API এন্ডপয়েন্টস ---

@app.route('/app')
def mini_app_handler():
    try:
        root_path = os.path.join(os.path.dirname(__file__), '..')
        return send_from_directory(os.path.join(root_path, 'frontend'), 'index.html')
    except Exception as e:
        print(f"Error serving mini-app: {e}"); return "Mini App not found", 404

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    try:
        user_id_str = request.args.get('user_id')
        first_name = request.args.get('first_name', 'Player')
        username = request.args.get('username', '')
        if not user_id_str: return jsonify({"error": "User ID is required"}), 400
        user_id = int(user_id_str)
        
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()

        if response.data:
            user_data = response.data[0]
            today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            if str(user_data.get('last_task_reset')) != today_str:
                update_response = supabase.table('users').update({'daily_tasks_completed': 0, 'last_task_reset': today_str}).eq('user_id', user_id).select().execute()
                return jsonify(update_response.data[0])
            return jsonify(user_data)
        else:
            print(f"User {user_id} not found. Creating new user.")
            new_user_data = { 'user_id': user_id, 'first_name': first_name, 'username': username, 'referral_code': generate_referral_code(), 'rix_balance': NEW_USER_BONUS, 'daily_tasks_completed': 0, 'last_task_reset': datetime.now(timezone.utc).strftime('%Y-%m-%d') }
            insert_response = supabase.table('users').insert(new_user_data).select().execute()
            return jsonify(insert_response.data[0])
    except Exception as e:
        print(f"Error in get_user_data: {e}"); return jsonify({"error": f"Internal server error: {e}"}), 500

@app.route('/api/complete_task', methods=['POST'])
def complete_task_api():
    try:
        data = request.json; user_id = data.get('user_id')
        if not user_id: return jsonify({"error": "User ID is required"}), 400
        user_id = int(user_id)
        
        user_data = supabase.table('users').select('daily_tasks_completed').eq('user_id', user_id).single().execute().data
        if not user_data: return jsonify({"error": "User not found"}), 404
        
        completed_tasks = user_data.get('daily_tasks_completed', 0)
        if completed_tasks >= DAILY_TASK_LIMIT:
            return jsonify({"success": False, "message": "You have completed all tasks for today."})

        update_rix_balance(user_id, TASK_REWARD)
        new_completed_count = completed_tasks + 1
        supabase.table('users').update({'daily_tasks_completed': new_completed_count}).eq('user_id', user_id).execute()
        
        new_user_data = supabase.table('users').select('*').eq('user_id', user_id).single().execute().data
        return jsonify({"success": True, "message": f"{TASK_REWARD} RiX received!", "user_data": new_user_data})
    except Exception as e:
        print(f"Error in complete_task: {e}"); return jsonify({"error": f"Internal server error: {e}"}), 500

@app.route('/', methods=['GET', 'POST'])
def webhook_handler():
    if request.method == 'POST':
        try: handle_update(request.json)
        except Exception as e: print(f"Error: {e}")
        return Response(status=200)
    elif request.method == 'GET':
        webhook_url = f"https://{VERCEL_URL}/"; bot.set_webhook(url=webhook_url, allowed_updates=['message', 'callback_query', 'web_app_data'])
        return "Webhook set"
    return "Unsupported"
