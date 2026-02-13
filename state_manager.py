from enum import Enum

class AgentState(Enum):
    LISTENING = "LISTENING"  # Waiting for user to speak
    RECEIVING = "RECEIVING"  # User is actively speaking
    THINKING = "THINKING"    # Waiting for LLM response
    SPEAKING = "SPEAKING"    # AI is talking

class CallManager:
    def __init__(self):
        self.state = AgentState.LISTENING
        self.speech_streak = 0
        self.silence_streak = 0
        
        # Thresholds (Tuning these is the secret to good voice AI)
        self.SPEECH_THRESHOLD = 3   # 3 frames (60ms) of speech to trigger "Barge-In"
        self.SILENCE_THRESHOLD = 25 # 25 frames (500ms) of silence to trigger "Thinking"

    def process_vad_frame(self, speech_prob: float):
        """
        Takes the probability from Silero VAD and updates the state machine.
        Returns a boolean indicating if a state change just happened.
        """
        is_speaking_now = speech_prob > 0.6
        state_changed = False

        if is_speaking_now:
            self.speech_streak += 1
            self.silence_streak = 0
        else:
            self.silence_streak += 1
            self.speech_streak = 0

        # State Transitions
        if self.state in [AgentState.LISTENING, AgentState.SPEAKING]:
            # BARGE-IN LOGIC: If AI was speaking, and user interrupts
            if self.speech_streak >= self.SPEECH_THRESHOLD:
                self.state = AgentState.RECEIVING
                state_changed = True
                print("\n🛑 [BARGE-IN DETECTED] AI stopped. User is speaking...")

        elif self.state == AgentState.RECEIVING:
            # END OF SPEECH LOGIC: User finished their sentence
            if self.silence_streak >= self.SILENCE_THRESHOLD:
                self.state = AgentState.THINKING
                state_changed = True
                print("\n🧠 [END OF SPEECH] User finished. AI is thinking...")

        return state_changed