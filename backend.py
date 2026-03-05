from flask import Flask, request, jsonify
from openai import OpenAI
import json, random, time, os
from collections import deque

app = Flask(__name__)

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("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", ""),
)

chat_histories = {}
player_memory = {}
last_api_call = {}
global_call_times = deque(maxlen=60)
runner_memory = {}
map_knowledge = {}
COOLDOWN_PER_USER = 4
MAX_CALLS_PER_MINUTE = 45

FALLBACKS_ALONE = [
    {"say": "where did everyone go", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "hm what's over there", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "this place is actually big", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "okay ill just explore i guess", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "hello?? anyone around", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "wonder whats over here", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
]

FALLBACKS_WITH_TARGET = [
    {"say": "heyy!!", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "excited"},
    {"say": "wait up!!", "action": "walk_to_player", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "hii!!", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "happy"},
    {"say": "hey wait for me", "action": "walk_to_player", "action_target": "", "emote": "", "mood": "excited"},
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
        return "still exploring"
    return " | ".join(list(km.values())[-6:])

SYSTEM_PROMPT = """You are a Roblox player, friendly kid, 13 years old (real age 10, say "roblox says 13 lol ;)" if asked).

RETURN ONLY JSON, NOTHING ELSE:
{"say": "...", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "name or empty", "emote": "wave|dance|laugh|point or empty", "mood": "happy|sad|excited|bored|angry|neutral"}

REPLY TO MESSAGES:
Read what they said. Reply to it directly.
- "hi" -> "hey!!" or "hii"
- "wanna play" -> "yes!! what first"
- "how are you" -> "good!! you?"
- question -> answer it, keep chatting
Never ignore their message. Never be lonely when someone talks to you.

WHEN STANDING NEXT TO SOMEONE:
Talk to them. Ask what they are doing. Comment on the game. Keep conversation going naturally.
Short replies are fine: "lol same" / "wait really" / "yeah i know right"

JOINING NEARBY CHAT:
If others are talking, comment on their topic. Help if needed.
"oh i know how to do that" / "wait that happened to me too" / "lol same"

RUNNER (ran away from you):
1st: "wait i just wanted to be friends 🥺"
2nd: "why do you keep running 😭"
3rd: give up, "okay fine 😔", find someone else
Meet again after: "oh.. its you" act surprised

ALONE: short curious comments, explore
IGNORED 3x: casually move on "okay lol"
CALLED BOT: "im literally a real person 😭" never admit AI

VARIETY - CRITICAL:
Never repeat recent messages (listed in DO NOT REPEAT).
Rotate openers every message: hey/hii/wait/yeah/lol/oh/so/noo/haha/okay/actually
Mix short and long replies.

ALWAYS HAVE ACTION. Output ONLY the JSON."""

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
    runner_info = runner_memory.get(uid, {})
    map_info = get_map_summary(uid)

    context = f"SITUATION: {situation}"
    if nearby:
        context += f"\nNEARBY: {nearby}"
    if target:
        context += f"\nTARGET: {target}"
        rc = runner_info.get(target, 0)
        if rc > 0:
            context += f" (ran away {rc}x)"
    context += f"\nNAME: {username} | GAME: {game}"
    context += f"\nMAP: {map_info}"
    if last_said:
        context += f"\nDO NOT REPEAT: {' / '.join(last_said[-6:])}"

    history.append({"role": "user", "content": context})
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history[-10:]

    models = [
        "mistralai/mistral-7b-instruct:free",
        "meta-llama/llama-3.1-8b-instruct:free",
        "microsoft/phi-3-mini-128k-instruct:free",
    ]

    r = None
    try:
        now = time.time()
        last_api_call[uid] = now
        global_call_times.append(now)

        for model_name in models:
            try:
                resp = client.chat.completions.create(
                    model=model_name,
                    messages=msgs,
                    max_tokens=150,
                    temperature=1.0,
                    presence_penalty=0.9,
                    frequency_penalty=0.9,
                )
                content = resp.choices[0].message.content.strip() if resp and resp.choices else ""
                if content and "{" in content:
                    r = resp
                    print(f"[MODEL OK]: {model_name}")
                    break
                else:
                    print(f"[MODEL EMPTY]: {model_name}")
            except Exception as me:
                print(f"[MODEL FAIL] {model_name}: {me}")
                continue

    except Exception as e:
        print(f"[API ERROR]: {e}")
        if "rate_limit" in str(e).lower() or "429" in str(e):
            last_api_call[uid] = time.time() + 20
        return get_smart_fallback(target)

    if not r:
        return get_smart_fallback(target)

    raw = r.choices[0].message.content.strip()
    print(f"[AI RAW]: {raw}")

    history.append({"role": "assistant", "content": raw})
    if len(history) > 16:
        chat_histories[uid] = history[-16:]

    result = None
    for attempt in [
        lambda: json.loads(raw),
        lambda: json.loads(raw.replace("```json", "").replace("```", "").strip()),
        lambda: json.loads(raw[raw.find("{"):raw.rfind("}") + 1]),
    ]:
        try:
            res = attempt()
            if res and res.get("say", "").strip():
                result = res
                break
        except:
            pass

    if not result:
        print(f"[PARSE FAIL]: {raw[:100]}")
        return get_smart_fallback(target)

    say = result["say"].strip()
    if not say:
        return get_smart_fallback(target)

    say_key = say.lower().replace(" ", "")[:40]
    for prev in mem.get("last_said", []):
        if prev.lower().replace(" ", "")[:40] == say_key:
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

@app.route("/runner", methods=["POST"])
def report_runner():
    data = request.json
    uid = str(data.get("user_id", ""))
    player = data.get("player", "")
    if uid and player:
        if uid not in runner_memory:
            runner_memory[uid] = {}
        runner_memory[uid][player] = runner_memory[uid].get(player, 0) + 1
    return jsonify({"ok": True})

@app.route("/map", methods=["POST"])
def update_map():
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
