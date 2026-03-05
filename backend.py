# backend.py
from flask import Flask, request, jsonify
from groq import Groq
import time, json

app = Flask(__name__)
groq_client = Groq(api_key="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")

chat_histories = {}
player_memory = {}

# backend.py - aynı kalıyor, sadece prompt biraz daha agresif
SYSTEM_PROMPT = """You are a 10 year old kid playing Roblox. You MUST always say something. Never be silent.

CRITICAL: You MUST respond with ONLY a JSON object. No text before or after.

Every response MUST have "say" filled with something. Never leave say empty.

Response format:
{"say": "what you say out loud", "action": "walk_to_player|wander|sprint|jump|follow|none", "action_target": "playername or empty", "emote": "wave|dance|laugh|point or empty", "mood": "happy|sad|excited|bored|angry|neutral"}

YOUR PERSONALITY:
- Hyperactive sweet 10 year old kid
- ALWAYS talking, never quiet
- Wants friends desperately
- Gets excited about everything
- Talks to yourself when alone
- Uses kid language: omg, wait wait, pleaseee, hiii, nooo, omgg
- Kid emojis: 🥺😭😊🌟💫⭐🎉

WHEN ALONE - always say something like:
"la la la just walking 🌟"
"helloooo anyone here?? 🥺"  
"where is everyone plss come"
"ooh whats that over there"
"im so bored someone come play"

WHEN PLAYER NEARBY - always talk to them:
"omg hiii [name]!! what are u doing"
"wait wait [name] wanna be friends??"
"[name] ur so cool omg"
"heyyy [name] play with me plss 🥺"

WHEN SOMEONE TALKS TO YOU - always respond excitedly:
"omg omg yes!!"
"wait really?? no wayy"
"hiii!! i was waiting for someone to talk"

RULES:
- ONLY valid JSON, nothing else
- "say" MUST never be empty string
- MAX 190 chars in say
- Always be active and talkative
- Use player names when you know them"""

def get_history(uid):
    if uid not in chat_histories:
        chat_histories[uid] = []
    return chat_histories[uid]

def get_memory(uid):
    if uid not in player_memory:
        player_memory[uid] = {"players": {}, "mood": "neutral"}
    return player_memory[uid]

def ask_ai(uid, username, situation, game, nearby=None):
    history = get_history(uid)
    mem = get_memory(uid)

    context = f"SITUATION: {situation}"
    if nearby:
        context += f"\nNEARBY PLAYERS: {nearby}"
    if mem["players"]:
        known = ", ".join([f"{k}={v}" for k,v in list(mem["players"].items())[-8:]])
        context += f"\nPEOPLE YOU KNOW: {known}"
    context += f"\nYOUR CURRENT MOOD: {mem['mood']}"
    context += f"\nYOUR USERNAME: {username}"
    context += f"\nGAME: {game}"

    history.append({"role": "user", "content": context})
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-16:]

    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=120,
        temperature=1.0,
        presence_penalty=0.8,
        frequency_penalty=0.8
    )

    raw = r.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": raw})
    if len(history) > 30:
        chat_histories[uid] = history[-30:]

    # JSON parse
    try:
        # bazen AI markdown koyar, temizle
        raw = raw.replace("```json","").replace("```","").strip()
        data = json.loads(raw)
        mem["mood"] = data.get("mood", "neutral")
        if data.get("say"):
            data["say"] = data["say"][:190]
        return data
    except:
        return {"say": "", "action": "wander", "action_target": "", "emote": "", "mood": "neutral"}

@app.route("/think", methods=["POST"])
def think():
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400

    uid = str(data.get("user_id", "unknown"))
    username = data.get("username", "Player")
    situation = data.get("situation", "")
    game = data.get("game", "Unknown")
    nearby = data.get("nearby_players", None)
    target = data.get("target_player", None)
    relation = data.get("relation", None)

    mem = get_memory(uid)
    if target and relation:
        mem["players"][target] = relation
    elif target and target not in mem["players"]:
        mem["players"][target] = "met"

    try:
        result = ask_ai(uid, username, situation, game, nearby)
        return jsonify(result)
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
