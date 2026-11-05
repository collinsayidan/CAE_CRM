"""An original, light instrumental bed for the CAE CRM videos, composed in code so there's no licence to worry about.

D major, 104 BPM: a soft pad on I-V-vi-IV, a plucked arpeggio, a round bass, a gentle kick and shaker. It builds over
the first bar, sits under the captions, and resolves on a held D chord at the very end of each length.

    python music/compose.py      writes public/music/bed-60.wav, bed-30.wav and bed-15.wav
"""
import os
import wave

import numpy as np

SR = 44100
BPM = 104
BEAT = 60 / BPM
OUT = os.path.join(os.path.dirname(__file__), "..", "public", "music")

# I - V - vi - IV in D: D, A, Bm, G (MIDI notes for the pad; the bass takes the root an octave down).
CHORDS = [[62, 66, 69, 74], [57, 64, 69, 73], [59, 62, 66, 71], [55, 62, 67, 71]]
rng = np.random.default_rng(7)


def hz(note):
    return 440 * 2 ** ((note - 69) / 12)


def env(n, attack, release):
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def lowpass(x, cutoff):
    # One-pole filter, run twice for a gentler slope.
    a = np.exp(-2 * np.pi * cutoff / SR)
    for _ in range(2):
        y = np.empty_like(x)
        acc = 0.0
        for i, v in enumerate(x):
            acc = (1 - a) * v + a * acc
            y[i] = acc
        x = y
    return x


def pad(notes, seconds):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for note in notes:
        for detune in (-0.08, 0.08):  # two slightly detuned voices per note, for width
            f = hz(note + detune)
            out += 2 * ((t * f) % 1) - 1  # saw
    return out * env(n, 0.35, 0.4) / (len(notes) * 2)


def pluck(note, seconds):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * hz(note) * t) + 0.3 * np.sin(2 * np.pi * hz(note) * 2 * t)
    return tone * np.exp(-t * 9) * env(n, 0.004, 0.02)


def bass(note, seconds):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * hz(note - 12) * t) * env(n, 0.01, 0.08) * (0.6 + 0.4 * np.exp(-t * 3))


def kick(seconds=0.35):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f = 50 + 90 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9)


def shaker(seconds=0.08):
    n = int(seconds * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    noise = noise - lowpass(noise, 5000)  # keep the top end
    return noise * np.exp(-t * 60)


def place(track, sound, at):
    i = int(at * SR)
    j = min(len(track), i + len(sound))
    if i < len(track):
        track[i:j] += sound[: j - i]


def compose(length):
    n = int((length + 1.5) * SR)  # room for the final chord to ring
    pads, plucks, low, drums = (np.zeros(n) for _ in range(4))
    bar = 4 * BEAT
    bars = int(length // bar)
    arp = [0, 1, 2, 3, 2, 1, 2, 3]  # pattern through the chord, in eighth notes
    for b in range(bars):
        chord = CHORDS[b % 4]
        start = b * bar
        place(pads, pad(chord, bar + 0.4), start)
        place(low, bass(chord[0], bar * 0.98), start)
        if b >= 1:  # the arpeggio and drums come in after the first bar
            for k, step in enumerate(arp):
                place(plucks, pluck(chord[step] + 12, BEAT * 0.9), start + k * BEAT / 2)
            for beat in range(4):
                place(drums, kick() * 0.9, start + beat * BEAT)
                place(drums, shaker() * 0.25, start + beat * BEAT + BEAT / 2)
    # The ending: a held D major chord where the music stops.
    end = bars * bar
    place(pads, pad([62, 66, 69, 74, 78], 1.8) * 1.2, end)
    place(low, bass(62, 1.6), end)
    place(plucks, pluck(74 + 12, 1.2), end)

    pads = lowpass(pads, 1800)
    mix = 0.55 * pads + 0.32 * plucks + 0.5 * low + 0.45 * drums
    # Short echo on the plucks' part of the mix for space.
    delay = int(BEAT * 0.75 * SR)
    echo = np.zeros_like(mix)
    echo[delay:] = 0.18 * plucks[:-delay]
    mix += echo
    # Fade in over the first half second, then fit it to exactly length + the ring of the last chord.
    mix *= env(len(mix), 0.5, 1.2)
    mix = mix[: int((end + 1.8) * SR)]
    mix /= np.max(np.abs(mix)) / 0.8  # leave headroom; Remotion sets the final level
    return mix


def save(name, x):
    stereo = np.stack([x, np.roll(x, 40)], axis=1)  # a touch of width
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(os.path.join(OUT, name), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    print("wrote", name, f"{len(x) / SR:.1f}s")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for seconds in (60, 30, 15):
        save(f"bed-{seconds}.wav", compose(seconds - 1.8))
