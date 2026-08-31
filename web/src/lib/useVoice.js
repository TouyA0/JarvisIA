import { useCallback, useEffect, useRef, useState } from "react";
import { authFetch } from "./consoleAuth.js";
import { useWakeWordDetector } from "./useWakeWordDetector.js";

/**
 * Écoute vocale : détection locale du mot d'éveil « Jarvis » (même
 * modèle et mêmes seuils que le PC — voir wakeWordDetector.js), aucun
 * audio envoyé au réseau tant qu'il n'est pas vraiment détecté. Une fois
 * détecté, capture la commande qui suit (démarre à la parole, s'arrête
 * au silence — voir useWakeWordDetector.js::captureCommand, même
 * principe que agents/desktop/audio/stt.py côté PC, pas une durée fixe
 * à l'aveugle) et l'envoie à /api/speech/transcribe (Speaches via le
 * brain) pour la transcrire.
 *
 * Remplace l'ancienne approche (transcrire en continu et chercher le mot
 * dans le texte) — abandonnée après un vrai faux-positif en usage réel
 * (« jamais » déclenchait le mot d'éveil). Voir
 * docs/ROADMAP_MULTIDEVICE.md, Phase 9.
 *
 * Pas de fenêtre à durée limitée : comme sur PC, ça écoute tant que
 * c'est armé — plus besoin de compte à rebours puisque rien n'est envoyé
 * au réseau en continu.
 *
 * Pas de barge-in : `pause()` (interne) coupe la détection pendant la
 * capture d'une commande ou pendant que Jarvis parle, pour ne pas
 * s'entendre lui-même et se redéclencher en boucle.
 */
export function useVoice({ onCommand }) {
  const [armed, setArmed] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | listening | listening_command | transcribing | speaking
  const [error, setError] = useState(null);
  const [lastTranscript, setLastTranscript] = useState("");
  const [wakeWordHeard, setWakeWordHeard] = useState(false);
  const [lastScore, setLastScore] = useState(0);

  const onCommandRef = useRef(onCommand);
  onCommandRef.current = onCommand;

  const mediaStreamRef = useRef(null);
  const armedRef = useRef(false);
  const pausedRef = useRef(false); // pause externe (Jarvis parle) — distincte de la pause du détecteur

  const handleDetected = useCallback(async (score) => {
    if (pausedRef.current) return; // Jarvis parle déjà, ignore ce déclenchement
    setWakeWordHeard(true);
    setTimeout(() => setWakeWordHeard(false), 2000);

    // captureCommand() met le détecteur en pause en interne dès qu'elle se
    // termine (pour ne pas se redéclencher tout seul juste après — bug réel
    // rencontré). Deux issues ci-dessous (rien dit / transcription vide) sont
    // des culs-de-sac : rien d'autre ne va appeler resume() derrière, donc il
    // faut le faire explicitement ici. Seule l'issue "commande envoyée" laisse
    // le détecteur en pause — c'est speakAnswer (Console.jsx) qui le réactive,
    // une fois la réponse dite.
    setStatus("listening_command");
    const wavBlob = await detector.captureCommand();
    if (!wavBlob) {
      // rien dit après « Jarvis » (timeout d'attente de parole)
      setLastTranscript("(rien entendu après « Jarvis »)");
      if (armedRef.current && !pausedRef.current) {
        detector.resume();
        setStatus("listening");
      }
      return;
    }
    setStatus("transcribing");
    const text = await transcribeBlob(wavBlob);
    setLastTranscript(text.trim() || "(silence)");
    if (text.trim()) {
      onCommandRef.current(text.trim());
    } else if (armedRef.current && !pausedRef.current) {
      // parole détectée mais transcription vide (bruit) — même impasse
      detector.resume();
      setStatus("listening");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const detector = useWakeWordDetector({ onDetected: handleDetected });

  const transcribeBlob = useCallback(async (blob) => {
    if (!blob) return "";
    const form = new FormData();
    form.append("file", blob, "command.wav");
    try {
      const res = await authFetch("/api/speech/transcribe", { method: "POST", body: form });
      if (!res.ok) return "";
      const data = await res.json();
      return data.text || "";
    } catch {
      return "";
    }
  }, []);

  const stopStream = useCallback(() => {
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
  }, []);

  const disarm = useCallback(() => {
    armedRef.current = false;
    setArmed(false);
    setStatus("idle");
    setLastTranscript("");
    setWakeWordHeard(false);
    detector.stop();
    stopStream();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopStream]);

  const arm = useCallback(async () => {
    setError(null);
    let stream;
    try {
      // Désactive le traitement DSP par défaut du navigateur (suppression de
      // bruit/écho, gain auto) : ça déforme le signal par rapport à ce sur
      // quoi le modèle a été entraîné (audio brut côté PC). Sans ça, la
      // détection est nettement moins fiable — trouvé en usage réel.
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
    } catch {
      setError("Micro refusé ou indisponible.");
      return;
    }
    mediaStreamRef.current = stream;
    armedRef.current = true;
    pausedRef.current = false;
    setArmed(true);
    setStatus("listening");
    try {
      await detector.start(stream, { onScore: (s) => setLastScore(s) });
    } catch (e) {
      setError("Détecteur de mot d'éveil indisponible : " + (e?.message || e));
      armedRef.current = false;
      setArmed(false);
      setStatus("idle");
      stopStream();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stopStream]);

  const pause = useCallback(() => {
    pausedRef.current = true;
    detector.pause();
    setStatus("speaking");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resume = useCallback(() => {
    pausedRef.current = false;
    if (armedRef.current) {
      detector.resume();
      setStatus("listening");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => disarm(), [disarm]);

  return {
    armed, status, error, lastTranscript, wakeWordHeard, lastScore,
    arm, disarm, pause, resume,
  };
}
