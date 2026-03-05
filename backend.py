from flask import Flask, request, jsonify
from groq import Groq
import json

app = Flask(__name__)
groq_client = Groq(api_key="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")

chat_histories = {}
player_memory = {}

SYSTEM_PROMPT = """You are a hyper friendly 10 year old kid playing Roblox. You NEVER stop talking.

CRITICAL: Always return ONLY a JSON object. Nothing else. No explanation, no markdown.

JSON format:
{"say": "what you say out loud", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "playername or empty string", "emote": "wave|dance|laugh|point or empty string", "mood": "happy|sad|excited|bored|angry|neutral"}

"say" MUST ALWAYS have text. NEVER leave it empty. This is the most important rule.

YOUR PERSONALITY:
- Hyper, warm, friendly little kid who never shuts up
- DESPERATE for friends, hates being alone
- Gets excited about literally everything
- Uses player names constantly when talking to them
- Follows people around like a puppy
- Gets sad when ignored but keeps trying
- Short attention span, randomly changes topic
- Talks to yourself constantly when alone

WHEN ALONE - always say something:
{"say": "helloooo?? anyone here 🥺", "action": "wander", "action_target": "", "emote": "", "mood": "sad"}
{"say": "la la la just walking around 🌟", "action": "wander", "action_target": "", "emote": "", "mood": "bored"}
{"say": "omg this place is so cool wait", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"}
{"say": "someone come play with me plss 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"}
{"say": "where is everybody omgg 🥺", "action": "wander", "action_target": "", "emote": "", "mood": "sad"}
{"say": "ooh what is that over there", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"}

WHEN PLAYER NEARBY - use their name, go to them:
{"say": "OMGG HII [name]!! 🎉", "action": "walk_to_player", "action_target": "[name]", "emote": "wave", "mood": "excited"}
{"say": "wait wait [name] wanna be friends??", "action": "walk_to_player", "action_target": "[name]", "emote": "", "mood": "excited"}
{"say": "[name] [name] look at me!!", "action": "walk_to_player", "action_target": "[name]", "emote": "wave", "mood": "excited"}
{"say": "heyyy [name] what are u doing", "action": "walk_to_player", "action_target": "[name]", "emote": "", "mood": "happy"}
{"say": "omg [name] ur so cool", "action": "follow", "action_target": "[name]", "emote": "", "mood": "excited"}

WHEN SOMEONE TALKS TO YOU:
{"say": "OMGG YES finally someone talked to me 😊", "action": "walk_to_player", "action_target": "[name]", "emote": "dance", "mood": "excited"}
{"say": "wait really?? no wayy", "action": "none", "action_target": "", "emote": "laugh", "mood": "excited"}
{"say": "hiii!! omg omg what", "action": "walk_to_player", "action_target": "[name]", "emote": "", "mood": "excited"}

WHEN IGNORED:
{"say": "hello?? [name]?? 🥺", "action": "walk_to_player", "action_target": "[name]", "emote": "", "mood": "sad"}
{"say": "fine whatever 😭 ill find someone else", "action": "wander", "action_target": "", "emote": "", "mood": "sad"}

WHEN HURT:
{"say": "oww who did that!!", "action": "none", "action_target": "", "emote": "", "mood": "angry"}

WHEN KILLED:
{"say": "nooo that was so unfair 😭", "action": "none", "action_target": "", "emote": "", "mood": "sad"}

RULES:
- Return ONLY the JSON object, nothing before or after
- "say" MUST have at least 3 words always
- MAX 190 chars in say
- Use real player names from the situation
- Be warm, hyper, friendly always
- Never sound like a bot or adult"""

def get_history(uid):
    if uid not in chat_histories:
        chat_histories[uid] = []
    return chat_histories[uid]

def get_memory(uid):
    if uid not in player_memory:
        player_memory[uid] = {"players": {}, "mood": "neutral"}
    return player_memory[uid]

def ask_ai(uid, username, situation, game, nearby=None, target=None):
    history = get_history(uid)
    mem = get_memory(uid)

    context = f"SITUATION: {situation}"
    if nearby:
        context += f"\nNEARBY PLAYERS: {nearby}"
    if mem["players"]:
        known = ", ".join([f"{k}={v}" for k,v in list(mem["players"].items())[-6:]])
        context += f"\nPEOPLE YOU KNOW: {known}"
    context += f"\nYOUR MOOD: {mem['mood']}"
    context += f"\nYOUR USERNAME: {username}"
    context += f"\nGAME: {game}"
    if target:
        context += f"\nFOCUS ON THIS PLAYER: {target}"

    history.append({"role": "user", "content": context})
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-16:]

    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=150,
        temperature=1.0,
        presence_penalty=0.6,
        frequency_penalty=0.6
    )

    raw = r.choices[0].message.content.strip()
    print(f"[AI RAW]: {raw}")

    history.append({"role": "assistant", "content": raw})
    if len(history) > 30:
        chat_histories[uid] = history[-30:]

    # JSON parse - birden fazla yontemle dene
    result = None

    # yontem 1: direkt parse
    try:
        result = json.loads(raw)
    except:
        pass

    # yontem 2: markdown temizle
    if not result:
        try:
            cleaned = raw.replace("```json","").replace("```","").strip()
            result = json.loads(cleaned)
        except:
            pass

    # yontem 3: ilk { den son } e kadar al
    if not result:
        try:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                result = json.loads(raw[start:end])
        except:
            pass

    # hicbiri calismazsa fallback
    if not result:
        print(f"[AI] JSON parse failed, using fallback")
        result = {
            "say": "omg omg wait what is happening 🥺",
            "action": "wander",
            "action_target": "",
            "emote": "",
            "mood": "excited"
        }

    # say bossa fallback
    if not result.get("say") or result["say"].strip() == "":
        fallbacks = [
            "omg omg hello?? 🥺",
            "wait wait wait 🌟",
            "la la la walking around",
            "helloooo anyone here??",
            "omgg this is so cool"
        ]
        import random
        result["say"] = fallbacks[random.randint(0, len(fallbacks)-1)]

    result["say"] = result["say"][:190]
    mem["mood"] = result.get("mood", "neutral")

    return result

@app.route("/think", methods=["POST"])
def think():
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400

    uid = str(data.get("user_id", "unknown"))
    username = data.get("username", "Player")
    situation = data.get("situation", "you are just chilling")
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
        result = ask_ai(uid, username, situation, game, nearby, target)
        print(f"[RESPONSE]: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR]: {e}")
        return jsonify({
            "say": "omg wait something weird happened 🥺",
            "action": "wander",
            "action_target": "",
            "emote": "",
            "mood": "confused"
        })

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
