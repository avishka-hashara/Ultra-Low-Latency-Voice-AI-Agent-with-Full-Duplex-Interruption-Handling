import os
import asyncio
import edge_tts
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class BrainEngine:
    def __init__(self):
        # Groq client automatically picks up GROQ_API_KEY from your .env
        self.client = Groq()
        
    async def process_turn(self, audio_file_path: str):
        """
        Executes the STT -> LLM -> TTS pipeline.
        """
        print("\n--- 🧠 COGNITIVE PIPELINE STARTED ---")
        
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

        # 2. LLM: Llama 3 on Groq
        print("⚡ Generating response...")
        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    # Strict prompt engineering for voice: Keep it short, no markdown, highly conversational.
                    "content": "You are a witty, ultra-fast AI voice assistant. Keep your answers strictly under 2 sentences. Speak naturally. Do not use asterisks or formatting."
                },
                {
                    "role": "user",
                    "content": user_text,
                }
            ],
            model="llama-3.1-8b-instant",
        )
        ai_text = chat_completion.choices[0].message.content.strip()
        print(f"🤖 AI: \"{ai_text}\"")

        # 3. TTS: Microsoft Edge Neural Voices
        print("🗣️ Synthesizing voice...")
        output_file = "ai_response.mp3"
        
        # 'en-US-ChristopherNeural' is a solid, natural male voice. 
        # You can change this later using `edge-tts --list-voices` in terminal.
        communicate = edge_tts.Communicate(ai_text, "en-US-ChristopherNeural")
        await communicate.save(output_file)
        
        print("✅ Pipeline Complete. Response saved to ai_response.mp3\n")
        
        return ai_text, output_file

# Quick standalone test block
if __name__ == "__main__":
    # If you run this file directly, it will test the pipeline using your last captured utterance.
    brain = BrainEngine()
    if os.path.exists("captured_utterance.wav"):
        asyncio.run(brain.process_turn("captured_utterance.wav"))
    else:
        print("❌ No captured_utterance.wav found. Run main.py and client.py first!")