import sounddevice as sd
import numpy as np
import wave
import os
import time

SAMPLE_RATE = 16000
DURATION = 1.5
OUTPUT_DIR = "samples_jarvis"

os.makedirs(OUTPUT_DIR, exist_ok=True)

print("=== Enregistrement des samples 'Jarvis' ===")
print("Tu vas dire 'Jarvis' 80 fois.")
print("Varie : ton normal, ton plus fort, plus doucement, plus vite, plus lentement.")
print("Appuie sur Entrée avant chaque enregistrement.\n")

for i in range(1, 81):
    input(f"Sample {i}/80 — Appuie sur Entrée puis dis 'Jarvis'")
    print("Enregistrement...")
    audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
    sd.wait()
    
    filepath = os.path.join(OUTPUT_DIR, f"jarvis_{i:02d}.wav")
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    
    print(f"✓ Sauvegardé\n")

print("=== Enregistrement terminé ! ===")
print(f"80 samples sauvegardés dans le dossier '{OUTPUT_DIR}'")