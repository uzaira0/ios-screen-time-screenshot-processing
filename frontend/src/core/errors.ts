export class DuplicateScreenshotError extends Error {
  readonly existingId: number;
  constructor(existingId: number) {
    super(`Duplicate image: already uploaded as screenshot #${existingId}`);
    this.name = "DuplicateScreenshotError";
    this.existingId = existingId;
  }
}
