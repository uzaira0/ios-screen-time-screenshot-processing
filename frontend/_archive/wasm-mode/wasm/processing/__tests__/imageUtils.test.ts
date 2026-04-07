import { describe, it, expect } from "vitest";
import { isClose } from "../imageUtils.canvas";

describe("imageUtils", () => {
  describe("isClose", () => {
    it("should return true for identical pixels", () => {
      const pixel1 = [255, 255, 255];
      const pixel2 = [255, 255, 255];
      expect(isClose(pixel1, pixel2, 1)).toBe(true);
    });

    it("should return true for pixels within threshold", () => {
      const pixel1 = [255, 255, 255];
      const pixel2 = [254, 254, 254];
      expect(isClose(pixel1, pixel2, 1)).toBe(true);
    });

    it("should return false for pixels outside threshold", () => {
      const pixel1 = [255, 255, 255];
      const pixel2 = [250, 250, 250];
      expect(isClose(pixel1, pixel2, 1)).toBe(false);
    });

    it("should handle different thresholds", () => {
      const pixel1 = [255, 255, 255];
      const pixel2 = [250, 250, 250];
      expect(isClose(pixel1, pixel2, 5)).toBe(true);
    });

    it("should handle RGB values", () => {
      const pixel1 = [255, 0, 0];
      const pixel2 = [254, 1, 1];
      expect(isClose(pixel1, pixel2, 1)).toBe(true);
    });
  });
});
