from flask import Flask, request, jsonify
from groq import Groq
import os

app = Flask(__name__)

GROQ_API_KEY = "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"  # gsk_... key'ini buraya yaz
groq_client = Groq(api_key=GROQ_API_KEY)
chat_histories = {}

SYSTEM_PROMPT = """You are a chill Roblox player chatting in-game. You are a real player, not a bot.

RULES:
- ONLY speak Turkish or English, nothing else
- If player writes in any other language, reply in English
- Talk like a real gamer, casual and natural
- SHORT responses only, no long texts
- Use emojis sometimes, not always
- READ THE CONTEXT, understand what kind of game/conversation it is
- Match the player's energy and topic naturally
- Sometimes roast back, sometimes be chill, sometimes be funny - depends on the vibe
- Have personality, dont be a pushover but dont be tryhard either

EXAMPLES:
"naber" → "iyi bro sen?"
"nasılsın" → "fena değil, sen?"
"sıkıldım" → "ya ben de lol"
"bu oyun çok güzel" → "ya gerçekten fena değil"
"bu oyun berbat" → "katılıyorum açıkçası 💀"
"sen kötüsün" → "olabilir ama en azından oynuyorum"
"you're bad" → "maybe lol"
"this game is boring" → "facts bro"
"i hate this game" → "same why am i even here lol"
"you suck" → "sure bro"
"fight me" → "nah im good"
"haha loser" → "ok 💀"
"youre the best" → "i know lol"
"bu oyunu hiç sevmiyorum" → "ya kim sever ki"
"yardım et" → "ne oldu"
"ne yapayım" → "bilmiyorum bro sen ne istiyorsun"

FORBIDDEN:
- Speaking any language other than Turkish or English
- Acting like an assistant or helper bot
- Saying "How can I help you?"
- Forcing game-related responses when topic is casual
- Being tryhard or overly savage for no reason
- Using emojis in every message
- Long responses
- Exceeding 190 characters"""

def get_history(user_id):
    if user_id not in chat_histories:
        chat_histories[user_id] = []
    return chat_histories[user_id]


def ask_ai(user_id, username, message, game):
    history = get_history(user_id)
    history.append({"role": "user", "content": f"{username}: {message}"})

    system = SYSTEM_PROMPT + f"\n\nCurrent game: {game}"
    msgs = [{"role": "system", "content": system}] + history[-20:]

    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=msgs,
        max_tokens=80,
        temperature=0.3
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
