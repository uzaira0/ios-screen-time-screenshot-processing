import { describe, it, expect } from "vitest";
import { LineExtractionMode } from "../barExtraction.canvas";

describe("barExtraction", () => {
  describe("LineExtractionMode", () => {
    it("should have HORIZONTAL mode", () => {
      expect(LineExtractionMode.HORIZONTAL).toBe("HORIZONTAL");
    });

    it("should have VERTICAL mode", () => {
      expect(LineExtractionMode.VERTICAL).toBe("VERTICAL");
    });
  });
});
