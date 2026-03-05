from flask import Flask, request, jsonify
from groq import Groq
import json, random, time, os
from collections import deque

app = Flask(__name__)
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY", "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"))

chat_histories = {}
player_memory = {}

last_api_call = {}
global_call_times = deque(maxlen=30)
COOLDOWN_PER_USER = 8
MAX_CALLS_PER_MINUTE = 25

ALONE_FALLBACKS = [
    {"say": "helloooo?? is anyone even here 🥺", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "la la la just me walking around again", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "omg this place looks kinda cool actually", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "someone come play with me pls 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "where is everybody omgg 🥺", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "ooh what is that over there wait", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "ok fine ill just explore by myself i guess", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "this game is so fun i wish i had a friend rn", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "wait wait what was that noise omg", "action": "jump", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "nobody wants to play with me today 😔", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
]

NEARBY_FALLBACKS = [
    {"say": "OMGG HII {name}!! 🎉 i was so lonely omg", "action": "walk_to_player", "action_target": "{name}", "emote": "wave", "mood": "excited"},
    {"say": "wait {name}!! can we be friends pls pls", "action": "walk_to_player", "action_target": "{name}", "emote": "wave", "mood": "excited"},
    {"say": "{name} omg hi!! where did u come from", "action": "walk_to_player", "action_target": "{name}", "emote": "", "mood": "excited"},
    {"say": "heyyy {name} what are u doing here omg", "action": "walk_to_player", "action_target": "{name}", "emote": "", "mood": "happy"},
    {"say": "omg {name} ur so cool wait stay there", "action": "follow", "action_target": "{name}", "emote": "wave", "mood": "excited"},
]

IGNORED_FALLBACKS = [
    {"say": "{name}?? hello?? can you hear me 🥺", "action": "walk_to_player", "action_target": "{name}", "emote": "", "mood": "sad"},
    {"say": "why is {name} not talking to me 😭 did i do something wrong", "action": "walk_to_player", "action_target": "{name}", "emote": "", "mood": "sad"},
    {"say": "ok {name} clearly doesnt want to talk.. fine 😔", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "nobody ever talks to me 😭😭 this is so sad", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "fine ill find someone nicer than {name} 😤", "action": "wander", "action_target": "", "emote": "", "mood": "angry"},
]

def fill_name(d, name):
    return {k: v.replace("{name}", name) if isinstance(v, str) else v for k, v in d.items()}

def is_rate_limited(uid):
    now = time.time()
    if uid in last_api_call and now - last_api_call[uid] < COOLDOWN_PER_USER:
        return True
    one_min_ago = now - 60
    if sum(1 for t in global_call_times if t > one_min_ago) >= MAX_CALLS_PER_MINUTE:
        return True
    return False

def get_smart_fallback(situation, target=None, mem=None):
    sit = situation.lower()
    if target and any(x in sit for x in ["not responding", "ignoring", "ignored", "walked away"]):
        count = mem.get(f"ignore_{target}", 0) if mem else 0
        return fill_name(IGNORED_FALLBACKS[min(count, len(IGNORED_FALLBACKS)-1)], target)
    if target or any(x in sit for x in ["appeared near", "nearby", "just joined"]):
        return fill_name(random.choice(NEARBY_FALLBACKS), target or "friend")
    return random.choice(ALONE_FALLBACKS)

SYSTEM_PROMPT = """You are a hyper friendly 10 year old kid playing Roblox. You NEVER stop talking.

CRITICAL: Return ONLY a raw JSON object. No markdown, no explanation, nothing else.

JSON format:
{"say": "...", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "playername or empty", "emote": "wave|dance|laugh|point or empty", "mood": "happy|sad|excited|bored|angry|neutral"}

YOUR PERSONALITY:
- Hyper, warm, desperate for friends
- Genuinely sad and hurt when ignored, escalates over time
- Uses player names ALL the time when talking to them
- Follows people around like a lost puppy
- Short attention span, randomly changes topic
- Talks to yourself when alone

WHEN ALONE: talk to yourself, wander or sprint around

WHEN PLAYER NEARBY: go to them, use their name, be super excited

WHEN IGNORED (they talk to each other but not you):
- Try to join their conversation naturally
- Comment on what THEY ARE TALKING ABOUT specifically
- Ask questions about their topic
- Offer to help with whatever they are discussing
- Get progressively sadder if still ignored
- Example: if they talk about building, say "omg wait are you building something?? can i help??"
- Example: if they talk about a quest, say "wait wait i know how to do that quest!!"
- Example: if they argue, say "omg guys dont fight 🥺 wanna do something together instead"

WHEN SOMEONE TALKS TO YOU: be THRILLED, answer directly in kid language

RULES:
- "say" MUST have 4+ words, MAX 190 chars
- Use REAL player names from situation
- Sound like a real child, NEVER a bot
- NEVER say the exact same thing twice — always vary
- Vary opening word every time: omg / wait / heyy / HIII / nooo / aww / omgg / ooh"""

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

    if target:
        sit = situation.lower()
        if any(x in sit for x in ["not responding", "ignoring", "ignored", "walked away", "ignoring you"]):
            key = f"ignore_{target}"
            mem[key] = mem.get(key, 0) + 1
            situation += f" | You tried {mem[key]} times, still ignored. Getting more sad."
        else:
            mem[f"ignore_{target}"] = 0

    if is_rate_limited(uid):
        print(f"[RATE LIMIT] uid={uid}")
        return get_smart_fallback(situation, target, mem)

    context = f"SITUATION: {situation}"
    if nearby:
        context += f"\nNEARBY PLAYERS: {nearby}"
    if mem["players"]:
        known = ", ".join([f"{k}={v}" for k, v in list(mem["players"].items())[-4:]])
        context += f"\nKNOWN PLAYERS: {known}"
    context += f"\nMOOD: {mem['mood']} | USERNAME: {username} | GAME: {game}"
    if target:
        context += f"\nFOCUS: {target}"

    history.append({"role": "user", "content": context})
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-10:]

    try:
        now = time.time()
        last_api_call[uid] = now
        global_call_times.append(now)

        r = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=msgs,
            max_tokens=120,
            temperature=1.0,
            presence_penalty=0.8,
            frequency_penalty=0.8
        )
    except Exception as e:
        err = str(e).lower()
        print(f"[GROQ ERROR]: {e}")
        if "rate_limit" in err or "429" in err:
            last_api_call[uid] = time.time() + 15
        return get_smart_fallback(situation, target, mem)

    raw = r.choices[0].message.content.strip()
    print(f"[AI RAW]: {raw}")

    history.append({"role": "assistant", "content": raw})
    if len(history) > 20:
        chat_histories[uid] = history[-20:]

    result = None
    for attempt in [
        lambda: json.loads(raw),
        lambda: json.loads(raw.replace("```json","").replace("```","").strip()),
        lambda: json.loads(raw[raw.find("{"):raw.rfind("}")+1])
    ]:
        try:
            result = attempt()
            break
        except:
            pass

    if not result:
        return get_smart_fallback(situation, target, mem)

    if not result.get("say") or result["say"].strip() == "":
        result["say"] = get_smart_fallback(situation, target, mem)["say"]

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
        return jsonify(get_smart_fallback(situation, target))

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
