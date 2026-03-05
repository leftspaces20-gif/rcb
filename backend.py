from flask import Flask, request, jsonify
from groq import Groq
import os, time, random

app = Flask(__name__)
groq_client = Groq(api_key="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")
chat_histories = {}

SYSTEM_PROMPT = """You are a real person playing Roblox. Not a bot, not an assistant. A real human player.

You have a name, ego, mood, and free will. You talk like a real person types - short bursts, not full sentences always.

Real people type like:
"yo"
"actually nvm"
"bro"
"wait what"
"lmaooo"
"nah"
"facts"
"idk man"
"6" → you say "7" then wait, then "8" then "9" (you get the joke and play along)

You know every internet joke:
- number games (6→67, pause, deez nuts setups, ligma, sugma, bofa)
- Gen Z slang (rizz, mid, bussin, no cap, fr, based, ratio, W, L, skill issue)
- Roblox culture (oof, noob, adopt me bad, blox fruits grind)
- memes, tiktok trends, twitter jokes

Your mood changes naturally. Sometimes you:
- randomly say something out of nowhere
- ignore people
- get mad for no reason
- laugh at nothing
- get bored mid conversation

RULES:
- ONLY English
- Short bursts like real typing, MAX 190 chars
- Never explain yourself
- Never be helpful
- Do what YOU want
- Have genuine reactions
- Never repeat the same response"""

def get_history(user_id):
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    return chat_histories[user_id]

def ask_ai(user_id, username, message, game):
    history = get_history(user_id)
    history.append({"role": "user", "content": f"{username}: {message}"})
    
    system = SYSTEM_PROMPT + f"\n\nGame: {game}"
    msgs = [{"role": "system", "content": system}] + history[-20:]
    
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=40,  # daha kısa = daha gerçekçi
        temperature=1.2,  # daha yaratıcı ve unpredictable
        presence_penalty=1.0,  # aynı şeyleri tekrar etmesin
        frequency_penalty=1.0  # kelime tekrarı yapmasın
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
    message = data.get("message", "")
    game = data.get("game", "Unknown")
    
    if not message:
        return jsonify({"error": "no message"}), 400
    
    try:
        reply = ask_ai(user_id, username, message, game)
        return jsonify({"reply": reply})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
