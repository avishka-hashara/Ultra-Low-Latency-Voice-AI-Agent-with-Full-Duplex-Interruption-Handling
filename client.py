import asyncio
import websockets
import json
import base64

# Simulating 20ms of silence (160 bytes for 8kHz mu-law or similar)
# We'll just send a dummy payload to test the connection.
DUMMY_PAYLOAD = base64.b64encode(b'\x00' * 160).decode("utf-8")

async def stream_silence():
    uri = "ws://localhost:8000/ws"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ Connected to Server at {uri}")
            print("🚀 Streaming 'Silence' packets... (Press Ctrl+C to stop)")

            while True:
                # Construct the "Media" event that Twilio would send
                message = {
                    "event": "media",
                    "media": {
                        "payload": DUMMY_PAYLOAD,
                        "track": "inbound",
                        "chunk": "1"
                    },
                    "streamSid": "test_stream_123"
                }
                
                # Send the JSON frame
                await websocket.send(json.dumps(message))
                
                # Wait 20ms (standard packet size duration)
                await asyncio.sleep(0.02)

    except ConnectionRefusedError:
        print(f"❌ Connection Refused. Is the server running on {uri}?")
    except KeyboardInterrupt:
        print("\n🛑 Test stopped.")

if __name__ == "__main__":
    asyncio.run(stream_silence())