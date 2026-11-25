import io

import openai

from voice_input.config import Config


class TranscribeError(Exception):
    pass


def _client(api_key: str):
    return openai.OpenAI(api_key=api_key, timeout=30.0, max_retries=2)


def transcribe(wav: bytes, config: Config) -> str:
    optional = {}
    if config.language is not None:
        optional["language"] = config.language
    try:
        result = _client(config.api_key).audio.transcriptions.create(
            model=config.model,
            file=("audio.wav", io.BytesIO(wav), "audio/wav"),
            **optional,
        )
    except Exception as exc:
        raise TranscribeError(f"Transcription failed: {exc}") from exc
    return result.text.strip()
