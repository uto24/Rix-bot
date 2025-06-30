# --- ধাপ ১: প্রয়োজনীয় লাইব্রেরি ইম্পোর্ট ---
import os
import uuid
from flask import Flask, request, Response, send_from_directory, jsonify
from flask_cors import CORS
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

def get_main_menu_keyboard():
    mini_app_url = f"https://{VERCEL_URL}/app" if VERCEL_URL else ""
    keyboard = [[InlineKeyboardButton("💎 ওপেন RiX Earn অ্যাপ", web_app={'url': mini_app_url})]]
    return InlineKeyboardMarkup(keyboard)

# --- ধাপ ৫: মূল সিঙ্ক্রোনাস লজিক (বটের জন্য) ---
def handle_update(update_data):
    update = Update.de_json(update_data, bot)
    
    if update.message and update.message.web_app_data:
        print(f"Received data from Mini App: {update.message.web_app_data.data}")
        return

    if update.message and update.message.text and update.message.text.startswith('/start'):
        user = update.message.from_user
        chat_id = update.message.chat_id
        text = update.message.text
        
        print(f"--- /start command initiated by user: {user.id} ---")

        command_parts = text.split()
        referrer_id = None

        if len(command_parts) > 1:
            referral_code = command_parts[1]
            print(f"Attempting to find referrer with code: {referral_code}")
            try:
                referrer_response = supabase.table('users').select('user_id').eq('referral_code', referral_code).limit(1).execute()
                if referrer_response.data:
                    referrer_id = int(referrer_response.data[0]['user_id'])
                    print(f"SUCCESS: Found referrer with ID: {referrer_id}")
                else:
                    print(f"INFO: Referral code '{referral_code}' not found.")
            except Exception as e:
                print(f"ERROR: Exception while looking up referrer: {e}")
        
        try:
            existing_user_response = supabase.table('users').select('user_id').eq('user_id', user.id).limit(1).execute()
            
            if not existing_user_response.data:
                print(f"INFO: User {user.id} is new. Proceeding to create profile.")
                initial_balance = NEW_USER_BONUS
                
                if referrer_id and referrer_id != user.id:
                    print(f"INFO: Awarding {REFERRAL_BONUS} RiX to referrer {referrer_id}")
                    update_rix_balance(referrer_id, REFERRAL_BONUS)
                    try:
                        bot.send_message(
                            chat_id=referrer_id,
                            text=f"🎉 Congratulations! {user.first_name} has joined using your referral link. You've received a {REFERRAL_BONUS} RiX bonus!"
                        )
                    except Exception as e:
                        print(f"WARNING: Could not send notification to referrer {referrer_id}: {e}")
                
                new_user_payload = {
                    'user_id': user.id, 'first_name': user.first_name, 'username': user.username or '',
                    'referral_code': generate_referral_code(), 'rix_balance': initial_balance,
                    'referred_by': referrer_id, 'daily_tasks_completed': 0,
                    'last_task_reset': datetime.now(timezone.utc).strftime('%Y-%m-%d')
                }
                
                print(f"INFO: Inserting new user with payload: {new_user_payload}")
                insert_response = supabase.table('users').insert(new_user_payload).execute()
                
                if len(insert_response.data) > 0:
                    print(f"SUCCESS: User {user.id} created successfully.")
                    welcome_message = f"স্বাগতম, {user.first_name}! আপনি বোনাস হিসেবে {NEW_USER_BONUS} RiX পেয়েছেন!"
                else:
                    print(f"CRITICAL: Failed to insert user {user.id}. Response: {insert_response}")
                    welcome_message = "Sorry, there was an error creating your profile. Please try again."
            else:
                print(f"INFO: User {user.id} already exists.")
                welcome_message = f"ফিরে আসার জন্য ধন্যবাদ, {user.first_name}!"
            
            bot.send_message(chat_id=chat_id, text=welcome_message, reply_markup=get_main_menu_keyboard())

        except Exception as e:
            print(f"CRITICAL: Unhandled exception in /start handler for user {user.id}: {e}")

