import os
import uvicorn
import json
import base64
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, Response
from dotenv import load_dotenv

from audio_engine import VADEngine
from state_manager import CallManager, AgentState  # NEW IMPORT

load_dotenv()

app = FastAPI()
vad_engine = VADEngine()

@app.post("/voice")
async def handle_voice_call(request: Request):
    host = request.headers.get("host") 
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect><Stream url="wss://{host}/ws" /></Connect>
    </Response>"""
    return Response(content=twiml_response, media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Client connected")
    
    call_manager = CallManager() # Initialize state for this specific call

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("event") == "media":
                payload_b64 = message["media"]["payload"]
                audio_bytes = base64.b64decode(payload_b64)

                # 1. Run VAD
                prob = vad_engine.process(audio_bytes)
                
                # 2. Feed probability to the State Machine
                call_manager.process_vad_frame(prob)

                # 3. Visual feedback for the terminal
                if call_manager.state == AgentState.RECEIVING:
                    print("🗣️", end="", flush=True)
                elif call_manager.state == AgentState.LISTENING:
                    print(".", end="", flush=True)

    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        print("\n🔌 Disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)