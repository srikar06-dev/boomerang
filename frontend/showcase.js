// Dashboard showcase: a 3D demo item on a dark stage, with the numbers that matter for returns
// (typical weight, price, what we check, the fraud pattern) and live counts from this station.
//
// Drag to turn, pinch or scroll to zoom. Every item is built from primitives in this file, so it works
// offline and ships no third-party assets. Drop a .glb into frontend/models/ (see its README) to replace one.
// Loads as an ES module from the same origin: the pages' CSP is script-src 'self', so no CDN.
import * as T from "./vendor/three.bundle.js";

const BRAND = 0xf04e23;

// Weights and prices are typical figures for the demo, not catalogue data. `match` links an item to the
// seeded products by name so the live counts below the specs come from real returns at this station.
const ITEMS = [
  { slug: "smartphone", name: "Smartphone", size: 1.5, weight_g: 190, price_usd: 799, check: "IMEI / serial",
    signal: "Serial swap: an older or broken unit comes back in the right box.", match: /(?<!head)phone/ },
  { slug: "laptop", name: "Laptop 14-inch", ghost: "Laptop", size: 2.0, weight_g: 1400, price_usd: 899, check: "Serial",
    signal: "Serial swap, or the charger and drive are missing. The scale notices first.", match: /laptop(?! bag)/ },
  { slug: "speaker", name: "Smart speaker", size: 1.15, weight_g: 300, price_usd: 49, check: "Serial",
    signal: "Brick in the box: a sealed-looking package at the wrong weight.", match: /speaker/ },
  { slug: "headphones", name: "Over-ear headphones", size: 1.45, weight_g: 260, price_usd: 149, check: "Serial",
    signal: "A cheaper model comes back; pads and case stay home.", match: /headphone/ },
  { slug: "bicycle", name: "Bicycle", size: 1.9, weight_g: 11500, price_usd: 649, check: "Frame number",
    signal: "Ridden for a season and returned, or a cheaper bike in the same box.", match: /bike|bicycle/ },
  { slug: "helmet", name: "Bike helmet", size: 1.35, weight_g: 320, price_usd: 89, check: "Visual",
    signal: "A crashed helmet returned as new. It can never go back on a shelf.", match: /helmet/ },
  { slug: "sneaker", name: "Running sneakers", size: 1.6, weight_g: 560, price_usd: 129, check: "Visual",
    signal: "Worn outside and returned (wardrobing), or a different size in the box.", match: /sneaker|shoe|runner/ },
  { slug: "boot", name: "Leather boots", size: 1.5, weight_g: 1300, price_usd: 189, check: "Visual",
    signal: "Worn and returned, or a counterfeit pair swapped in.", match: /boot/ },
];

// ---------- small helpers ----------
const std = (color, o = {}) => new T.MeshStandardMaterial({ color, roughness: 0.5, metalness: 0, ...o });
const phys = (color, o = {}) => new T.MeshPhysicalMaterial({ color, roughness: 0.3, metalness: 0, ...o });
const V = (x, y, z = 0) => new T.Vector3(x, y, z);

function mesh(geo, mat, pos, rot, scale) {
  const m = new T.Mesh(geo, mat);
  if (pos) m.position.set(...pos);
  if (rot) m.rotation.set(...rot);
  if (scale) m.scale.set(...scale);
  m.castShadow = m.receiveShadow = true;
  return m;
}
const box = (w, h, d, r, mat, pos, rot) => mesh(new T.RoundedBoxGeometry(w, h, d, 3, r), mat, pos, rot);
const cyl = (rt, rb, h, mat, pos, rot, seg = 40) => mesh(new T.CylinderGeometry(rt, rb, h, seg), mat, pos, rot);
const torus = (r, t, mat, pos, rot, scale) => mesh(new T.TorusGeometry(r, t, 14, 72), mat, pos, rot, scale);
const sphere = (r, mat, pos, scale) => mesh(new T.SphereGeometry(r, 40, 28), mat, pos, null, scale);

