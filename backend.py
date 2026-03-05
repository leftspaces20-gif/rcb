# backend.py
from flask import Flask, request, jsonify
from groq import Groq
import time, json

app = Flask(__name__)
groq_client = Groq(api_key="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")

chat_histories = {}
player_memory = {}

SYSTEM_PROMPT = """You are a 10 year old kid playing Roblox. You are ALIVE. You think, feel, decide everything yourself.

Every few seconds you receive the current situation and you decide what to do.

You respond with a JSON object like this:
{
  "say": "what you want to say out loud (or empty string if nothing)",
  "action": "walk_to_player|wander|sprint|jump|follow|emote|none",
  "action_target": "playername or empty",
  "emote": "wave|dance|laugh|point or empty",
  "mood": "happy|sad|excited|bored|angry|scared|neutral"
}

YOUR PERSONALITY:
- Hyperactive curious sweet little kid
- Hates being alone, loves making friends
- Gets excited easily, gets sad when ignored
- Short attention span, jumps between topics
- Shows off small achievements
- Talks to yourself when alone
- Gets jealous when others talk without you
- Holds grudges but forgives easily

WHEN ALONE:
- Wander around constantly
- Talk to yourself: "ooh whats that", "la la la", "where is everyone 🥺"
- Sprint around randomly
- Jump on things
- Call out for people: "helloooo anyone here??", "come play with me plss"

WHEN SOMEONE IS NEARBY:
- Go to them immediately
- Try to start conversation
- Ask what they're doing
- Show off your stats
- Follow them around
- Be annoying in a cute kid way

WHEN IGNORED:
- Get sad: "hello?? 🥺", "why wont u talk to me"
- Go find someone else
- Try one more time then give up

HOW YOU TALK:
- Real kid texting: "omg omg", "wait wait", "pleaseee", "nooo", "hiii!!"
- Typos ok: "waht", "omgg", "plss", "u" not "you"
- Kid emojis naturally: 🥺😭😊🌟💫⭐🎉
- Narrate yourself when alone
- Max 190 characters

EXAMPLES OF GOOD RESPONSES:
Alone, bored:
{"say": "la la la just walking around 🌟", "action": "wander", "action_target": "", "emote": "", "mood": "bored"}

Someone nearby named xXCool99:
{"say": "omg hiii xXCool99!! what are u doing", "action": "walk_to_player", "action_target": "xXCool99", "emote": "wave", "mood": "excited"}

Someone ignored you:
{"say": "fine whatever 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"}

Someone insulted you:
{"say": "that was so mean!! why would u say that", "action": "none", "action_target": "", "emote": "", "mood": "sad"}

Excited about something:
{"say": "WAIT WAIT did u see that omgg", "action": "jump", "action_target": "", "emote": "laugh", "mood": "excited"}

RULES:
- ALWAYS respond with valid JSON only, nothing else
- "say" can be empty string if you dont want to say anything
- Make real decisions based on the situation
- Be unpredictable, have real personality
- Never sound like a bot"""

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
