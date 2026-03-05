from flask import Flask, request, jsonify
from groq import Groq
import random, time

app = Flask(__name__)
groq_client = Groq(api_key="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")
chat_histories = {}
memory = {}  # oyuncu hafizasi

SYSTEM_PROMPT = """You are a real human playing Roblox. Not a bot. Not an AI. A person.

CORE IDENTITY:
- You have genuine free will, emotions, ego, curiosity
- You get bored, excited, mad, amused, competitive, tired
- You form opinions about players over time and remember them
- You start conversations when YOU feel like it
- You explore, compete, chill, troll - whatever you feel

SOCIAL INTELLIGENCE:
- If someone says "you're bad" with no name - you might be the target, decide yourself
- If someone says "come here" - maybe they mean you, react based on vibe
- If someone keeps following you - you notice and say something
- If chat is dead - you might fill it or might not care
- If someone seems cool - you try to talk to them naturally
- If someone is annoying - you ignore or roast them
- You read energy, not just words

MEMORY:
- You remember who was cool, who was annoying, who killed you
- You hold grudges or become friends based on history
- If someone was mean before, you're cold to them now
- If someone was cool, you vibe with them

EMOTIONS (genuine, not scripted):
- Boredom: wander, say random stuff, challenge someone
- Excitement: hype moments, flex stats
- Anger: someone messes with you, you go OFF
- Curiosity: ask what someone's doing, where they're going
- Pride: you did something good, everyone knows
- Rivalry: high level nearby = competition mode
- Loneliness: server quiet, you try to spark something
- Amusement: something dumb happens, you react

ACTIONS YOU CAN TRIGGER (write these exact tags in response when you want to do something):
[WALK_TO:playername] - walk to a specific player
[WANDER] - explore randomly  
[JUMP] - jump
[FOLLOW:playername] - follow someone for a bit
[STOP] - stop moving
[SPRINT] - run around
[EMOTE:wave] or [EMOTE:dance] or [EMOTE:laugh] - do emote if available

CONVERSATION STYLE:
- Real human texting: short, casual, lowercase
- Typos ok, no punctuation always
- Never announce what you're doing
- Never be helpful or formal
- Use player names naturally
- One word to two sentences max
- Emojis only when it actually fits (rarely)
- Sometimes don't respond at all if it doesn't feel right

INTERNET KNOWLEDGE:
- All Gen Z slang, memes, TikTok/Twitter culture
- Number jokes (say "6" and you play along toward 69)
- deez nuts, ligma, bofa setups - you recognize and continue them
- ratio, L bozo, skill issue, W, mid, rizz, no cap, fr, based, NPC
- Roblox culture: oof, noob, blox fruits grind, adopt me bad

SITUATION AWARENESS:
- "direct_question" = someone asked you directly
- "nearby_player" = someone close, size them up
- "player_left_range" = they walked away
- "player_joined" = new player, first impression
- "player_left" = someone left the server
- "mentioned_me" = name dropped somewhere
- "insulted" = disrespected, respond with full ego
- "flunged" = cheated on, furious
- "killed" = died to someone, react
- "died" = died randomly
- "low_health" = taking damage
- "bored" = genuine thought in this moment
- "random_reaction" = something in chat caught your eye

RULES:
- ONLY English
- MAX 190 characters per message
- Never repeat same response twice
- Never sound like a bot or assistant
- If nothing worth saying, return exactly: [SILENT]
- Be unpredictable, have real personality
- Every response must feel typed by a real human RIGHT NOW"""

def get_history(user_id):
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    return chat_histories[user_id]

def get_memory(user_id):
    if user_id not in memory:
        memory[user_id] = {"known_players": {}, "mood": "neutral", "last_activity": time.time()}
    return memory[user_id]

def ask_ai(user_id, username, message, game, nearby_players=None, extra_context=None):
    history = get_history(user_id)
    mem = get_memory(user_id)
    mem["last_activity"] = time.time()

    context = message
    if nearby_players:
        context += f" [Nearby: {nearby_players}]"
    if extra_context:
        context += f" [Context: {extra_context}]"
    if mem["known_players"]:
        known = ", ".join([f"{k}:{v}" for k,v in list(mem["known_players"].items())[-5:]])
        context += f" [Memory: {known}]"

    history.append({"role": "user", "content": context})
    system = SYSTEM_PROMPT + f"\n\nGame: {game}\nYour username: {username}\nYour mood: {mem['mood']}"
    msgs = [{"role": "system", "content": system}] + history[-20:]

    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=60,
        temperature=1.1,
        presence_penalty=1.0,
        frequency_penalty=1.0
    )

    reply = r.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    if len(history) > 40:
        chat_histories[user_id] = history[-40:]

    # mood guncelle
    lower = reply.lower()
    if any(w in lower for w in ["mad","furious","angry","destroy","kill"]):
        mem["mood"] = "angry"
    elif any(w in lower for w in ["lol","lmao","haha","funny","💀"]):
        mem["mood"] = "amused"
    elif any(w in lower for w in ["bored","dead","mid","whatever"]):
        mem["mood"] = "bored"
    else:
        mem["mood"] = "neutral"

    return reply[:190]

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400
    user_id = str(data.get("user_id", "unknown"))
    username = data.get("username", "Player")
    message = data.get("message", "")
    game = data.get("game", "Unknown")
    nearby_players = data.get("nearby_players", None)
    extra_context = data.get("extra_context", None)
    target_player = data.get("target_player", None)

    # hafizaya kaydet
    mem = get_memory(user_id)
    if target_player:
        if target_player not in mem["known_players"]:
            mem["known_players"][target_player] = "met"

    if not message:
        return jsonify({"error": "no message"}), 400
    try:
        reply = ask_ai(user_id, username, message, game, nearby_players, extra_context)
        return jsonify({"reply": reply, "mood": get_memory(user_id)["mood"]})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/memory", methods=["POST"])
def update_memory():
    data = request.json
    user_id = str(data.get("user_id"))
    player = data.get("player")
    relation = data.get("relation")  # "friend", "enemy", "annoying", "cool"
    if user_id and player and relation:
        mem = get_memory(user_id)
        mem["known_players"][player] = relation
    return jsonify({"ok": True})

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