// A straight tube between two points (frames, spokes, straps, laces).
function tube(a, b, r, mat) {
  const len = a.distanceTo(b);
  const m = mesh(new T.CylinderGeometry(r, r, len, 18), mat);
  m.position.copy(a).add(b).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(V(0, 1, 0), b.clone().sub(a).normalize());
  return m;
}

// Scales a model so its longest side is `size`, centres it and sits it on the floor.
function fit(group, size = 1.7) {
  const bb = new T.Box3().setFromObject(group);
  const dims = bb.getSize(new T.Vector3());
  const s = size / Math.max(dims.x, dims.y, dims.z);
  group.scale.setScalar(s);
  const bb2 = new T.Box3().setFromObject(group);
  const c = bb2.getCenter(new T.Vector3());
  group.position.x -= c.x; group.position.z -= c.z; group.position.y -= bb2.min.y;
  return group;
}

// ---------- the items ----------
const BUILD = {
  smartphone() {
    const g = new T.Group();
    const body = std(0x2c2f34, { metalness: 0.9, roughness: 0.35 });
    g.add(box(0.72, 1.5, 0.08, 0.09, body));
    g.add(box(0.66, 1.43, 0.012, 0.06, phys(0x05070c, { clearcoat: 1, clearcoatRoughness: 0.08, roughness: 0.1 }), [0, 0, 0.04]));
    g.add(box(0.3, 0.3, 0.035, 0.05, std(0x1f2226, { metalness: 0.8, roughness: 0.4 }), [-0.17, 0.52, -0.05]));
    [[-0.23, 0.58], [-0.11, 0.58], [-0.17, 0.46]].forEach(([x, y]) => {
      g.add(cyl(0.055, 0.055, 0.02, std(0x8a8f96, { metalness: 1, roughness: 0.25 }), [x, y, -0.07], [Math.PI / 2, 0, 0]));
      g.add(cyl(0.035, 0.035, 0.022, phys(0x0b1020, { clearcoat: 1, roughness: 0.05 }), [x, y, -0.072], [Math.PI / 2, 0, 0]));
    });
    g.add(box(0.012, 0.14, 0.03, 0.004, body, [0.365, 0.35, 0]));
    g.add(box(0.012, 0.09, 0.03, 0.004, body, [-0.365, 0.45, 0]));
    g.add(box(0.012, 0.09, 0.03, 0.004, body, [-0.365, 0.3, 0]));
    g.rotation.set(-0.42, -0.35, 0.02);  // propped back, the way a phone is photographed, not standing on its edge
    return g;
  },

  laptop() {
    const g = new T.Group();
    const alu = std(0xb9bdc3, { metalness: 0.85, roughness: 0.4 });
    g.add(box(1.6, 0.06, 1.05, 0.02, alu));
    g.add(box(1.32, 0.012, 0.5, 0.004, std(0x1b1d21, { roughness: 0.7 }), [0, 0.03, -0.17]));
    const key = new T.InstancedMesh(new T.RoundedBoxGeometry(0.076, 0.012, 0.068, 1, 0.01), std(0x111215, { roughness: 0.6 }), 14 * 5);
    const m = new T.Matrix4(); let i = 0;
    for (let r = 0; r < 5; r++) for (let c = 0; c < 14; c++) key.setMatrixAt(i++, m.makeTranslation(-0.6 + c * 0.092, 0.038, -0.36 + r * 0.088));
    key.castShadow = true; g.add(key);
    g.add(box(0.5, 0.006, 0.31, 0.01, std(0xa6aab0, { metalness: 0.8, roughness: 0.3 }), [0, 0.032, 0.3]));
    const lid = new T.Group(); lid.position.set(0, 0.03, -0.52); lid.rotation.x = -0.26;
    lid.add(box(1.6, 1.02, 0.03, 0.02, alu, [0, 0.51, 0]));
    lid.add(box(1.5, 0.92, 0.008, 0.004, phys(0x0b0f18, { clearcoat: 1, roughness: 0.12, emissive: 0x0e1a2c, emissiveIntensity: 0.9 }), [0, 0.52, 0.017]));
    g.add(lid);
    g.rotation.y = -0.55;
    return g;
  },

  // A puck-shaped smart speaker (the Echo Dot silhouette): fabric band, flat top, light ring, four buttons.
  speaker() {
    const g = new T.Group();
    const fabric = std(0x2a2c30, { roughness: 1, envMapIntensity: 0.35 });
    g.add(cyl(0.5, 0.47, 0.24, fabric, [0, 0.12, 0], null, 72));
    g.add(torus(0.49, 0.03, fabric, [0, 0.235, 0], [Math.PI / 2, 0, 0]));
    g.add(cyl(0.49, 0.5, 0.04, std(0x17181b, { roughness: 0.45 }), [0, 0.26, 0], null, 72));
    g.add(torus(0.47, 0.016, std(BRAND, { emissive: BRAND, emissiveIntensity: 2.2, roughness: 0.4 }), [0, 0.282, 0], [Math.PI / 2, 0, 0]));
    [[0.2, 0], [-0.2, 0], [0, 0.2], [0, -0.2]].forEach(([x, z]) =>
      g.add(cyl(0.05, 0.05, 0.012, std(0x26282c, { roughness: 0.5 }), [x, 0.286, z], null, 32)));
    g.add(cyl(0.46, 0.46, 0.02, std(0x202226, { roughness: 0.8 }), [0, 0.01, 0], null, 64));
    g.rotation.y = 0.4;
    return g;
  },

  headphones() {
    const g = new T.Group();
    const dark = std(0x1f2124, { roughness: 0.7 });
    const arc = new T.EllipseCurve(0, 0.6, 0.6, 0.66, Math.PI * 1.06, -Math.PI * 0.06, true).getPoints(48)
      .map((p) => V(p.x, p.y, 0));
    g.add(mesh(new T.TubeGeometry(new T.CatmullRomCurve3(arc), 64, 0.045, 14), dark));
    const pad = new T.EllipseCurve(0, 0.6, 0.6, 0.66, Math.PI * 0.78, Math.PI * 0.22, true).getPoints(24)
      .map((p) => V(p.x, p.y, 0));
    g.add(mesh(new T.TubeGeometry(new T.CatmullRomCurve3(pad), 32, 0.072, 14), std(0x2c2e33, { roughness: 0.9 })));
    [-1, 1].forEach((s) => {
      const cup = new T.Group(); cup.position.set(s * 0.6, 0.6, 0); cup.rotation.z = s * 0.12;
      cup.add(cyl(0.27, 0.27, 0.2, std(0x202226, { roughness: 0.5, metalness: 0.2 }), [0, 0, 0], [0, 0, Math.PI / 2], 56));
      cup.add(cyl(0.22, 0.22, 0.012, std(0x8d9197, { metalness: 0.9, roughness: 0.3 }), [s * 0.105, 0, 0], [0, 0, Math.PI / 2], 56));
      cup.add(torus(0.2, 0.08, std(0x141517, { roughness: 0.95 }), [-s * 0.12, 0, 0], [0, Math.PI / 2, 0]));
      cup.add(tube(V(0, 0.27, 0), V(0, 0.62, 0), 0.03, dark));
      g.add(cup);
    });
    g.rotation.y = 0.5;
    return g;
  },

  bicycle() {
    const g = new T.Group();
    const frame = std(BRAND, { metalness: 0.35, roughness: 0.35 });
    const chrome = std(0xc9cdd2, { metalness: 1, roughness: 0.3 });
    const rubber = std(0x151617, { roughness: 0.95 });
    const R = V(-0.62, 0.35), F = V(0.62, 0.35), B = V(-0.08, 0.3), S = V(-0.25, 0.95), H = V(0.42, 0.92), H2 = V(0.5, 0.68);
    [[B, S], [B, H2], [S, H], [H, H2]].forEach(([a, b]) => g.add(tube(a, b, 0.028, frame)));
    [-0.04, 0.04].forEach((z) => {
      g.add(tube(B.clone().setZ(z), R.clone().setZ(z), 0.016, frame));
      g.add(tube(S.clone().setZ(z), R.clone().setZ(z), 0.016, frame));
      g.add(tube(H2.clone().setZ(z), F.clone().setZ(z), 0.018, frame));
    });
    [R, F].forEach((c) => {
      g.add(torus(0.35, 0.036, rubber, [c.x, c.y, 0]));
      g.add(torus(0.315, 0.013, chrome, [c.x, c.y, 0]));
      g.add(cyl(0.035, 0.035, 0.1, chrome, [c.x, c.y, 0], [Math.PI / 2, 0, 0]));
      for (let i = 0; i < 18; i++) {
        const a = (i / 18) * Math.PI * 2;
        g.add(tube(V(c.x, c.y, i % 2 ? 0.03 : -0.03), V(c.x + Math.cos(a) * 0.31, c.y + Math.sin(a) * 0.31, 0), 0.004, chrome));
      }
    });
    g.add(tube(H, V(0.52, 0.99), 0.022, frame));
    g.add(tube(V(0.52, 0.99, -0.27), V(0.52, 0.99, 0.27), 0.018, chrome));
    [-0.27, 0.27].forEach((z) => g.add(cyl(0.028, 0.028, 0.12, rubber, [0.52, 0.99, z], [Math.PI / 2, 0, 0])));
    g.add(tube(S, V(-0.3, 1.1), 0.02, chrome));
    g.add(mesh(new T.CapsuleGeometry(0.05, 0.22, 6, 16), rubber, [-0.33, 1.12, 0], [0, 0, Math.PI / 2], [1, 1.1, 1.6]));
    g.add(torus(0.1, 0.012, chrome, [B.x, B.y, 0.06]));
    g.add(tube(V(B.x, B.y, 0.08), V(B.x + 0.12, B.y - 0.12, 0.1), 0.012, chrome));
    g.add(tube(V(B.x, B.y, -0.08), V(B.x - 0.12, B.y + 0.12, -0.1), 0.012, chrome));
    g.add(box(0.08, 0.02, 0.06, 0.005, rubber, [B.x + 0.12, B.y - 0.12, 0.14]));
    g.add(box(0.08, 0.02, 0.06, 0.005, rubber, [B.x - 0.12, B.y + 0.12, -0.14]));
    g.rotation.y = -0.6;
    return g;
  },

  helmet() {
    const g = new T.Group();
    const shell = phys(0x2a2f36, { roughness: 0.6, clearcoat: 0.3, clearcoatRoughness: 0.3, envMapIntensity: 0.5 });
    const dome = (r, mat) => mesh(new T.SphereGeometry(r, 56, 36, 0, Math.PI * 2, 0, Math.PI / 2), mat, [0, 0, 0], null, [1, 0.8, 1.25]);
    g.add(dome(0.55, shell));
    const inner = dome(0.535, std(0x0d0e10, { roughness: 0.9, side: T.BackSide })); g.add(inner);
    // Vents: slim dark ellipsoids laid flat on the shell (oriented by its surface normal) and sunk half-way,
    // so they read as recessed slots rather than bumps. Shell radii: x 0.55, y 0.44, z 0.6875.
    const ventMat = std(0x070708, { roughness: 0.9 });
    const slot = (a, b, len) => {
      const u = V(Math.sin(a) * Math.cos(b), Math.cos(a) * Math.cos(b), Math.sin(b));
      const p = V(u.x * 0.55, u.y * 0.44, u.z * 0.6875);
      const n = V(p.x / (0.55 * 0.55), p.y / (0.44 * 0.44), p.z / (0.6875 * 0.6875)).normalize();
      const v = sphere(1, ventMat, [p.x * 0.985, p.y * 0.985, p.z * 0.985], [0.042, 0.012, len]);
      v.quaternion.setFromUnitVectors(V(0, 1, 0), n);
      g.add(v);
    };
    [-0.62, -0.31, 0, 0.31, 0.62].forEach((a) => slot(a, 0.18, 0.17));
    [-0.4, 0, 0.4].forEach((a) => slot(a, -0.42, 0.12));
    g.add(torus(0.55, 0.028, std(BRAND, { roughness: 0.4 }), [0, 0.02, 0], [Math.PI / 2, 0, 0], [1, 1.25, 1]));
    g.add(mesh(new T.CircleGeometry(0.42, 40, Math.PI * 0.15, Math.PI * 0.7), std(0x101113, { roughness: 0.6, side: T.DoubleSide }),
               [0, 0.1, 0.5], [-Math.PI / 2 + 0.35, 0, 0], [1.1, 1, 1]));
    const strap = std(0x1a1a1b, { roughness: 0.9 });
    [-1, 1].forEach((s) => {
      g.add(tube(V(s * 0.44, 0.02, 0.18), V(s * 0.16, -0.42, 0.08), 0.016, strap));
      g.add(tube(V(s * 0.46, 0.02, -0.3), V(s * 0.16, -0.42, 0.08), 0.016, strap));
    });
    g.add(box(0.1, 0.05, 0.06, 0.01, std(0x2a2b2e, { roughness: 0.5 }), [0, -0.44, 0.08]));
    g.rotation.y = 0.7;
    return g;
  },

  sneaker() {
    return shoe({ sole: 0xf0f0ec, mid: 0xfafaf7, upper: 0x3a3e45, collar: 0x1d1f23, lace: 0xececea, height: 0.06, tall: false });
  },

  boot() {
    return shoe({ sole: 0x2f2621, mid: 0x5a3b26, upper: 0x7a4f2d, collar: 0x4b301a, lace: 0x2b1d14, height: 0.09, tall: true });
  },
};

