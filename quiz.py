import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from pymongo import MongoClient
import threading, os, time, json, io
import certifi 
from datetime import datetime

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://your-app.onrender.com") 
ADMIN_ID = 8557964907 

# Channel Details
CHANNEL_USERNAME = "@errorkid_05" 
CHANNEL_LINK = "https://t.me/errorkid_05"

MONGO_URI = os.getenv("MONGO_URI")

# 🎁 REFER AND EARN REWARDS (Yahan File IDs dalein)
# Format: {Referral_Count: "TELEGRAM_FILE_ID"}
# File ID paane ke liye bot ko file bhejein aur file_id copy karein.
REWARD_FILES = {
    2: "FILE_ID_FOR_2_REF",  # Replace with actual File ID
    5: "FILE_ID_FOR_5_REF",
    10: "FILE_ID_FOR_10_REF"
}

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
CORS(app)

# ==========================================
# 🗄️ DATABASE CONNECTION
# ==========================================
db_connected = False
try:
    if not MONGO_URI:
        print("⚠️ WARNING: MONGO_URI not found!")
    else:
        client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
        db = client['neet_bot_db']
        users_col = db['users']
        questions_col = db['questions']
        logs_col = db['score_logs']
        db_connected = True
        print("✅ Connected to MongoDB Cloud Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Failed: {e}")

