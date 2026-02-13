import asyncio
import websockets
import json
import base64
import wave
import audioop

WAV_FILE = "test_speech.wav" 

async def listen_to_server(websocket):
    """Background task that catches the AI's response and saves it."""
    ai_audio_buffer = bytearray()
    try:
        while True:
            data = await websocket.recv()
            message = json.loads(data)
            
            if message.get("event") == "media":
                payload = message["media"]["payload"]
                chunk = base64.b64decode(payload)
                # Decode AI's Mu-Law back to listenable PCM
                pcm_chunk = audioop.ulaw2lin(chunk, 2)
                ai_audio_buffer.extend(pcm_chunk)
                
                # Visual feedback that the AI is talking
                print("🔊", end="", flush=True)
                
    except websockets.exceptions.ConnectionClosed:
        pass # Normal when we hang up
    except Exception as e:
        print(f"\n❌ Listener Error: {e}")
    finally:
        # When we hang up, save everything the AI said to a file
        if len(ai_audio_buffer) > 0:
            with wave.open("server_response.wav", "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(8000)
                wf.writeframes(ai_audio_buffer)
            print("\n💾 Saved AI response to server_response.wav")

async def stream_wav():
    uri = "ws://localhost:8000/ws"
    
    try:
        wf = wave.open(WAV_FILE, 'rb')
        in_rate = wf.getframerate()
        out_rate = 8000
        
        async with websockets.connect(uri) as websocket:
            print(f"✅ Connected to Server at {uri}")
            
            # --- START THE EAR (Concurrent Listener) ---
            listener_task = asyncio.create_task(listen_to_server(websocket))
            # -------------------------------------------
            
            print("🚀 Streaming audio chunks in real-time...")
            chunk_size = int(in_rate * 0.02) 
            rate_state = None
            finished_streaming = False

            while True:
                frames = wf.readframes(chunk_size)
                
                if not frames:
                    if not finished_streaming:
                        print("\n🏁 Finished streaming file. Sending silence to trigger AI...")
                        silence_bytes = b'\xff' * 160 
                        silence_payload = base64.b64encode(silence_bytes).decode("utf-8")
                        
                        for _ in range(50):
                            message = {"event": "media", "media": {"payload": silence_payload}}
                            await websocket.send(json.dumps(message))
                            await asyncio.sleep(0.02)
                            
                        print("📞 Waiting on the line for AI response... (Press Ctrl+C to hang up)")
                        finished_streaming = True
                    
                    # Keep the connection alive while we wait for the server to think and reply
                    await asyncio.sleep(1) 
                    continue

                # DSP PIPELINE (Send Audio)
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

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(stream_wav())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")