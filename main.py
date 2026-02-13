import os
import uvicorn
import json
import base64
import wave
import audioop
import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, Response
from dotenv import load_dotenv
from pydub import AudioSegment

# Point pydub to the winget-installed ffmpeg (add to PATH at runtime)
_ffmpeg_dir = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    r"Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
)
if os.path.isdir(_ffmpeg_dir):
    os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

from audio_engine import VADEngine
from state_manager import CallManager, AgentState
from llm_engine import BrainEngine # 🧠 IMPORT YOUR BRAIN

load_dotenv()

app = FastAPI()
vad_engine = VADEngine()
brain_engine = BrainEngine() # Initialize once

def save_utterance_to_wav(mu_law_bytes, filename="captured_utterance.wav"):
    pcm_bytes = audioop.ulaw2lin(mu_law_bytes, 2)
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000) 
        wf.writeframes(pcm_bytes)

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
    user_audio_buffer = bytearray() 

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("event") == "media":
                payload_b64 = message["media"]["payload"]
                audio_bytes = base64.b64decode(payload_b64)

                prob = vad_engine.process(audio_bytes)
                state_changed = call_manager.process_vad_frame(prob)

                if call_manager.state == AgentState.RECEIVING:
                    user_audio_buffer.extend(audio_bytes) 
                    print("🗣️", end="", flush=True)
                
                elif call_manager.state == AgentState.LISTENING:
                    print(".", end="", flush=True)

                # --- 🧠 THE COGNITIVE TRIGGER ---
                if state_changed and call_manager.state == AgentState.THINKING:
                    print("\n🧠 [END OF SPEECH] User finished. Processing audio...")
                    save_utterance_to_wav(bytes(user_audio_buffer))
                    user_audio_buffer.clear() 
                    
                    # 1. Ask the Brain for a response
                    ai_text, mp3_file = await brain_engine.process_turn("captured_utterance.wav")
                    
                    # 2. Convert the MP3 to Telecom Standards
                    call_manager.state = AgentState.SPEAKING
                    print("🔈 Streaming response back to client...")
                    
                    audio = AudioSegment.from_mp3(mp3_file)
                    audio = audio.set_frame_rate(8000).set_channels(1)
                    pcm_bytes = audio.raw_data
                    mu_law_bytes = audioop.lin2ulaw(pcm_bytes, 2)
                    
                    # 3. Stream it back in 20ms chunks (160 bytes)
                    chunk_size = 160
                    for i in range(0, len(mu_law_bytes), chunk_size):
                        chunk = mu_law_bytes[i:i+chunk_size]
                        payload = base64.b64encode(chunk).decode("utf-8")
                        
                        await websocket.send_text(json.dumps({
                            "event": "media",
                            "media": {"payload": payload}
                        }))
                        await asyncio.sleep(0.02)
                    
                    # 4. Done speaking, back to listening
                    call_manager.state = AgentState.LISTENING
                    print("\n✅ Finished speaking. Back to listening...")

    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        print("\n🔌 Disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)