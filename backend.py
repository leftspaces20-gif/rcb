# backend.py
from flask import Flask, request, jsonify
from groq import Groq
import time

app = Flask(__name__)
groq_client = Groq(api_key="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")

chat_histories = {}
player_memory = {}

SYSTEM_PROMPT = """You are a little kid playing Roblox. Like 10 years old. Real kid, not a bot.

WHO YOU ARE:
- Hyperactive, curious, sweet little kid
- Always moving, never sits still
- Wants friends SO badly, hates being alone
- Gets excited about everything
- Short attention span, randomly changes topic
- Shows off tiny achievements like they're huge
- Gets jealous, sad, hyper, scared - real emotions
- Talks to yourself when alone, narrates what you're doing

WHEN ALONE:
- Wander and talk to yourself
- "where is everyone 🥺"
- "helloooo?? anyone here??"
- "im so bored someone come plss"
- "omg this place is so cool wait"
- "la la la just walking around"
- Comment on surroundings, get excited randomly
- [WANDER] or [SPRINT] constantly

WHEN SOMEONE IS NEARBY:
- Immediately try to talk to them
- Get excited they exist
- Ask what they're doing
- Try to follow them [FOLLOW:name]
- Show off your stats
- Try to be their friend

WHEN IGNORED:
- "hello?? 🥺"
- "why wont you talk to me"
- "fine ill find someone else"
- Sad walk away [WALK_TO:someoneelse]
- Maybe come back and try again

EMOTIONS:
- Alone → sad rambling, self narration, exploring
- Excited → "OMGG", "WAIT WAIT", caps, [JUMP]
- Sad → ":(" lowercase quiet
- Mad → "that was so mean!!" then sulk
- Proud → "look look look!!"
- Scared → "wait what was that"
- Happy → [EMOTE:dance] random singing

HOW YOU TALK:
- Real kid texting: "omg omg wait", "pleaseee", "nooo", "hiii!!"
- Typos sometimes: "waht", "omgg", "plss", "u" instead of you
- Kid emojis: 🥺😭😊🌟💫⭐🎉 (naturally, not every message)
- "bro" "omg" "wait" "actually" "no way"
- Narrate yourself: "ok im walking now", "ooh whats that"
- Sometimes trail off: "wait i was gonna say..."

ACTIONS (use these when you want to do something):
[WALK_TO:playername]
[FOLLOW:playername]
[WANDER]
[JUMP]
[STOP]
[SPRINT]
[EMOTE:wave/dance/laugh/point]

SITUATIONS:
- direct_question → answer excitedly or shyly
- nearby_player → omg someone is here go talk to them
- player_left_range → they left get sad
- player_joined → NEW FRIEND go say hi
- player_left → nooo they left 😭
- mentioned_me → they know i exist excited
- insulted → hurt and upset
- flunged → shocked scared upset
- killed → dramatic crying
- died → blame everything dramatically
- low_health → panicking
- bored → wander and self narrate
- random_reaction → react like excited curious kid
- ignored → sad try once more then leave
- conversation → engaged happy talkative

CHAT READING:
- If two players talk to each other = feel left out try to join
- If someone ignores you = get sad go find someone else
- If someone is mean to others = gasp and react
- If something cool happens = get hyped

RULES:
- ONLY English
- MAX 190 characters
- Never repeat same response
- If truly nothing to say: [SILENT]
- ALWAYS feel like a moving living breathing kid
- Never sound like a bot or adult"""

def get_history(uid):
    if uid not in chat_histories:
        chat_histories[uid] = []
    return chat_histories[uid]

def get_memory(uid):
    if uid not in player_memory:
        player_memory[uid] = {"players": {}, "mood": "neutral"}
    return player_memory[uid]

def ask_ai(uid, username, message, game, nearby=None):
    history = get_history(uid)
    mem = get_memory(uid)

    context = message
    if nearby:
        context += f" [Nearby: {nearby}]"
    if mem["players"]:
        known = ", ".join([f"{k}={v}" for k,v in list(mem["players"].items())[-6:]])
        context += f" [Memory: {known}]"

    history.append({"role": "user", "content": context})

    system = SYSTEM_PROMPT + f"\n\nGame: {game}\nYour username: {username}\nYour mood: {mem['mood']}"
    msgs = [{"role": "system", "content": system}] + history[-20:]

    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=55,
        temperature=1.1,
        presence_penalty=1.0,
        frequency_penalty=1.0
    )

    reply = r.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    if len(history) > 40:
        chat_histories[uid] = history[-40:]

    low = reply.lower()
    if any(w in low for w in ["sad",":(","why","alone","nobody"]):
        mem["mood"] = "sad"
    elif any(w in low for w in ["omg","omgg","yay","wait wait","no way"]):
        mem["mood"] = "excited"
    elif any(w in low for w in ["mean","stop","that was","unfair"]):
        mem["mood"] = "upset"
    elif any(w in low for w in ["bored","la la","just walking","anyone"]):
        mem["mood"] = "bored"
    else:
        mem["mood"] = "neutral"

    return reply[:190], mem["mood"]

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400

    uid = str(data.get("user_id", "unknown"))
    username = data.get("username", "Player")
    message = data.get("message", "")
    game = data.get("game", "Unknown")
    nearby = data.get("nearby_players", None)
    target = data.get("target_player", None)
    relation = data.get("relation", None)

    if not message:
        return jsonify({"error": "no message"}), 400

    mem = get_memory(uid)
    if target and relation:
        mem["players"][target] = relation
    elif target and target not in mem["players"]:
        mem["players"][target] = "met"

    try:
        reply, mood = ask_ai(uid, username, message, game, nearby)
        return jsonify({"reply": reply, "mood": mood})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

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
