import { describe, it, expect } from "vitest";
import { encodeWav } from "./encodeWav";

async function readHeader(blob) {
  const buf = await blob.arrayBuffer();
  return new DataView(buf);
}

describe("encodeWav", () => {
  it("écrit un en-tête RIFF/WAVE valide avec la bonne taille", async () => {
    const samples = new Float32Array([0, 0.5, -0.5, 1, -1]);
    const blob = encodeWav(samples, 16000);
    expect(blob.size).toBe(44 + samples.length * 2);

    const view = await readHeader(blob);
    const str = (offset, len) =>
      String.fromCharCode(...Array.from({ length: len }, (_, i) => view.getUint8(offset + i)));

    expect(str(0, 4)).toBe("RIFF");
    expect(str(8, 4)).toBe("WAVE");
    expect(str(12, 4)).toBe("fmt ");
    expect(str(36, 4)).toBe("data");
    expect(view.getUint32(24, true)).toBe(16000); // sample rate
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint16(34, true)).toBe(16); // bits/sample
  });

  it("écrête les échantillons hors de [-1, 1] sans déborder l'entier 16 bits", async () => {
    const samples = new Float32Array([2, -2]);
    const blob = encodeWav(samples);
    const view = await readHeader(blob);
    expect(view.getInt16(44, true)).toBe(0x7fff);
    expect(view.getInt16(46, true)).toBe(-0x8000);
  });
});
