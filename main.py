import os
import uvicorn
import json
import base64
import wave
import asyncio
import aiosqlite
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from pydub import AudioSegment

from audio_engine import VADEngine
from state_manager import CallManager, AgentState
from llm_engine import BrainEngine 
from database import init_db, get_db_connection
from auth import get_password_hash, verify_password, create_access_token, decode_token

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

vad_engine = VADEngine()
brain_engine = BrainEngine() 

@app.on_event("startup")
async def startup_event():
    await init_db()

class UserRegister(BaseModel):
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
 

def save_utterance_to_wav(pcm_bytes, filename="captured_utterance.wav"):
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2) # 16-bit
        wf.setframerate(16000) # Upgraded to 16kHz
        wf.writeframes(pcm_bytes)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return int(user_id)

@app.delete("/reset-memory")
async def reset_memory(user_id: int = Depends(get_current_user)):
    async with aiosqlite.connect("storage.db") as db:
        await db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        await db.commit()
    return {"message": "Memory reset successfully"}

@app.post("/register")
async def register(user: UserRegister):
    hashed_password = get_password_hash(user.password)
    async with aiosqlite.connect("storage.db") as db:
        try:
            await db.execute("INSERT INTO users (email, password_hash) VALUES (?, ?)", (user.email, hashed_password))
            await db.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(status_code=400, detail="Email already registered")
    return {"message": "User registered successfully"}

@app.post("/token", response_model=Token)
async def login(user: UserLogin):
    async with aiosqlite.connect("storage.db") as db:
        async with db.execute("SELECT id, password_hash FROM users WHERE email = ?", (user.email,)) as cursor:
            row = await cursor.fetchone()
    
    if not row or not verify_password(user.password, row[1]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": str(row[0])}) # Store User ID in token
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/")
async def get_login_page():
    # Landing page is now Login
    with open("login.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

@app.get("/dashboard")
async def get_dashboard():
    with open("dashboard.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)


@app.websocket("/ws/web")
async def websocket_web_endpoint(websocket: WebSocket, token: str = Query(...)):
    user_id = decode_token(token)
    if not user_id:
        await websocket.close(code=4003) # Forbidden
        return
    user_id = int(user_id)

    await websocket.accept()
    print("✅ Browser Client Connected [16kHz PCM Full Duplex]")
    
    call_manager = CallManager()
    user_audio_buffer = bytearray() 
    outbound_audio_queue = asyncio.Queue()

    async def send_audio_task():
        try:
            while True:
                chunk = await outbound_audio_queue.get()
                payload = base64.b64encode(chunk).decode("utf-8")
                await websocket.send_text(json.dumps({
                    "event": "media",
                    "media": {"payload": payload}
                }))
                outbound_audio_queue.task_done()
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            pass

    sender_task = asyncio.create_task(send_audio_task())

    async def process_brain_task(audio_bytes_to_process):
        await websocket.send_text(json.dumps({"event": "state", "state": AgentState.THINKING.value}))
        save_utterance_to_wav(audio_bytes_to_process)
        
        user_text, ai_text, mp3_file = await brain_engine.process_turn("captured_utterance.wav", user_id)
        
        # Send transcripts to UI
        await websocket.send_text(json.dumps({"event": "transcript", "role": "user", "text": user_text}))
        await websocket.send_text(json.dumps({"event": "transcript", "role": "ai", "text": ai_text}))
        
        if call_manager.state == AgentState.RECEIVING:
            return

        call_manager.state = AgentState.SPEAKING
        await websocket.send_text(json.dumps({"event": "state", "state": AgentState.SPEAKING.value}))
        
        # Convert MP3 straight to 16kHz PCM
        audio = AudioSegment.from_mp3(mp3_file)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        pcm_bytes = audio.raw_data
        
        chunk_size = 6400 # 200ms of 16kHz 16-bit audio = 6400 bytes
        for i in range(0, len(pcm_bytes), chunk_size):
            if call_manager.state != AgentState.SPEAKING:
                break
            chunk = pcm_bytes[i:i+chunk_size]
            await outbound_audio_queue.put(chunk)
        
        # Wait for all chunks to actually be sent over WebSocket
        await outbound_audio_queue.join()

        if call_manager.state == AgentState.SPEAKING:
            call_manager.state = AgentState.LISTENING
            await websocket.send_text(json.dumps({"event": "state", "state": AgentState.LISTENING.value}))

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message.get("event") == "media":
                audio_bytes = base64.b64decode(message["media"]["payload"])

                prob = vad_engine.process(audio_bytes)
                state_changed = call_manager.process_vad_frame(prob)

                if state_changed:
                    await websocket.send_text(json.dumps({"event": "state", "state": call_manager.state.value}))

                if call_manager.state == AgentState.RECEIVING:
                    user_audio_buffer.extend(audio_bytes) 
                    
                    if state_changed:
                        print("\n🛑 [BARGE-IN] User interrupted!")
                        # Fire a "clear" event to the browser to instantly stop playback
                        await websocket.send_text(json.dumps({"event": "clear"}))
                        while not outbound_audio_queue.empty():
                            outbound_audio_queue.get_nowait()
                            outbound_audio_queue.task_done()

                if state_changed and call_manager.state == AgentState.THINKING:
                    print("\n🧠 Processing audio...")
                    buffer_copy = bytes(user_audio_buffer)
                    user_audio_buffer.clear() 
                    asyncio.create_task(process_brain_task(buffer_copy))

    except WebSocketDisconnect:
        print("\n🔌 Client disconnected.")
    finally:
        sender_task.cancel() 

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)