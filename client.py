import asyncio
import websockets
import json
import base64
import wave
import audioop

FILE_1 = "test_speech.wav"
FILE_2 = "interrupt.wav" # Ensure this file exists in your folder!

async def listen_to_server(websocket):
    """Background task to catch the AI's response."""
    ai_audio_buffer = bytearray()
    try:
        while True:
            data = await websocket.recv()
            message = json.loads(data)
            
            if message.get("event") == "media":
                payload = message["media"]["payload"]
                chunk = base64.b64decode(payload)
                pcm_chunk = audioop.ulaw2lin(chunk, 2)
                ai_audio_buffer.extend(pcm_chunk)
                
                print("🔊", end="", flush=True)
                
    except websockets.exceptions.ConnectionClosed:
        pass 
    except Exception as e:
        print(f"\n❌ Listener Error: {e}")
    finally:
        if len(ai_audio_buffer) > 0:
            with wave.open("server_response.wav", "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(ai_audio_buffer)
            print("\n💾 Saved combined AI responses to server_response.wav")

async def send_silence(websocket, duration_seconds):
    """Helper to send exact amounts of telecom silence."""
    frames = int(duration_seconds / 0.02)
    silence_bytes = b'\xff' * 160 
    payload = base64.b64encode(silence_bytes).decode("utf-8")
    
    for _ in range(frames):
        message = {"event": "media", "media": {"payload": payload}}
        await websocket.send(json.dumps(message))
        await asyncio.sleep(0.02)

async def stream_file(filename, websocket):
    """Helper to handle DSP and stream a specific wav file."""
    try:
        wf = wave.open(filename, 'rb')
        in_rate = wf.getframerate()
        out_rate = 8000
        
        print(f"\n🎵 Streaming {filename} (Sample Rate: {in_rate}Hz -> {out_rate}Hz)...")
        chunk_size = int(in_rate * 0.02) 
        rate_state = None

        while True:
            frames = wf.readframes(chunk_size)
            if not frames:
                break

            if wf.getnchannels() == 2:
                frames = audioop.tomono(frames, 2, 0.5, 0.5)
            if in_rate != out_rate:
                frames_8k, rate_state = audioop.ratecv(frames, 2, 1, in_rate, out_rate, rate_state)
            else:
                frames_8k = frames

            mu_law_data = audioop.lin2ulaw(frames_8k, 2)
            payload = base64.b64encode(mu_law_data).decode("utf-8")
            
            message = {"event": "media", "media": {"payload": payload}}
            await websocket.send(json.dumps(message))
            await asyncio.sleep(0.02) 

    except FileNotFoundError:
        print(f"\n❌ Error: Could not find '{filename}'. Did you create it?")

async def run_barge_in_test():
    uri = "ws://localhost:8000/ws"
    
    async with websockets.connect(uri) as websocket:
        print(f"✅ Connected to Server at {uri}")
        
        # 1. Start the Ear
        asyncio.create_task(listen_to_server(websocket))
        
        # 2. Send the first message
        await stream_file(FILE_1, websocket)
        
        # 3. Trigger the AI to think and respond
        print("🤐 User went silent. Waiting for AI to process...")
        await send_silence(websocket, duration_seconds=1.5)
        
        # 4. Give the AI time to generate TTS and start speaking
        print("⏳ Letting AI talk for a moment...")
        await send_silence(websocket, duration_seconds=2.0)
        
        # 5. THE INTERRUPTION
        print("\n💥 BARGE-IN! User interrupts the AI mid-sentence!")
        await stream_file(FILE_2, websocket)
        
        # 6. Trigger AI's second response
        print("🤐 User went silent again. Waiting for AI's reaction...")
        await send_silence(websocket, duration_seconds=1.5)
        
        # 7. Stay on the line to hear the final response
        print("📞 Staying on the line for 5 seconds to catch audio...")
        await send_silence(websocket, duration_seconds=5.0)
        
        print("\n📞 Test complete. Hanging up.")

if __name__ == "__main__":
    try:
        asyncio.run(run_barge_in_test())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")