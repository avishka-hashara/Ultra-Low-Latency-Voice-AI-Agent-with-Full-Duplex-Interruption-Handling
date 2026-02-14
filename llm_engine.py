import os
import asyncio
import time
import edge_tts
import aiosqlite
from groq import Groq
from dotenv import load_dotenv
from textblob import TextBlob

load_dotenv()

class BrainEngine:
    def __init__(self):
        # Groq client automatically picks up GROQ_API_KEY from your .env
        self.client = Groq()
        
    async def process_turn(self, audio_file_path: str, user_id: int):
        """
        Executes the STT -> LLM -> TTS pipeline with history.
        """
        start_time = time.time()
        print(f"\n--- 🧠 COGNITIVE PIPELINE STARTED (User ID: {user_id}) ---")
        
        # 0. Load History
        history = []
        async with aiosqlite.connect("storage.db") as db:
            async with db.execute("SELECT role, content FROM conversations WHERE user_id = ? ORDER BY timestamp ASC LIMIT 20", (user_id,)) as cursor:
                rows = await cursor.fetchall()
                for role, content in rows:
                    history.append({"role": role, "content": content})
        
        # 1. STT: Whisper on Groq
        print("👂 Transcribing audio...")
        with open(audio_file_path, "rb") as file:
            transcription = self.client.audio.transcriptions.create(
              file=(audio_file_path, file.read()),
              model="whisper-large-v3",
              response_format="text"
            )
        user_text = transcription.strip()
        print(f"👤 USER: \"{user_text}\"")

        # Analyze Sentiment
        user_sentiment = TextBlob(user_text).sentiment.polarity

        # Save User Turn
        async with aiosqlite.connect("storage.db") as db:
            await db.execute("INSERT INTO conversations (user_id, role, content, sentiment_score) VALUES (?, ?, ?, ?)", (user_id, "user", user_text, user_sentiment))
            await db.commit()
            
        history.append({"role": "user", "content": user_text})

        # 2. LLM: Llama 3 on Groq
        print("⚡ Generating response...")
        
        messages = [
            {
                "role": "system",
                "content": "You are a witty, ultra-fast AI voice assistant. Keep your answers strictly under 2 sentences. Speak naturally. Do not use asterisks or formatting."
            }
        ] + history

        chat_completion = self.client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant",
        )
        ai_text = chat_completion.choices[0].message.content.strip()
        print(f"🤖 AI: \"{ai_text}\"")

        # Calculate Latency
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)

        # Save AI Turn
        async with aiosqlite.connect("storage.db") as db:
            await db.execute("INSERT INTO conversations (user_id, role, content, latency_ms) VALUES (?, ?, ?, ?)", (user_id, "assistant", ai_text, latency_ms))
            await db.commit()

        # 3. TTS: Microsoft Edge Neural Voices
        print("🗣️ Synthesizing voice...")
        output_file = "ai_response.mp3"
        communicate = edge_tts.Communicate(ai_text, "en-US-ChristopherNeural")
        await communicate.save(output_file)
        
        print("✅ Pipeline Complete. Response saved to ai_response.mp3\n")
        
        return user_text, ai_text, output_file

# Quick standalone test block
if __name__ == "__main__":
    # If you run this file directly, it will test the pipeline using your last captured utterance.
    brain = BrainEngine()
    if os.path.exists("captured_utterance.wav"):
        asyncio.run(brain.process_turn("captured_utterance.wav"))
    else:
        print("❌ No captured_utterance.wav found. Run main.py and client.py first!")