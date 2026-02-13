import os
import uvicorn
import json
import base64
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, Response
from dotenv import load_dotenv

# NEW: Import our Audio Engine
from audio_engine import VADEngine

load_dotenv()

app = FastAPI()

# Initialize VAD (Global instance to avoid reloading per call)
vad_engine = VADEngine()

@app.post("/voice")
async def handle_voice_call(request: Request):
    host = request.headers.get("host") 
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="wss://{host}/ws" />
        </Connect>
    </Response>
    """
    return Response(content=twiml_response, media_type="application/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Client connected")

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("event") == "media":
                # 1. Extract raw payload
                payload_b64 = message["media"]["payload"]
                audio_bytes = base64.b64decode(payload_b64)

                # 2. Analyze with VAD
                # We interpret > 0.5 probability as "Speaking"
                prob = vad_engine.process(audio_bytes)
                
                if prob > 0.5:
                    print(f"🗣️  USER SPEAKING! (Prob: {prob:.2f})")
                else:
                    # Print a dot to show aliveness without spamming
                    # end="" keeps it on one line
                    print(".", end="", flush=True) 

    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        print("\n🔌 Disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)