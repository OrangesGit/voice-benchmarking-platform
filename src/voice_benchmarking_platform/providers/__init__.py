from voice_benchmarking_platform.providers.base import STTProvider
from voice_benchmarking_platform.providers.openai_whisper import OpenAIWhisperProvider
from voice_benchmarking_platform.providers.deepgram import DeepgramProvider

try:
    from voice_benchmarking_platform.providers.assemblyai import AssemblyAIProvider
    __all__ = ["STTProvider", "OpenAIWhisperProvider", "DeepgramProvider", "AssemblyAIProvider"]
except ImportError:
    __all__ = ["STTProvider", "OpenAIWhisperProvider", "DeepgramProvider"]
