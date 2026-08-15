// Détecteur de mot d'éveil « Jarvis » — même modèle que le PC
// (agents/desktop/wakeword/jarvis_wakeword.tflite, converti en ONNX),
// même prétraitement (voir wakeWordFeatures.js). Contrairement à
// l'ancienne approche (transcrire en continu et chercher le mot dans le
// texte), rien ne quitte le navigateur tant que le mot n'est pas
// vraiment détecté — comme sur PC.
import { computeMfccFlat } from "./wakeWordFeatures.js";

export const SAMPLE_RATE = 16000;
export const WINDOW_SECONDS = 1.5;
export const WINDOW_SAMPLES = Math.round(SAMPLE_RATE * WINDOW_SECONDS); // 24000
const TARGET_RMS = 0.05;
export const MIN_RMS = 0.0012;
export const THRESHOLD = 0.9;
export const CONSECUTIVE_HITS = 2;
export const COOLDOWN_SECONDS = 2.0;

let sessionPromise = null;

async function getSession() {
  if (!sessionPromise) {
    sessionPromise = (async () => {
      const ort = await import("onnxruntime-web/wasm");
      ort.env.wasm.wasmPaths = "/ort/";
      ort.env.wasm.numThreads = 1; // évite d'exiger les en-têtes COOP/COEP (SharedArrayBuffer)
      ort.env.wasm.proxy = false;
      return ort.InferenceSession.create("/models/jarvis_wakeword.onnx", {
        executionProviders: ["wasm"],
      });
    })();
  }
  return sessionPromise;
}

/** Précharge le modèle avant la première fenêtre à scorer, pour ne pas
 * payer le coût de chargement pile au moment où on commence à écouter. */
export function preloadModel() {
  getSession().catch(() => {}); // l'erreur réelle remontera au premier score()
}

function rms(audio) {
  let sum = 0;
  for (let i = 0; i < audio.length; i++) sum += audio[i] * audio[i];
  return Math.sqrt(sum / audio.length);
}

function normalize(audio) {
  const r = rms(audio);
  if (r < 1e-7) return audio;
  const scale = TARGET_RMS / r;
  const out = new Float32Array(audio.length);
  for (let i = 0; i < audio.length; i++) out[i] = audio[i] * scale;
  return out;
}

/**
 * Score une fenêtre audio de WINDOW_SAMPLES échantillons (16kHz, mono,
 * float32 dans [-1, 1]). Retourne un score [0, 1] — >= THRESHOLD signifie
 * "Jarvis" probablement prononcé.
 */
export async function scoreWindow(audioWindow) {
  const r = rms(audioWindow);
  if (r < MIN_RMS) return { score: 0, rms: r }; // trop silencieux, pas la peine d'inférer

  const normalized = normalize(audioWindow);
  const { flat, nFrames } = computeMfccFlat(normalized);
  if (nFrames !== 47) return { score: 0, rms: r }; // fenêtre incomplète (démarrage)

  const ort = await import("onnxruntime-web/wasm");
  const session = await getSession();
  const tensor = new ort.Tensor("float32", flat, [1, nFrames, 40]);
  const feeds = { [session.inputNames[0]]: tensor };
  const results = await session.run(feeds);
  const score = results[session.outputNames[0]].data[0];
  return { score, rms: r };
}
