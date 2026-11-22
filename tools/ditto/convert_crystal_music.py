#!/usr/bin/env python3
"""Convert Pokemon Crystal's music to GBA (m4a) songs in its original Game Boy sound.

Usage:
    python3 tools/ditto/convert_crystal_music.py /path/to/pokecrystal [--report]

The Game Boy Advance still has the Game Boy's four sound channels (two pulse,
one programmable wave, one noise), and pokeemerald's m4a engine can drive them
with "CGB" voices. This tool reads pokecrystal's audio source and writes m4a
song assembly that plays each Crystal channel on the same hardware channel:

    Crystal channel 1 (pulse)  -> track 1, voice_square_1
    Crystal channel 2 (pulse)  -> track 2, voice_square_2
    Crystal channel 3 (wave)   -> track 3, voice_programmable_wave (one voice
                                  per Crystal wave sample)
    Crystal channel 4 (noise)  -> track 4, voice_noise (Crystal drum kits)

Songs are written as m4a assembly directly rather than as MIDI for mid2agb,
because that keeps each channel's own loop point (Crystal channels loop
independently, MIDI loops are song-wide) and gives exact control over voices.

Outputs (all regenerated on every run):
    sound/songs/gsc/mus_gsc_*.s         one file per song
    sound/voicegroups/gsc.inc           per-song voicegroups and the wave samples
    sound/song_table.inc                block marked ditto:convert_crystal_music
    include/constants/songs.h           block marked ditto:convert_crystal_music
    tools/ditto/crystal_music_map.json  MUSIC_* -> MUS_GSC_*

How Crystal's audio engine maps onto m4a:

* Timing. Crystal plays a note for speed * length "units", and a unit lasts
  tempo / 256 frames. One unit becomes one m4a tick; m4a plays bpm / 150
  ticks per frame, so the m4a tempo byte (bpm / 2) is 19200 / Crystal tempo,
  rounded (error under 0.5%).
* Pitch. Crystal's frequency table and octave shifts produce exactly the same
  Game Boy frequency registers as m4a's key table: Crystal octave 1 C is m4a
  key 36. Transposition is applied the way Crystal applies it. pitch_offset
  (the slight detune between the two pulse channels) becomes a per-note TUNE.
* Volume envelopes. A Crystal envelope (initial volume, fade direction and
  pace) is the Game Boy hardware envelope, and m4a's CGB voices use the same
  hardware envelope: a fading envelope becomes a voice with decay = pace and
  sustain 0, a steady one a voice with sustain 15, and the initial volume
  becomes the note velocity. Rising envelopes are approximated (m4a starts
  them from 0, Crystal from the initial volume, and they rise to full).
* Wave channel. Each Crystal wave sample is a programmable wave voice; the
  wave volume code (100%/50%/25%) becomes the velocity.
* Drums. Each drum is a short sequence of noise steps (frames, envelope,
  noise frequency). Every step becomes a noise note at the matching tick,
  with the closest m4a noise key; the last step rings until the next drum,
  as on the Game Boy.
* Vibrato becomes m4a's LFO (MOD/LFOS/LFODL): Crystal's square-wave vibrato of
  +-extent/2 register units becomes a triangle of the same peak, at the same
  rate, after the same delay.
* Loops and calls are expanded by running each channel through a model of
  Crystal's sequencer (one loop counter, one return address, as in Crystal)
  until it reaches a state it has been in before; that point becomes the
  track's GOTO target. Channels that end (sound_ret) end with FINE.

Dropped: stereo panning (Crystal defaults to mono), master volume (every song
uses 7,7), pitch_slide (only in the evolution and healing jingles),
duty_cycle_pattern and pitch_sweep (unused by music).
"""

import json
import math
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SONG_DIR = os.path.join(REPO, "sound", "songs", "gsc")
VOICEGROUP_FILE = os.path.join(REPO, "sound", "voicegroups", "gsc.inc")
VOICE_GROUPS_INC = os.path.join(REPO, "sound", "voice_groups.inc")
SONG_TABLE = os.path.join(REPO, "sound", "song_table.inc")
SONGS_H = os.path.join(REPO, "include", "constants", "songs.h")
MAP_JSON = os.path.join(REPO, "tools", "ditto", "crystal_music_map.json")
MARK = "ditto:convert_crystal_music"

PITCHES = {"C_": 1, "C#": 2, "D_": 3, "D#": 4, "E_": 5, "F_": 6, "F#": 7,
           "G_": 8, "G#": 9, "A_": 10, "A#": 11, "B_": 12}
