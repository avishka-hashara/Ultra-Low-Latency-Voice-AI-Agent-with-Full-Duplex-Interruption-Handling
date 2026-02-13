import os
import uvicorn
import json
import base64
import wave
import audioop
import asyncio
from fastapi import FastAPI, WebSocket, Request, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from dotenv import load_dotenv

# Auto-detect winget-installed ffmpeg BEFORE importing pydub
_ffmpeg_dir = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    r"Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin"
)
if os.path.isdir(_ffmpeg_dir):
    os.environ["PATH"] = _ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

from pydub import AudioSegment

from audio_engine import VADEngine
from state_manager import CallManager, AgentState
from llm_engine import BrainEngine 

load_dotenv()

app = FastAPI()
vad_engine = VADEngine()
brain_engine = BrainEngine() 

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
    print("✅ Client connected [Full Duplex Mode]")
    
    call_manager = CallManager()
    user_audio_buffer = bytearray() 
    
    # 🗄️ The Async Queue: Decouples the Mouth from the Brain
    outbound_audio_queue = asyncio.Queue()

    # --- TASK 1: THE MOUTH (Sender Loop) ---
    async def send_audio_task():
        try:
            while True:
                # This pauses safely until a chunk is placed in the queue
                chunk = await outbound_audio_queue.get()
                
                payload = base64.b64encode(chunk).decode("utf-8")
                await websocket.send_text(json.dumps({
                    "event": "media",
                    "media": {"payload": payload}
                }))
                
                outbound_audio_queue.task_done()
                await asyncio.sleep(0.02) # Standard network tick
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"❌ Sender Error: {e}")

    sender_task = asyncio.create_task(send_audio_task())

    # --- TASK 2: THE BRAIN (Cognitive Background Process) ---
    async def process_brain_task(audio_bytes_to_process):
        save_utterance_to_wav(audio_bytes_to_process)
        
        # Run the heavy LLM/TTS pipeline
        ai_text, mp3_file = await brain_engine.process_turn("captured_utterance.wav")
        
        # 🛑 BARGE-IN CHECK #1: Did the user start talking while we were thinking?
        if call_manager.state == AgentState.RECEIVING:
            print("\n🛑 Aborting reply. User spoke while I was thinking.")
            return

        call_manager.state = AgentState.SPEAKING
        print("🔈 Queueing response for playback...")
        
        audio = AudioSegment.from_mp3(mp3_file)
        audio = audio.set_frame_rate(8000).set_channels(1)
        pcm_bytes = audio.raw_data
        mu_law_bytes = audioop.lin2ulaw(pcm_bytes, 2)
        
        chunk_size = 160
        for i in range(0, len(mu_law_bytes), chunk_size):
            # 🛑 BARGE-IN CHECK #2: Did the user start talking while we were queueing?
            if call_manager.state != AgentState.SPEAKING:
                break
            
            chunk = mu_law_bytes[i:i+chunk_size]
            await outbound_audio_queue.put(chunk)
        
        # Reset state if the AI finished its sentence without interruption
        if call_manager.state == AgentState.SPEAKING:
            call_manager.state = AgentState.LISTENING
            print("\n✅ Finished queueing speech. Listening...")

    # --- TASK 3: THE EAR (Main WebSocket Loop) ---
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

                    # 🛑 THE BARGE-IN TRIGGER 🛑
                    # If we just switched to speaking mode, clear the Mouth's queue immediately!
                    if state_changed:
                        print("\n🛑 [BARGE-IN] Silencing the AI!")
                        while not outbound_audio_queue.empty():
                            outbound_audio_queue.get_nowait()
                            outbound_audio_queue.task_done()
                
                elif call_manager.state == AgentState.LISTENING:
                    print(".", end="", flush=True)

                if state_changed and call_manager.state == AgentState.THINKING:
                    print("\n🧠 [END OF SPEECH] Dispatching to Brain...")
                    
                    # Copy the buffer and clear it so the Ear is ready immediately
                    buffer_copy = bytes(user_audio_buffer)
                    user_audio_buffer.clear() 
                    
                    # Fire-and-forget the Brain task
                    asyncio.create_task(process_brain_task(buffer_copy))

    except WebSocketDisconnect:
        print("\n🔌 Client disconnected.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        sender_task.cancel() # Kill the mouth task cleanly
        print("\n🔌 Socket closed")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)