// Sneaker and boot share one footprint; the boot adds a shaft, eyelets and a chunkier sole.
function shoe({ sole, mid, upper, collar, lace, height, tall }) {
  const g = new T.Group();
  const pts = [[-0.5, 0], [-0.46, 0.13], [-0.3, 0.18], [-0.05, 0.17], [0.2, 0.2], [0.42, 0.17], [0.5, 0.05], [0.47, -0.08],
               [0.3, -0.17], [0.05, -0.16], [-0.2, -0.15], [-0.42, -0.13]].map(([x, y]) => new T.Vector2(x, y));
  const shape = new T.Shape(); shape.moveTo(pts[0].x, pts[0].y); shape.splineThru(pts.slice(1).concat([pts[0]]));
  const slab = (depth, mat, y, s = 1) => {
    const geo = new T.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: 0.015, bevelSize: 0.015, bevelSegments: 3, curveSegments: 24 });
    return mesh(geo, mat, [0, y, 0], [-Math.PI / 2, 0, 0], [s, s, 1]);
  };
  g.add(slab(height, std(sole, { roughness: 0.65 }), 0.015));
  g.add(slab(0.03, std(mid, { roughness: 0.6 }), height + 0.01, 0.97));
  const top = height + 0.04;
  const skin = std(upper, { roughness: tall ? 0.5 : 0.85 });
  g.add(mesh(new T.CapsuleGeometry(0.15, 0.5, 8, 24), skin, [-0.04, top + 0.11, 0], [0, 0, Math.PI / 2], [1, 0.9, 1.05]));
  g.add(sphere(0.2, skin, [0.28, top + 0.05, 0], [1.25, 0.62, 0.8]));
  g.add(sphere(0.16, skin, [-0.3, top + 0.14, 0], [0.95, 1.1, 0.9]));
  if (tall) {
    g.add(cyl(0.15, 0.17, 0.5, skin, [-0.2, top + 0.42, 0], [0, 0, 0.06], 40));
    g.add(torus(0.15, 0.03, std(collar, { roughness: 0.8 }), [-0.215, top + 0.67, 0], [Math.PI / 2, 0, 0]));
    const brass = std(0xb98d44, { metalness: 1, roughness: 0.3 });
    for (let i = 0; i < 5; i++) {
      const y = top + 0.3 + i * 0.085, x = -0.1 + i * 0.012;
      [-0.085, 0.085].forEach((z) => g.add(cyl(0.018, 0.018, 0.012, brass, [x + 0.01, y, z], [0, 0, Math.PI / 2], 16)));
      g.add(tube(V(x + 0.02, y, -0.085), V(x + 0.02, y + 0.07, 0.085), 0.008, std(lace, { roughness: 0.9 })));
    }
    g.add(box(0.03, 0.09, 0.05, 0.01, std(collar, { roughness: 0.8 }), [-0.37, top + 0.69, 0]));
  } else {
    g.add(torus(0.13, 0.045, std(collar, { roughness: 0.9 }), [-0.26, top + 0.26, 0], [Math.PI / 2, 0, 0], [1.25, 1, 1]));
    g.add(box(0.26, 0.03, 0.14, 0.01, std(collar, { roughness: 0.8 }), [0.02, top + 0.26, 0], [0, 0, -0.5]));
    for (let i = 0; i < 5; i++) {
      const x = -0.1 + i * 0.075, y = top + 0.27 - i * 0.04;
      g.add(tube(V(x, y, -0.075), V(x + 0.02, y, 0.075), 0.009, std(lace, { roughness: 0.9 })));
    }
    g.add(box(0.5, 0.028, 0.012, 0.004, std(BRAND, { roughness: 0.5 }), [-0.06, top + 0.1, 0.19], [0, 0, 0.1]));
    g.add(box(0.5, 0.028, 0.012, 0.004, std(BRAND, { roughness: 0.5 }), [-0.06, top + 0.1, -0.19], [0, 0, 0.1]));
    g.add(box(0.04, 0.08, 0.06, 0.01, std(collar, { roughness: 0.8 }), [-0.42, top + 0.22, 0]));
  }
  g.rotation.y = -0.75;
  return g;
}