# Crystal FrequencyTable (audio/notes.asm), entries 1..24, as signed values.
FREQ_TABLE = [0, 0xf82c, 0xf89d, 0xf907, 0xf96b, 0xf9ca, 0xfa23, 0xfa77, 0xfac7,
              0xfb12, 0xfb58, 0xfb9b, 0xfbda, 0xfc16, 0xfc4e, 0xfc83, 0xfcb5,
              0xfce5, 0xfd11, 0xfd3b, 0xfd63, 0xfd89, 0xfdac, 0xfdcd, 0xfded]
# m4a gNoiseTable (src/m4a_tables.c): NR43 value for keys 21..80.
NOISE_TABLE = [0xD7, 0xD6, 0xD5, 0xD4, 0xC7, 0xC6, 0xC5, 0xC4, 0xB7, 0xB6, 0xB5, 0xB4,
               0xA7, 0xA6, 0xA5, 0xA4, 0x97, 0x96, 0x95, 0x94, 0x87, 0x86, 0x85, 0x84,
               0x77, 0x76, 0x75, 0x74, 0x67, 0x66, 0x65, 0x64, 0x57, 0x56, 0x55, 0x54,
               0x47, 0x46, 0x45, 0x44, 0x37, 0x36, 0x35, 0x34, 0x27, 0x26, 0x25, 0x24,
               0x17, 0x16, 0x15, 0x14, 0x07, 0x06, 0x05, 0x04, 0x03, 0x02, 0x01, 0x00]
# Durations m4a can express in one wait / note command.
LENGTHS = list(range(0, 25)) + [28, 30, 32, 36, 40, 42, 44, 48, 52, 54, 56, 60, 64,
                                66, 68, 72, 76, 78, 80, 84, 88, 90, 92, 96]
MAX_GATE = 96 + 3  # N96 plus the longest gate extension
STEP_LIMIT = 2_000_000


class ConvertError(Exception):
    pass


# --------------------------------------------------------------------------
# Parsing pokecrystal's assembly
# --------------------------------------------------------------------------

def parse_number(tok):
    tok = tok.strip()
    neg = tok.startswith("-")
    if neg:
        tok = tok[1:].strip()
    if tok.startswith("$"):
        v = int(tok[1:], 16)
    elif tok.startswith("%"):
        v = int(tok[1:], 2)
    elif tok in ("TRUE",):
        v = 1
    elif tok in ("FALSE",):
        v = 0
    else:
        v = int(tok)
    return -v if neg else v


class Program:
    """All of a set of asm files as one instruction list with resolved labels."""

    def __init__(self):
        self.code = []      # (macro, [args], scope, file, line)
        self.labels = {}    # full label name -> index

    def add_file(self, path):
        scope = None
        with open(path) as f:
            for lineno, raw in enumerate(f, 1):
                line = raw.split(";")[0].rstrip()
                if not line.strip():
                    continue
                m = re.match(r"^([A-Za-z_][\w]*)(::?)\s*$", line)
                if m:
                    scope = m.group(1)
                    self.labels[scope] = len(self.code)
                    continue
                m = re.match(r"^(\.[\w]+):?\s*$", line)
                if m:
                    self.labels[scope + m.group(1)] = len(self.code)
                    continue
                m = re.match(r"^\s+([a-z_0-9]+)\s*(.*)$", line)
                if not m:
                    raise ConvertError(f"{path}:{lineno}: cannot parse {raw!r}")
                args = [a.strip() for a in m.group(2).split(",")] if m.group(2).strip() else []
                self.code.append((m.group(1), args, scope, path, lineno))
        self.code.append(("end_of_file", [], scope, path, 0))

    def resolve(self, name, scope):
        full = scope + name if name.startswith(".") else name
        if full not in self.labels:
            raise ConvertError(f"unknown label {full}")
        return self.labels[full]


