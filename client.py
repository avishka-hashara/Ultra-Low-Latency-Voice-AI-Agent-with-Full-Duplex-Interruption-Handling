import asyncio
import websockets
import json
import base64
import wave
import audioop

# The file we are going to stream
WAV_FILE = "test_speech.wav" 

async def stream_wav():
    uri = "ws://localhost:8000/ws"
    
    try:
        wf = wave.open(WAV_FILE, 'rb')
        in_rate = wf.getframerate()
        out_rate = 8000  # Target telecom sample rate
        
        print(f"🎵 Opened {WAV_FILE} (Sample Rate: {in_rate}Hz -> Resampling to {out_rate}Hz)")
        
        async with websockets.connect(uri) as websocket:
            print(f"✅ Connected to Server at {uri}")
            print("🚀 Streaming audio chunks in real-time...")

            # We want to read 20ms of audio at the ORIGINAL sample rate
            chunk_size = int(in_rate * 0.02) 
            
            # State required for audioop continuous rate conversion
            rate_state = None

            while True:
                frames = wf.readframes(chunk_size)
                
                if not frames:
                    print("\n🏁 Finished streaming file. Staying on the line in silence...")
                    
                    # Hardcode exactly 160 bytes of Mu-Law silence (20ms at 8kHz)
                    silence_bytes = b'\xff' * 160 
                    silence_payload = base64.b64encode(silence_bytes).decode("utf-8")
                    
                    for _ in range(50):
                        message = {
                            "event": "media", 
                            "media": {"payload": silence_payload}
                        }
                        await websocket.send(json.dumps(message))
                        await asyncio.sleep(0.02)
                        
                    print("📞 Hanging up.")
                    break

                # --- DSP PIPELINE ---
                
                # 1. Convert to Mono if the source is stereo
                if wf.getnchannels() == 2:
                    frames = audioop.tomono(frames, 2, 0.5, 0.5)

                # 2. Resample from Source Rate (e.g., 44100) to Target Rate (8000)
                if in_rate != out_rate:
                    frames_8k, rate_state = audioop.ratecv(frames, 2, 1, in_rate, out_rate, rate_state)
                else:
                    frames_8k = frames

                # 3. Compress to Mu-Law
                mu_law_data = audioop.lin2ulaw(frames_8k, 2)

                # --------------------

                payload = base64.b64encode(mu_law_data).decode("utf-8")
                message = {
                    "event": "media",
                    "media": {
                        "payload": payload
                    }
                }
                
                await websocket.send(json.dumps(message))
                await asyncio.sleep(0.02) 

    except FileNotFoundError:
        print(f"❌ Error: Could not find '{WAV_FILE}'. Check the folder.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(stream_wav())
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")