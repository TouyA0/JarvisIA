// MFCC identique à librosa.feature.mfcc(y, sr=16000, n_mfcc=40) — port
// validé numériquement contre la sortie Python réelle (voir docs/
// ROADMAP_MULTIDEVICE.md, Phase 9) : sur 10 échantillons réels (5 Jarvis,
// 5 négatifs), l'écart avec le score du modèle original est de 0.00000.
// Ne pas modifier ces formules sans revalider — le modèle est sensible au
// moindre écart de prétraitement (mêmes réglages que
// agents/desktop/audio/wakeword.py et wakeword/entrainer.py).
const SR = 16000;
const N_FFT = 2048;
const HOP = 512;
const N_MELS = 128;
const N_MFCC = 40;

function fft(re, im) {
  const n = re.length;
  if (n <= 1) return;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    const wRe = Math.cos(ang), wIe = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let curRe = 1, curIe = 0;
      for (let j = 0; j < len / 2; j++) {
        const uRe = re[i + j], uIe = im[i + j];
        const vRe = re[i + j + len / 2] * curRe - im[i + j + len / 2] * curIe;
        const vIe = re[i + j + len / 2] * curIe + im[i + j + len / 2] * curRe;
        re[i + j] = uRe + vRe; im[i + j] = uIe + vIe;
        re[i + j + len / 2] = uRe - vRe; im[i + j + len / 2] = uIe - vIe;
        const nRe = curRe * wRe - curIe * wIe;
        const nIe = curRe * wIe + curIe * wRe;
        curRe = nRe; curIe = nIe;
      }
    }
  }
}

function hannWindow(N) {
  const w = new Float64Array(N);
  for (let n = 0; n < N; n++) w[n] = 0.5 - 0.5 * Math.cos((2 * Math.PI * n) / N);
  return w;
}
const WINDOW = hannWindow(N_FFT);

function powerSpectrogram(audio) {
  const pad = N_FFT >> 1;
  const padded = new Float64Array(audio.length + 2 * pad);
  padded.set(audio, pad);
  const nFrames = 1 + Math.floor((padded.length - N_FFT) / HOP);
  const nBins = N_FFT / 2 + 1;
  const S = Array.from({ length: nBins }, () => new Float64Array(nFrames));

  for (let t = 0; t < nFrames; t++) {
    const start = t * HOP;
    const re = new Float64Array(N_FFT);
    const im = new Float64Array(N_FFT);
    for (let n = 0; n < N_FFT; n++) re[n] = padded[start + n] * WINDOW[n];
    fft(re, im);
    for (let k = 0; k < nBins; k++) S[k][t] = re[k] * re[k] + im[k] * im[k];
  }
  return S;
}

// Mel scale "Slaney" (htk=False) — formules exactes de librosa.filters.mel
function hzToMel(f) {
  const fSp = 200.0 / 3;
  let mel = f / fSp;
  const minLogHz = 1000.0;
  const minLogMel = minLogHz / fSp;
  const logstep = Math.log(6.4) / 27.0;
  if (f >= minLogHz) mel = minLogMel + Math.log(f / minLogHz) / logstep;
  return mel;
}
function melToHz(mel) {
  const fSp = 200.0 / 3;
  let f = fSp * mel;
  const minLogHz = 1000.0;
  const minLogMel = minLogHz / fSp;
  const logstep = Math.log(6.4) / 27.0;
  if (mel >= minLogMel) f = minLogHz * Math.exp(logstep * (mel - minLogMel));
  return f;
}

