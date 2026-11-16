"""
Pulse evidence check for the public try page (and anything else that gets a recording from an unknown source).

Why it exists: the 4-stage model was trained on SIMULATED clips. A recording of plain air, breath or room noise is far
from anything it saw, and it can still answer "infested". Literature (claims L3, L4) describes larval activity as trains
of SHORT pulses (milliseconds to a few tens of ms) rising above a quiet background. So before we believe a non-healthy
answer we ask a simple, explainable question: did we hear short, separate pulses well above the background level?
If not, the sound is reported as "no larva-like pulses" instead of an infestation stage.

This is a plain signal-processing rule (no training). It is NOT proof of infestation, and it does not make the model
better on real palms. It only stops obvious non-larval sounds (air, hum, fans, speech) from being reported as infestation.
"""
import numpy as np
from scipy.signal import butter, sosfiltfilt, hilbert, find_peaks, peak_widths

BAND = (150.0, 1800.0)        # Hz. Wind/breath rumble and mains hum are mostly below 150 Hz.
ENV_HZ = 200.0                # the envelope is kept at 200 values per second (5 ms bins)
FLOOR_WINDOW_S = 1.0          # background level = a low percentile of the envelope in a sliding 1 s window
FLOOR_PCT = 40
HEIGHT_RATIO = 6.0            # a pulse must rise this many times above the local background
MIN_DISTANCE_S = 0.045        # two pulses closer than this count as one
MAX_WIDTH_S = 0.080           # a pulse is short: envelope width at half height below 80 ms (speech syllables and gusts are longer)
MIN_EVENTS = 2                # fewer separate pulses than this in the whole clip: "no larva-like pulses"
MAX_ACTIVE_FRACTION = 0.35    # if the envelope is far above the background for more than this share of the time, it is a sustained sound, not pulses


def _bandpass(x, sr):
    hi = min(BAND[1], sr / 2 - 50.0)
    sos = butter(4, [BAND[0], hi], btype="bandpass", fs=sr, output="sos")
    return sosfiltfilt(sos, x)


def _envelope(y, sr):
    env = np.abs(hilbert(y))
    step = max(1, int(round(sr / ENV_HZ)))
    n = (len(env) // step) * step
    return env[:n].reshape(-1, step).mean(axis=1), sr / step


def pulse_evidence(audio, sr=4000):
    """Returns {"n_events", "events_per_s", "duration_s", "median_width_ms", "active_fraction", "silent"}. audio: 1-D float array."""
    x = np.asarray(audio, dtype=np.float64).ravel()
    dur = len(x) / float(sr) if sr else 0.0
    out = {"n_events": 0, "events_per_s": 0.0, "duration_s": round(dur, 2), "median_width_ms": None, "active_fraction": 0.0, "silent": False, "times_s": []}
    if len(x) < sr * 0.5:
        out["silent"] = True
        return out
    x = x - np.mean(x)
    if float(np.sqrt(np.mean(x ** 2))) < 1e-5:
        out["silent"] = True
        return out
    env, er = _envelope(_bandpass(x, sr), sr)
    w = max(3, int(FLOOR_WINDOW_S * er)) | 1
    pad = np.pad(env, (w // 2, w // 2), mode="reflect")
    floor = np.percentile(np.lib.stride_tricks.sliding_window_view(pad, w), FLOOR_PCT, axis=1)[: len(env)]
    floor = np.maximum(floor, 1e-9 + 0.02 * float(np.median(env)))
    ratio = env / floor
    out["active_fraction"] = round(float(np.mean(ratio > 2.5)), 3)
    peaks, _ = find_peaks(ratio, height=HEIGHT_RATIO, distance=max(1, int(MIN_DISTANCE_S * er)))
    if len(peaks) == 0:
        return out
    widths = peak_widths(ratio, peaks, rel_height=0.5)[0] / float(er)
    keep = widths <= MAX_WIDTH_S
    n = int(np.sum(keep))
    out["n_events"] = n
    out["events_per_s"] = round(n / dur, 2) if dur else 0.0
    out["times_s"] = [round(float(t) / er, 2) for t in peaks[keep][:80]]
    if n:
        out["median_width_ms"] = round(float(np.median(widths[keep])) * 1000.0, 1)
    return out


def min_events_for(duration_s):
    """At least MIN_EVENTS pulses, and for long clips about one pulse per 5 seconds (so 12 s needs 3)."""
    import math
    return max(MIN_EVENTS, int(math.ceil(0.2 * float(duration_s or 0.0))))


def has_pulses(evidence):
    return ((not evidence.get("silent")) and evidence.get("n_events", 0) >= min_events_for(evidence.get("duration_s"))
            and evidence.get("active_fraction", 0.0) <= MAX_ACTIVE_FRACTION)