# --- ধাপ ৬: Vercel এর জন্য ওয়েব সার্ভার এবং API এন্ডপয়েন্টস ---
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
        user_id_str = request.args.get('user_id');
        if not user_id_str: return jsonify({"error": "User ID is required"}), 400
        user_id = int(user_id_str)
        response = supabase.table('users').select('*').eq('user_id', user_id).execute()
        if response.data:
            user_data = response.data[0]; today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            if str(user_data.get('last_task_reset')) != today_str:
                supabase.table('users').update({'daily_tasks_completed': 0, 'last_task_reset': today_str}).eq('user_id', user_id).execute()
                updated_response = supabase.table('users').select('*').eq('user_id', user_id).single().execute()
                return jsonify(updated_response.data)
            return jsonify(user_data)
        else:
            first_name = request.args.get('first_name', 'Player'); username = request.args.get('username', '')
            new_user_data = {'user_id': user_id, 'first_name': first_name, 'username': username, 'referral_code': generate_referral_code(), 'rix_balance': NEW_USER_BONUS, 'daily_tasks_completed': 0, 'last_task_reset': datetime.now(timezone.utc).strftime('%Y-%m-%d')}
            insert_response = supabase.table('users').insert(new_user_data).execute()
            if insert_response.data: return jsonify(insert_response.data[0])
            else: return jsonify({"error": "Could not create profile"}), 500
    except Exception as e: return jsonify({"error": f"Internal server error: {e}"}), 500

@app.route('/api/get_referrals', methods=['GET'])
def get_referrals_api():
    try:
        user_id_str = request.args.get('user_id')
        if not user_id_str: return jsonify({"error": "User ID is required"}), 400
        user_id = int(user_id_str)
        response = supabase.table('users').select('first_name, created_at').eq('referred_by', user_id).order('created_at', desc=True).limit(20).execute()
        return jsonify(response.data)
    except Exception as e: return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/api/complete_task', methods=['POST'])
def complete_task_api():
    try:
        data = request.json; user_id = data.get('user_id');
        if not user_id: return jsonify({"error": "User ID is required"}), 400
        user_id = int(user_id)
        user_data = supabase.table('users').select('daily_tasks_completed').eq('user_id', user_id).single().execute().data
        if not user_data: return jsonify({"error": "User not found"}), 404
        completed_tasks = user_data.get('daily_tasks_completed', 0)
        if completed_tasks >= DAILY_TASK_LIMIT: return jsonify({"success": False, "message": "All tasks completed for today."})
        update_rix_balance(user_id, TASK_REWARD); new_completed_count = completed_tasks + 1
        supabase.table('users').update({'daily_tasks_completed': new_completed_count}).eq('user_id', user_id).execute()
        new_user_data = supabase.table('users').select('*').eq('user_id', user_id).single().execute().data
        return jsonify({"success": True, "message": f"{TASK_REWARD} RiX received!", "user_data": new_user_data})
    except Exception as e: return jsonify({"error": f"Internal server error: {e}"}), 500

@app.route('/api/claim_mining', methods=['POST'])
def claim_mining_api():
    try:
        data = request.json; user_id = data.get('user_id');
        if not user_id: return jsonify({"error": "User ID is required"}), 400
        user_id = int(user_id)
        user_response = supabase.table('users').select('last_mining_claim').eq('user_id', user_id).execute()
        if not user_response.data: return jsonify({"error": "User not found"}), 404
        user_data = user_response.data[0]; last_claim_str = user_data.get('last_mining_claim')
        can_claim = False
        if not last_claim_str: can_claim = True
        else:
            try:
                last_claim_time = parse(last_claim_str); next_claim_time = last_claim_time + timedelta(hours=MINING_COOLDOWN_HOURS)
                if datetime.now(timezone.utc) >= next_claim_time: can_claim = True
            except (TypeError, ValueError): can_claim = True
        if can_claim:
            update_rix_balance(user_id, MINING_REWARD); now_utc = datetime.now(timezone.utc).isoformat()
            supabase.table('users').update({'last_mining_claim': now_utc}).eq('user_id', user_id).execute()
            new_user_data = supabase.table('users').select('*').eq('user_id', user_id).single().execute().data
            return jsonify({"success": True, "message": f"{MINING_REWARD} RiX successfully claimed!", "user_data": new_user_data})
        else:
            next_claim_time = parse(last_claim_str) + timedelta(hours=MINING_COOLDOWN_HOURS)
            return jsonify({"success": False, "message": "It's not time to claim yet.", "next_claim_time": next_claim_time.isoformat()})
    except Exception as e: return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@app.route('/', methods=['GET', 'POST'])
def webhook_handler():
    if request.method == 'POST':
        try: handle_update(request.json)
        except Exception as e: print(f"Error: {e}")
        return Response(status=200)
    elif request.method == 'GET':
        webhook_url = f"https://{VERCEL_URL}/"; bot.set_webhook(url=webhook_url)
        return "Webhook set"
    return "Unsupported"
