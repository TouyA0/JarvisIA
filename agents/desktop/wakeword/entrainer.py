"""Entraînement du détecteur de wake word « Jarvis ».

Trois corrections par rapport à la version précédente :

1. SPLIT AVANT AUGMENTATION. Avant, les 5 variantes d'un même enregistrement se
   retrouvaient réparties entre train et test : le modèle était évalué sur des
   quasi-copies de ce qu'il avait appris, et l'accuracy affichée n'avait aucun
   sens. On sépare maintenant les FICHIERS, puis on n'augmente que le train.

2. DÉCALAGE TEMPOREL. À l'inférence, jarvis.py score une fenêtre glissante :
   le mot peut se trouver n'importe où dans les 1.5 s. À l'entraînement il était
   toujours aligné pareil. On décale donc aléatoirement le signal dans la fenêtre.

3. BRUIT SYNTHÉTIQUE PLAFONNÉ. Le bruit gaussien est trivialement séparable de
   la parole : en faire 66 % des négatifs apprenait au modèle « parole vs
   silence » au lieu de « jarvis vs autre mot ». Il est maintenant plafonné, et
   le script réclame de vrais négatifs parlés s'il n'y en a pas assez.

Le script termine en proposant un seuil de décision fondé sur les scores
réellement obtenus sur le jeu de test — à reporter dans WAKE_WORD_THRESHOLD.
"""

import os
import sys

# La console Windows est en cp1252 : sans ça, le moindre caractère accentué
# ou fléché fait planter le script en fin d'entraînement.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

import numpy as np
import librosa
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.keras import layers, models

SAMPLE_RATE = 16000
DURATION = 1.5
N_SAMPLES = int(SAMPLE_RATE * DURATION)
POSITIFS_DIR = "samples_jarvis"
NEGATIFS_DIR = "samples_negatifs"
MODEL_OUTPUT = "jarvis_wakeword.tflite"

TEST_RATIO = 0.2
MAX_SHIFT = int(0.35 * SAMPLE_RATE)   # ±350 ms de décalage dans la fenêtre
# Le bruit pur ne doit jamais dominer les négatifs, sinon la tâche devient triviale
# (le modèle apprendrait « parole vs silence » au lieu de « jarvis vs autre mot »).
MAX_SYNTHETIC_NOISE_RATIO = 0.35
RNG = np.random.default_rng(42)


TARGET_RMS = 0.05

def normalize_audio(audio):
    """Ramène le signal à un niveau de référence — DOIT rester identique à jarvis.py.

    Les MFCC dépendent de l'amplitude. Les échantillons enregistrés ici sont à
    RMS ~0.002 alors que jarvis.py ne score que de l'audio au-dessus de son
    seuil de silence : sans normalisation, le modèle est interrogé à
    l'inférence sur une plage de volume qu'il n'a jamais vue à l'entraînement.
    Normaliser des deux côtés rend la détection invariante au volume.
    """
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms < 1e-7:
        return audio
    return (audio * (TARGET_RMS / rms)).astype(np.float32)


def extract_features(audio):
    if len(audio) < N_SAMPLES:
        audio = np.pad(audio, (0, N_SAMPLES - len(audio)))
    else:
        audio = audio[:N_SAMPLES]
    audio = normalize_audio(audio.astype(np.float32))
    mfcc = librosa.feature.mfcc(y=audio, sr=SAMPLE_RATE, n_mfcc=40)
    return mfcc.T  # (47, 40)


def load_wav(filepath):
    audio, _ = librosa.load(filepath, sr=SAMPLE_RATE, duration=DURATION)
    return audio


def time_shift(audio, shift):
    """Décale le signal dans la fenêtre en complétant par du silence.

    Reproduit la condition d'inférence : la fenêtre glissante ne garantit
    aucun alignement du mot.
    """
    out = np.zeros(N_SAMPLES, dtype=np.float32)
    src = audio[:N_SAMPLES]
    if shift >= 0:
        end = min(N_SAMPLES, shift + len(src))
        out[shift:end] = src[:end - shift]
    else:
        src = src[-shift:]
        out[:len(src)] = src
    return out


