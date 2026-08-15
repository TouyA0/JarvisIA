import { useCallback, useRef } from "react";
import {
  scoreWindow, preloadModel, WINDOW_SAMPLES, THRESHOLD,
  CONSECUTIVE_HITS, COOLDOWN_SECONDS,
} from "./wakeWordDetector.js";
import { encodeWav } from "./encodeWav.js";

const STEP_CHUNKS = 4; // score toutes les 4 x 512 échantillons (~128ms), comme agents/desktop/audio/wakeword.py
const CHUNK_SAMPLES = 512;
const SAMPLE_RATE = 16000;
const CHUNK_MS = (CHUNK_SAMPLES / SAMPLE_RATE) * 1000; // 32ms

// Sur PC, une seconde vérification (Silero VAD, un vrai modèle de
// détection de parole) confirme qu'il y a réellement de la voix avant de
// déclencher — voir agents/desktop/audio/wakeword.py::listen(). Sans elle
// ici, le modèle wake word seul se déclenche parfois sur un bruit bref
// (clic de clavier, etc.), trouvé en usage réel. Pas de Silero dans le
// navigateur (autre modèle à porter, hors scope) : à défaut, on exige
// qu'un son fort dure un minimum de temps d'affilée dans la fenêtre —
// un clic est une impulsion de quelques ms, un mot parlé dure des
// centaines de ms. Filtre plus grossier qu'un vrai VAD, mais suffisant
// pour ce cas précis.
//
// Le seuil DOIT rester un niveau micro réaliste, pas un niveau de
// synthèse vocale : un vrai enregistrement de "Jarvis" mesure ~0.0027 de
// RMS brut (avant la normalisation que fait le modèle en interne) contre
// 0.0012 pour le bruit de fond (WAKE_WORD_MIN_RMS, agents/desktop/config.py)
// — largement en dessous de ce à quoi peut sonner une voix de synthèse
// Piper (bien plus forte). Testé avec `web/dist/test_jarvis_01.wav`
// (échantillon d'entraînement réel) après le premier réglage à 0.01 qui
// ratait la détection — corrigé.
export const SPEECH_RMS_THRESHOLD = 0.0018;
const MIN_SUSTAINED_MS = 200; // durée continue minimale pour valider une détection
const CHUNK_HISTORY_LEN = Math.ceil(24000 / CHUNK_SAMPLES) + 2; // ~ la fenêtre de scoring (1.5s) + marge

// Capture de commande après détection — même logique que
// agents/desktop/audio/stt.py::transcribe() (VAD au lieu d'une durée
// fixe) : attend le début de la parole, capture jusqu'au silence.
// Pas de Silero ici (modèle à part, hors scope) — le seuil RMS partagé
// ci-dessus (SPEECH_RMS_THRESHOLD) suffit pour distinguer parole/silence.
const SILENCE_END_CHUNKS = 12; // ~380ms de silence pour clore la commande
const MAX_WAIT_FOR_SPEECH_CHUNKS = 90; // ~2.9s sans parole → on abandonne
const MAX_CAPTURE_CHUNKS = 280; // ~9s de commande max (garde-fou)
const PRE_BUFFER_CHUNKS = 3; // ~100ms conservés avant le déclenchement, pour ne pas couper le tout début

/**
 * Boucle de détection locale, en continu, tant que le stream tourne —
 * même modèle et mêmes seuils que le PC (voir wakeWordDetector.js).
 * Rien n'est envoyé au réseau ici : uniquement du calcul dans le
 * navigateur, sur l'audio brut du micro.
 */
