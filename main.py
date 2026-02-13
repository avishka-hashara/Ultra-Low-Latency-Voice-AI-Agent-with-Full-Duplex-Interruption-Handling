import os
import uvicorn
import json
import base64
import wave
import struct
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, Response
from dotenv import load_dotenv

from audio_engine import VADEngine
from state_manager import CallManager, AgentState

load_dotenv()

app = FastAPI()
vad_engine = VADEngine()

def save_utterance_to_wav(mu_law_bytes, filename="captured_utterance.wav"):
    """Converts Mu-Law bytes back to a listenable WAV file."""
    from audio_engine import _MULAW_TABLE
    pcm_samples = [_MULAW_TABLE[b] for b in mu_law_bytes]
    pcm_bytes = struct.pack(f"<{len(pcm_samples)}h", *pcm_samples)
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000) # Standard telephony sample rate
        wf.writeframes(pcm_bytes)
    print(f"\n💾 Utterance successfully saved to {filename}!")

@app.post("/voice")
async def handle_voice_call(request: Request):
    host = request.headers.get("host") 
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response><Connect><Stream url="wss://{host}/ws" /></Connect></Response>"""
    return Response(content=twiml_response, media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Client connected")
    
    call_manager = CallManager()
    user_audio_buffer = bytearray() # 🪣 THIS IS OUR BUCKET

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("event") == "media":
                payload_b64 = message["media"]["payload"]
                audio_bytes = base64.b64decode(payload_b64)

                # 1. Run VAD
                prob = vad_engine.process(audio_bytes)
                
                # 2. Check State
                state_changed = call_manager.process_vad_frame(prob)

                # 3. Buffer Logic
                if call_manager.state == AgentState.RECEIVING:
                    user_audio_buffer.extend(audio_bytes) # Add water to the bucket
                    print("🗣️", end="", flush=True)
                
                elif call_manager.state == AgentState.LISTENING:
                    print(".", end="", flush=True)

                # 4. End of Utterance Logic
                if state_changed and call_manager.state == AgentState.THINKING:
                    print("\n🧠 [END OF SPEECH] User finished. Processing audio...")
                    
                    # Save the bucket to a file
                    save_utterance_to_wav(bytes(user_audio_buffer))
                    
                    # Empty the bucket for the next time the user speaks
                    user_audio_buffer.clear() 
                    
                    # (Temporary) Reset back to LISTENING to keep the loop going
                    call_manager.state = AgentState.LISTENING

    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        print("\n🔌 Disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)