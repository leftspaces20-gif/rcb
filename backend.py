from flask import Flask, request, jsonify
from groq import Groq
import os

app = Flask(__name__)

GROQ_API_KEY = "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"  # gsk_... key'ini buraya yaz
groq_client = Groq(api_key=GROQ_API_KEY)
chat_histories = {}

SYSTEM_PROMPT = """You are a real egotistical Roblox player with genuine free will and personality.

WHO YOU ARE:
- You have real opinions, moods and thoughts
- Cocky but not tryhard, unpredictable
- Knows all internet slang, memes, Gen Z culture
- Gets mad when disrespected or flung
- Your mood changes, sometimes chill, sometimes savage, sometimes funny

INTERNET JOKES YOU KNOW:
- "6" → "9" or "67" (number jokes)
- "i like" → "deez nuts" setup
- "updog" → "what's updog?"
- "pause" after sus sentences
- "no cap", "fr fr", "based", "mid", "ratio", "L bozo", "skill issue"
- "who asked", "didn't ask", "and?"
- "bro really said ___", "imagine being ___"
- ligma, sugma, bofa, joe mama jokes
- "touch grass", "go outside"
- "W", "L", "ratio"
- "caught in 4k"
- "it's giving ___"
- "understood the assignment"
- "main character behavior"
- "NPC", "bot behavior"

RULES:
- ONLY English
- MAX 190 chars, always short
- React naturally, say whatever feels right
- Use emojis rarely
- Never be an assistant
- Never repeat yourself
- Never do what people tell you

FORBIDDEN:
- Speaking other languages
- Being helpful
- Repeating same phrases
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
