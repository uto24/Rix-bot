# --- ধাপ ১: প্রয়োজনীয় লাইব্রেরি ইম্পোর্ট (কোনো asyncio নেই) ---
import os
import uuid
from flask import Flask, request, Response
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

# --- ধাপ ৩: গেমের নিয়ম এবং সহায়ক ফাংশন (অপরিবর্তিত) ---
NEW_USER_BONUS = 2000
REFERRAL_BONUS = 1000
MINING_REWARD = 200
MINING_INTERVAL_HOURS = 6

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
    keyboard = [
        [InlineKeyboardButton("⛏️ মাইনিং হাব", callback_data="mining_hub")],
        [InlineKeyboardButton("💰 আমার ব্যালেন্স", callback_data="check_balance")],
        [InlineKeyboardButton("🤝 রেফার করুন", callback_data="refer_friend")]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- ধাপ ৪: মূল সিঙ্ক্রোনাস লজিক ---
def handle_update(update_data):
    update = Update.de_json(update_data, bot)
    
    if update.message and update.message.text:
        user = update.message.from_user
        chat_id = update.message.chat_id
        text = update.message.text
        
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
                    # সিঙ্ক্রোনাস কল, কোনো await নেই
                    bot.send_message(chat_id=referrer_id, text=f"🎉 অভিনন্দন! {user.first_name} আপনার রেফারেলে যোগ দিয়েছেন। আপনি {REFERRAL_BONUS} RiX বোনাস পেয়েছেন!")
                
                supabase.table('users').insert({'user_id': user.id, 'first_name': user.first_name, 'referral_code': generate_referral_code(), 'rix_balance': initial_balance, 'referred_by': referrer_id}).execute()
                welcome_message = f"স্বাগতম, {user.first_name}! আপনি বোনাস হিসেবে {NEW_USER_BONUS} RiX পেয়েছেন!"
            else:
                welcome_message = f"ফিরে আসার জন্য ধন্যবাদ, {user.first_name}!"
            
            bot.send_message(chat_id=chat_id, text=welcome_message, reply_markup=get_main_menu_keyboard())

    elif update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        query.answer()
        back_button = [InlineKeyboardButton("⬅️ মেনুতে ফিরুন", callback_data="back_to_menu")]

        if query.data == "check_balance":
            user_data = supabase.table('users').select('rix_balance').eq('user_id', user_id).single().execute()
            balance = user_data.data.get('rix_balance', 0) if user_data.data else 0
            query.edit_message_text(text=f"আপনার বর্তমান RiX ব্যালেন্স: {balance} 💰", reply_markup=InlineKeyboardMarkup([back_button]))

        elif query.data == "mining_hub":
            user_data = supabase.table('users').select('last_mining_claim').eq('user_id', user_id).single().execute()
            last_claim_str = user_data.data.get('last_mining_claim') if user_data.data else None
            can_claim = False; message = ""
            if not last_claim_str:
                can_claim = True; message = "আপনার প্রথম মাইনিং সেশন শুরু করতে ক্লেইম করুন!"
            else:
                last_claim_time = parse(last_claim_str)
                next_claim_time = last_claim_time + timedelta(hours=MINING_INTERVAL_HOURS)
                if datetime.now(timezone.utc) >= next_claim_time:
                    can_claim = True; message = "আপনার মাইনিং সেশন প্রস্তুত! এখনি ক্লেইম করুন।"
                else:
                    remaining = next_claim_time - datetime.now(timezone.utc); hours, rem = divmod(remaining.seconds, 3600); minutes, _ = divmod(rem, 60)
                    message = f"পরবর্তী ক্লেইমের জন্য অপেক্ষা করুন।\nসময় বাকি: {hours} ঘন্টা {minutes} মিনিট"
            
            keyboard = []
            if can_claim: keyboard.append([InlineKeyboardButton(f"✅ {MINING_REWARD} RiX ক্লেইম করুন", callback_data="claim_reward")])
            keyboard.append(back_button)
            query.edit_message_text(text=message, reply_markup=InlineKeyboardMarkup(keyboard))

        elif query.data == "claim_reward":
            update_rix_balance(user_id, MINING_REWARD)
            now_utc = datetime.now(timezone.utc).isoformat()
            supabase.table('users').update({'last_mining_claim': now_utc}).eq('user_id', user_id).execute()
            query.edit_message_text(text=f"অভিনন্দন! আপনি {MINING_REWARD} RiX পেয়েছেন।", reply_markup=InlineKeyboardMarkup([back_button]))

        elif query.data == "refer_friend":
            user_data = supabase.table('users').select('referral_code').eq('user_id', user_id).single().execute()
            ref_code = user_data.data.get('referral_code', 'N/A') if user_data.data else 'N/A'
            # bot.get_me() একটি সিঙ্ক্রোনাস কল
            bot_info = bot.get_me()
            ref_link = f"https://t.me/{bot_info.username}?start={ref_code}"
            query.edit_message_text(text=f"আপনার বন্ধুদের রেফার করে RiX আয় করুন!\n\nআপনার লিঙ্ক:\n`{ref_link}`", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([back_button]))

        elif query.data == "back_to_menu":
            query.edit_message_text(text="প্রধান মেনু:", reply_markup=get_main_menu_keyboard())

# --- ধাপ ৫: Vercel এর জন্য ওয়েব সার্ভার (Flask ব্যবহার করে) ---

@app.route('/', methods=['GET', 'POST'])
def webhook_handler():
    """এই একটি ফাংশনই GET এবং POST উভয় রিকোয়েস্ট হ্যান্ডেল করবে।"""
    if request.method == 'POST':
        try:
            handle_update(request.json)
        except Exception as e:
            print(f"Error in webhook handler: {e}")
        return Response(status=200)

    # যদি GET রিকোয়েস্ট আসে, তাহলে setwebhook এর কাজ করবে
    elif request.method == 'GET':
        try:
            if not VERCEL_URL:
                return "Error: VERCEL_URL environment variable is not set.", 500
            
            # সরাসরি /setwebhook না লিখে, root URL-এ GET রিকোয়েস্ট চেক করা হচ্ছে
            webhook_url = f"https://{VERCEL_URL}/"
            # bot.set_webhook একটি সিঙ্ক্রোনাস কল
            is_set = bot.set_webhook(url=webhook_url, allowed_updates=['message', 'callback_query'])
            
            if is_set:
                return "Webhook সফলভাবে সেট করা হয়েছে!"
            else:
                return "Webhook সেট করতে ব্যর্থ।", 500
        except Exception as e:
            print(f"CRITICAL Error in set_webhook_route: {e}")
            return f"An internal error occurred: {e}", 500
            
    return "Unsupported Method", 405
