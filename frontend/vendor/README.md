# Vendored libraries

`three.bundle.js` is Three.js 0.187.0 (MIT) plus OrbitControls, RoomEnvironment, RoundedBoxGeometry and
GLTFLoader, bundled into one ES module with esbuild. The pages ship a `script-src 'self'` Content-Security-Policy,
so nothing is loaded from a CDN. Rebuild with `scripts/build_three_bundle.sh`.