function buildMelFilterbank() {
  const nBins = N_FFT / 2 + 1;
  const fMax = SR / 2;
  const melMin = hzToMel(0);
  const melMax = hzToMel(fMax);
  const melPts = new Float64Array(N_MELS + 2);
  for (let i = 0; i < N_MELS + 2; i++) melPts[i] = melMin + ((melMax - melMin) * i) / (N_MELS + 1);
  const hzPts = Array.from(melPts, melToHz);

  const fftFreqs = new Float64Array(nBins);
  for (let k = 0; k < nBins; k++) fftFreqs[k] = (k * SR) / N_FFT;

  const fdiff = new Float64Array(N_MELS + 1);
  for (let i = 0; i < N_MELS + 1; i++) fdiff[i] = hzPts[i + 1] - hzPts[i];

  const weights = Array.from({ length: N_MELS }, () => new Float64Array(nBins));
  for (let i = 0; i < N_MELS; i++) {
    for (let k = 0; k < nBins; k++) {
      const lower = -(hzPts[i] - fftFreqs[k]) / fdiff[i];
      const upper = (hzPts[i + 2] - fftFreqs[k]) / fdiff[i + 1];
      weights[i][k] = Math.max(0, Math.min(lower, upper));
    }
    const enorm = 2.0 / (hzPts[i + 2] - hzPts[i]);
    for (let k = 0; k < nBins; k++) weights[i][k] *= enorm;
  }
  return weights;
}
const MEL_FILTERBANK = buildMelFilterbank();

function melspectrogram(audio) {
  const S = powerSpectrogram(audio);
  const nBins = S.length, nFrames = S[0].length;
  const out = Array.from({ length: N_MELS }, () => new Float64Array(nFrames));
  for (let m = 0; m < N_MELS; m++) {
    for (let t = 0; t < nFrames; t++) {
      let acc = 0;
      for (let k = 0; k < nBins; k++) acc += MEL_FILTERBANK[m][k] * S[k][t];
      out[m][t] = acc;
    }
  }
  return out;
}

function powerToDb(S) {
  const amin = 1e-10, topDb = 80.0;
  const nMels = S.length, nFrames = S[0].length;
  const out = Array.from({ length: nMels }, () => new Float64Array(nFrames));
  let maxVal = -Infinity;
  for (let m = 0; m < nMels; m++)
    for (let t = 0; t < nFrames; t++) {
      const v = 10 * Math.log10(Math.max(amin, S[m][t]));
      out[m][t] = v;
      if (v > maxVal) maxVal = v;
    }
  for (let m = 0; m < nMels; m++)
    for (let t = 0; t < nFrames; t++)
      out[m][t] = Math.max(out[m][t], maxVal - topDb);
  return out;
}

function dctOrtho(logSpec) {
  const nMels = logSpec.length, nFrames = logSpec[0].length;
  const out = Array.from({ length: N_MFCC }, () => new Float64Array(nFrames));
  for (let t = 0; t < nFrames; t++) {
    const col = new Float64Array(nMels);
    for (let m = 0; m < nMels; m++) col[m] = logSpec[m][t];
    for (let k = 0; k < N_MFCC; k++) {
      let acc = 0;
      for (let n = 0; n < nMels; n++) acc += col[n] * Math.cos((Math.PI * k * (2 * n + 1)) / (2 * nMels));
      acc *= 2;
      acc *= k === 0 ? Math.sqrt(1 / (4 * nMels)) : Math.sqrt(1 / (2 * nMels));
      out[k][t] = acc;
    }
  }
  return out;
}

/** audio : Float32Array normalisé (RMS cible), longueur WAKE_WORD_WINDOW_SAMPLES.
 * Retourne un Float32Array à plat, layout (nFrames, 40) — prêt pour le tenseur (1, 47, 40). */
export function computeMfccFlat(audio) {
  const mel = melspectrogram(audio);
  const db = powerToDb(mel);
  const mfcc = dctOrtho(db); // [40][nFrames]
  const nFrames = mfcc[0].length;
  const flat = new Float32Array(nFrames * N_MFCC);
  for (let t = 0; t < nFrames; t++)
    for (let k = 0; k < N_MFCC; k++)
      flat[t * N_MFCC + k] = mfcc[k][t];
  return { flat, nFrames };
}
