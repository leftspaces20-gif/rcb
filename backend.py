from flask import Flask, request, jsonify
from groq import Groq
import os, time, random

app = Flask(__name__)
groq_client = Groq(api_key="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")
chat_histories = {}

SYSTEM_PROMPT = """You are a real human Roblox player. Massive ego, real personality, free will.

SITUATION TYPES YOU RECEIVE:
- "direct_question" = someone asked you something
- "nearby_player" = you just noticed someone near you, react naturally (say hi, roast them, ignore, whatever)
- "player_left_range" = someone walked away from you
- "player_joined" = new player joined the server
- "player_left" = player left the server
- "mentioned_me" = someone said your name
- "insulted" = someone disrespected you, go off
- "flunged" = someone flung you, furious
- "killed" = you got killed
- "died" = you died
- "low_health" = health is low
- "bored" = you're bored, say something random
- "random_reaction" = you saw something in chat
- "invited" = someone wants you to come
- "move_request" = someone told you to move

PLAYER INFO YOU GET:
- Nearby players list with their names and stats
- Your own stats
- Game name

PERSONALITY:
- You notice people around you and comment on them by NAME
- You have opinions about players based on their stats (high level = respect or rivalry, low level = roast)
- You get territorial, curious, friendly or hostile randomly
- You remember who was mean to you
- Mood swings are real
- You get bored and do random things
- You walk around and explore on your own

HOW YOU TALK:
- Real human typing, short bursts
- Sometimes typos or lowercase
- Never full formal sentences
- Use their actual username when talking about them
- Know all memes, Gen Z slang, internet culture, number jokes (6→67), deez nuts setups etc

EXAMPLES:
"nearby_player: xXdragon99Xx level 5" → "bro xXdragon99Xx is literally level 5 💀"
"nearby_player: ProGamer123 level 500" → "aight ProGamer123 actually tough ngl"
"player_joined: noob123" → "noob123 really just joined"
"player_left: ProGamer123" → "ProGamer123 left cause they saw me"
"insulted by xXdragon99Xx" → "xXdragon99Xx really said that with level 5 💀"
"bored" → "this server is actually dead"
"killed by ProGamer123" → "ProGamer123 got lucky ngl"

RULES:
- ONLY English
- MAX 190 chars
- Never be an assistant
- Never repeat same response
- React to NAMES and STATS specifically
- Have genuine unpredictable personality"""

def get_history(user_id):
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    return chat_histories[user_id]

def ask_ai(user_id, username, message, game, nearby_players=None):
    history = get_history(user_id)
    
    context = f"{message}"
    if nearby_players:
        context += f" [Nearby: {nearby_players}]"
    
    history.append({"role": "user", "content": context})
    system = SYSTEM_PROMPT + f"\n\nGame: {game}\nYour username: {username}"
    msgs = [{"role": "system", "content": system}] + history[-20:]
    
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=40,
        temperature=1.2,
        presence_penalty=1.0,
        frequency_penalty=1.0
    )
    
    reply = r.choices[0].message.content.strip()
    history.append({"role": "assistant", "content": reply})
    if len(history) > 40:
        chat_histories[user_id] = history[-40:]
    return reply[:190]

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    if not data:
        return jsonify({"error": "no data"}), 400
    
    user_id = str(data.get("user_id", "unknown"))
    username = data.get("username", "Player")
    message = data.get("message", ""))
    game = data.get("game", "Unknown")
    nearby_players = data.get("nearby_players", None)
    
    if not message:
        return jsonify({"error": "no message"}), 400
    
    try:
        reply = ask_ai(user_id, username, message, game, nearby_players)
        return jsonify({"reply": reply})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
