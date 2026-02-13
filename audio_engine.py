import torch
import numpy as np

class VADEngine:
    def __init__(self):
        self.model, utils = torch.hub.load(
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False,
            trust_repo=True
        )
        self.model.eval()
        print("✅ Silero VAD Loaded")

    def process(self, pcm_int16_bytes):
        """Processes raw 16-bit PCM audio directly from the browser."""
        # Convert bytes directly to Int16 numpy array
        audio_int16 = np.frombuffer(pcm_int16_bytes, dtype=np.int16)
        # Normalize to Float32 for Silero
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        
        tensor = torch.from_numpy(audio_float32)
        # We are now running at a high-quality 16000Hz sample rate!
        speech_prob = self.model(tensor, 16000).item() 
        return speech_prob