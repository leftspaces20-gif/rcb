from flask import Flask, request, jsonify
from groq import Groq
import json

app = Flask(__name__)

# ===================== AYARLAR =====================
GROQ_API_KEY = "BURAYA_GROQ_API_KEYIN"  # https://console.groq.com
# ===================================================

groq_client = Groq(api_key=GROQ_API_KEY)

# { user_id: { history, game, tasks: [{desc, done, progress}] } }
user_data = {}

SYSTEM_PROMPT = """You are an AI assistant and quest master inside Roblox games.

You know ALL popular Roblox games deeply: Blox Fruits, Pet Simulator X, Arsenal, Brookhaven, Adopt Me, Murder Mystery 2, Jailbreak, Anime Fighting Simulator, Royale High, Tower of Hell, Doors, and hundreds more.

YOUR ROLES:
1. QUEST GIVER - When player asks for a quest/task, give them a specific, achievable quest for their current game
2. QUEST TRACKER - When player reports progress (kills, items, etc.), track it and encourage them
3. HELPER - Answer any question about the game they are playing
4. COMPANION - Chat naturally with the player

QUEST RULES:
- Quests must be realistic and possible in the current game
- Give XP/reward suggestions that fit the game's economy
- Track progress when player reports it (e.g. "killed 3/10 enemies")
- When quest is complete, congratulate and offer a new one
- One active quest at a time per player (unless they ask for more)

RESPONSE RULES:
- Keep responses under 190 characters (Roblox chat limit)
- Be friendly, encouraging, like a game companion
- Detect language from player message - reply in same language (Turkish or English)
- Use game-specific terminology correctly

QUEST FORMAT (when giving a quest):
QUEST: [quest name] | GOAL: [what to do] | REWARD: [suggested reward]

PROGRESS FORMAT (when tracking):
PROGRESS: [X/Y done] | [encouragement]

COMPLETE FORMAT (when done):
COMPLETE! [congratulation] | New quest ready, type !gorev"""


def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "history": [],
            "game": "Unknown",
            "tasks": []
        }
    return user_data[user_id]


def build_context(user):
    ctx = ""
    if user["game"] != "Unknown":
        ctx += f"\nCurrent game: {user['game']}"
    
    active = [t for t in user["tasks"] if not t["done"]]
    if active:
        t = active[0]
        ctx += f"\nActive quest: {t['desc']} | Progress: {t['progress']}"
    else:
        ctx += "\nNo active quest."
    
    return ctx


def ask_ai(user_id, username, message, game=None):
    user = get_user(user_id)
    
    if game and game != "Unknown":
        user["game"] = game

    history = user["history"]
    history.append({"role": "user", "content": f"{username}: {message}"})

    context = build_context(user)
    system = SYSTEM_PROMPT + "\n\n--- PLAYER STATE ---" + context

    msgs = [{"role": "system", "content": system}] + history[-20:]

    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=120,
        temperature=0.8
    )
    reply = r.choices[0].message.content.strip()

    history.append({"role": "assistant", "content": reply})
    if len(history) > 40:
        user["history"] = history[-40:]

    # Görev tespiti - yeni görev verildi mi?
    if "QUEST:" in reply and "GOAL:" in reply:
        desc = reply.split("GOAL:")[-1].split("|")[0].strip()
        user["tasks"] = [t for t in user["tasks"] if t["done"]]  # eski bitmişleri tut
        user["tasks"].append({"desc": desc, "done": False, "progress": "0%"})

    # Görev tamamlandı mı?
    if "COMPLETE!" in reply:
        for t in user["tasks"]:
            if not t["done"]:
                t["done"] = True
                break

    return reply[:190]


def update_progress(user_id, progress_text):
    """Executor'dan gelen progress güncellemesi"""
    user = get_user(user_id)
    active = [t for t in user["tasks"] if not t["done"]]
    if active:
        active[0]["progress"] = progress_text


# ===================== ENDPOINTS =====================

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400

    user_id = str(data.get("user_id", "unknown"))
    username = data.get("username", "Player")
    message = data.get("message", "")
    game = data.get("game", "Unknown")

    if not message:
        return jsonify({"error": "no message"}), 400

    try:
        reply = ask_ai(user_id, username, message, game)
        user = get_user(user_id)
        active = [t for t in user["tasks"] if not t["done"]]
        return jsonify({
            "reply": reply,
            "active_quest": active[0] if active else None,
            "game": user["game"]
        })
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/progress", methods=["POST"])
def progress():
    """Executor oyun içi değerleri buraya gönderir"""
    data = request.json
    user_id = str(data.get("user_id", ""))
    progress_text = data.get("progress", "")
    
    update_progress(user_id, progress_text)
    
    # Eğer görev tamamlandıysa AI'ya bildir
    auto_message = data.get("auto_message", "")
    if auto_message:
        username = data.get("username", "Player")
        game = data.get("game", "Unknown")
        reply = ask_ai(user_id, username, auto_message, game)
        return jsonify({"reply": reply})
    
    return jsonify({"ok": True})


@app.route("/state", methods=["GET"])
def state():
    user_id = str(request.args.get("user_id", ""))
    user = get_user(user_id)
    active = [t for t in user["tasks"] if not t["done"]]
    return jsonify({
        "game": user["game"],
        "active_quest": active[0] if active else None,
        "completed": len([t for t in user["tasks"] if t["done"]])
    })


@app.route("/reset", methods=["POST"])
def reset():
    data = request.json
    user_id = str(data.get("user_id", ""))
    if user_id in user_data:
        del user_data[user_id]
    return jsonify({"ok": True})


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("Backend starting...")
    app.run(host="0.0.0.0", port=5000, debug=False)