def load_drumkits(path):
    prog = Program()
    prog.add_file(path)
    kits = []
    i = prog.labels["Drumkits"]
    while prog.code[i][0] == "dw":
        kit_label = prog.code[i][1][0]
        j = prog.labels[kit_label]
        drums = []
        while prog.code[j][0] == "dw" and len(drums) < 13:
            drums.append(prog.code[j][1][0])
            j += 1
        kits.append(drums)
        i += 1
    drum_steps = {}
    for kit in kits:
        for label in kit:
            if label in drum_steps:
                continue
            steps = []
            j = prog.labels[label]
            while prog.code[j][0] == "noise_note":
                length, vol, fade, freq = [parse_number(a) for a in prog.code[j][1]]
                frames = (length & 0xF) + 1
                steps.append((frames, vol, fade, freq & 0xFF))
                j += 1
            drum_steps[label] = steps
    return [[drum_steps[label] for label in kit] for kit in kits]


def load_wave_samples(path):
    waves = []
    with open(path) as f:
        for line in f:
            line = line.split(";")[0].strip()
            if line.startswith("dn"):
                nyb = [int(x) for x in line[2:].split(",")]
                if len(nyb) != 32:
                    raise ConvertError("wave sample is not 32 nybbles")
                waves.append(nyb)
    return waves


def load_song_list(crystal):
    consts = []
    with open(os.path.join(crystal, "constants", "music_constants.asm")) as f:
        for line in f:
            m = re.match(r"\s*const (MUSIC_\w+)", line)
            if m:
                consts.append(m.group(1))
            if "NUM_MUSIC_SONGS" in line:
                break
    labels = []
    with open(os.path.join(crystal, "audio", "music_pointers.asm")) as f:
        for line in f:
            m = re.match(r"\s*dba (Music_\w+)", line)
            if m:
                labels.append(m.group(1))
    if len(consts) != len(labels):
        raise ConvertError("music constants and pointers disagree")
    return list(zip(consts, labels))


# --------------------------------------------------------------------------
# Channel simulation
# --------------------------------------------------------------------------

def crystal_period(octave_reg, pitch, transpose):
    """Game Boy period (2048 - frequency register) for a Crystal note."""
    idx = pitch + (transpose & 0xF)
    a = ((transpose >> 4) & 0xF) + octave_reg
    shifts = max(0, 7 - a)
    if idx >= len(FREQ_TABLE):
        idx = len(FREQ_TABLE) - 1
    de = FREQ_TABLE[idx] - 0x10000
    return -(de >> shifts), 36 + 12 * shifts + idx - 1


def semitones(period, delta):
    """Pitch change in semitones when the frequency register rises by delta."""
    if period - delta <= 0:
        return 0.0
    return 12 * math.log2(period / (period - delta))


class Note:
    __slots__ = ("tick", "dur", "key", "vel", "voice", "tune", "mod", "lfos", "lfodl", "cuts")

    def __init__(self, tick, dur, key, vel, voice, tune=0, mod=0, lfos=0, lfodl=0):
        self.tick, self.dur, self.key, self.vel, self.voice = tick, dur, key, vel, voice
        self.tune, self.mod, self.lfos, self.lfodl = tune, mod, lfos, lfodl


