"""
Generates synthetic sound effects for PanelFlow animations.
All SFX are original, synthesized from scratch using numpy/scipy.

Run from this directory:
    python generate_sfx.py
"""

import os
import numpy as np
from scipy.signal import chirp, butter, lfilter
from pydub import AudioSegment

SR = 44100
OUT = os.path.dirname(os.path.abspath(__file__))


def to_seg(samples: np.ndarray) -> AudioSegment:
    samples = np.clip(samples, -1.0, 1.0)
    pcm = (samples * 32767).astype(np.int16)
    return AudioSegment(pcm.tobytes(), frame_rate=SR, sample_width=2, channels=1)


def save(seg: AudioSegment, name: str) -> None:
    path = os.path.join(OUT, name)
    seg.export(path, format="mp3", bitrate="128k")
    print(f"  wrote {name}  ({len(seg)}ms)")


def env_exp(t: np.ndarray, decay: float) -> np.ndarray:
    return np.exp(-t * decay)


# ── sfx_impact.mp3 ────────────────────────────────────────────────────────────
# Comic punch thud: 3-layer design — deep resonant sub, punchy mid body,
# hard attack transient. Used by burst, slam, punch_in, shockwave, recoil.
def make_impact() -> AudioSegment:
    dur = 0.75
    t = np.linspace(0, dur, int(SR * dur))
    n = len(t)

    # Layer 1 — deep resonant sub (the "BOOM")
    # Pitch drops fast: 150 Hz → 38 Hz over ~80 ms, then holds
    freq_sub = 38 + 112 * np.exp(-t * 30)
    phase_sub = np.cumsum(2 * np.pi * freq_sub / SR)
    sub = np.sin(phase_sub)
    # soft-clip to add warmth without harshness
    sub = np.tanh(sub * 2.0) / np.tanh(2.0)
    sub *= env_exp(t, 5)   # very slow decay — the body lingers

    # Layer 2 — mid punch body (the "THWACK")
    # Pitch drops: 320 Hz → 140 Hz over ~60 ms
    freq_mid = 140 + 180 * np.exp(-t * 40)
    phase_mid = np.cumsum(2 * np.pi * freq_mid / SR)
    mid = np.sin(phase_mid) * env_exp(t, 18) * 0.50

    # Layer 3 — attack transient: 8 ms of low-passed noise burst
    trans_len = int(SR * 0.008)
    trans = np.zeros(n)
    trans[:trans_len] = np.random.randn(trans_len)
    b_t, a_t = butter(2, 400 / (SR / 2), btype="low")
    trans = lfilter(b_t, a_t, trans) * 0.55

    # Layer 4 — faint room tail: decaying filtered noise adds size
    tail_noise = np.random.randn(n) * env_exp(t, 12) * 0.08
    b_tail, a_tail = butter(2, 300 / (SR / 2), btype="low")
    tail = lfilter(b_tail, a_tail, tail_noise)

    sig = sub * 0.65 + mid + trans + tail

    # High-pass at 28 Hz, low-pass at 900 Hz (let the mid thwack breathe, kill thin highs)
    b_hp, a_hp = butter(2, 28 / (SR / 2), btype="high")
    sig = lfilter(b_hp, a_hp, sig)
    b_lp, a_lp = butter(2, 900 / (SR / 2), btype="low")
    sig = lfilter(b_lp, a_lp, sig)

    peak = np.max(np.abs(sig)) or 1.0
    return to_seg(sig / peak * 0.93)


# ── sfx_snap.mp3 ─────────────────────────────────────────────────────────────
# Sharp crack: broadband noise burst with short, fast decay. Used by snap.
def make_snap() -> AudioSegment:
    dur = 0.18
    t = np.linspace(0, dur, int(SR * dur))
    e = env_exp(t, 55)
    noise = np.random.randn(len(t)) * e * 0.75
    tone = np.sin(2 * np.pi * 350 * t) * e * 0.25
    sig = noise + tone
    b, a = butter(2, 80 / (SR / 2), btype="high")
    sig = lfilter(b, a, sig)
    return to_seg(sig * 0.95)