def augment(audio):
    """Variantes d'entraînement — à n'appliquer QUE sur le split train."""
    base = audio[:N_SAMPLES]
    if len(base) < N_SAMPLES:
        base = np.pad(base, (0, N_SAMPLES - len(base)))

    versions = [base]
    versions.append(base + RNG.standard_normal(N_SAMPLES).astype(np.float32) * 0.005)
    versions.append(base + RNG.standard_normal(N_SAMPLES).astype(np.float32) * 0.015)
    versions.append(base * RNG.uniform(0.5, 0.9))    # parole plus lointaine / plus basse
    for _ in range(3):                                # décalages temporels
        versions.append(time_shift(base, int(RNG.integers(-MAX_SHIFT, MAX_SHIFT))))
    for n_steps in (-1, 1):
        try:
            versions.append(librosa.effects.pitch_shift(base, sr=SAMPLE_RATE, n_steps=n_steps))
        except Exception:
            pass
    return versions


def list_wavs(directory):
    if not os.path.isdir(directory):
        return []
    return [os.path.join(directory, f) for f in sorted(os.listdir(directory))
            if f.lower().endswith(".wav")]


# ── 1. Split au niveau des FICHIERS (aucune fuite possible) ───────────────────
pos_files = list_wavs(POSITIFS_DIR)
neg_files = list_wavs(NEGATIFS_DIR)

if not pos_files:
    raise SystemExit(f"Aucun échantillon dans {POSITIFS_DIR}/ — lance d'abord enregistrer.py")

print(f"Fichiers : {len(pos_files)} positifs, {len(neg_files)} négatifs réels")
if len(neg_files) < len(pos_files):
    print(f"  ATTENTION : seulement {len(neg_files)} négatifs parlés pour {len(pos_files)} positifs.")
    print("  Le modèle apprendra surtout « parole vs silence » plutôt que « jarvis vs autre mot ».")
    print("  Enregistre des négatifs qui soient de la VRAIE PAROLE : mots proches")
    print("  (« service », « avis », « Java », « ravi »), et tes conversations courantes.")

pos_train_f, pos_test_f = train_test_split(pos_files, test_size=TEST_RATIO, random_state=42)
if neg_files:
    neg_train_f, neg_test_f = train_test_split(neg_files, test_size=TEST_RATIO, random_state=42)
else:
    neg_train_f, neg_test_f = [], []

print(f"Split fichiers → train : {len(pos_train_f)}+/{len(neg_train_f)}-"
      f"  test : {len(pos_test_f)}+/{len(neg_test_f)}-")


# ── 2. Train : augmenté. Test : brut (conditions réelles) ─────────────────────
def build(files, augmented):
    feats = []
    for path in files:
        audio = load_wav(path)
        for version in (augment(audio) if augmented else [audio]):
            f = extract_features(version)
            if f.shape == (47, 40):
                feats.append(f)
    return feats

print("\nExtraction des features...")
pos_train = build(pos_train_f, augmented=True)
neg_train = build(neg_train_f, augmented=True)
pos_test = build(pos_test_f, augmented=False)
neg_test = build(neg_test_f, augmented=False)

def synthetic_negative():
    """Non-parole variée SPECTRALEMENT.

    Comme extract_features normalise le niveau, faire varier le volume
    n'apprend rien au modèle : seule la forme du spectre compte. On couvre donc
    bruit blanc/rose/brun, tonalités pures et ronflement secteur — les sources
    de faux positifs réelles une fois le silence amplifié par la normalisation.
    """
    kind = RNG.integers(0, 5)
    t = np.arange(N_SAMPLES) / SAMPLE_RATE
    if kind == 0:                                    # blanc
        sig = RNG.standard_normal(N_SAMPLES)
    elif kind in (1, 2):                             # rose / brun (spectre en 1/f)
        white = RNG.standard_normal(N_SAMPLES)
        spec = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(N_SAMPLES, 1 / SAMPLE_RATE)
        freqs[0] = 1.0
        spec /= freqs ** (0.5 if kind == 1 else 1.0)
        sig = np.fft.irfft(spec, n=N_SAMPLES)
    elif kind == 3:                                  # tonalité pure + harmonique
        f0 = RNG.uniform(50, 900)
        sig = np.sin(2 * np.pi * f0 * t) + 0.3 * np.sin(2 * np.pi * 2 * f0 * t)
    else:                                            # ronflement secteur 50 Hz
        sig = np.sin(2 * np.pi * 50 * t) + 0.4 * np.sin(2 * np.pi * 150 * t)
        sig += RNG.standard_normal(N_SAMPLES) * 0.1
    return sig.astype(np.float32)


max_noise = int(len(neg_train) * MAX_SYNTHETIC_NOISE_RATIO / (1 - MAX_SYNTHETIC_NOISE_RATIO)) \
    if neg_train else len(pos_train) // 3
