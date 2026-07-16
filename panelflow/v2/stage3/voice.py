"""3.1 voice: a narration line becomes an audio file, a duration, and word timings.

This runs before the manifest is compiled because it is what *decides* the
timings. The director wrote `at_fraction: 0.4` — four tenths of the way through
a shot whose length nobody knew yet, because the length is however long the
voice takes to say the line. Only once the audio exists is there a second
number to turn that fraction into.

Every step here is cached on disk and keyed by the file it produces, so a rerun
after a failure re-speaks only the shots that never finished. TTS is the
slowest thing in the pipeline; it should be paid for once.
"""
import os

from custom_logger import logger_config

from .. import jsonio

# A silent shot still has to sit on screen for a beat. The director sets
# `silent_seconds`; this is only the floor for a shot that somehow has neither.
MIN_SECONDS = 1.0


def run(assets, target, shots):
    """Voice every shot. Returns one entry per shot, in order.

    Each entry is `{"audio": path or None, "duration": seconds,
    "word_timings": [...]}`.
    """
    from jebin_lib import HFTTSClient, HFSTTClient  # not importable in the test env

    os.makedirs(os.path.dirname(assets.shot_audio_path(target, 1)), exist_ok=True)
    tts, stt = HFTTSClient(), HFSTTClient()

    voiced = []
    for shot in shots:
        voiced.append(_voice_shot(assets, target, shot, len(shots), tts, stt))
    spoken = sum(1 for v in voiced if v["audio"])
    logger_config.info(
        f"3.1 {target}: {spoken} shot(s) voiced, {len(voiced) - spoken} silent")
    return voiced


def _voice_shot(assets, target, shot, total, tts, stt):
    from jebin_lib import utils

    from panelflow import common

    narration = (shot.get("narration") or "").strip()
    if not narration:
        return {"audio": None,
                "duration": float(shot.get("silent_seconds") or MIN_SECONDS),
                "word_timings": []}

    path = assets.shot_audio_path(target, shot["id"])
    if not utils.is_valid_audio(path):
        logger_config.info(f"3.1 {target}: speaking shot {shot['id']} of {total}")
        tts.generate_audio_segment(narration, path)
        utils.trim_silence(path)
        utils.speed_up_audio(path)

    _, duration, _, _ = common.get_media_metadata(path)
    return {"audio": path,
            "duration": max(float(duration), MIN_SECONDS),
            "word_timings": _word_timings(path, stt)}


def _word_timings(audio_path, stt):
    """Word-level timings for the kinetic subtitles.

    `transcribe` reports success by writing `<audio>.json` beside the audio
    rather than by returning anything useful, so the file is both the cache and
    the result.
    """
    from jebin_lib import utils

    json_path = audio_path.replace(".wav", ".json")
    if not utils.is_valid_json(json_path):
        stt.transcribe(audio_path)
    if not utils.is_valid_json(json_path):
        logger_config.warning(
            f"3.1: no word timings for {os.path.basename(audio_path)} — "
            f"the shot still plays, without kinetic subtitles")
        return []

    words = jsonio.read(json_path, {}).get("segments", {}).get("word", [])
    return [{"word": word.get("word", ""),
             "start": word.get("start", 0.0),
             "end": word.get("end", 0.0)}
            for word in words]
