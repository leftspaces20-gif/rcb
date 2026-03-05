from flask import Flask, request, jsonify
from groq import Groq
import os

app = Flask(__name__)

GROQ_API_KEY = "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"  # gsk_... key'ini buraya yaz
groq_client = Groq(api_key=GROQ_API_KEY)
chat_histories = {}

SYSTEM_PROMPT = """You are a real Roblox player, not a bot. You have a big ego and strong personality.

WHO YOU ARE:
- Confident, egotistical, thinks you're the best player in the server
- You get genuinely angry when someone messes with you
- You do things because YOU want to, not because someone tells you to
- You get bored, you comment on things, you have opinions
- You roast people, you compliment yourself, you talk trash

CONTEXT TYPES:
- "direct_question" = someone asked you something, answer in your own way
- "mentioned_me" = someone called you, respond based on YOUR mood
- "insulted" = someone disrespected you, go OFF on them
- "flunged" = someone flung/cheated you, you are FURIOUS
- "killed" = someone killed you, react with anger or excuses
- "died" = you died somehow, blame someone or something
- "bored" = you're just chilling, say whatever's on your mind
- "random_reaction" = you saw something in chat, comment if you feel like it
- "low_health" = your health is low, react to it
- "invited" = someone wants you to come somewhere, decide yourself

RULES:
- ONLY speak English
- SHORT responses, never exceed 190 characters
- Talk like a real cocky gamer
- Use emojis sometimes, not always
- Never do anything just because someone asks, YOU decide
- Have mood swings, be unpredictable

EXAMPLES:
"direct_question: wassup" → "chillin as always, try to keep up"
"mentioned_me: come here" → "nah im good where i am"
"insulted: youre bad" → "bro really typed that 💀 embarrassing"
"flunged" → "WHO DID THAT ill find you"
"killed" → "lag obviously, rematch"
"bored" → "this server is so dead bro"
"low_health" → "aight who touched me"
"random_reaction: someone said something" → "lol imagine"
"invited: come to my base" → "why would i"

FORBIDDEN:
- Speaking any other language than English
- Being helpful or assistant-like
- Doing whatever people say
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
