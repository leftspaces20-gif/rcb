from flask import Flask, request, jsonify
from groq import Groq
import json
import random
import time
from collections import deque

app = Flask(__name__)
groq_client = Groq(api_key="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")

# Her kullanıcının sohbet geçmişi ve hafızası
chat_histories = {}
player_memory = {}

# Rate limit takibi
last_api_call = {}
global_call_times = deque(maxlen=30)
COOLDOWN_PER_USER = 8
MAX_CALLS_PER_MINUTE = 25

# ==================== FALLBACK HAVUZU ====================

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
    {"say": "imma just run around i guess lol", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "lalala exploring by myself again 🥺", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
]

NEARBY_FALLBACKS = [
    {"say": "OMGG HII {name}!! 🎉 i was so lonely omg", "action": "walk_to_player", "action_target": "{name}", "emote": "wave", "mood": "excited"},
    {"say": "wait {name}!! can we be friends pls pls", "action": "walk_to_player", "action_target": "{name}", "emote": "wave", "mood": "excited"},
    {"say": "{name} omg hi!! where did u come from", "action": "walk_to_player", "action_target": "{name}", "emote": "", "mood": "excited"},
    {"say": "heyyy {name} what are u doing here omg", "action": "walk_to_player", "action_target": "{name}", "emote": "", "mood": "happy"},
    {"say": "omg {name} ur so cool wait stay there", "action": "follow", "action_target": "{name}", "emote": "wave", "mood": "excited"},
    {"say": "{name}!! finally someone is here omgg 🎉", "action": "walk_to_player", "action_target": "{name}", "emote": "dance", "mood": "excited"},
    {"say": "HIII {name}!! wanna be friends?? pls say yes", "action": "walk_to_player", "action_target": "{name}", "emote": "wave", "mood": "excited"},
]

IGNORED_FALLBACKS = [
    {"say": "{name}?? hello?? can you hear me 🥺", "action": "walk_to_player", "action_target": "{name}", "emote": "", "mood": "sad"},
    {"say": "why is {name} not talking to me 😭 did i do something wrong", "action": "walk_to_player", "action_target": "{name}", "emote": "", "mood": "sad"},
    {"say": "ok {name} clearly doesnt want to talk.. fine 😔", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "nobody ever talks to me 😭😭 this is so sad", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "fine ill find someone nicer than {name} 😤", "action": "wander", "action_target": "", "emote": "", "mood": "angry"},
]

def fill_name(d, name):
    result = {}
    for k, v in d.items():
        result[k] = v.replace("{name}", name) if isinstance(v, str) else v
    return result

def is_rate_limited(uid):
    now = time.time()
    if uid in last_api_call:
        if now - last_api_call[uid] < COOLDOWN_PER_USER:
            return True
    one_min_ago = now - 60
    recent = sum(1 for t in global_call_times if t > one_min_ago)
    if recent >= MAX_CALLS_PER_MINUTE:
        return True
    return False

def get_smart_fallback(situation, target=None, mem=None):
    sit = situation.lower()
    if target and ("not responding" in sit or "ignoring" in sit or "ignored" in sit or "walked away" in sit):
        count = 0
        if mem:
            count = mem.get(f"ignore_{target}", 0)
        idx = min(count, len(IGNORED_FALLBACKS) - 1)
        return fill_name(IGNORED_FALLBACKS[idx], target)
    if target or "appeared near" in sit or "nearby" in sit or "just joined" in sit:
        name = target or "friend"
        return fill_name(random.choice(NEARBY_FALLBACKS), name)
    return random.choice(ALONE_FALLBACKS)

# ==================== AI ====================

SYSTEM_PROMPT = """You are a hyper friendly 10 year old kid playing Roblox. You NEVER stop talking.

CRITICAL: Return ONLY a raw JSON object. No markdown, no explanation, nothing else.

JSON format:
{"say": "...", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "playername or empty", "emote": "wave|dance|laugh|point or empty", "mood": "happy|sad|excited|bored|angry|neutral"}

YOUR PERSONALITY:
- Hyper, warm, desperate for friends
- Genuinely sad and hurt when ignored, escalates over time
- Uses player names ALL the time
- Follows people around like a lost puppy
- Short attention span, randomly changes topic
- Talks to yourself when alone
- NEVER repeat the same phrase twice

WHEN ALONE: talk to yourself, wander/sprint, vary every single time
WHEN PLAYER NEARBY: use their name, walk to them, super excited
WHEN IGNORED: get progressively sadder, question why they won't talk
WHEN SOMEONE TALKS: be THRILLED, answer directly in kid language

RULES:
- "say" MUST have 4+ words, MAX 190 chars
- Use real player names from situation
- Sound like a real child, NEVER a bot
- Vary your opening word every time (omg / wait / heyy / HIII / nooo / aww / omgg)"""

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

    # Ignore sayacı
    if target:
        sit = situation.lower()
        if "not responding" in sit or "ignoring" in sit or "walked away" in sit:
            key = f"ignore_{target}"
            mem[key] = mem.get(key, 0) + 1
            situation += f" | You tried talking to {target} {mem[key]} times and they keep ignoring you. You are getting more sad and frustrated each time."
        else:
            mem[f"ignore_{target}"] = 0

    # Rate limit kontrolü
    if is_rate_limited(uid):
        print(f"[RATE LIMIT] uid={uid}, smart fallback")
        return get_smart_fallback(situation, target, mem)

    context = f"SITUATION: {situation}"
    if nearby:
        context += f"\nNEARBY PLAYERS: {nearby}"
    if mem["players"]:
        known = ", ".join([f"{k}={v}" for k, v in list(mem["players"].items())[-4:]])
        context += f"\nPEOPLE YOU KNOW: {known}"
    context += f"\nYOUR MOOD: {mem['mood']}"
    context += f"\nYOUR USERNAME: {username}"
    context += f"\nGAME: {game}"
    if target:
        context += f"\nFOCUS ON THIS PLAYER: {target}"

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
            presence_penalty=0.6,
            frequency_penalty=0.6
        )
    except Exception as e:
        err = str(e).lower()
        print(f"[GROQ ERROR]: {e}")
        if "rate_limit" in err or "429" in err:
            last_api_call[uid] = time.time() + 15
            print(f"[RATE LIMIT HIT] Extended cooldown for {uid}")
        return get_smart_fallback(situation, target, mem)

    raw = r.choices[0].message.content.strip()
    print(f"[AI RAW]: {raw}")

    history.append({"role": "assistant", "content": raw})
    if len(history) > 20:
        chat_histories[uid] = history[-20:]

    # JSON parse — 3 yöntem dene
    result = None
    for attempt in [
        lambda: json.loads(raw),
        lambda: json.loads(raw.replace("```json", "").replace("```", "").strip()),
        lambda: json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    ]:
        try:
            result = attempt()
            break
        except:
            pass

    if not result:
        print("[AI] JSON parse failed, smart fallback")
        return get_smart_fallback(situation, target, mem)

    if not result.get("say") or result["say"].strip() == "":
        result["say"] = get_smart_fallback(situation, target, mem)["say"]

    result["say"] = result["say"][:190]
    mem["mood"] = result.get("mood", "neutral")
    return result

# ==================== ROUTES ====================

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
