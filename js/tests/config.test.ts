import { describe, it, expect } from "vitest";
import {
  CHROMIUM_VERSION,
  getChromiumVersion,
  getDefaultStealthArgs,
  getCacheDir,
  getBinaryDir,
  getDownloadUrl,
} from "../src/config.js";
import { _buildArgsForTest, migrateTimezoneId } from "../src/playwright.js";

describe("config", () => {
  it("CHROMIUM_VERSION matches expected format", () => {
    expect(CHROMIUM_VERSION).toMatch(/^\d+\.\d+\.\d+\.\d+(\.\d+)?$/);
  });

  it("getDefaultStealthArgs returns expected flags", () => {
    const args = getDefaultStealthArgs();
    const isMac = process.platform === "darwin";

    expect(args).toContain("--no-sandbox");
    expect(args).toContain("--disable-blink-features=AutomationControlled");

    if (isMac) {
      expect(args).toContain("--fingerprint-platform=macos");
      // macOS: no hardware-concurrency or GPU spoofing (uses native values)
      expect(args.some((a) => a.includes("hardware-concurrency"))).toBe(false);
    } else {
      expect(args).toContain("--fingerprint-platform=windows");
      expect(args).toContain("--fingerprint-hardware-concurrency=8");
    }

    // Should have a random fingerprint seed
    const fingerprintArg = args.find((a) => a.startsWith("--fingerprint="));
    expect(fingerprintArg).toBeDefined();
    const seed = Number(fingerprintArg!.split("=")[1]);
    expect(seed).toBeGreaterThanOrEqual(10000);
    expect(seed).toBeLessThanOrEqual(99999);
  });

  it("getDefaultStealthArgs generates different seeds", () => {
    const seeds = new Set<string>();
    for (let i = 0; i < 10; i++) {
      const args = getDefaultStealthArgs();
      const fp = args.find((a) => a.startsWith("--fingerprint="))!;
      seeds.add(fp);
    }
    // With 90k possible seeds, 10 calls should produce at least 2 unique
    expect(seeds.size).toBeGreaterThan(1);
  });

  it("getCacheDir returns ~/.cloakbrowser by default", () => {
    const dir = getCacheDir();
    expect(dir).toContain(".cloakbrowser");
  });

  it("getBinaryDir includes platform version", () => {
    const dir = getBinaryDir();
    expect(dir).toContain(`chromium-${getChromiumVersion()}`);
  });

  it("getDownloadUrl contains platform version and platform tag", () => {
    const url = getDownloadUrl();
    expect(url).toContain(getChromiumVersion());
    expect(url).toContain("cloakbrowser-");
    expect(url).toContain(".tar.gz");
    expect(url).toContain("cloakbrowser.dev");
  });
});

describe("buildArgs timezone/locale", () => {
  it("injects --fingerprint-timezone when timezone is set", () => {
    const args = _buildArgsForTest({ timezone: "America/New_York" });
    expect(args).toContain("--fingerprint-timezone=America/New_York");
  });

  it("injects --lang when locale is set", () => {
    const args = _buildArgsForTest({ locale: "en-US" });
    expect(args).toContain("--lang=en-US");
  });

  it("injects both when both are set", () => {
    const args = _buildArgsForTest({ timezone: "Europe/Berlin", locale: "de-DE" });
    expect(args).toContain("--fingerprint-timezone=Europe/Berlin");
    expect(args).toContain("--lang=de-DE");
  });

  it("injects timezone/locale even when stealthArgs=false", () => {
    const args = _buildArgsForTest({ stealthArgs: false, timezone: "America/New_York", locale: "en-US" });
    expect(args).toContain("--fingerprint-timezone=America/New_York");
    expect(args).toContain("--lang=en-US");
    expect(args.some(a => a.startsWith("--fingerprint="))).toBe(false);
  });

  it("does not inject flags when not set", () => {
    const args = _buildArgsForTest({});
    expect(args.some(a => a.startsWith("--fingerprint-timezone="))).toBe(false);
    expect(args.some(a => a.startsWith("--lang="))).toBe(false);
  });
});

describe("migrateTimezoneId deprecation", () => {
  it("migrates timezoneId to timezone", () => {
    const result = migrateTimezoneId({ timezoneId: "Europe/Paris" });
    expect(result.timezone).toBe("Europe/Paris");
    expect(result).not.toHaveProperty("timezoneId");
  });

  it("preserves explicit timezone over timezoneId", () => {
    const result = migrateTimezoneId({ timezone: "UTC", timezoneId: "Europe/Paris" });
    expect(result.timezone).toBe("UTC");
    expect(result).not.toHaveProperty("timezoneId");
  });

  it("returns options unchanged when no timezoneId", () => {
    const opts = { timezone: "UTC" };
    const result = migrateTimezoneId(opts);
    expect(result).toBe(opts); // same reference, no copy
    expect(result.timezone).toBe("UTC");
  });

  it("returns options unchanged when neither is set", () => {
    const opts = {};
    const result = migrateTimezoneId(opts);
    expect(result).toBe(opts);
  });
});
