"""Build the short keyboard sprite from unicaegames' CC0 soundpack ZIP."""
import hashlib
import io
import json
from pathlib import Path
import sys
import wave
import zipfile

import numpy as np

archive = Path(sys.argv[1])
output = Path(__file__).resolve().parents[1] / 'src/flycodex/web'
rate = 44100
slot_frames = 4410
press_frames = 3969  # 90 ms, leaving a gap even at the lowest playback rate.
slots = []
records = []
with zipfile.ZipFile(archive) as zipped:
    for index in range(1, 17):
        name = f'Single Keys/keypress-{index:03d}.wav'
        raw = zipped.read(name)
        with wave.open(io.BytesIO(raw)) as source:
            assert source.getframerate() == rate and source.getsampwidth() == 2
            data = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(float) / 32768
            data = data.reshape(-1, source.getnchannels()).mean(axis=1)
        onset = max(0, int(np.flatnonzero(np.abs(data) >= np.max(np.abs(data)) * .12)[0]) - 44)
        press = data[onset:onset + press_frames].copy()
        press -= press.mean()
        press[:44] *= np.linspace(0, 1, 44)
        press[-353:] *= np.linspace(1, 0, 353)
        gain = min(.055 / np.sqrt(np.mean(press ** 2)), .75 / np.max(np.abs(press)))
        press *= gain
        slot = np.zeros(slot_frames)
        slot[:len(press)] = press
        slots.append(slot)
        records.append({'file': name, 'source_sha256': hashlib.sha256(raw).hexdigest(),
                        'onset_frame': onset, 'gain': float(gain), 'slot': index - 1})
with wave.open(str(output / 'keyboard.wav'), 'wb') as wav:
    wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
    wav.writeframes((np.concatenate(slots) * 32767).astype('<i2').tobytes())
manifest = {'author': 'unicaegames', 'license': 'CC0-1.0',
            'source': 'https://opengameart.org/content/keyboard-soundpack-1-typing-and-single-keystrokes',
            'download': 'https://opengameart.org/sites/default/files/unicae_games_keyboard_soundpack_1_0.zip',
            'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
            'sample_rate': rate, 'slot_seconds': .1, 'press_seconds': .09,
            'samples': records, 'output_sha256': hashlib.sha256((output / 'keyboard.wav').read_bytes()).hexdigest()}
(output / 'keyboard-sources.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Built {len(slots)} distinct recorded keypresses; {(output / "keyboard.wav").stat().st_size} bytes')
