import os
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

def extract_features(audio):
    if len(audio) < N_SAMPLES:
        audio = np.pad(audio, (0, N_SAMPLES - len(audio)))
    else:
        audio = audio[:N_SAMPLES]
    mfcc = librosa.feature.mfcc(y=audio.astype(np.float32), sr=SAMPLE_RATE, n_mfcc=40)
    return mfcc.T  # (47, 40)

def load_wav(filepath):
    audio, _ = librosa.load(filepath, sr=SAMPLE_RATE, duration=DURATION)
    return audio

def augment(audio):
    """Génère 4 versions augmentées d'un audio — multiplie les samples x5 au total"""
    versions = [audio]

    # Bruit de fond léger
    noise = audio + np.random.randn(len(audio)).astype(np.float32) * 0.005
    versions.append(noise)

    # Bruit plus fort
    noise2 = audio + np.random.randn(len(audio)).astype(np.float32) * 0.015
    versions.append(noise2)

    # Légèrement plus rapide (pitch shift +1 demi-ton)
    try:
        shifted_up = librosa.effects.pitch_shift(audio, sr=SAMPLE_RATE, n_steps=1)
        versions.append(shifted_up)
    except:
        versions.append(audio)

    # Légèrement plus lent (pitch shift -1 demi-ton)
    try:
        shifted_down = librosa.effects.pitch_shift(audio, sr=SAMPLE_RATE, n_steps=-1)
        versions.append(shifted_down)
    except:
        versions.append(audio)

    return versions

# --- Chargement positifs ---
print("Chargement des samples positifs (Jarvis)...")
positive_features = []
for filename in sorted(os.listdir(POSITIFS_DIR)):
    if filename.endswith(".wav"):
        audio = load_wav(os.path.join(POSITIFS_DIR, filename))
        for version in augment(audio):
            feat = extract_features(version)
            if feat.shape == (47, 40):
                positive_features.append(feat)

print(f"  {len(positive_features)} samples positifs après augmentation")

# --- Chargement négatifs réels ---
print("Chargement des samples négatifs (vraie parole)...")
negative_features = []
if os.path.exists(NEGATIFS_DIR):
    for filename in sorted(os.listdir(NEGATIFS_DIR)):
        if filename.endswith(".wav"):
            audio = load_wav(os.path.join(NEGATIFS_DIR, filename))
            for version in augment(audio):
                feat = extract_features(version)
                if feat.shape == (47, 40):
                    negative_features.append(feat)
    print(f"  {len(negative_features)} samples négatifs réels après augmentation")
else:
    print("  Dossier samples_negatifs introuvable — uniquement bruit généré")

# Compléter avec du bruit généré pour équilibrer si besoin
n_bruit = max(0, len(positive_features) * 2 - len(negative_features))
print(f"  Génération de {n_bruit} samples de bruit supplémentaires...")
for _ in range(n_bruit):
    noise = np.random.randn(N_SAMPLES).astype(np.float32) * 0.01
    feat = extract_features(noise)
    if feat.shape == (47, 40):
        negative_features.append(feat)

print(f"\nTotal : {len(positive_features)} positifs / {len(negative_features)} négatifs")

# --- Dataset ---
X = np.array(positive_features + negative_features)
y = np.array([1] * len(positive_features) + [0] * len(negative_features))

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.15, random_state=42, stratify=y
)

print(f"Train : {len(X_train)} | Test : {len(X_test)}")

# --- Modèle ---
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

# --- Entraînement ---
print("\nEntraînement...")
callbacks = [
    tf.keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True),
    tf.keras.callbacks.ReduceLROnPlateau(patience=4, factor=0.5)
]
model.fit(
    X_train, y_train,
    epochs=60,
    batch_size=16,
    validation_data=(X_test, y_test),
    callbacks=callbacks,
    verbose=1
)

loss, acc = model.evaluate(X_test, y_test, verbose=0)
print(f"\nPrécision finale sur test : {acc*100:.1f}%")

if acc < 0.85:
    print("Attention : précision faible. Enregistre plus de samples et relance.")

# --- Export TFLite ---
print("\nConversion en TFLite...")
converter = tf.lite.TFLiteConverter.from_keras_model(model)
tflite_model = converter.convert()

with open(MODEL_OUTPUT, 'wb') as f:
    f.write(tflite_model)

print(f"\n✓ Modèle sauvegardé : {MODEL_OUTPUT}")
print(f"  Précision : {acc*100:.1f}%")
print("Lance jarvis.py pour tester !")