n_noise = min(max_noise, max(0, len(pos_train) - len(neg_train)))
for _ in range(n_noise):
    f = extract_features(synthetic_negative())
    if f.shape == (47, 40):
        neg_train.append(f)

print(f"  train : {len(pos_train)} positifs / {len(neg_train)} négatifs "
      f"(dont {n_noise} bruit synthétique)")
print(f"  test  : {len(pos_test)} positifs / {len(neg_test)} négatifs (non augmentés)")

if not neg_test:
    print("  ATTENTION : aucun négatif en test — la précision mesurée sera optimiste.")

X_train = np.array(pos_train + neg_train)
y_train = np.array([1] * len(pos_train) + [0] * len(neg_train))
X_test = np.array(pos_test + neg_test)
y_test = np.array([1] * len(pos_test) + [0] * len(neg_test))


# ── 3. Modèle ─────────────────────────────────────────────────────────────────
print("\nConstruction du modèle...")
model = models.Sequential([
    layers.Input(shape=(47, 40)),
    layers.Conv1D(64, 3, activation='relu', padding='same'),
    layers.BatchNormalization(),
    layers.MaxPooling1D(2),
    layers.Conv1D(128, 3, activation='relu', padding='same'),
    layers.BatchNormalization(),
    layers.MaxPooling1D(2),
    layers.Conv1D(64, 3, activation='relu', padding='same'),
    layers.GlobalAveragePooling1D(),
    layers.Dense(64, activation='relu'),
    layers.Dropout(0.4),
    layers.Dense(1, activation='sigmoid')
])
model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
model.summary()

print("\nEntraînement...")
model.fit(
    X_train, y_train,
    epochs=60,
    batch_size=16,
    validation_data=(X_test, y_test),
    callbacks=[
        tf.keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True,
                                         monitor="val_loss"),
        tf.keras.callbacks.ReduceLROnPlateau(patience=4, factor=0.5),
    ],
    verbose=1
)


# ── 4. Évaluation honnête + choix du seuil ────────────────────────────────────
scores = model.predict(X_test, verbose=0).ravel()
pos_scores = scores[y_test == 1]
neg_scores = scores[y_test == 0]

print("\n" + "=" * 58)
print("ÉVALUATION (test non augmenté — aucune fuite depuis le train)")
print("=" * 58)
print(f"  Positifs : score médian {np.median(pos_scores):.3f} "
      f"[min {pos_scores.min():.3f} / max {pos_scores.max():.3f}]")
if len(neg_scores):
    print(f"  Négatifs : score médian {np.median(neg_scores):.3f} "
          f"[min {neg_scores.min():.3f} / max {neg_scores.max():.3f}]")

best = None
print(f"\n  {'seuil':>6} {'rappel':>8} {'précision':>10} {'faux pos.':>10}")
for thr in (0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.96, 0.98):
    tp = int((pos_scores >= thr).sum())
    fp = int((neg_scores >= thr).sum()) if len(neg_scores) else 0
    recall = tp / max(1, len(pos_scores))
    precision = tp / max(1, tp + fp)
    print(f"  {thr:>6.2f} {recall:>8.1%} {precision:>10.1%} {fp:>10}")
    # Un faux positif est bien plus coûteux qu'un raté : on exige la précision
    # maximale, puis le meilleur rappel à précision égale.
    if best is None or (precision, recall) > best[1]:
        best = (thr, (precision, recall))

print("=" * 58)
if best:
    thr, (precision, recall) = best
    print(f"Seuil suggéré : WAKE_WORD_THRESHOLD = {thr:.2f}"
          f"  (rappel {recall:.0%}, précision {precision:.0%})")
    print("  → à reporter dans jarvis.py")
if len(pos_scores) and np.median(pos_scores) < 0.9:
    print("Le modèle est peu confiant sur les positifs : enregistre plus de samples.")
if len(neg_scores) and neg_scores.max() > 0.5:
    print("Des négatifs parlés scorent haut : ajoute des négatifs phonétiquement proches.")

# ── 5. Export TFLite ──────────────────────────────────────────────────────────
print("\nConversion en TFLite...")
converter = tf.lite.TFLiteConverter.from_keras_model(model)
with open(MODEL_OUTPUT, 'wb') as f:
    f.write(converter.convert())
print(f"Modèle sauvegardé : {MODEL_OUTPUT}")
print("Lance jarvis.py pour tester.")
