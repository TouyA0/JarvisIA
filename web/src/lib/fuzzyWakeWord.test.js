import { describe, it, expect } from "vitest";
import { findWakeWord } from "./fuzzyWakeWord";

describe("findWakeWord", () => {
  it("détecte le mot d'éveil exact et renvoie le reste de la phrase", () => {
    expect(findWakeWord("Jarvis quelle heure est-il")).toEqual({
      found: true,
      remainder: "quelle heure est-il",
    });
  });

  it("tolère les déformations Whisper connues (Javi)", () => {
    expect(findWakeWord("Javi allume la lumière")).toEqual({
      found: true,
      remainder: "allume la lumiere",
    });
  });

  it("ignore les accents et la casse", () => {
    const { found } = findWakeWord("JÀRVIS dis bonjour");
    expect(found).toBe(true);
  });

  it("ne déclenche pas sur des mots français proches (jamais, jadis)", () => {
    expect(findWakeWord("je n'irai jamais là-bas").found).toBe(false);
    expect(findWakeWord("jadis on faisait autrement").found).toBe(false);
  });

  it("ne trouve rien dans une phrase sans mot d'éveil", () => {
    expect(findWakeWord("quelle heure est-il")).toEqual({
      found: false,
      remainder: "",
    });
  });
});
