// Whisper déforme parfois "Jarvis" (petit modèle, nom inventé) — vu en test
// réel : "Jarvis" → "Javi". Une correspondance exacte raterait trop
// souvent, d'où une tolérance légère (distance de Levenshtein ≤ 2).

function levenshtein(a, b) {
  const m = a.length;
  const n = b.length;
  const d = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
  for (let j = 0; j <= n; j++) d[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
    }
  }
  return d[m][n];
}

function normalize(text) {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

const WAKE_WORD = "jarvis";

// Distance <= 2 s'est révélée bien trop permissive en usage réel : des
// mots français courants ("jamais", "jadis") tombent dans cette marge et
// déclenchaient le mot d'éveil sur n'importe quelle phrase. Resserré à
// <= 1 (quasi-exact), complété par une liste explicite des déformations
// Whisper réellement observées (ex. "Jarvis" → "Javi", distance 2) plutôt
// que d'élargir la tolérance générale pour ce seul cas.
const KNOWN_VARIANTS = new Set(["jarvis", "javi", "jarvi", "jarviss", "djarvis"]);

/**
 * Cherche "jarvis" (tolérant aux déformations Whisper connues) dans
 * `text`. Retourne { found, remainder } — remainder = ce qui suit le mot
 * détecté dans la phrase (potentiellement la commande elle-même).
 */
export function findWakeWord(text) {
  const normalized = normalize(text);
  const words = normalized.split(/\s+/).filter(Boolean);
  for (let i = 0; i < words.length; i++) {
    const w = words[i].replace(/[.,!?;:]/g, "");
    if (w.length < 4) continue;
    if (KNOWN_VARIANTS.has(w) || levenshtein(w, WAKE_WORD) <= 1) {
      const remainder = words.slice(i + 1).join(" ").trim();
      return { found: true, remainder };
    }
  }
  return { found: false, remainder: "" };
}
