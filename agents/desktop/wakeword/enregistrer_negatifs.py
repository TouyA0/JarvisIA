import sounddevice as sd
import numpy as np
import wave
import os

SAMPLE_RATE = 16000
DURATION = 1.5
OUTPUT_DIR = "samples_negatifs"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# 50 phrases à dire — variées pour que le modèle apprenne à ignorer tout sauf "Jarvis"
PHRASES = [
    # Mots du quotidien courts
    "bonjour", "merci", "d'accord", "ouais", "non",
    "super", "parfait", "okay", "stop", "attends",
    # Commandes que tu dirais près du PC
    "lance ça", "ouvre Chrome", "ferme la fenêtre", "monte le son", "baisse le son",
    "prends un screenshot", "cherche sur Google", "ouvre Spotify", "mets en pause", "reprends",
    # Phrases normales de conversation
    "c'est quoi ça", "montre moi", "comment ça marche", "t'es sûr", "bonne idée",
    "qu'est ce que tu fais", "dis moi", "explique moi", "c'est bon", "pas maintenant",
    # Mots qui sonnent vaguement proche de Jarvis (les plus importants)
    "Harvey", "Paris", "Davis", "Larry", "Marcus",
    "service", "surface", "partir", "harbor", "target",
    # Phrases avec des syllabes similaires
    "par ici", "tu vois", "c'est parti", "vas y", "marche",
    # Bruits de voix naturels
    "hm ouais", "ah voilà", "ah oui c'est ça", "euh attends", "ok ok",
    # Nombres et lettres
    "un deux trois", "quatre cinq six", "A B C", "zéro un", "dix vingt trente",
]

print("=== Enregistrement des samples NÉGATIFS ===")
print("Ces samples apprennent à Jarvis à ignorer tout ce qui n'est pas 'Jarvis'.")
print("Dis chaque phrase naturellement, à voix normale.\n")

for i, phrase in enumerate(PHRASES, 1):
    input(f"Sample {i}/50 — Appuie sur Entrée puis dis : '{phrase}'")
    print("Enregistrement...")
    audio = sd.rec(int(DURATION * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
    sd.wait()

    filepath = os.path.join(OUTPUT_DIR, f"negatif_{i:02d}.wav")
    with wave.open(filepath, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())

    print(f"✓ Sauvegardé\n")

print("=== Enregistrement terminé ! ===")
print(f"50 samples négatifs sauvegardés dans '{OUTPUT_DIR}'")
print("Lance maintenant entrainer.py")