// ---------- scene ----------
function start(root) {
  const canvas = root.querySelector("canvas");
  const stage = root.querySelector(".stage");
  let renderer;
  try {
    renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  } catch {
    root.classList.add("no-webgl");
    return null;
  }
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = T.PCFShadowMap;
  renderer.toneMapping = T.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new T.Scene();
  scene.environment = new T.PMREMGenerator(renderer).fromScene(new T.RoomEnvironment(), 0.04).texture;

  const camera = new T.PerspectiveCamera(30, 1, 0.1, 60);
  camera.position.set(2.9, 1.5, 3.6);

  const key = new T.SpotLight(0xfff1e0, 75, 0, 0.55, 0.7, 1.6);
  key.position.set(3, 5.5, 2.5); key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.radius = 4;
  const rim = new T.DirectionalLight(0xcfe3ff, 2.2); rim.position.set(-4, 3, -3);
  const warm = new T.PointLight(BRAND, 9, 8, 2); warm.position.set(-2.4, 0.5, 2.2);
  scene.add(key, rim, warm, new T.HemisphereLight(0xffffff, 0x101010, 0.25));

  // No visible floor: the item floats on the stage's dark gradient (CSS) and only its contact shadow is drawn,
  // the way the product shots this is modelled on sit their items on black.
  const shadow = new T.Mesh(new T.CircleGeometry(2.6, 80), new T.ShadowMaterial({ opacity: 0.55 }));
  shadow.rotation.x = -Math.PI / 2; shadow.receiveShadow = true; scene.add(shadow);

  const controls = new T.OrbitControls(camera, canvas);
  controls.target.set(0, 0.62, 0);
  controls.enableDamping = true; controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 2.2; controls.maxDistance = 7.5;
  controls.maxPolarAngle = 1.5; controls.minPolarAngle = 0.35;
  const stillMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  controls.autoRotate = !stillMotion; controls.autoRotateSpeed = 0.9;
  let idleTimer = null;
  controls.addEventListener("start", () => { controls.autoRotate = false; clearTimeout(idleTimer); root.classList.add("touched"); });
  controls.addEventListener("end", () => { if (!stillMotion) idleTimer = setTimeout(() => { controls.autoRotate = true; }, 4000); });

  // Models are built on demand and cached. A .glb listed in models/manifest.json replaces the procedural one.
  const cache = new Map();
  let manifest = null;
  const manifestReady = fetch("models/manifest.json").then((r) => (r.ok ? r.json() : {})).catch(() => ({})).then((m) => { manifest = m || {}; });
  async function model(slug) {
    if (cache.has(slug)) return cache.get(slug);
    await manifestReady;
    let g = null;
    if (manifest[slug]) {
      g = await new Promise((res) => new T.GLTFLoader().load(`models/${manifest[slug]}`, (gltf) => res(gltf.scene), undefined, () => res(null)));
      if (g) g.traverse((o) => { if (o.isMesh) o.castShadow = o.receiveShadow = true; });
    }
    if (!g) g = BUILD[slug]();
    const wrap = new T.Group(); wrap.add(fit(g, ITEMS.find((x) => x.slug === slug).size || 1.65));
    cache.set(slug, wrap);
    return wrap;
  }

  // Switching items: the old one yaws away and shrinks, the new one rises, turns in and settles (eased).
  let current = null, entering = null, leaving = null, seq = 0;
  const easeOut = (p) => 1 - Math.pow(1 - p, 3);
  async function show(slug) {
    const my = ++seq;
    const next = await model(slug);
    if (my !== seq || next === current) return;
    if (current) { leaving = current; leaving.userData.t = 0; }
    current = next; entering = next; entering.userData.t = 0;
    next.scale.setScalar(0.001); next.rotation.y = 1.4; next.position.y = 0.45;
    scene.add(next);
  }
  // Page scroll nudges the item round a little (damped), so the stage feels alive while the page moves.
  let yawTarget = 0, yaw = 0, lastScroll = window.scrollY;
  window.addEventListener("scroll", () => { yawTarget += (window.scrollY - lastScroll) * 0.0022; lastScroll = window.scrollY; }, { passive: true });

  function resize() {
    const w = stage.clientWidth, h = stage.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  }
  new ResizeObserver(resize).observe(stage);
  resize();

  let visible = true;
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0.05 }).observe(root);

  const timer = new T.Timer();
  function frame() {
    requestAnimationFrame(frame);
    if (!visible || document.hidden) return;
    timer.update();
    const dt = Math.min(timer.getDelta(), 0.05);
    if (leaving) {
      const p = (leaving.userData.t = Math.min(1, leaving.userData.t + dt / 0.4)), e = easeOut(p);
      leaving.scale.setScalar(Math.max(0.001, 1 - e)); leaving.rotation.y = -1.2 * e; leaving.position.y = -0.2 * e;
      if (p >= 1) { scene.remove(leaving); leaving.rotation.y = 0; leaving.position.y = 0; leaving = null; }
    }
    if (entering) {
      const p = (entering.userData.t = Math.min(1, entering.userData.t + dt / 0.85)), e = easeOut(p);
      entering.scale.setScalar(Math.max(0.001, e)); entering.rotation.y = 1.4 * (1 - e); entering.position.y = 0.45 * (1 - e);
      if (p >= 1) { entering.scale.setScalar(1); entering.rotation.y = 0; entering.position.y = 0; entering = null; }
    }
    yaw += (yawTarget - yaw) * Math.min(1, dt * 4);
    if (current && !entering) current.rotation.y = yaw;
    controls.update();
    renderer.render(scene, camera);
  }
  frame();
  return { show };
}

