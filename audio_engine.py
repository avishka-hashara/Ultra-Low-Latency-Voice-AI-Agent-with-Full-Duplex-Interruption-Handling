"""
Voice Activity Detection (VAD) Engine

A lightweight, energy-based VAD that works with Twilio's mulaw-encoded
8kHz audio streams. Uses only the standard library (no audioop, no torch).
Compatible with Python 3.13+.
"""

import struct
import math


# ── Mulaw decoding table (ITU-T G.711) ──────────────────────────────
# Pre-compute all 256 possible mulaw byte → 16-bit PCM sample mappings.
def _build_mulaw_table() -> list[int]:
    """Build a 256-entry lookup table: mulaw byte → signed 16-bit PCM."""
    MULAW_BIAS = 33
    table = []
    for byte_val in range(256):
        # Complement and extract sign / exponent / mantissa
        val = ~byte_val & 0xFF
        sign = val & 0x80
        exponent = (val >> 4) & 0x07
        mantissa = val & 0x0F

        sample = ((mantissa << 3) + MULAW_BIAS) << exponent
        sample -= MULAW_BIAS

        if sign:
            sample = -sample

        # Clamp to 16-bit range
        sample = max(-32768, min(32767, sample))
        table.append(sample)
    return table


_MULAW_TABLE = _build_mulaw_table()


# ── Mulaw encoding (PCM → mulaw, replaces audioop.lin2ulaw) ─────────
_MULAW_ENCODE_MAX = 0x1FFF
_MULAW_ENCODE_BIAS = 33

def _encode_mulaw_sample(sample: int) -> int:
    """Encode a single signed 16-bit PCM sample to a mulaw byte."""
    sign = 0
    if sample < 0:
        sign = 0x80
        sample = -sample
    sample = min(sample + _MULAW_ENCODE_BIAS, _MULAW_ENCODE_MAX)
    exponent = 7
    for exp_val in range(7, -1, -1):
        if sample & (1 << (exp_val + 3)):
            exponent = exp_val
            break
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return ~(sign | (exponent << 4) | mantissa) & 0xFF

def lin2ulaw(pcm_data: bytes, sample_width: int = 2) -> bytes:
    """Convert 16-bit linear PCM bytes to mulaw-encoded bytes."""
    n_samples = len(pcm_data) // sample_width
    samples = struct.unpack(f"<{n_samples}h", pcm_data)
    return bytes(_encode_mulaw_sample(s) for s in samples)


class VADEngine:
    """
    Simple energy-based Voice Activity Detection engine.

    Processes raw mulaw-encoded audio chunks and returns a probability
    (0.0 – 1.0) indicating the likelihood that speech is present.
    """

    def __init__(self, energy_threshold: float = 500.0, smoothing: float = 0.7):
        """
        Args:
            energy_threshold: RMS energy level above which speech is likely.
                              Twilio mulaw silence is typically ~10-50 RMS;
                              speech is ~300-3000+ RMS.
            smoothing:        Exponential moving average factor (0-1).
                              Higher → more smoothing, slower reaction.
        """
        self.energy_threshold = energy_threshold
        self.smoothing = smoothing
        self._prev_prob = 0.0

    @staticmethod
    def _mulaw_to_pcm(audio_bytes: bytes) -> list[int]:
        """Decode mulaw bytes to a list of signed 16-bit PCM samples."""
        return [_MULAW_TABLE[b] for b in audio_bytes]

    @staticmethod
    def _rms(samples: list[int]) -> float:
        """Calculate root-mean-square of a list of samples."""
        if not samples:
            return 0.0
        sum_sq = sum(s * s for s in samples)
        return math.sqrt(sum_sq / len(samples))

    def process(self, audio_bytes: bytes) -> float:
        """
        Analyze a chunk of mulaw-encoded audio bytes.

        Args:
            audio_bytes: Raw mulaw 8-bit audio data (as sent by Twilio).

        Returns:
            A float between 0.0 and 1.0 representing speech probability.
        """
        try:
            # Decode mulaw → PCM samples
            samples = self._mulaw_to_pcm(audio_bytes)

            # Calculate RMS energy
            rms = self._rms(samples)

            # Map RMS to a 0–1 probability
            raw_prob = min(1.0, rms / self.energy_threshold)

            # Exponential smoothing to reduce flickering
            smoothed = (self.smoothing * self._prev_prob) + ((1 - self.smoothing) * raw_prob)
            self._prev_prob = smoothed

            return smoothed

        except Exception:
            return 0.0