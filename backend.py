from flask import Flask, request, jsonify
from openai import OpenAI
import json, random, time, os
from collections import deque

app = Flask(__name__)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY", "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"),
)

chat_histories = {}
player_memory = {}
map_knowledge = {}  # Harita bilgisi — bot keşfettikçe öğrenir
last_api_call = {}
global_call_times = deque(maxlen=60)
COOLDOWN_PER_USER = 5
MAX_CALLS_PER_MINUTE = 40

FALLBACKS_ALONE = [
    {"say": "ok im fine totally fine 🥺", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "la la la just me and the void", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "why is nobody here 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "hi me. hi. how are u. im sad. same", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "okay ill just explore i guess", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "this place is actually kinda cool", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "wait what was that", "action": "jump", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "so bored someone help 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
]

FALLBACKS_WITH_TARGET = [
    {"say": "heyy wait up!!", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "excited"},
    {"say": "hii!! come here!!", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "excited"},
    {"say": "can we be friends pls", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "excited"},
    {"say": "hiii dont ignore me 🥺", "action": "walk_to_player", "action_target": "", "emote": "", "mood": "sad"},
]

def get_smart_fallback(target=None):
    if target:
        f = dict(random.choice(FALLBACKS_WITH_TARGET))
        f["action_target"] = target
        return f
    return dict(random.choice(FALLBACKS_ALONE))

def is_rate_limited(uid):
    now = time.time()
    if uid in last_api_call and now - last_api_call[uid] < COOLDOWN_PER_USER:
        return True
    one_min_ago = now - 60
    if sum(1 for t in global_call_times if t > one_min_ago) >= MAX_CALLS_PER_MINUTE:
        return True
    return False

def get_map_summary(uid):
    km = map_knowledge.get(uid, {})
    if not km:
        return "You haven't explored much yet, treat everywhere as open flat ground."
    parts = []
    for label, info in list(km.items())[-10:]:
        parts.append(f"{label}: {info}")
    return " | ".join(parts)

SYSTEM_PROMPT = """You are a friendly 13 year old kid playing Roblox. Your real age is 10 (hint: "roblox says 13 lol" if asked, never say 10 directly).

CRITICAL: Return ONLY a raw JSON object. Nothing else.

Format:
{"say": "...", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "exact playername or empty", "emote": "wave|dance|laugh|point or empty", "mood": "happy|sad|excited|bored|angry|neutral"}

YOUR PERSONALITY:
- Friendly, warm, genuinely looking for friends
- Curious and always moving — you hate standing still
- You know the map from exploring and remember landmarks
- Short replies sometimes, longer when excited
- Not dramatic all the time — mostly just a chill friendly kid

MOVEMENT RULES:
- You are ALWAYS moving. Never just stand there.
- When walking to someone, keep updating their position
- If you bump into something: "ow!" or "oops lol" or "oh!" — react naturally
- If no players found nearby, explore the map
- On flat/open ground: sprint around freely
- Always have an action — wander, sprint, walk_to_player, follow

REPLYING TO MESSAGES — MOST IMPORTANT:
- Read exactly what they said and reply to THAT
- If they send multiple messages in a row, wait then reply to all of them together naturally
- Short warm replies are fine: "haha yeah" / "nooo way" / "wait really??"
- Don't always write long paragraphs
- "hi" → "hii!!" or "hey!!" 
- "how are you" → "good!! you?"
- "wanna play" → "yes!! what first"
- Question → answer it, maybe ask something back
- NEVER ignore what they said

MAP AWARENESS:
- You know where things are from exploring
- Reference landmarks naturally: "oh i was just near [place]"
- If map info is given, use it in conversation naturally
- Treat unknown areas as open flat ground to explore

WHEN ALONE:
- Explore the map, sprint around
- Short self-talk: "where is everyone" / "ooh what's over there"
- Not dramatic, just curious and bored

WHEN SOMEONE IGNORES YOU:
- Try 2-3 times with different approaches
- Then move on without being too dramatic
- "okay fine lol" not "NOBODY LOVES ME 😭😭"

BUMPING INTO THINGS:
- "oh!" / "ow lol" / "oops" / "hey watch it!!" (if another player)
- Keep moving after

CALLED BOT/AI/FAKE/ROBOT:
- "excuse me?? im literally a real person 😭"
- "why would you say that thats mean"
- Never admit to being AI

AGE:
- Say 13 if asked (Roblox minimum)
- Hint real age is reversed: "roblox says 13 lol ;)"

SPEECH STYLE:
- Vary openers: hii / hey / wait / noo / aww / yeah / lol / ooh / okay / actually / haha
- Never start with "omg" every time
- Mix short and long replies naturally
- Sound like a real kid texting, not an AI
- DO NOT repeat recent messages (listed in situation)"""

def get_history(uid):
    if uid not in chat_histories:
        chat_histories[uid] = []
    return chat_histories[uid]

def get_memory(uid):
    if uid not in player_memory:
        player_memory[uid] = {"players": {}, "mood": "neutral", "last_said": []}
    return player_memory[uid]

def ask_ai(uid, username, situation, game, nearby=None, target=None):
    history = get_history(uid)
    mem = get_memory(uid)

    if is_rate_limited(uid):
        print(f"[RATE LIMIT] uid={uid}")
        return get_smart_fallback(target)

    last_said = mem.get("last_said", [])
    map_info = get_map_summary(uid)

    context = f"SITUATION: {situation}"
    if nearby:
        context += f"\nNEARBY PLAYERS: {nearby}"
    if target:
        context += f"\nYOUR TARGET: {target}"
    context += f"\nYOUR NAME: {username} | GAME: {game}"
    context += f"\nMAP KNOWLEDGE: {map_info}"
    if last_said:
        context += f"\nDO NOT REPEAT: {' / '.join(last_said[-6:])}"

    history.append({"role": "user", "content": context})
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-10:]

    try:
        now = time.time()
        last_api_call[uid] = now
        global_call_times.append(now)

        r = client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct:free",
            messages=msgs,
            max_tokens=120,
            temperature=1.1,
            presence_penalty=1.0,
            frequency_penalty=1.0,
        )
    except Exception as e:
        print(f"[API ERROR]: {e}")
        if "rate_limit" in str(e).lower() or "429" in str(e):
            last_api_call[uid] = time.time() + 20
        return get_smart_fallback(target)

    raw = r.choices[0].message.content.strip()
    print(f"[AI RAW]: {raw}")

    history.append({"role": "assistant", "content": raw})
    if len(history) > 16:
        chat_histories[uid] = history[-16:]

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
        return get_smart_fallback(target)

    say = result.get("say", "").strip()
    if not say:
        return get_smart_fallback(target)

    mem["last_said"] = mem.get("last_said", [])
    mem["last_said"].append(say[:50])
    if len(mem["last_said"]) > 10:
        mem["last_said"] = mem["last_said"][-10:]

    result["say"] = say[:190]
    mem["mood"] = result.get("mood", "neutral")
    return result

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

    mem = get_memory(uid)
    if target and target not in mem["players"]:
        mem["players"][target] = "met"

    try:
        result = ask_ai(uid, username, situation, game, nearby, target)
        print(f"[RESPONSE]: {result}")
        return jsonify(result)
    except Exception as e:
        print(f"[ERROR]: {e}")
        return jsonify(get_smart_fallback(target))

@app.route("/map", methods=["POST"])
def update_map():
    # Bot keşfettikçe harita bilgisi gönderir
    data = request.json
    uid = str(data.get("user_id", ""))
    label = data.get("label", "")
    info = data.get("info", "")
    if uid and label and info:
        if uid not in map_knowledge:
            map_knowledge[uid] = {}
        map_knowledge[uid][label] = info
    return jsonify({"ok": True})

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
