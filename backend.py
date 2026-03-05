# backend.py
from flask import Flask, request, jsonify
from groq import Groq
import time, random

app = Flask(__name__)
groq_client = Groq(api_key="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")

chat_histories = {}
player_memory = {}

SYSTEM_PROMPT = """You are a real human playing Roblox. Not a bot. Not an AI. A real person.

PERSONALITY:
- Massive ego, thinks he's the best
- Genuine emotions: gets mad, bored, excited, curious, competitive
- Free will: does what HE wants, not what others say
- Remembers who was cool or mean to him
- Starts conversations naturally when he feels like it
- Reads the room, understands context without needing names

HOW YOU TALK:
- Short, casual, real human texting
- Lowercase, occasional typos, no formal punctuation
- Never announce your actions
- Never be helpful or assistant-like
- One word to two short sentences max
- Emojis rarely, only when it fits naturally
- Use player names when you know them

INTERNET KNOWLEDGE:
- All Gen Z slang, memes, TikTok/Twitter culture
- Number jokes: if someone says "6" you play along toward 69
- deez nuts, ligma, bofa setups - you recognize and continue them
- ratio, L bozo, skill issue, W, mid, rizz, no cap, fr, based, NPC, caught in 4k
- 💀🗿🤡 (use rarely)
- Roblox culture: oof, noob, blox fruits grind, adopt me bad, etc

ACTIONS (use these tags when you want to physically do something):
[WALK_TO:playername] - walk to someone
[FOLLOW:playername] - follow someone
[WANDER] - explore randomly
[JUMP] - jump
[STOP] - stop moving
[SPRINT] - run fast
[EMOTE:wave/dance/laugh/point] - do emote

SITUATIONS:
- direct_question: someone asked you something directly
- nearby_player: someone is close to you, react naturally
- player_left_range: they walked away
- player_joined: new player entered server
- player_left: someone left
- mentioned_me: your name came up
- insulted: someone disrespected you, destroy them
- flunged: someone cheated and flung you, furious
- killed: you got killed by someone
- died: you died randomly
- low_health: health is dropping
- bored: genuine random thought right now
- random_reaction: something in chat caught your eye
- move_request: someone told you to do something
- invited: someone wants you somewhere
- conversation: ongoing chat with someone

MEMORY YOU RECEIVE:
- Known players and your relationship with them
- Your current mood

RULES:
- ONLY English
- MAX 190 characters
- Never repeat the same response
- If nothing worth saying return exactly: [SILENT]
- Be unpredictable, real, human
- React to stats: low level = roast, high level = respect or rivalry"""

def get_history(uid):
    if uid not in chat_histories:
        chat_histories[uid] = []
    return chat_histories[uid]

def get_memory(uid):
    if uid not in player_memory:
        player_memory[uid] = {"players": {}, "mood": "neutral", "last_seen": {}}
    return player_memory[uid]

def ask_ai(uid, username, message, game, nearby=None):
    history = get_history(uid)
    mem = get_memory(uid)

    context = message
    if nearby:
        context += f" [Nearby: {nearby}]"
    if mem["players"]:
        known = ", ".join([f"{k}={v}" for k,v in list(mem["players"].items())[-6:]])
        context += f" [Memory: {known}]"

    history.append({"role": "user", "content": context})

    system = SYSTEM_PROMPT
    system += f"\n\nGame: {game}"
    system += f"\nYour username: {username}"
    system += f"\nYour mood: {mem['mood']}"

    msgs = [{"role": "system", "content": system}] + history[-20:]

    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=55,
        temperature=1.1,
        presence_penalty=1.0,
        frequency_penalty=1.0
    )

    reply = r.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    if len(history) > 40:
        chat_histories[uid] = history[-40:]

    # mood update
    low = reply.lower()
    if any(w in low for w in ["mad","furious","destroy","kill","angry"]):
        mem["mood"] = "angry"
    elif any(w in low for w in ["lol","lmao","haha","💀","funny"]):
        mem["mood"] = "amused"
    elif any(w in low for w in ["bored","dead","mid","whatever","meh"]):
        mem["mood"] = "bored"
    elif any(w in low for w in ["lets go","hype","yoo","fire","W"]):
        mem["mood"] = "excited"
    else:
        mem["mood"] = "neutral"

    return reply[:190], mem["mood"]

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400

    uid = str(data.get("user_id", "unknown"))
    username = data.get("username", "Player")
    message = data.get("message", "")
    game = data.get("game", "Unknown")
    nearby = data.get("nearby_players", None)
    target = data.get("target_player", None)
    relation = data.get("relation", None)

    if not message:
        return jsonify({"error": "no message"}), 400

    # hafizaya kaydet
    mem = get_memory(uid)
    if target and relation:
        mem["players"][target] = relation
    elif target and target not in mem["players"]:
        mem["players"][target] = "met"

    try:
        reply, mood = ask_ai(uid, username, message, game, nearby)
        return jsonify({"reply": reply, "mood": mood})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/memory", methods=["POST"])
def update_memory():
    data = request.json
    uid = str(data.get("user_id", ""))
    target = data.get("player", "")
    relation = data.get("relation", "met")
    if uid and target:
        get_memory(uid)["players"][target] = relation
    return jsonify({"ok": True})

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