# ==========================================
# 🔐 HELPER FUNCTIONS
# ==========================================
def check_membership(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        print(f"Membership Check Error: {e}")
        return False

def get_join_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 Join Channel (Must)", url=CHANNEL_LINK))
    markup.add(InlineKeyboardButton("🔄 Check Status", callback_data="check_sub"))
    return markup

def calculate_grade_stats(xp):
    level = 1; cost = 100; temp_xp = xp
    while temp_xp >= cost:
        temp_xp -= cost; level += 1; cost += 20
    percent = (temp_xp / cost) * 100
    return {"grade": level, "current_xp": temp_xp, "req_xp": cost, "percent": min(percent, 100)}

def parse_txt_file(content):
    lines = content.splitlines()
    meta = {"source": None, "type": None, "chapter": None}
    questions = []
    for line in lines[:15]:
        lower = line.lower()
        if "source:" in lower: meta["source"] = line.split(":",1)[1].strip()
        if "type:" in lower: meta["type"] = line.split(":",1)[1].strip()
        if "chapter:" in lower: meta["chapter"] = line.split(":",1)[1].strip()
    if not all(meta.values()): return None, "❌ Header Missing!"
    for line in lines:
        if "|" in line and "SOURCE:" not in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 6:
                try:
                    ans = int(parts[5]) - 1
                    if 0 <= ans <= 3:
                        questions.append({"q": parts[0], "opts": parts[1:5], "ans": ans})
                except: pass
    return meta, questions

# ==========================================
# 🤖 BOT HANDLERS (Updated with Refer & Admin)
# ==========================================
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    text = m.text.split()
    
    # REFERRAL LOGIC
    if len(text) > 1:
        referrer_id = text[1]
        # Check: Not self-referral, Referrer exists, New User check
        if referrer_id != str(uid) and db_connected:
            existing_user = users_col.find_one({"_id": uid})
            if not existing_user:
                # Increment referrer count
                users_col.update_one(
                    {"_id": int(referrer_id)},
                    {"$inc": {"referrals": 1}}
                )
                print(f"➕ Referral counted for {referrer_id}")

    # MEMBERSHIP CHECK
    if not check_membership(uid):
        bot.send_message(
            m.chat.id, 
            "⚠️ **Access Denied!**\n\nYou must join our official channel to use this bot.\nJoin and click 'Check Status'.", 
            reply_markup=get_join_markup(),
            parse_mode="Markdown"
        )
        return

    app_url = os.getenv("WEB_APP_URL", WEB_APP_URL)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🧬 OPEN NEET PRO", web_app=WebAppInfo(url=app_url)))
    markup.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
    bot.send_message(m.chat.id, f"Welcome Future Doctor, {m.from_user.first_name}! 🩺\n\n✅ **Verification Successful**", reply_markup=markup)

# --- 1. BROADCAST FEATURE ---
@bot.message_handler(commands=['broadcast'])
def broadcast_msg(m):
    if m.from_user.id != ADMIN_ID: return
    msg = m.text.replace("/broadcast", "").strip()
    if not msg:
        bot.reply_to(m, "❌ Message text missing!")
        return
    
    if not db_connected: return
    users = users_col.find({}, {"_id": 1})
    count = 0
    bot.reply_to(m, "🚀 Broadcast Started...")
    
    for u in users:
        try:
            bot.send_message(u['_id'], msg)
            count += 1
            time.sleep(0.05) # Prevent flood wait
        except: pass
    bot.reply_to(m, f"✅ Broadcast sent to {count} users.")

# --- 2. BACKUP & RESTORE FEATURE ---
@bot.message_handler(commands=['backup'])
def backup_db(m):
    if m.from_user.id != ADMIN_ID or not db_connected: return
    
    # Export Users & Questions
    users = list(users_col.find())
    questions = list(questions_col.find({}, {"_id": 0})) # Exclude ObjectId for clean JSON
    
    backup_data = {
        "users": users,
        "questions": questions,
        "timestamp": str(datetime.now())
    }
    
    # Create In-Memory File
    json_str = json.dumps(backup_data, default=str, indent=2)
    bio = io.BytesIO(json_str.encode('utf-8'))
    bio.name = f"backup_{int(time.time())}.json"
    
    bot.send_document(m.chat.id, bio, caption="📂 Database Backup")

@bot.message_handler(commands=['restore'])
def restore_db(m):
    if m.from_user.id != ADMIN_ID: return
    bot.reply_to(m, "📂 Please reply to this message with the Backup JSON file.")
    bot.register_next_step_handler(m, process_restore)

def process_restore(m):
    if not m.document or not db_connected: return
    try:
        file_info = bot.get_file(m.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        data = json.loads(downloaded)
        
        # Restore logic (Upsert to prevent duplicate errors)
        if 'questions' in data:
            for q in data['questions']:
                questions_col.update_one(
                    {"source": q.get('source'), "type": q.get('type'), "chapter": q.get('chapter')},
                    {"$set": q}, upsert=True
                )
        
        if 'users' in data:
            for u in data['users']:
                uid = u.pop('_id', None)
                if uid:
                    users_col.update_one({"_id": uid}, {"$set": u}, upsert=True)
                    
        bot.reply_to(m, "✅ Database Restored Successfully!")
    except Exception as e:
        bot.reply_to(m, f"❌ Restore Failed: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    uid = call.from_user.id
    if check_membership(uid):
        bot.answer_callback_query(call.id, "✅ Verified!")
        app_url = os.getenv("WEB_APP_URL", WEB_APP_URL)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🧬 OPEN NEET PRO", web_app=WebAppInfo(url=app_url)))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"Welcome Future Doctor, {call.from_user.first_name}! 🩺\n\n✅ **Verification Successful**",
            reply_markup=markup
        )
    else:
        bot.answer_callback_query(call.id, "❌ Not Joined Yet!", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if str(message.from_user.id) != str(ADMIN_ID): return 
    # File ID helper for Admin to setup rewards
    if message.caption == "id":
        bot.reply_to(message, f"File ID: `{message.document.file_id}`", parse_mode="Markdown")
        return

    if not db_connected: 
        bot.reply_to(message, "❌ DB Error")
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        content = downloaded.decode('utf-8')
        meta, data = parse_txt_file(content)
        if not meta: 
            bot.reply_to(message, data)
            return

        filter_q = {"source": meta['source'], "type": meta['type'], "chapter": meta['chapter']}
        update_q = {"$set": {"source": meta['source'], "type": meta['type'], "chapter": meta['chapter'], "data": data}}
        questions_col.update_one(filter_q, update_q, upsert=True)
        bot.reply_to(message, f"☁️ Saved: {meta['chapter']} ({len(data)} Qs)")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

# ==========================================
# 🌐 API ROUTES
# ==========================================
@app.route('/')
def index(): return render_template('quiz.html')

@app.route('/api/get_data')
def get_data():
    if not db_connected: return jsonify({})
    all_docs = questions_col.find({}, {"_id": 0})
    tree = {}
    for doc in all_docs:
        src, typ, chap = doc['source'], doc['type'], doc['chapter']
        if src not in tree: tree[src] = {}
        if typ not in tree[src]: tree[src] = {}
        tree[src][typ][chap] = doc['data']
    return jsonify(tree)

@app.route('/api/user/sync', methods=['POST'])
def sync_user():
    if not db_connected: return jsonify({"error": "No DB"})
    data = request.json
    uid, name = str(data.get('id')), data.get('name')
    score_add = int(data.get('add_score', 0))
    mistakes = data.get('mistakes', []); solved = data.get('solved', [])
    
    user = users_col.find_one({"_id": int(uid)})
    if not user: 
        user = {"_id": int(uid), "name": name, "xp": 0, "mistakes": [], "referrals": 0, "claimed": []}
        users_col.insert_one(user)
    
    new_xp = max(0, user.get('xp', 0) + score_add)
    if score_add > 0: logs_col.insert_one({"uid": int(uid), "name": name, "score": score_add, "ts": time.time()})
    
    curr_mistakes = user.get('mistakes', [])
    exist = {m['q'] for m in curr_mistakes}
    for m in mistakes: 
        if m['q'] not in exist: curr_mistakes.append(m)
    if solved: curr_mistakes = [m for m in curr_mistakes if m['q'] not in solved]
        
    users_col.update_one({"_id": int(uid)}, {"$set": {"xp": new_xp, "name": name, "mistakes": curr_mistakes}})
    stats = calculate_grade_stats(new_xp)
    return jsonify({"grade": f"Grade {stats['grade']}", "current_xp": stats['current_xp'], "req_xp": stats['req_xp'], "percent": stats['percent'], "mistake_count": len(curr_mistakes), "mistakes_list": curr_mistakes})

# --- 4. REFERRAL SYSTEM APIs ---
@app.route('/api/referral/stats', methods=['GET'])
def get_ref_stats():
    if not db_connected: return jsonify({"count": 0, "claimed": []})
    uid = request.args.get('uid')
    user = users_col.find_one({"_id": int(uid)})
    if user:
        return jsonify({
            "count": user.get('referrals', 0),
            "claimed": user.get('claimed', [])
        })
    return jsonify({"count": 0, "claimed": []})

@app.route('/api/referral/claim', methods=['POST'])
def claim_reward():
    if not db_connected: return jsonify({"error": "No DB"})
    data = request.json
    uid = int(data.get('uid'))
    milestone = int(data.get('milestone'))
    
    user = users_col.find_one({"_id": uid})
    current_refs = user.get('referrals', 0)
    claimed = user.get('claimed', [])
    
    # Validate
    if milestone not in REWARD_FILES: return jsonify({"error": "Invalid Reward"})
    if milestone in claimed: return jsonify({"error": "Already Claimed"})
    if current_refs < milestone: return jsonify({"error": "Not enough referrals"})
    
    # Send File
    try:
        file_id = REWARD_FILES[milestone]
        bot.send_document(uid, file_id, caption=f"🎁 Congratulations! Here is your reward for {milestone} referrals.")
        
        # Update DB
        users_col.update_one({"_id": uid}, {"$push": {"claimed": milestone}})
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/api/leaderboard/<filter>')
def leaderboard(filter):
    if not db_connected: return jsonify({"top": [], "user": None})
    uid_req = request.args.get('uid')
    try: uid_req = int(uid_req)
    except: uid_req = 0
    
    now = time.time(); pipeline = []
    if filter == 'daily': pipeline.append({"$match": {"ts": {"$gt": now - 86400}}})
    elif filter == 'weekly': pipeline.append({"$match": {"ts": {"$gt": now - 604800}}})
    
    if filter == 'all':
        top_cursor = users_col.find().sort("xp", -1).limit(100)
        top_100 = [{"rank": i+1, "name": u['name'], "score": u.get('xp', 0), "uid": u['_id']} for i, u in enumerate(top_cursor)]
    else:
        pipeline.extend([{"$group": {"_id": "$uid", "name": {"$first": "$name"}, "total": {"$sum": "$score"}}}, {"$sort": {"total": -1}}, {"$limit": 100}])
        results = list(logs_col.aggregate(pipeline))
        top_100 = [{"rank": i+1, "name": r['name'], "score": r['total'], "uid": r['_id']} for i, r in enumerate(results)]
    
    user_rank = None
    if uid_req:
        for u in top_100:
            if u['uid'] == uid_req: user_rank = u; break
    return jsonify({"top": top_100, "user": user_rank})

@app.route('/api/admin/delete', methods=['POST'])
def delete_item():
    if not db_connected: return jsonify({"error": "No DB"})
    data = request.json
    if str(data.get('uid')) != str(ADMIN_ID): return jsonify({"error": "Unauthorized"})
    path, target = data.get('path', []), data.get('target')
    try:
        if len(path) == 0: questions_col.delete_many({"source": target})
        elif len(path) == 1: questions_col.delete_many({"source": path[0], "type": target})
        elif len(path) == 2: questions_col.delete_one({"source": path[0], "type": path[1], "chapter": target})
        return jsonify({"status": "deleted"})
    except: return jsonify({"error": "DB Error"})

if __name__ == "__main__":
    t = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))))
    t.start()
    bot.infinity_polling()
