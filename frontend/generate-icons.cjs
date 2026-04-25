// Generate the SVG master icon and PNG rasters for the PWA manifest.
// Sharp is used for rasterization (already a transitive dep).
const fs = require("fs");
const path = require("path");
const sharp = require("sharp");

const svg = `
<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <rect width="512" height="512" fill="#3b82f6"/>
  <path d="M128 128h256v256H128z" fill="white" opacity="0.3"/>
  <circle cx="256" cy="200" r="40" fill="white"/>
  <rect x="156" y="280" width="200" height="24" rx="12" fill="white"/>
  <rect x="156" y="320" width="140" height="24" rx="12" fill="white"/>
  <text x="256" y="420" font-family="Arial, sans-serif" font-size="48" font-weight="bold" text-anchor="middle" fill="white">SP</text>
</svg>
`.trim();

const iconsDir = path.join(__dirname, "public", "icons");
if (!fs.existsSync(iconsDir)) {
  fs.mkdirSync(iconsDir, { recursive: true });
}

fs.writeFileSync(path.join(iconsDir, "icon.svg"), svg);
console.log("✓ SVG icon written to public/icons/icon.svg");

const sizes = [192, 512];
const svgBuf = Buffer.from(svg, "utf-8");

(async () => {
  for (const size of sizes) {
    const outFile = path.join(iconsDir, `icon-${size}.png`);
    await sharp(svgBuf, { density: 384 }).resize(size, size).png().toFile(outFile);
    console.log(`✓ PNG ${size}×${size} written to public/icons/icon-${size}.png`);
  }
  // Maskable: pad the artwork inside a 80% safe area (centered) over the
  // background colour so Android's adaptive icon mask doesn't clip the SP glyph.
  const maskableSize = 512;
  const innerSize = Math.round(maskableSize * 0.8);
  const innerPng = await sharp(svgBuf, { density: 384 }).resize(innerSize, innerSize).png().toBuffer();
  await sharp({
    create: {
      width: maskableSize,
      height: maskableSize,
      channels: 4,
      background: { r: 59, g: 130, b: 246, alpha: 1 },
    },
  })
    .composite([{ input: innerPng, gravity: "center" }])
    .png()
    .toFile(path.join(iconsDir, "icon-maskable-512.png"));
  console.log("✓ PNG maskable 512×512 written to public/icons/icon-maskable-512.png");
})().catch((err) => {
  console.error("Icon generation failed:", err);
  process.exit(1);
});