# ── sfx_whoosh.mp3 ────────────────────────────────────────────────────────────
# Big descending sweep with air texture and a settling tail.
# Used by slide_*, tilt_in, spin_in.
def make_whoosh() -> AudioSegment:
    dur = 0.90
    t = np.linspace(0, dur, int(SR * dur))

    # Core sweep: wider frequency range, longer travel
    sweep = chirp(t, f0=3200, f1=80, t1=dur, method="log") * 0.55

    # Second harmonic sweep slightly offset for thickness
    sweep2 = chirp(t, f0=1600, f1=120, t1=dur, method="log") * 0.25

    # Air texture: filtered noise riding alongside the sweep
    noise = np.random.randn(len(t))
    b_n, a_n = butter(2, [200 / (SR / 2), 3000 / (SR / 2)], btype="band")
    air = lfilter(b_n, a_n, noise) * 0.20

    # Envelope: near-instant attack (3ms), long exponential tail
    e = (1 - np.exp(-t * 60)) * env_exp(t, 3.5)
    sig = (sweep + sweep2 + air) * e

    # Gentle high-pass only — keep the low-end body
    b_hp, a_hp = butter(2, 55 / (SR / 2), btype="high")
    sig = lfilter(b_hp, a_hp, sig)

    peak = np.max(np.abs(sig)) or 1.0
    return to_seg(sig / peak * 0.88)


# ── sfx_whip.mp3 ─────────────────────────────────────────────────────────────
# Very fast, tight whoosh. Used by whip_left, whip_right.
def make_whip() -> AudioSegment:
    dur = 0.22
    t = np.linspace(0, dur, int(SR * dur))
    sweep = chirp(t, f0=4000, f1=80, t1=dur, method="log") * 0.55
    noise = np.random.randn(len(t)) * 0.10
    e = (1 - np.exp(-t * 60)) * env_exp(t, 18)
    sig = (sweep + noise) * e
    b, a = butter(2, 80 / (SR / 2), btype="high")
    sig = lfilter(b, a, sig)
    return to_seg(sig * 0.90)


# ── sfx_flash.mp3 ─────────────────────────────────────────────────────────────
# Electrical snap + high crackle. Used by flash.
def make_flash() -> AudioSegment:
    dur = 0.22
    t = np.linspace(0, dur, int(SR * dur))
    e = env_exp(t, 28)
    crackle = np.random.randn(len(t)) * e * 0.45
    b_high, a_high = butter(2, 1800 / (SR / 2), btype="high")
    crackle = lfilter(b_high, a_high, crackle)
    tone = np.sin(2 * np.pi * 2200 * t) * e * 0.35
    sub = np.sin(2 * np.pi * 90 * t) * env_exp(t, 45) * 0.20
    sig = crackle + tone + sub
    return to_seg(sig * 0.88)


# ── sfx_heartbeat.mp3 ────────────────────────────────────────────────────────
# Two-beat cardiac thud (lub-dub). Used by heartbeat.
def make_heartbeat() -> AudioSegment:
    dur = 0.90
    t = np.linspace(0, dur, int(SR * dur))
    sig = np.zeros(len(t))

    def thud(start: float, amp: float) -> np.ndarray:
        tt = np.clip(t - start, 0, None)
        e = np.exp(-tt * 28)
        return (
            np.sin(2 * np.pi * 55 * tt) * 0.60
            + np.sin(2 * np.pi * 90 * tt) * 0.30
        ) * e * amp

    sig += thud(0.00, 0.85)   # lub
    sig += thud(0.22, 0.55)   # dub — slightly softer
    b, a = butter(2, 30 / (SR / 2), btype="high")
    sig = lfilter(b, a, sig)
    return to_seg(sig * 0.88)


# ── sfx_rumble.mp3 ────────────────────────────────────────────────────────────
# Low-frequency rumble with fade in/out. Used by tremble, rattle.
def make_rumble() -> AudioSegment:
    dur = 1.50
    t = np.linspace(0, dur, int(SR * dur))
    noise = np.random.randn(len(t))
    b, a = butter(4, 200 / (SR / 2), btype="low")
    low = lfilter(b, a, noise)
    # shape: 60ms fade in, 150ms fade out
    fade_in = np.minimum(t / 0.06, 1.0)
    fade_out = np.minimum((dur - t) / 0.15, 1.0)
    sig = low * fade_in * fade_out
    # normalise
    peak = np.max(np.abs(sig)) or 1.0
    return to_seg(sig / peak * 0.75)