export function useWakeWordDetector({ onDetected }) {
  const onDetectedRef = useRef(onDetected);
  onDetectedRef.current = onDetected;

  const audioCtxRef = useRef(null);
  const workletNodeRef = useRef(null);
  const sourceRef = useRef(null);
  const ringBufferRef = useRef(new Float32Array(WINDOW_SAMPLES));
  const ringFilledRef = useRef(0);
  const chunkCounterRef = useRef(0);
  const consecutiveHitsRef = useRef(0);
  const lastTriggerRef = useRef(0);
  const scoringRef = useRef(false); // évite d'empiler des inférences si l'une traîne
  const pausedRef = useRef(false);
  const onScoreRef = useRef(null); // callback debug UI (score courant)

  const captureRef = useRef(null); // état de la capture de commande en cours (non null = mode capture)
  const loudHistoryRef = useRef([]); // booléens "chunk fort ou non", les CHUNK_HISTORY_LEN derniers

  const rmsOf = (chunk) => {
    let sum = 0;
    for (let i = 0; i < chunk.length; i++) sum += chunk[i] * chunk[i];
    return Math.sqrt(sum / chunk.length);
  };

  const longestLoudRunMs = () => {
    let best = 0, current = 0;
    for (const loud of loudHistoryRef.current) {
      current = loud ? current + 1 : 0;
      if (current > best) best = current;
    }
    return best * CHUNK_MS;
  };

  const scoreChunk = useCallback(async (chunk) => {
    loudHistoryRef.current.push(rmsOf(chunk) >= SPEECH_RMS_THRESHOLD);
    if (loudHistoryRef.current.length > CHUNK_HISTORY_LEN) loudHistoryRef.current.shift();

    const buf = ringBufferRef.current;
    buf.copyWithin(0, chunk.length);
    buf.set(chunk, buf.length - chunk.length);
    ringFilledRef.current = Math.min(WINDOW_SAMPLES, ringFilledRef.current + chunk.length);

    chunkCounterRef.current += 1;
    if (ringFilledRef.current < WINDOW_SAMPLES) return;
    if (chunkCounterRef.current < STEP_CHUNKS) return;
    chunkCounterRef.current = 0;
    if (pausedRef.current || scoringRef.current) return;

    scoringRef.current = true;
    try {
      const { score, rms } = await scoreWindow(buf);
      onScoreRef.current?.(score, rms);

      if (score >= THRESHOLD) {
        consecutiveHitsRef.current += 1;
      } else {
        consecutiveHitsRef.current = 0;
      }

      const now = performance.now() / 1000;
      if (
        consecutiveHitsRef.current >= CONSECUTIVE_HITS &&
        now - lastTriggerRef.current > COOLDOWN_SECONDS
      ) {
        if (longestLoudRunMs() >= MIN_SUSTAINED_MS) {
          lastTriggerRef.current = now;
          consecutiveHitsRef.current = 0;
          onDetectedRef.current?.(score);
        } else {
          // le modèle est confiant mais le son est trop bref pour être de la
          // parole (clic, choc...) — probable faux positif, on ignore sans
          // repartir de zéro sur le cooldown (pas une vraie détection)
          consecutiveHitsRef.current = 0;
        }
      }
    } finally {
      scoringRef.current = false;
    }
  }, []);

  const captureChunk = useCallback((chunk) => {
    const cap = captureRef.current;
    if (!cap) return;
    const rms = rmsOf(chunk);
    cap.elapsedChunks += 1;

    if (!cap.speechStarted) {
      cap.preBuffer.push(chunk);
      if (cap.preBuffer.length > PRE_BUFFER_CHUNKS) cap.preBuffer.shift();
      if (rms >= SPEECH_RMS_THRESHOLD) {
        cap.speechStarted = true;
        cap.frames.push(...cap.preBuffer);
        cap.preBuffer = [];
      } else if (cap.elapsedChunks >= MAX_WAIT_FOR_SPEECH_CHUNKS) {
        cap.resolve(null); // rien dit après le mot d'éveil
        captureRef.current = null;
      }
      return;
    }

    cap.frames.push(chunk);
    if (rms < SPEECH_RMS_THRESHOLD) {
      cap.silentChunks += 1;
    } else {
      cap.silentChunks = 0;
    }

    const totalCaptured = cap.frames.length;
    if (cap.silentChunks >= SILENCE_END_CHUNKS || totalCaptured >= MAX_CAPTURE_CHUNKS) {
      const total = new Float32Array(totalCaptured * CHUNK_SAMPLES);
      cap.frames.forEach((f, i) => total.set(f, i * CHUNK_SAMPLES));
      cap.resolve(encodeWav(total, SAMPLE_RATE));
      captureRef.current = null;
    }
  }, []);

  // Après la capture d'une commande, on reste explicitement en pause
  // (pausedRef=true) jusqu'à ce que resume() soit appelé — PAS dès que la
  // capture se termine. Bug réel trouvé en usage : si le scoring
  // repartait automatiquement à la fin de la capture, il y avait une
  // fenêtre de plusieurs centaines de ms (le temps de transcrire, avant
  // que useVoice.js n'appelle pause()) où le détecteur rescorait avec
  // encore l'écho de la commande dans sa fenêtre glissante, et se
  // redéclenchait tout seul juste après une vraie détection.
  const pushChunk = useCallback((chunk) => {
    if (captureRef.current) {
      captureChunk(chunk);
    } else if (!pausedRef.current) {
      scoreChunk(chunk);
    }
  }, [captureChunk, scoreChunk]);

  /** À appeler juste après une détection : capture la commande qui suit
   * (attend le début de la parole, s'arrête au silence) et retourne un
   * Blob WAV, ou null si rien n'a été dit. Met le détecteur en pause à la
   * fin — il faut appeler resume() explicitement une fois tout le tour
   * terminé (réponse comprise), pas juste après la capture. */
  const captureCommand = useCallback(() => {
    return new Promise((resolve) => {
      captureRef.current = {
        speechStarted: false, elapsedChunks: 0, silentChunks: 0,
        preBuffer: [], frames: [],
        resolve: (result) => {
          captureRef.current = null;
          pausedRef.current = true;
          resolve(result);
        },
      };
    });
  }, []);

  const start = useCallback(async (stream, { onScore } = {}) => {
    onScoreRef.current = onScore || null;
    ringBufferRef.current.fill(0);
    ringFilledRef.current = 0;
    chunkCounterRef.current = 0;
    consecutiveHitsRef.current = 0;
    loudHistoryRef.current = [];
    pausedRef.current = false;
    preloadModel();

    // sampleRate: 16000 — best effort ; les navigateurs qui l'ignorent
    // rééchantillonnent en interne, ce qui reste correct (juste un peu
    // plus de calcul), voir docs/ROADMAP_MULTIDEVICE.md Phase 9.
    const audioCtx = new AudioContext({ sampleRate: 16000 });
    await audioCtx.audioWorklet.addModule("/wakeword-worklet.js");

    const source = audioCtx.createMediaStreamSource(stream);
    const worklet = new AudioWorkletNode(audioCtx, "wakeword-capture");
    worklet.port.onmessage = (e) => pushChunk(e.data);
    source.connect(worklet);
    // pas de connect(audioCtx.destination) : on ne veut pas jouer le micro en sortie

    audioCtxRef.current = audioCtx;
    workletNodeRef.current = worklet;
    sourceRef.current = source;
  }, [pushChunk]);

  const stop = useCallback(() => {
    workletNodeRef.current?.port.close();
    sourceRef.current?.disconnect();
    workletNodeRef.current?.disconnect();
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    workletNodeRef.current = null;
    sourceRef.current = null;
    captureRef.current = null;
  }, []);

  const pause = useCallback(() => { pausedRef.current = true; }, []);
  const resume = useCallback(() => {
    // Vide la fenêtre glissante et l'historique : sans ça, l'audio d'avant
    // la pause (la fin du mot d'éveil, voire la commande elle-même) reste
    // dedans et se fait rescorer dès la reprise — trouvé en usage réel,
    // ça redéclenchait juste après une détection légitime.
    ringBufferRef.current.fill(0);
    ringFilledRef.current = 0;
    chunkCounterRef.current = 0;
    consecutiveHitsRef.current = 0;
    loudHistoryRef.current = [];
    pausedRef.current = false;
  }, []);

  return { start, stop, pause, resume, captureCommand };
}
