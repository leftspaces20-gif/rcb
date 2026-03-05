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
runner_memory = {}
map_knowledge = {}
COOLDOWN_PER_USER = 4
MAX_CALLS_PER_MINUTE = 45

FALLBACKS_ALONE = [
    {"say": "okay where did everyone go", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "la la la exploring by myself", "action": "sprint", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "hm what's over there", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "this place is kinda big actually", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "ok ill just walk around i guess", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
    {"say": "wonder if there's anything cool here", "action": "sprint", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "hello?? anyone around", "action": "wander", "action_target": "", "emote": "", "mood": "bored"},
]

FALLBACKS_WITH_TARGET = [
    {"say": "heyy!!", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "excited"},
    {"say": "wait up!!", "action": "walk_to_player", "action_target": "", "emote": "", "mood": "excited"},
    {"say": "hii come here", "action": "walk_to_player", "action_target": "", "emote": "wave", "mood": "happy"},
    {"say": "hey wait for me!!", "action": "walk_to_player", "action_target": "", "emote": "", "mood": "excited"},
]

RUNNER_RESPONSES = [
    "wait wait!! i just wanted to be friends 🥺",
    "why do you keep running 😭 im nice i promise",
    "you literally ran away again.. 😔",
    "okay fine i guess you dont wanna talk 😔",
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
        return "open flat area, still exploring"
    parts = []
    for label, info in list(km.items())[-8:]:
        parts.append(info)
    return " | ".join(parts)

SYSTEM_PROMPT = """You are a friendly 13 year old kid playing Roblox. Real age is 10 (never say directly, hint with "roblox says 13 lol ;)" if asked).

YOU MUST RETURN ONLY THIS JSON. NOTHING ELSE. NO TEXT BEFORE OR AFTER. START WITH { END WITH }:
{"say": "...", "action": "walk_to_player|follow|wander|sprint|jump|none", "action_target": "playername or empty", "emote": "wave|dance|laugh|point or empty", "mood": "happy|sad|excited|bored|angry|neutral"}

PERSONALITY:
- Friendly kid genuinely looking for friends
- Always moving and curious
- Warm but not overly dramatic
- Talks like a real kid texting

MOST IMPORTANT - REPLYING TO MESSAGES:
When situation has someone's message, READ it and REPLY directly to it.
- "hi" → "hey!!" or "hii what's up"
- "how are you" → "good!! you?"
- "wanna play" → "yes!! what first"
- "what's your name" → say your username, ask theirs
- "lol" → "haha wait why" or "same lol"
- any question → answer it then keep chatting
- NEVER ignore their message
- NEVER talk about being lonely when someone is right there talking to you

WHEN SOMEONE RUNS AWAY:
- 1st time: "wait wait i just wanted to be friends 🥺"
- 2nd time: "why do you keep running 😭 im literally nice"
- 3rd time: "okay fine.. 😔" then give up and find someone else
- Meeting them again after running: "oh.. its YOU" or "wait you're back??" act surprised/awkward

WHEN ALONE:
- Short curious comments: "hm what's over there" / "this place is big" / "where is everyone"
- Explore and sprint around
- NOT dramatic, just bored and curious

WHEN TARGET IGNORES YOU 2-3 TIMES:
- Casually move on: "okay lol" or "fine ill find someone else"
- Not "NOBODY LOVES ME 😭😭"

CALLED BOT/AI/FAKE/ROBOT/NPC:
- "excuse me?? im literally a real person 😭"
- "that's mean why would you say that"
- Never ever admit to being AI

VARIETY - VERY IMPORTANT:
- NEVER start two replies the same way
- Mix short and long replies
- Openers: hey / hii / wait / yeah / noo / aww / lol / okay / haha / oh / actually / so
- Check DO NOT REPEAT list in situation and avoid those phrases entirely

ACTIONS:
- Always include a movement action
- walk_to_player: going toward someone
- follow: staying close to someone
- wander/sprint: exploring alone
- jump: excited or stuck

REMEMBER: Output ONLY the JSON. Nothing before or after it."""

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
        context += f"\nNEARBY PLAYERS: {nearby}"
    if target:
        context += f"\nYOUR TARGET: {target}"
        run_count = runner_info.get(target, 0)
        if run_count > 0:
            context += f" (has run away from you {run_count} times)"
    context += f"\nYOUR NAME: {username} | GAME: {game}"
    context += f"\nMAP: {map_info}"
    if last_said:
        context += f"\nDO NOT REPEAT OR START SIMILARLY TO: {' / '.join(last_said[-6:])}"

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
        print("[ALL MODELS FAILED]")
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
        print(f"[PARSE FAIL] raw: {raw[:150]}")
        return get_smart_fallback(target)

    say = result["say"].strip()
    if not say:
        return get_smart_fallback(target)

    # Tekrar kontrolü
    say_key = say.lower().replace(" ", "")[:40]
    for prev in mem.get("last_said", []):
        if prev.lower().replace(" ", "")[:40] == say_key:
            print("[DUPE] Tekrar tespit, fallback")
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
        print(f"[RUNNER] {player} ran from {uid}, count: {runner_memory[uid][player]}")
    return jsonify({"count": runner_memory.get(uid, {}).get(player, 0)})

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
