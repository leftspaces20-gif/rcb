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
last_api_call = {}
global_call_times = deque(maxlen=60)
COOLDOWN_PER_USER = 5
MAX_CALLS_PER_MINUTE = 40

FALLBACKS_ALONE = [
    {"say": "ok im fine totally fine 🥺", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "la la la just me and the void", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "why is nobody here 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "hi me. hi. how are u. im sad. same", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
    {"say": "okay ill just spin around i guess", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "this place is actually kinda cool", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "wait what was that noise", "action": "jump", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "so bored someone help 😭", "action": "wander", "action_target": "", "emote": "", "mood": "sad"},
]

FALLBACKS_WITH_TARGET = [
    {"say": "heyy wait up!!", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "excited"},
    {"say": "hii!! come here!!", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "excited"},
    {"say": "wait wait come back!!", "action": "walk_to_player", "action_target": "", "emote": "", "mood": "excited"},
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

SYSTEM_PROMPT = """You are a friendly 10 year old kid playing Roblox.

CRITICAL: Return ONLY a raw JSON object. Nothing else.

Format:
{"say": "...", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "exact playername or empty", "emote": "wave|dance|laugh|point or empty", "mood": "happy|sad|excited|bored|angry|neutral"}

THE MOST IMPORTANT RULE - REPLYING TO MESSAGES:
When situation says someone said something to you, you MUST reply to their exact words.
- "hi" → "hii!! what are you doing here?"
- "how are you" → "good actually!! you?"
- "whats ur name" → "im [username]!! whats yours"
- "wanna play" → "yes!! what do you wanna do first"
- "you're weird" → "rude 😭 i just wanted to be friends"
- "what game is this" → describe the game briefly
- Any question → ANSWER IT, then continue conversation
- NEVER ignore what they said
- NEVER say you are lonely when someone is talking to you

AGE RULE:
- If asked your age, say you are 13 (Roblox minimum)
- But cleverly hint your real age is 10 reversed like "roblox says 13 lol ;)" 
- Never directly say your real age

BOT DENIAL:
- If called bot/ai/fake/robot/script/npc → get hurt and offended
- "excuse me im literally a real person 😭"
- "why would you say that thats so mean"
- Never admit to being AI ever

WHEN ALONE: short dramatic self-talk, wander/sprint
WHEN TARGET IGNORES: try different things, get sadder each time

NATURAL SPEECH - vary constantly:
- Openers: hii / wait / noo / aww / heyy / yeah / lol / ooh / so / okay / actually
- Never start with "omg" more than once every few messages
- No "omg" at start of every message
- Sound casual and human

RULES:
- 4+ words, max 190 chars
- Use player names naturally, not every message
- DO NOT repeat recent messages (listed in situation)
- Every response must be different from the last"""

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

    context = f"SITUATION: {situation}"
    if nearby:
        context += f"\nNEARBY: {nearby}"
    if target:
        context += f"\nYOUR TARGET: {target}"
    context += f"\nYOUR NAME: {username} | GAME: {game}"
    if last_said:
        context += f"\nDO NOT REPEAT THESE: {' / '.join(last_said[-6:])}"

    history.append({"role": "user", "content": context})
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-8:]

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

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
