import { describe, expect, it } from "vitest";
import { waveChunkOf, waveFileName } from "./wave";

describe("生波形のファイルの分け方", () => {
  it("窓の添字 60 個ごとに 1 ファイル", () => {
    expect(waveChunkOf(0)).toBe(0);
    expect(waveChunkOf(59)).toBe(0);
    expect(waveChunkOf(60)).toBe(1);
    expect(waveChunkOf(1799)).toBe(29);
  });

  it("ファイル名は pipeline と同じ 3 桁の 0 詰め", () => {
    expect(waveFileName("ride_20261109_030109", 4)).toBe("wave_ride_20261109_030109_004.json");
    expect(waveFileName("ride_001", 123)).toBe("wave_ride_001_123.json");
  });
});