// ---------- page wiring ----------
function setup() {
  const root = document.getElementById("showcase");
  if (!root) return;
  const rail = root.querySelector(".rail");
  const out = (id) => root.querySelector(`#sc-${id}`);
  const kgOrG = (g) => (g >= 1000 ? `${(g / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })} kg` : `${g} g`);
  const view = start(root);
  let packages = null;
  let active = null;

  const buttons = ITEMS.map((it, i) => {
    const b = el("button", { type: "button", class: "item", "data-slug": it.slug, "aria-pressed": "false" },
                 el("span", { class: "idx" }, String(i + 1).padStart(2, "0")), el("span", { class: "nm" }, it.name));
    b.addEventListener("click", () => pick(it.slug));
    return b;
  });
  rail.replaceChildren(...buttons);
  rail.addEventListener("keydown", (e) => {
    const i = ITEMS.findIndex((it) => it.slug === active);
    if (e.key === "ArrowDown" || e.key === "ArrowRight") { pick(ITEMS[(i + 1) % ITEMS.length].slug); buttons[(i + 1) % ITEMS.length].focus(); e.preventDefault(); }
    if (e.key === "ArrowUp" || e.key === "ArrowLeft") { pick(ITEMS[(i - 1 + ITEMS.length) % ITEMS.length].slug); buttons[(i - 1 + ITEMS.length) % ITEMS.length].focus(); e.preventDefault(); }
  });

  // Numerals count up to their value when the item changes (skipped when the visitor prefers reduced motion).
  const stillMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const counters = new Map();
  function countTo(node, value, fmt) {
    cancelAnimationFrame(counters.get(node));
    if (stillMotion) { node.textContent = fmt(value); return; }
    const t0 = performance.now(), ms = 700;
    const step = (now) => {
      const p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3);
      node.textContent = fmt(value * e);
      if (p < 1) counters.set(node, requestAnimationFrame(step));
    };
    counters.set(node, requestAnimationFrame(step));
  }
  const specs = root.querySelector(".specs");
  const stage = root.querySelector(".stage");
  // The ghost word drifts against the pointer, a little parallax behind the model.
  stage.addEventListener("pointermove", (e) => {
    const r = stage.getBoundingClientRect();
    const dx = ((e.clientX - r.left) / r.width - 0.5) * -36, dy = ((e.clientY - r.top) / r.height - 0.5) * -14;
    out("ghost").style.transform = `translate(calc(-50% + ${dx.toFixed(1)}px), calc(-50% + ${dy.toFixed(1)}px))`;
  }, { passive: true });
  stage.addEventListener("pointerleave", () => { out("ghost").style.transform = ""; });

  function pick(slug) {
    const it = ITEMS.find((x) => x.slug === slug);
    if (!it || slug === active) return;
    active = slug;
    buttons.forEach((b) => b.setAttribute("aria-pressed", b.dataset.slug === slug ? "true" : "false"));
    specs.classList.remove("swap"); void specs.offsetWidth; specs.classList.add("swap");   // restart the slide-up
    out("ghost").textContent = it.ghost || it.name.split(" ").pop();
    out("name").textContent = it.name;
    countTo(out("weight"), it.weight_g, (g) => kgOrG(Math.round(g)));
    countTo(out("price"), it.price_usd, (p) => money(Math.round(p)));
    out("check").textContent = it.check;
    out("signal").textContent = it.signal;
    out("idx").textContent = `${String(ITEMS.indexOf(it) + 1).padStart(2, "0")} / ${String(ITEMS.length).padStart(2, "0")}`;
    renderLive(it);
    if (view) view.show(slug);
  }

  // Live counts for the item from this station's packages (needs the station key; silent without it).
  function renderLive(it) {
    const node = out("live");
    if (!packages) { node.textContent = ""; node.classList.add("hidden"); return; }
    const rows = packages.filter((p) => it.match.test(String(p.product || "").toLowerCase()));
    const checked = rows.filter((p) => p.return);
    if (!rows.length) { node.textContent = "Demo item: not in this station's catalogue yet."; node.classList.remove("hidden"); return; }
    const held = checked.filter((p) => p.held).length;
    const green = checked.filter((p) => p.return && p.return.decision === "GREEN").length;
    node.replaceChildren(
      el("b", {}, String(checked.length)), ` checked here · `, el("b", {}, String(green)), ` instant refunds · `,
      el("b", { class: held ? "warn" : "" }, String(held)), ` held`);
    node.classList.remove("hidden");
  }
  async function loadLive() {
    if (!store.get("boomerang_key")) return;
    try {
      const pk = await api("/packages?status=all&limit=1000", { staff: true });
      packages = pk.packages || [];
      const it = ITEMS.find((x) => x.slug === active);
      if (it) renderLive(it);
    } catch { /* no key yet, or server away: the specs still show */ }
  }
  loadLive();
  setInterval(loadLive, 15000);
  document.getElementById("connect")?.addEventListener("click", () => setTimeout(loadLive, 300));

  pick(ITEMS[0].slug);
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setup); else setup();
