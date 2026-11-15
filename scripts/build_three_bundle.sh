#!/usr/bin/env sh
# Rebuilds frontend/vendor/three.bundle.js (Three.js + the add-ons the dashboard showcase uses).
# The pages have a 'self'-only Content-Security-Policy, so the library is served from this repo, not a CDN.
set -eu
cd "$(dirname "$0")/.."
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
npm init -y >/dev/null
npm install --silent three@0.187.0 esbuild@0.28.2
cat > entry.js <<'JS'
// Boomerang vendored Three.js bundle: the library plus the few add-ons the showcase uses.
// Rebuild with scripts/build_three_bundle.sh. MIT licensed (three.js, https://threejs.org).
export * from "three";
export { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
export { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
export { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
export { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
JS
npx esbuild entry.js --bundle --format=esm --minify --legal-comments=none --outfile=three.bundle.js
cd - >/dev/null
cp "$tmp/three.bundle.js" frontend/vendor/three.bundle.js
echo "wrote frontend/vendor/three.bundle.js ($(wc -c < frontend/vendor/three.bundle.js) bytes)"
