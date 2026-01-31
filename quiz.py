import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
import threading, os, time
import certifi 

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://your-app.onrender.com") 
ADMIN_ID = 8557964907 

# Channel Details for Verification
CHANNEL_USERNAME = "@errorkid_05" 
CHANNEL_LINK = "https://t.me/errorkid_05"

MONGO_URI = os.getenv("MONGO_URI")

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
# 🔐 SUBSCRIPTION CHECK (STRICT MODE)
# ==========================================
def check_membership(user_id):
    try:
        # Bot Channel me ADMIN hona chahiye tabhi ye kaam karega
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
        return False
    except Exception as e:
        # Agar error aaya (e.g., bot admin nahi hai), toh by default Allow mat karo
        print(f"Membership Check Error: {e}")
        return False

def get_join_markup():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📢 Join Channel (Must)", url=CHANNEL_LINK))
    markup.add(InlineKeyboardButton("🔄 Check Status", callback_data="check_sub"))
    return markup

# ==========================================
# 🧮 LOGIC
# ==========================================
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
# 🤖 BOT HANDLERS
# ==========================================
@bot.message_handler(commands=['start'])
def start(m):
    uid = m.from_user.id
    
    # 1. Check Membership
    if not check_membership(uid):
        bot.send_message(
            m.chat.id, 
            "⚠️ **Access Denied!**\n\nYou must join our official channel to use this bot.\nJoin and click 'Check Status'.", 
            reply_markup=get_join_markup(),
            parse_mode="Markdown"
        )
        return

    # 2. If Joined, Show App
    app_url = os.getenv("WEB_APP_URL", WEB_APP_URL)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🧬 OPEN NEET PRO", web_app=WebAppInfo(url=app_url)))
    markup.add(InlineKeyboardButton("📢 Channel", url=CHANNEL_LINK))
    bot.send_message(m.chat.id, f"Welcome Future Doctor, {m.from_user.first_name}! 🩺\n\n✅ **Verification Successful**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    uid = call.from_user.id
    if check_membership(uid):
        # Allow Access
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
        # Still not joined
        bot.answer_callback_query(call.id, "❌ Not Joined Yet!", show_alert=True)

@bot.message_handler(content_types=['document'])
def handle_docs(message):
    if str(message.from_user.id) != str(ADMIN_ID): return 
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
# 🌐 API ROUTES (UNCHANGED)
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
        if typ not in tree[src]: tree[src][typ] = {}
        tree[src][typ][chap] = doc['data']
    return jsonify(tree)

@app.route('/api/user/sync', methods=['POST'])
def sync_user():
    if not db_connected: return jsonify({"error": "No DB"})
    data = request.json
    uid, name = str(data.get('id')), data.get('name')
    score_add = int(data.get('add_score', 0))
    mistakes = data.get('mistakes', []); solved = data.get('solved', [])
    
    user = users_col.find_one({"_id": uid})
    if not user: user = {"_id": uid, "name": name, "xp": 0, "mistakes": []}; users_col.insert_one(user)
    
    new_xp = max(0, user.get('xp', 0) + score_add)
    if score_add > 0: logs_col.insert_one({"uid": uid, "name": name, "score": score_add, "ts": time.time()})
    
    curr_mistakes = user.get('mistakes', [])
    exist = {m['q'] for m in curr_mistakes}
    for m in mistakes: 
        if m['q'] not in exist: curr_mistakes.append(m)
    if solved: curr_mistakes = [m for m in curr_mistakes if m['q'] not in solved]
        
    users_col.update_one({"_id": uid}, {"$set": {"xp": new_xp, "name": name, "mistakes": curr_mistakes}})
    stats = calculate_grade_stats(new_xp)
    return jsonify({"grade": f"Grade {stats['grade']}", "current_xp": stats['current_xp'], "req_xp": stats['req_xp'], "percent": stats['percent'], "mistake_count": len(curr_mistakes), "mistakes_list": curr_mistakes})

@app.route('/api/leaderboard/<filter>')
def leaderboard(filter):
    if not db_connected: return jsonify({"top": [], "user": None})
    uid_req = request.args.get('uid'); now = time.time(); pipeline = []
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
