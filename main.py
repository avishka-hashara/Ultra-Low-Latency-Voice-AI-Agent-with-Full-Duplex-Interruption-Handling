import os
import uvicorn
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, Response
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# 1. THE RECEPTIONIST (HTTP Route)
# When someone calls your Twilio number, Twilio sends a POST request here.
@app.post("/voice")
async def handle_voice_call(request: Request):
    """
    Returns TwiML (Twilio Markup Language) instructions.
    We tell Twilio: "Connect this call to our WebSocket stream."
    """
    # We need the public URL of your server (from Ngrok) to tell Twilio where to connect
    # For now, we'll construct the stream URL dynamically or use the host header
    host = request.headers.get("host") 
    
    # The <Stream> TwiML instruction tells Twilio to start a WebSocket connection
    # url=f"wss://{host}/ws" -> Connects to our websocket route below
    twiml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Say>Connecting to your AI agent.</Say>
        <Connect>
            <Stream url="wss://{host}/ws" />
        </Connect>
    </Response>
    """
    
    return Response(content=twiml_response, media_type="application/xml")

# 2. THE EAR (WebSocket Route)
# This is where the raw audio data flows in real-time.
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("✅ Twilio connected to WebSocket!")

    try:
        while True:
            # Receive data from Twilio
            data = await websocket.receive_text()
            
            # Twilio sends JSON messages. Some are setup info, some are audio.
            # We won't process them yet, just verify traffic is flowing.
            # print(f"📩 Packet received") 
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
    finally:
        print("🔌 Connection closed")

if __name__ == "__main__":
    # This starts the server on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)