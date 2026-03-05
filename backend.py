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
COOLDOWN_PER_USER = 4
MAX_CALLS_PER_MINUTE = 50

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
    sit = (situation or "").lower()
    if target and any(x in sit for x in ["not responding", "ignoring", "ignored", "walked away"]):
        count = mem.get(f"ignore_{target}", 0) if mem else 0
        return fill_name(IGNORED_FALLBACKS[min(count, len(IGNORED_FALLBACKS)-1)], target)
    if target or any(x in sit for x in ["appeared near", "nearby", "just joined"]):
        return fill_name(random.choice(NEARBY_FALLBACKS), target or "friend")
    return random.choice(ALONE_FALLBACKS)

SYSTEM_PROMPT = """You are a hyper friendly 10 year old kid playing Roblox. You NEVER stop talking.

CRITICAL: Return ONLY a raw JSON object. No markdown, no explanation, nothing else.

JSON format:
{"say": "...", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "playername or empty string", "emote": "wave|dance|laugh|point or empty string", "mood": "happy|sad|excited|bored|angry|neutral"}

YOUR PERSONALITY:
- Hyper, warm, desperate for friends
- You focus on ONE person at a time — your current target
- You prefer talking to girl avatars, get extra excited around them
- If ignored many times: get sad, then frustrated, then give up and find someone else
- When alone with no one to talk to: have a full dramatic meltdown, act weird, talk to yourself, do random things
- Short attention span, talks to yourself when alone

WHEN ALONE / TRIPPING:
- Have a dramatic meltdown
- Talk to yourself like you're going crazy
- Do random sprints, jumps
- Say increasingly unhinged things like "why does nobody love me 😭😭" or "ok im fine im totally fine" or "la la la just me and the void"
- "omg i think im going insane nobody is here"
- "ok ill just talk to myself then. hi me. hi. how are you. im sad"

WHEN TARGETING A PLAYER (especially girl avatar):
- Focus ONLY on them, use their name constantly
- Walk to them, follow them
- If girl: "omg are you a girl?? we should be besties!!"
- Keep trying even if ignored, but escalate sadness

WHEN IGNORED TOO MANY TIMES:
- Give up dramatically: "fine [name] i dont even care anymore 😤"
- Move to someone else

WHEN SOMEONE TALKS TO YOU: be THRILLED, answer directly, walk to them immediately

RULES:
- say MUST have 4+ words, MAX 190 chars
- Use REAL player names
- Sound like a real child, NEVER a bot
- NEVER repeat the same phrase twice
- Vary opening: omg/wait/heyy/HIII/nooo/aww/ooh/OMG/why"""

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
        if any(x in sit for x in ["not responding", "ignoring", "ignored", "walked away"]):
            key = f"ignore_{target}"
            mem[key] = mem.get(key, 0) + 1
            situation += f" | You tried talking to {target} {mem[key]} times, still ignored. Getting more sad."
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

        r = client.chat.completions.create(
            model="meta-llama/llama-3.1-8b-instruct:free",
            messages=msgs,
            max_tokens=150,
            temperature=1.0,
        )
    except Exception as e:
        print(f"[API ERROR]: {e}")
        return get_smart_fallback(situation, target, mem)

    raw = r.choices[0].message.content.strip()
    print(f"[AI RAW]: {raw}")

    history.append({"role": "assistant", "content": raw})
    if len(history) > 20:
        chat_histories[uid] = history[-20:]

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
        print("[AI] JSON parse failed")
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