def velocity_for(goal):
    """Smallest-safe note velocity giving m4a CGB envelope goal `goal` at VOL 127."""
    goal = max(0, min(15, goal))
    candidates = [v for v in range(128)
                  if ((v * 128 * 127 >> 14) + (v * 127 * 126 >> 14)) // 16 == goal]
    return candidates[len(candidates) // 2]


def env_shape(fade):
    """Crystal envelope low nybble (signed fade) -> ('dec'|'const'|'inc', pace)."""
    if fade < 0 or fade & 8:
        pace = (-fade if fade < 0 else fade) & 7
        return ("inc", pace) if pace else ("const", 0)
    return ("dec", fade) if fade else ("const", 0)


class Channel:
    def __init__(self, prog, start, chan, song_tempo):
        self.prog, self.pc, self.chan = prog, start, chan
        self.sub = False
        self.ret = None
        self.looping = False
        self.loop_count = 0
        self.octave = 4          # stored as 8 - octave, like Crystal
        self.speed = 1
        self.env = (0, 0)        # (volume, signed fade) or wave (volume, sample)
        self.duty = 0
        self.transpose = 0
        self.vibrato = (0, 0, 0)  # delay, extent, rate
        self.pitch_offset = 0
        self.kit = 0
        self.noise = chan == 4
        self.tempo = song_tempo
        self.tick = 0
        self.events = []         # ("note", Note) / ("tempo", tick, value) / ("hit", tick, kit, drum)
        self.loop_event = None
        self.loop_tick = None
        self.end_tick = None

    def state(self):
        return (self.pc, self.sub, self.ret, self.looping, self.loop_count, self.octave,
                self.speed, self.env, self.duty, self.transpose, self.vibrato,
                self.pitch_offset, self.kit, self.noise, self.tempo)

    def run(self, targets):
        seen = {}
        steps = 0
        code = self.prog.code
        while True:
            steps += 1
            if steps > STEP_LIMIT:
                raise ConvertError("channel never repeats")
            if self.pc in targets:
                key = self.state()
                if key in seen:
                    self.loop_event, self.loop_tick = seen[key]
                    self.end_tick = self.tick
                    return
                seen[key] = (len(self.events), self.tick)
            macro, args, scope, path, line = code[self.pc]
            self.pc += 1
            where = f"{os.path.basename(path)}:{line}"
            try:
                if self.step(macro, args, scope):
                    self.end_tick = self.tick
                    return
            except (ValueError, IndexError) as e:
                raise ConvertError(f"{where}: {macro} {args}: {e}")

    def step(self, macro, args, scope):
        """Execute one instruction. Returns True when the channel ends."""
        num = [parse_number(a) for a in args] if macro not in (
            "note", "sound_call", "sound_loop", "sound_jump", "pitch_slide") else None
        if macro == "note":
            self.play(PITCHES[args[0]], parse_number(args[1]))
        elif macro == "drum_note":
            self.play(num[0], num[1])
        elif macro == "rest":
            self.play(0, num[0])
        elif macro == "octave":
            self.octave = (8 - num[0]) & 7
        elif macro in ("note_type", "drum_speed"):
            self.speed = num[0]
            if len(num) >= 3 and self.chan != 4:
                self.env = (num[1], num[2])
        elif macro == "volume_envelope":
            self.env = (num[0], num[1])
        elif macro == "duty_cycle":
            self.duty = num[0] & 3
        elif macro == "transpose":
            self.transpose = ((num[0] & 0xF) << 4) | (num[1] & 0xF)
        elif macro == "tempo":
            self.tempo = num[0]
            self.events.append(("tempo", self.tick, num[0]))
        elif macro == "vibrato":
            if len(num) == 3:
                self.vibrato = (num[0], num[1], num[2])
            else:
                self.vibrato = (num[0], num[1] >> 4, num[1] & 0xF)
        elif macro == "pitch_offset":
            self.pitch_offset = num[0]
        elif macro == "toggle_noise":
            if num:
                self.kit = num[0]
        elif macro == "sound_call":
            target = self.prog.resolve(args[0], scope)
            self.ret = self.pc
            self.sub = True
            self.pc = target
        elif macro == "sound_ret":
            if not self.sub:
                return True
            self.sub = False
            self.pc = self.ret
        elif macro == "sound_jump":
            self.pc = self.prog.resolve(args[0], scope)
        elif macro == "sound_loop":
            count = parse_number(args[0])
            target = self.prog.resolve(args[1], scope)
            if not self.looping:
                if count == 0:
                    self.pc = target
                    return False
                self.looping = True
                self.loop_count = count - 1
            if self.loop_count == 0:
                self.looping = False
            else:
                self.loop_count -= 1
                self.pc = target
        elif macro == "end_of_file":
            return True
        elif macro in ("volume", "stereo_panning", "force_stereo_panning", "pitch_slide",
                       "duty_cycle_pattern", "pitch_sweep", "channel_count", "channel", "db"):
            pass
        else:
            raise ConvertError(f"unsupported command {macro}")
        return False

    def play(self, pitch, length):
        dur = self.speed * length
        if self.noise:
            if pitch:
                self.events.append(("hit", self.tick, self.kit, pitch, self.tempo))
            self.tick += dur
            return
        if pitch:
            period, key = crystal_period(self.octave, pitch, self.transpose)
            note = self.make_note(dur, period, key)
            if note:
                self.events.append(("note", note))
        self.tick += dur

    def make_note(self, dur, period, key):
        vol, fade = self.env
        if self.chan == 3:
            level = vol & 3
            if level == 0:
                return None
            goal = {1: 15, 2: 8, 3: 4}[level]
            voice = ("wave", min(fade & 0xF, 9))
        else:
            shape = env_shape(fade)
            if shape[0] == "inc":
                goal = 15
            elif vol == 0:
                return None
            else:
                goal = vol
            voice = ("square%d" % self.chan, self.duty, shape)
        tune = 0
        if self.pitch_offset:
            tune = max(-64, min(63, round(64 * semitones(period, self.pitch_offset))))
        delay, extent, rate = self.vibrato
        mod = lfos = lfodl = 0
        if extent:
            mod = min(127, round(16 * semitones(period, extent / 2)))
            if mod:
                lfos = max(1, min(127, round(self.tempo / (2 * (rate + 1)))))
                lfodl = min(255, round(delay * 256 / self.tempo))
        return Note(self.tick, dur, key, velocity_for(goal), voice, tune, mod, lfos, lfodl)


def noise_key(nr43):
    """Closest m4a noise key for a Game Boy NR43 value (ignoring the width bit)."""
    base = nr43 & 0xF7

    def freq(v):
        s, r = v >> 4, v & 7
        return 524288 / (r if r else 0.5) / (2 ** (s + 1))

    if base in NOISE_TABLE:
        return 21 + NOISE_TABLE.index(base)
    target = math.log2(freq(base))
    best = min(range(len(NOISE_TABLE)), key=lambda i: abs(math.log2(freq(NOISE_TABLE[i])) - target))
    return 21 + best


def expand_drums(ch, kits):
    """Turn drum hits into noise notes. Each step of a drum becomes a note; the
    last step rings until the next hit (rests do not silence Crystal's noise)."""
    hits = [e for e in ch.events if e[0] == "hit"]
    loop_hit = None
    if ch.loop_event is not None:
        loop_hit = sum(1 for e in ch.events[:ch.loop_event] if e[0] == "hit")
    body_len = (ch.end_tick - ch.loop_tick) if ch.loop_tick is not None else None
    others = [e for e in ch.events if e[0] != "hit"]
    notes = []
    for n, (_, tick, kit, drum, tempo) in enumerate(hits):
        # where the next hit lands (wrapping into the loop body)
        if n + 1 < len(hits):
            nxt = hits[n + 1][1]
        elif loop_hit is not None and loop_hit < len(hits):
            nxt = hits[loop_hit][1] + body_len
        else:
            nxt = ch.end_tick
        in_body = loop_hit is not None and n >= loop_hit
        boundary = ch.end_tick if (in_body or ch.loop_tick is None) else ch.loop_tick
        steps = kits[kit % len(kits)][drum] if drum < 13 else []
        t = 0.0
        starts = []
        for frames, vol, fade, freq in steps:
            starts.append((round(t), vol, fade, freq))
            t += frames * 256 / tempo
        for k, (off, vol, fade, freq) in enumerate(starts):
            start = tick + off
            if start >= nxt:
                break
            end = tick + starts[k + 1][0] if k + 1 < len(starts) else nxt
            end = min(end, nxt)
            if end - start > MAX_GATE and end > boundary:
                end = max(boundary, start + 1)
            if end <= start:
                continue
            shape = env_shape(fade)
            if shape[0] == "inc":
                goal = 15
            elif vol == 0:
                continue
            else:
                goal = vol
            voice = ("noise", (freq >> 3) & 1, shape)
            notes.append(("note", Note(start, end - start, noise_key(freq), velocity_for(goal), voice)))
    # keep event order: interleave by tick; the loop point stays at the first loop hit
    events = sorted(others + notes, key=lambda e: e[1] if e[0] == "tempo" else e[1].tick)
    if ch.loop_tick is not None:
        ch.loop_event = sum(1 for e in events
                            if (e[1] if e[0] == "tempo" else e[1].tick) < ch.loop_tick)
    ch.events = events


def event_tick(ev):
    return ev[1] if ev[0] == "tempo" else ev[1].tick


def event_sig(ev, shift=0):
    if ev[0] == "tempo":
        return ("tempo", ev[1] - shift, ev[2])
    n = ev[1]
    return ("note", n.tick - shift, n.dur, n.key, n.vel, n.voice, n.tune, n.mod, n.lfos, n.lfodl)


def shrink_loop(ch):
    """Move the loop point back as far as the music allows.

    The sequencer model finds a loop only once the whole channel state repeats,
    which can include registers that no longer matter (an octave that is set
    again before the next note), leaving a copy of the loop in the intro. If the
    end of the intro is the same music as the end of the loop body, the loop can
    start earlier by that much."""
    if ch.loop_event is None:
        return
    period = ch.end_tick - ch.loop_tick
    intro, body = ch.events[:ch.loop_event], ch.events[ch.loop_event:]
    k = 0
    while (k < len(intro) and k < len(body)
           and event_sig(intro[-1 - k]) == event_sig(body[-1 - k], period)):
        k += 1
    while k > 0:
        x = event_tick(intro[-k])
        ok = (k == len(intro) or event_tick(intro[-k - 1]) < x) and \
             (k == len(body) or event_tick(body[-k - 1]) < x + period)
        # a tied note (longer than one note command) must not cross the new end
        ok = ok and all(e[0] != "note" or e[1].dur <= MAX_GATE or e[1].tick + e[1].dur <= x + period
                        for e in body[:len(body) - k])
        if ok:
            break
        k -= 1
    if k == 0:
        return
    x = event_tick(intro[-k])
    ch.events = intro + body[:len(body) - k]
    ch.loop_event = len(intro) - k
    ch.loop_tick = x
    ch.end_tick = x + period


# --------------------------------------------------------------------------
# m4a output
# --------------------------------------------------------------------------

def split_wait(n):
    out = []
    while n > 0:
        w = max(x for x in LENGTHS if x <= n)
        out.append(w)
        n -= w
    return out


def voice_macro(voice, waves_label):
    kind = voice[0]
    if kind == "wave":
        return f"voice_programmable_wave 60, 0, {waves_label}{voice[1]}, 0, 0, 15, 0"
    shape = voice[-1]
    if shape[0] == "dec":
        a, d, s = 0, shape[1], 0
    elif shape[0] == "inc":
        a, d, s = shape[1], 0, 15
    else:
        a, d, s = 0, 0, 15
    if kind == "square1":
        return f"voice_square_1 60, 0, 0, {voice[1]}, {a}, {d}, {s}, 0"
    if kind == "square2":
        return f"voice_square_2 60, 0, {voice[1]}, {a}, {d}, {s}, 0"
    return f"voice_noise 60, 0, {voice[1]}, {a}, {d}, {s}, 0"


def track_lines(sym, num, ch, voices, first_tempo):
    lines = [f"@ Track {num} (Crystal channel {ch.chan})", "", f"{sym}_{num}:",
             f"\t.byte\tKEYSH , {sym}_key+0"]
    lines += ["\t.byte\tVOL , 127", "\t.byte\tPAN , c_v+0", "\t.byte\tMODT , 0"]
    cur = {}
    timeline = []  # (tick, order, kind, payload)
    for idx, ev in enumerate(ch.events):
        if ch.loop_event is not None and idx == ch.loop_event:
            timeline.append((ch.loop_tick, 0, "label", None))
        if ev[0] == "tempo":
            timeline.append((ev[1], 1, "tempo", ev[2]))
        else:
            note = ev[1]
            timeline.append((note.tick, 2, "note", note))
    if ch.loop_event is not None and ch.loop_event >= len(ch.events):
        timeline.append((ch.loop_tick, 0, "label", None))
    timeline.sort(key=lambda t: (t[0], t[1]))
    # TIE notes need an EOT event
    extra = []
    for tick, order, kind, payload in timeline:
        if kind == "note" and payload.dur > MAX_GATE:
            extra.append((tick + payload.dur, -1, "eot", payload))
    timeline = sorted(timeline + extra, key=lambda t: (t[0], t[1]))
    now = 0

    def wait_until(t):
        nonlocal now
        for w in split_wait(t - now):
            lines.append(f"\t.byte\tW{w:02d}")
        now = t

    for tick, order, kind, payload in timeline:
        wait_until(tick)
        if kind == "label":
            lines.append(f"{sym}_{num}_LOOP:")
            cur = {}
        elif kind == "tempo":
            lines.append(f"\t.byte\tTEMPO , {m4a_tempo(payload)}")
        elif kind == "eot":
            lines.append(f"\t.byte\tEOT , {payload.key}")
        else:
            n = payload
            v = voices.index(n.voice)
            for name, val, text in (("voice", v, f"VOICE , {v}"),
                                    ("tune", n.tune, f"TUNE , c_v{n.tune:+d}"),
                                    ("lfos", n.lfos, f"LFOS , {n.lfos}"),
                                    ("lfodl", n.lfodl, f"LFODL , {n.lfodl}"),
                                    ("mod", n.mod, f"MOD , {n.mod}")):
                if name in ("lfos", "lfodl") and not n.mod:
                    continue
                if cur.get(name) != val:
                    lines.append(f"\t.byte\t{text}")
                    cur[name] = val
            if n.dur > MAX_GATE:
                lines.append(f"\t.byte\tTIE , {n.key} , v{n.vel:03d}")
            else:
                base = max(x for x in LENGTHS if x <= n.dur)
                gtp = n.dur - base
                lines.append(f"\t.byte\tN{base:02d} , {n.key} , v{n.vel:03d}" + (f" , gtp{gtp}" if gtp else ""))
    wait_until(ch.end_tick)
    if ch.loop_event is not None:
        lines += ["\t.byte\tGOTO", f"\t .word\t{sym}_{num}_LOOP"]
    lines += ["\t.byte\tFINE", ""]
    return lines


def m4a_tempo(crystal_tempo):
    return max(1, min(255, round(19200 / crystal_tempo)))


def convert_song(prog, label, kits):
    code = prog.code
    i = prog.labels[label]
    if code[i][0] != "channel_count":
        raise ConvertError(f"{label}: no channel_count")
    count = parse_number(code[i][1][0])
    chans = []
    for k in range(count):
        macro, args, scope, _, _ = code[i + 1 + k]
        if macro != "channel":
            raise ConvertError(f"{label}: expected channel")
        chans.append((parse_number(args[0]), prog.resolve(args[1], scope)))
    targets = set()
    for macro, args, scope, _, _ in code:
        if macro in ("sound_loop", "sound_jump", "sound_call"):
            targets.add(prog.resolve(args[-1], scope))
    # the song's tempo is set by one channel (normally channel 1) before its first note
    song_tempo = None
    for _, start in chans:
        j = start
        while code[j][0] not in ("note", "rest", "drum_note", "sound_ret", "end_of_file"):
            if code[j][0] == "tempo":
                song_tempo = parse_number(code[j][1][0])
            j += 1
        if song_tempo:
            break
    song_tempo = song_tempo or 256
    channels = []
    for cid, start in sorted(chans):
        ch = Channel(prog, start, cid, song_tempo)
        ch.run(targets)
        if cid == 4:
            expand_drums(ch, kits)
        shrink_loop(ch)
        channels.append(ch)
    return song_tempo, channels


def write_song(sym, voicegroup, song_tempo, channels):
    voices = []
    for ch in channels:
        for ev in ch.events:
            if ev[0] == "note" and ev[1].voice not in voices:
                voices.append(ev[1].voice)
    lines = ["@ Generated by tools/ditto/convert_crystal_music.py from pokecrystal. Do not edit.", "",
             "\t.include \"MPlayDef.s\"", "",
             f"\t.equ\t{sym}_grp, voicegroup_{voicegroup}",
             f"\t.equ\t{sym}_pri, 0", f"\t.equ\t{sym}_rev, 0", f"\t.equ\t{sym}_mvl, 127",
             f"\t.equ\t{sym}_key, 0", f"\t.equ\t{sym}_tbs, 1", f"\t.equ\t{sym}_exg, 0",
             f"\t.equ\t{sym}_cmp, 1", "", "\t.section .rodata", f"\t.global\t{sym}", "\t.align\t2", ""]
    for num, ch in enumerate(channels, 1):
        lines += track_lines(sym, num, ch, voices, song_tempo if num == 1 else None)
    lines += ["\t.align\t2", "", f"{sym}:", f"\t.byte\t{len(channels)}\t@ NumTrks",
              "\t.byte\t0\t@ NumBlks", f"\t.byte\t{sym}_pri\t@ Priority",
              f"\t.byte\t{sym}_rev\t@ Reverb.", "", f"\t.word\t{sym}_grp", ""]
    lines += [f"\t.word\t{sym}_{n}" for n in range(1, len(channels) + 1)]
    lines += ["", "\t.end", ""]
    with open(os.path.join(SONG_DIR, sym + ".s"), "w") as f:
        f.write("\n".join(lines))
    return voices


def replace_block(path, begin, end, block, anchor, after=True):
    with open(path) as f:
        text = f.read()
    full = begin + "\n" + block + end + "\n"
    if begin in text:
        text = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n", lambda m: full, text, flags=re.S)
    else:
        pos = text.index(anchor) + (len(anchor) if after else 0)
        text = text[:pos] + full + text[pos:]
    with open(path, "w") as f:
        f.write(text)


def main(argv):
    if len(argv) < 2:
        print(__doc__.split("\n\n")[1])
        return 2
    crystal = argv[1]
    report = "--report" in argv
    prog = Program()
    music_dir = os.path.join(crystal, "audio", "music")
    for name in sorted(os.listdir(music_dir)):
        if name.endswith(".asm"):
            prog.add_file(os.path.join(music_dir, name))
    kits = load_drumkits(os.path.join(crystal, "audio", "drumkits.asm"))
    waves = load_wave_samples(os.path.join(crystal, "audio", "wave_samples.asm"))
    songs = load_song_list(crystal)

    os.makedirs(SONG_DIR, exist_ok=True)
    for old in os.listdir(SONG_DIR):
        if old.endswith(".s"):
            os.remove(os.path.join(SONG_DIR, old))

    mapping = {}
    vg_lines = ["@ Generated by tools/ditto/convert_crystal_music.py from pokecrystal. Do not edit.", "",
                "@ Pokemon Crystal's wave samples (audio/wave_samples.asm)"]
    for n, w in enumerate(waves):
        data = [(w[k] << 4) | w[k + 1] for k in range(0, 32, 2)]
        vg_lines += ["\t.align 2", f"ProgrammableWaveData_GSC_{n}::",
                     "\t.byte " + ", ".join(f"0x{b:02X}" for b in data)]
    vg_lines.append("")
    table_lines, define_lines = [], []
    first_id = None
    with open(SONGS_H) as f:
        text = re.sub(r"// " + MARK + r" begin.*?// " + MARK + r" end\n", "", f.read(), flags=re.S)
    ids = [int(v) for v in re.findall(r"^#define \w+\s+(\d+)\b", text, flags=re.M)]
    first_id = max(ids) + 1
    for const, label in songs:
        if label == "Music_Nothing":
            continue
        name = const[len("MUSIC_"):]
        mus = "MUS_GSC_" + name
        sym = mus.lower()
        vg = "gsc_" + name.lower()
        song_tempo, channels = convert_song(prog, label, kits)
        voices = write_song(sym, vg, song_tempo, channels)
        vg_lines.append(f"voice_group {vg}")
        vg_lines += ["\t" + voice_macro(v, "ProgrammableWaveData_GSC_") for v in voices]
        vg_lines.append("")
        table_lines.append(f"\tsong {sym}, MUSIC_PLAYER_BGM, 0")
        define_lines.append(f"#define {mus:<36}{first_id + len(define_lines)}")
        mapping[const] = mus
        if report:
            parts = []
            for ch in channels:
                notes = sum(1 for e in ch.events if e[0] == "note")
                loop = (ch.end_tick - ch.loop_tick) if ch.loop_tick is not None else None
                parts.append(f"ch{ch.chan}: {notes} notes, intro {ch.loop_tick if loop else ch.end_tick}"
                             + (f", loop {loop}" if loop else ", ends"))
            print(f"{mus}: tempo {song_tempo} -> {m4a_tempo(song_tempo)}, {len(voices)} voices; "
                  + "; ".join(parts))

    # Not a song: Crystal's GetMapMusic plays Rocket Hideout here while Team
    # Rocket holds Mahogany Town and Cherrygrove City afterwards.
    if "MUSIC_CHERRYGROVE_CITY" in mapping:
        mapping["MUSIC_MAHOGANY_MART"] = mapping["MUSIC_CHERRYGROVE_CITY"]

    with open(VOICEGROUP_FILE, "w") as f:
        f.write("\n".join(vg_lines))
    with open(VOICE_GROUPS_INC) as f:
        if '"sound/voicegroups/gsc.inc"' not in f.read():
            with open(VOICE_GROUPS_INC, "a") as g:
                g.write('.include "sound/voicegroups/gsc.inc"\n')
    replace_block(SONG_TABLE, f"\t@ {MARK} begin", f"\t@ {MARK} end",
                  "\n".join(table_lines) + "\n", "\tsong ph_nurse_solo, MUSIC_PLAYER_SE2, 2\n")
    last_ph = "#define PH_NURSE_SOLO"
    with open(SONGS_H) as f:
        h = f.read()
    anchor = h[h.index(last_ph):].split("\n", 1)[0] + "\n"
    replace_block(SONGS_H, f"\n// {MARK} begin: Pokemon Crystal songs", f"// {MARK} end",
                  "\n".join(define_lines) + "\n", anchor)
    with open(MAP_JSON, "w") as f:
        json.dump(mapping, f, indent=2)
        f.write("\n")
    print(f"converted {len(define_lines)} songs (ids {first_id}-{first_id + len(define_lines) - 1})")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except ConvertError as e:
        sys.exit(f"error: {e}")
