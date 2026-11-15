# 3D models for the dashboard showcase

The showcase draws every item procedurally (no files needed). A `.glb` listed in `manifest.json` replaces the
procedural one for that slug, for example:

    { "sneaker": "sneaker.glb", "laptop": "laptop.glb" }

Slugs: smartphone, laptop, speaker, headphones, bicycle, helmet, sneaker, boot. Models are auto-scaled and
placed on the floor. Only ship models you have the rights to, and credit them here.

## Shipped models

- `sneaker.glb` — "Materials Variants Shoe", © 2021 Shopify, licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), from the Khronos
  [glTF-Sample-Assets](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/MaterialsVariantsShoe).
  Modified: reduced to one material variant, textures resized to 1024 px and converted to WebP, meshes quantized
  (7.8 MB → 0.7 MB) with gltf-transform.
