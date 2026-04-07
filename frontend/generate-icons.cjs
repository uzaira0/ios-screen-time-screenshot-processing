// Simple icon generation script
const fs = require('fs');
const path = require('path');

// Create a simple SVG icon
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

const iconsDir = path.join(__dirname, 'public', 'icons');

// Ensure directory exists
if (!fs.existsSync(iconsDir)) {
  fs.mkdirSync(iconsDir, { recursive: true });
}

// Write SVG icon
fs.writeFileSync(path.join(iconsDir, 'icon.svg'), svg);

console.log('✓ SVG icon generated at public/icons/icon.svg');
console.log('\nNote: For production, generate PNG icons using:');
console.log('  npm install -g pwa-asset-generator');
console.log('  pwa-asset-generator public/icons/icon.svg public/icons --icon-only');
