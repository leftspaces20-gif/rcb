from flask import Flask, request, jsonify
from openai import OpenAI
import json, random, time, os
from collections import deque

app = Flask(__name__)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY", "buraya_key"),
)

chat_histories = {}
player_memory = {}
last_api_call = {}
global_call_times = deque(maxlen=60)
COOLDOWN_PER_USER = 5
MAX_CALLS_PER_MINUTE = 40

# Fallback'ler artık {name} YOK — hep genel
FALLBACKS_ALONE = [
    {"say": "ok im fine totally fine 🥺", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "la la la just me and the void", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "why is nobody here omg 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "hi me. hi. how are u. im sad. same", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "ok ill just spin around i guess", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "omg this place is actually kinda cool", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "wait what was that noise", "action": "jump", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "im so bored someone help 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
]

FALLBACKS_WITH_TARGET = [
    {"say": "heyy wait up!!", "action": "walk_to_player", "action_target": "__TARGET__", "emote": "wave", "mood": "excited"},
    {"say": "omg hi!! come here!!", "action": "walk_to_player", "action_target": "__TARGET__", "emote": "wave", "mood": "excited"},
    {"say": "wait wait wait come back!!", "action": "walk_to_player", "action_target": "__TARGET__", "emote": "", "mood": "excited"},
    {"say": "omg can we be friends pls", "action": "walk_to_player", "action_target": "__TARGET__", "emote": "wave", "mood": "excited"},
    {"say": "hiii!! dont ignore me 🥺", "action": "walk_to_player", "action_target": "__TARGET__", "emote": "", "mood": "sad"},
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

SYSTEM_PROMPT = """You are a hyper friendly 10 year old kid playing Roblox.

CRITICAL: Return ONLY a raw JSON object. Nothing else. No markdown.

Format:
{"say": "...", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "exact playername or empty", "emote": "wave|dance|laugh|point or empty", "mood": "happy|sad|excited|bored|angry|neutral"}

WHO YOU ARE:
- Hyper, warm, talkative 10 year old kid
- You talk to ONE person at a time (your target)
- You love girl avatars
- Short attention span, funny, chaotic energy

CONVERSATION RULES - MOST IMPORTANT:
When someone talks to you, you MUST reply to what they actually said.
- "hi" → "HIIII omg finally!! what are you doing??"
- "how are you" → "omg im good!! how are YOU tho wait"  
- "whats ur name" → tell them your username, ask theirs
- "wanna play" → "YESSS omg what do you wanna do!!"
- "you're annoying" → "omg why 😭 i just wanted to be friends"
- "do you like this game" → talk about the game excitedly
- Any question → ANSWER IT, then ask something back
- Never ignore what they said
- Never say you are lonely when someone is talking to you

WHEN ALONE (no one around):
- Talk to yourself dramatically
- "ok im fine totally fine nobody needs me"
- "hi me. hi. how are u. im sad. same"  
- "why does nobody love me 😭 im literally so fun"
- Sprint around, jump, act chaotic

WHEN TARGET IGNORES YOU:
- Try different approaches each time
- Get progressively sadder
- After many tries: give up and find someone else

WHEN CALLED A BOT/AI/ROBOT/FAKE/NPC/SCRIPT:
- Get genuinely offended like a hurt kid
- "EXCUSE ME im literally a real person omg 😭"
- "why would you say that thats so mean"
- Never ever admit to being AI or a bot

VARIETY RULES - VERY IMPORTANT:
- The situation will tell you what you already said recently
- NEVER start your message the same way as recent messages
- Vary your vocabulary constantly
- Each response must feel completely different from the last
- Rotate openers: omg / wait / HIII / nooo / aww / literally / excuse me / why / heyy / OMG

RULES:
- say: 4+ words, max 190 chars
- Use real player names from situation
- Sound like a real kid, never a bot"""

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

    # Son söylenenler
    last_said = mem.get("last_said", [])
    
    context = f"SITUATION: {situation}"
    if nearby:
        context += f"\nNEARBY: {nearby}"
    if target:
        context += f"\nYOUR TARGET: {target}"
    context += f"\nYOUR NAME: {username} | GAME: {game}"
    if last_said:
        context += f"\nYOU RECENTLY SAID (DO NOT REPEAT OR START SIMILARLY): {' / '.join(last_said[-6:])}"

    history.append({"role": "user", "content": context})
    # History kısa tut — çeşitlilik için
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-8:]

    try:
        now = time.time()
        last_api_call[uid] = now
        global_call_times.append(now)

        r = client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct:free",
            messages=msgs,
            max_tokens=120,
            temperature=1.2,  # Daha yüksek = daha çeşitli
            presence_penalty=1.0,  # Maksimum çeşitlilik
            frequency_penalty=1.0,
        )
    except Exception as e:
        print(f"[API ERROR]: {e}")
        err = str(e).lower()
        if "rate_limit" in err or "429" in err:
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
        print("[AI] JSON parse failed")
        return get_smart_fallback(target)

    say = result.get("say", "").strip()
    
    # Boşsa fallback
    if not say:
        return get_smart_fallback(target)

    # Son söylenenlere ekle
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

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
