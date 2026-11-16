import { describe, expect, it } from "vitest";
import { firmwareLabel, isSlowerThanSet, rateBadge, recordingNote, sensorLabel } from "./recording";
import type { RecordingSettings } from "./types";

const V37: RecordingSettings = {
  firmware: "CT125_LOGGER_V3.7",
  accel_chip: "ADXL345",
  accel_bus: "i2c",
  accel_odr_hz: 800,
  accel_fs_hz: 798.6,
  accel_range_g: 16,
  feature_fs_hz: 399.3,
};

describe("記録の設定の表示", () => {
  it("カードの印は設定の速さ", () => {
    expect(rateBadge(V37)).toBe("800 Hz");
    expect(rateBadge({ ...V37, accel_odr_hz: null, accel_fs_hz: 398.5 })).toBe("399 Hz");
  });

  it("版は短くする", () => {
    expect(firmwareLabel("CT125_LOGGER_V3.7")).toBe("V3.7");
    expect(firmwareLabel("other")).toBe("other");
    expect(firmwareLabel(null)).toBeNull();
  });

  it("センサーとつなぎ方", () => {
    expect(sensorLabel(V37)).toBe("ADXL345（I2C）");
    expect(sensorLabel({ ...V37, accel_bus: "spi" })).toBe("ADXL345（SPI）");
    expect(sensorLabel({ ...V37, accel_bus: null })).toBe("ADXL345");
    expect(sensorLabel({ ...V37, accel_chip: null, accel_bus: null })).toBeNull();
  });

  it("実測が設定より 5% を超えて遅いと知らせる", () => {
    expect(isSlowerThanSet(V37)).toBe(false);
    expect(isSlowerThanSet({ ...V37, accel_fs_hz: 750 })).toBe(true);
    expect(isSlowerThanSet({ ...V37, accel_odr_hz: null, accel_fs_hz: 100 })).toBe(false);
  });

  it("説明に設定・実測・間引きを書く", () => {
    expect(recordingNote(V37)).toBe("設定 800 Hz・実測 798.6 Hz・振動の数値は 399.3 Hz に間引いて計算");
    expect(recordingNote({ ...V37, accel_odr_hz: 400, accel_fs_hz: 398.5, feature_fs_hz: 398.5 })).toBe("設定 400 Hz・実測 398.5 Hz");
    expect(recordingNote({ ...V37, accel_fs_hz: 700, feature_fs_hz: 350 })).toContain("取りこぼしの疑い");
  });
});
