import asyncio
import websockets
import json
import base64
import wave
import struct

# ── Pure-Python lin2ulaw (replaces audioop, removed in Python 3.13+) ──
_MULAW_MAX = 0x1FFF
_MULAW_BIAS = 33

def _encode_mulaw_sample(sample: int) -> int:
    """Encode a single signed 16-bit PCM sample to a mulaw byte."""
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    sample = min(sample + _MULAW_BIAS, _MULAW_MAX)
    exponent = 7
    for exp_val in range(7, -1, -1):
        if sample & (1 << (exp_val + 3)):
            exponent = exp_val
            break
    mantissa = (sample >> (exponent + 3)) & 0x0F
    mulaw_byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
    return mulaw_byte

def lin2ulaw(pcm_data: bytes, sample_width: int = 2) -> bytes:
    """Convert 16-bit linear PCM bytes to mulaw-encoded bytes."""
    n_samples = len(pcm_data) // sample_width
    samples = struct.unpack(f"<{n_samples}h", pcm_data)
    return bytes(_encode_mulaw_sample(s) for s in samples)


# The file we are going to stream
WAV_FILE = "test_speech.wav" 

async def stream_wav():
    uri = "ws://localhost:8000/ws"
    
    try:
        # Open the WAV file
        wf = wave.open(WAV_FILE, 'rb')
        print(f"🎵 Opened {WAV_FILE} (Sample Rate: {wf.getframerate()}Hz)")
        
        async with websockets.connect(uri) as websocket:
            print(f"✅ Connected to Server at {uri}")
            print("🚀 Streaming audio chunks in real-time...")

            # Calculate how many frames equal 20 milliseconds of audio
            chunk_size = int(wf.getframerate() * 0.02) 

            while True:
                frames = wf.readframes(chunk_size)
                
                if not frames:
                    print("\n🏁 Finished streaming file.")
                    break

                # The Engineering Part: Mimic Twilio's network compression.
                # Telecom networks compress standard PCM audio to Mu-Law.
                if wf.getsampwidth() == 2:
                    mu_law_data = lin2ulaw(frames, 2)
                else:
                    mu_law_data = frames 

                # Encode to Base64 (JSON requirement)
                payload = base64.b64encode(mu_law_data).decode("utf-8")

                # Wrap in Twilio's exact JSON structure
                message = {
                    "event": "media",
                    "media": {
                        "payload": payload
                    }
                }
                
                await websocket.send(json.dumps(message))
                
                # Sleep 20ms to simulate the latency of an actual phone call
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