# ── sfx_slam.mp3 ──────────────────────────────────────────────────────────────
# Panel crashing into place from the side — heavy wall-hit + metallic ring.
# Used by slam_left, slam_right.
def make_slam() -> AudioSegment:
    dur = 0.70
    t = np.linspace(0, dur, int(SR * dur))
    n = len(t)

    # Sub thud — fast pitch drop like something very heavy hitting a surface
    freq = 45 + 160 * np.exp(-t * 45)
    phase = np.cumsum(2 * np.pi * freq / SR)
    sub = np.tanh(np.sin(phase) * 2.5) / np.tanh(2.5)
    sub *= env_exp(t, 6)

    # Metallic ring — the wall resonating after impact
    ring = np.sin(2 * np.pi * 820 * t) * env_exp(t, 14) * 0.18
    ring += np.sin(2 * np.pi * 1350 * t) * env_exp(t, 20) * 0.10

    # Hard noise slam — first 12 ms only, low-passed for weight not thinness
    slam_len = int(SR * 0.012)
    slam = np.zeros(n)
    slam[:slam_len] = np.random.randn(slam_len)
    b_s, a_s = butter(2, 500 / (SR / 2), btype="low")
    slam = lfilter(b_s, a_s, slam) * 0.60

    sig = sub * 0.70 + ring + slam

    b_hp, a_hp = butter(2, 28 / (SR / 2), btype="high")
    sig = lfilter(b_hp, a_hp, sig)

    peak = np.max(np.abs(sig)) or 1.0
    return to_seg(sig / peak * 0.92)


# ── sfx_punch.mp3 ─────────────────────────────────────────────────────────────
# Aggressive zoom punch toward the viewer — short, sharp, mid-heavy thwack.
# Used by punch_in.
def make_punch() -> AudioSegment:
    dur = 0.32
    t = np.linspace(0, dur, int(SR * dur))
    n = len(t)

    # Mid-heavy smack — the "THWACK" of impact, centered around 350–600 Hz
    freq_hit = 420 + 200 * np.exp(-t * 60)
    phase_hit = np.cumsum(2 * np.pi * freq_hit / SR)
    hit = np.sin(phase_hit) * env_exp(t, 22) * 0.65

    # Body resonance — short low punch body
    freq_body = 90 + 60 * np.exp(-t * 35)
    phase_body = np.cumsum(2 * np.pi * freq_body / SR)
    body = np.sin(phase_body) * env_exp(t, 18) * 0.40

    # Very brief crack transient — 6 ms
    crack_len = int(SR * 0.006)
    crack = np.zeros(n)
    crack[:crack_len] = np.random.randn(crack_len)
    b_c, a_c = butter(2, [200 / (SR / 2), 1200 / (SR / 2)], btype="band")
    crack = lfilter(b_c, a_c, crack) * 0.50

    sig = hit + body + crack

    b_hp, a_hp = butter(2, 50 / (SR / 2), btype="high")
    sig = lfilter(b_hp, a_hp, sig)
    b_lp, a_lp = butter(2, 2000 / (SR / 2), btype="low")
    sig = lfilter(b_lp, a_lp, sig)

    peak = np.max(np.abs(sig)) or 1.0
    return to_seg(sig / peak * 0.93)


if __name__ == "__main__":
    print("Generating PanelFlow SFX...")
    save(make_impact(),    "sfx_impact.mp3")
    save(make_snap(),      "sfx_snap.mp3")
    save(make_whoosh(),    "sfx_whoosh.mp3")
    save(make_whip(),      "sfx_whip.mp3")
    save(make_flash(),     "sfx_flash.mp3")
    save(make_heartbeat(), "sfx_heartbeat.mp3")
    save(make_rumble(),    "sfx_rumble.mp3")
    save(make_slam(),      "sfx_slam.mp3")
    save(make_punch(),     "sfx_punch.mp3")
    print("Done.")
