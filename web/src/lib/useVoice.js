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
 * Barge-in : `pause()` (interne) coupe la détection pendant la capture
 * d'une commande et pendant que Jarvis réfléchit/transcrit (rien à
 * interrompre à ce moment-là), mais le détecteur reste actif pendant la
 * lecture audio de la réponse (drainQueue) — le modèle tourne déjà en
 * continu dans le navigateur, ça ne coûte rien de plus. Un « Jarvis »
 * entendu pendant que Jarvis parle coupe net la lecture en cours
 * (voir interruptSpeaking) et enchaîne directement sur la capture de la
 * nouvelle commande, comme au repos.
 *
 * Présence multi-appareils (`presence`, voir usePresence.js) : entendre
 * « Jarvis » ici fait de CE navigateur l'appareil actif (dépasse le PC
 * fixe ou une autre Console ouverte ailleurs, voir brain/presence.py).
 * L'audio de synthèse n'est joué que si cette Console est toujours
 * l'appareil actif au moment de le lire — sinon le texte s'affiche quand
 * même, juste sans le son, pour ne pas faire parler deux appareils en
 * même temps sur la même conversation.
 */
export function useVoice({ onCommand, presence }) {
  const [armed, setArmed] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | listening | listening_command | transcribing | speaking
  const [error, setError] = useState(null);
  const [lastTranscript, setLastTranscript] = useState("");
  const [wakeWordHeard, setWakeWordHeard] = useState(false);
  const [lastScore, setLastScore] = useState(0);

  const onCommandRef = useRef(onCommand);
  onCommandRef.current = onCommand;
  const presenceRef = useRef(presence);
  presenceRef.current = presence;

  const mediaStreamRef = useRef(null);
  const armedRef = useRef(false);
  const pausedRef = useRef(false); // pause externe (Jarvis parle) — distincte de la pause du détecteur
  const audioRef = useRef(null); // lecture TTS en cours, pour qu'Échap puisse la couper (voir stopSpeaking)

  // File de synthèse : chaque phrase du tour en cours lance sa synthèse dès
  // son arrivée (les fetches tournent donc en parallèle du réseau), et la
  // lecture les enchaîne dans l'ordre dès que le premier segment est prêt —
  // au lieu d'attendre le bloc entier comme avant. Même principe que le
  // streaming phrase par phrase de agents/desktop/audio/tts.py côté PC.
  const audioQueueRef = useRef([]); // Promise<Blob|null>[], dans l'ordre d'arrivée
  const playingRef = useRef(false); // une boucle de lecture est déjà active — Jarvis parle (barge-in armé)
  const turnEndedRef = useRef(true); // plus aucune phrase à attendre pour le tour en cours
  const playResolveRef = useRef(null); // débloque la lecture en cours depuis stopSpeaking/interruptSpeaking
  const suppressResumeRef = useRef(false); // un barge-in gère lui-même la suite : sauter le resume() de fin de drainQueue

  const handleDetected = useCallback(async (score) => {
    if (pausedRef.current) {
      if (!playingRef.current) return; // en pleine réflexion/transcription : rien à interrompre, on ignore
      // Barge-in : Jarvis est en train de parler (playingRef actif depuis
      // drainQueue) — on le coupe net et on enchaîne directement sur la
      // capture de la nouvelle commande, comme si on partait du repos.
      suppressResumeRef.current = true;
      interruptSpeaking();
    }
    setWakeWordHeard(true);
    setTimeout(() => setWakeWordHeard(false), 2000);
    presenceRef.current?.activate?.();

    // captureCommand() met le détecteur en pause en interne dès qu'elle se
    // termine (pour ne pas se redéclencher tout seul juste après — bug réel
    // rencontré). Deux issues ci-dessous (rien dit / transcription vide) sont
    // des culs-de-sac : rien d'autre ne va appeler resume() derrière, donc il
    // faut le faire explicitement ici — y compris quand on arrive d'un
    // barge-in (pausedRef.current est alors resté à true, il faut le
    // relâcher nous-mêmes). Seule l'issue "commande envoyée" laisse le
    // détecteur en pause — c'est speakAnswer (Console.jsx) qui le réactive,
    // une fois la réponse dite.
    setStatus("listening_command");
    const wavBlob = await detector.captureCommand();
    if (!wavBlob) {
      // rien dit après « Jarvis » (timeout d'attente de parole)
      setLastTranscript("(rien entendu après « Jarvis »)");
      pausedRef.current = false;
      if (armedRef.current) {
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
    } else {
      // parole détectée mais transcription vide (bruit) — même impasse
      pausedRef.current = false;
      if (armedRef.current) {
        detector.resume();
        setStatus("listening");
      }
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
    // Ne coupe pas le détecteur : il reste self-pausé par captureCommand()
    // pendant la réflexion/transcription, et drainQueue le réactive lui-même
    // dès que la lecture audio démarre (barge-in, voir handleDetected).
    pausedRef.current = true;
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

  const synthesize = useCallback(async (text) => {
    try {
      const res = await authFetch("/api/speech/synthesize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) return null;
      return await res.blob();
    } catch {
      return null;
    }
  }, []);

  // Draine la file dans l'ordre : chaque Promise a été lancée dès l'arrivée
  // de sa phrase (voir speakPhrase), donc le segment suivant a de bonnes
  // chances d'être déjà prêt — ou en cours — quand le précédent finit de
  // jouer, sans le silence d'attente du bloc entier. Ne reprend l'écoute
  // qu'une fois la file vide *et* le tour terminé (speakEnd), pour ne pas
  // se redéclencher entre deux phrases du même tour.
  const drainQueue = useCallback(async () => {
    if (playingRef.current) return;
    playingRef.current = true;
    // Second palier du barge-in : le modèle de détection tourne déjà en
    // continu dans le navigateur, donc pas de coût à le laisser actif
    // pendant que Jarvis parle — seule différence avec l'écoute au repos,
    // handleDetected traite un « Jarvis » entendu ici comme une coupure.
    if (armedRef.current) detector.resume();
    while (audioQueueRef.current.length) {
      const blob = await audioQueueRef.current.shift();
      // Un autre appareil a pris la main entre-temps (voir presence,
      // usePresence.js) — le texte reste affiché normalement (Console.jsx
      // le tient de chat.phrase, indépendant de cette file), mais cette
      // Console ne double pas l'audio de synthèse par-dessus l'autre.
      if (blob && presenceRef.current?.isActive?.() !== false) {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audioRef.current = audio;
        await new Promise((resolve) => {
          playResolveRef.current = resolve;
          audio.onended = resolve;
          audio.onerror = resolve;
          audio.play().catch(resolve);
        });
        playResolveRef.current = null;
        URL.revokeObjectURL(url);
        if (audioRef.current === audio) audioRef.current = null;
      }
    }
    playingRef.current = false;
    if (turnEndedRef.current) {
      // Un barge-in (handleDetected) a déjà pris la suite lui-même — cette
      // boucle ne fait que se terminer après avoir été coupée court, il ne
      // faut pas repasser en "listening" par-dessus son "listening_command".
      if (suppressResumeRef.current) suppressResumeRef.current = false;
      else resume();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resume]);

  // Empile une phrase dès sa réception (Console.jsx/Hud.jsx la relaient
  // depuis chat.phrase) : la synthèse démarre immédiatement, la lecture
  // s'enchaîne dès que le segment précédent (ou rien) est prêt.
  const speakPhrase = useCallback(
    (text) => {
      const trimmed = (text || "").trim();
      if (!trimmed) return;
      turnEndedRef.current = false;
      audioQueueRef.current.push(synthesize(trimmed));
      drainQueue();
    },
    [synthesize, drainQueue],
  );

  // Signale la fin du tour (chat.done) : plus aucune phrase à attendre —
  // reprend l'écoute dès que la file en cours se vide (immédiatement si
  // elle est déjà vide, par exemple une réponse sans aucune phrase).
  const speakEnd = useCallback(() => {
    turnEndedRef.current = true;
    if (!playingRef.current && audioQueueRef.current.length === 0) resume();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resume]);

  // Coupe la lecture en cours sans attendre la fin naturelle du clip et
  // vide la file — utilisé par Échap (stopSpeaking, qui reprend l'écoute
  // ensuite) et par le barge-in vocal (handleDetected, qui enchaîne lui-même
  // sur la capture d'une commande au lieu de reprendre l'écoute passive).
  const interruptSpeaking = useCallback(() => {
    audioQueueRef.current = [];
    turnEndedRef.current = true;
    const audio = audioRef.current;
    audioRef.current = null;
    if (audio) audio.pause();
    playResolveRef.current?.();
    playResolveRef.current = null;
  }, []);

  // Échap : coupe la parole et reprend l'écoute comme si le tour s'était
  // terminé normalement.
  const stopSpeaking = useCallback(() => {
    interruptSpeaking();
    if (!playingRef.current) resume();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interruptSpeaking, resume]);

  useEffect(() => () => disarm(), [disarm]);

  return {
    armed, status, error, lastTranscript, wakeWordHeard, lastScore,
    arm, disarm, pause, resume, speakPhrase, speakEnd, stopSpeaking,
  };
}
