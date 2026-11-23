---
name: threejs-textures
allowed-tools: Read, Glob
description: Three.js textures - texture types, UV mapping, environment maps, texture settings. Use when working with images, UV coordinates, cubemaps, HDR environments, or texture optimization.
metadata:
  triggers: three.js texture, UV mapping, cubemap, environment map, HDR texture, texture optimization
---

# Three.js Textures

## Iron Law

**Always set texture.colorSpace = THREE.SRGBColorSpace for albedo/color maps — omitting this causes washed-out colors in physically-based rendering.**

## Quick Start

```javascript
import * as THREE from "three";

// Load texture
const loader = new THREE.TextureLoader();
const texture = loader.load("texture.jpg");

// Apply to material
const material = new THREE.MeshStandardMaterial({
  map: texture,
});
```

## Texture Loading

### Basic Loading

```javascript
const loader = new THREE.TextureLoader();

// Async with callbacks
loader.load(
  "texture.jpg",
  (texture) => console.log("Loaded"),
  (progress) => console.log("Progress"),
  (error) => console.error("Error"),
);

// Synchronous style (loads async internally)
const texture = loader.load("texture.jpg");
material.map = texture;
```

### Promise Wrapper

```javascript
function loadTexture(url) {
  return new Promise((resolve, reject) => {
    new THREE.TextureLoader().load(url, resolve, undefined, reject);
  });
}

// Usage
const [colorMap, normalMap, roughnessMap] = await Promise.all([
  loadTexture("color.jpg"),
  loadTexture("normal.jpg"),
  loadTexture("roughness.jpg"),
]);
```

## Texture Configuration

### Color Space

Critical for accurate color reproduction.

```javascript
// Color/albedo textures - use sRGB
colorTexture.colorSpace = THREE.SRGBColorSpace;

// Data textures (normal, roughness, metalness, AO) - leave as default
// Do NOT set colorSpace for data textures (NoColorSpace is default)
```

### Wrapping Modes

```javascript
texture.wrapS = THREE.RepeatWrapping; // Horizontal
texture.wrapT = THREE.RepeatWrapping; // Vertical

// Options:
// THREE.ClampToEdgeWrapping - Stretches edge pixels (default)
// THREE.RepeatWrapping - Tiles the texture
// THREE.MirroredRepeatWrapping - Tiles with mirror flip
```

### Repeat, Offset, Rotation

```javascript
// Tile texture 4x4
texture.repeat.set(4, 4);
texture.wrapS = THREE.RepeatWrapping;
texture.wrapT = THREE.RepeatWrapping;

// Offset (0-1 range)
texture.offset.set(0.5, 0.5);

// Rotation (radians, around center)
texture.rotation = Math.PI / 4;
texture.center.set(0.5, 0.5); // Rotation pivot
```

### Filtering

```javascript
// Minification (texture larger than screen pixels)
texture.minFilter = THREE.LinearMipmapLinearFilter; // Default, smooth
texture.minFilter = THREE.NearestFilter; // Pixelated
texture.minFilter = THREE.LinearFilter; // Smooth, no mipmaps

// Magnification (texture smaller than screen pixels)
texture.magFilter = THREE.LinearFilter; // Smooth (default)
texture.magFilter = THREE.NearestFilter; // Pixelated (retro games)

// Anisotropic filtering (sharper at angles)
texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
```

### Generate Mipmaps

```javascript
// Usually true by default
texture.generateMipmaps = true;

// Disable for non-power-of-2 textures or data textures
texture.generateMipmaps = false;
texture.minFilter = THREE.LinearFilter;
```

## Texture Types

### Texture Type Quick Reference

| Type | Class | When to Use |
|------|-------|-------------|
| Image file | `TextureLoader` | JPG, PNG, WebP — most textures |
| Raw pixel data | `DataTexture` | Procedural/computed textures |
| HTML Canvas | `CanvasTexture` | Dynamic labels, HUD, sprite sheets |
| Video | `VideoTexture` | Playing video on a mesh (auto-updates) |
| Compressed | `KTX2Loader` | Production, mobile — smallest file size |

> Detailed examples for DataTexture, CanvasTexture, VideoTexture, KTX2 → `references/advanced-textures.md`

## Cube Textures

For environment maps and skyboxes.

### CubeTextureLoader

```javascript
const loader = new THREE.CubeTextureLoader();
const cubeTexture = loader.load([
  "px.jpg",
  "nx.jpg", // +X, -X
  "py.jpg",
  "ny.jpg", // +Y, -Y
  "pz.jpg",
  "nz.jpg", // +Z, -Z
]);

// As background
scene.background = cubeTexture;

// As environment map
scene.environment = cubeTexture;
material.envMap = cubeTexture;
```

### Equirectangular to Cubemap

```javascript
import { RGBELoader } from "three/examples/jsm/loaders/RGBELoader.js";

const pmremGenerator = new THREE.PMREMGenerator(renderer);
pmremGenerator.compileEquirectangularShader();

new RGBELoader().load("environment.hdr", (texture) => {
  const envMap = pmremGenerator.fromEquirectangular(texture).texture;
  scene.environment = envMap;
  scene.background = envMap;

  texture.dispose();
  pmremGenerator.dispose();
});
```

## HDR Textures

### RGBELoader

```javascript
import { RGBELoader } from "three/examples/jsm/loaders/RGBELoader.js";

const loader = new RGBELoader();
loader.load("environment.hdr", (texture) => {
  texture.mapping = THREE.EquirectangularReflectionMapping;
  scene.environment = texture;
  scene.background = texture;
});
```

### EXRLoader

```javascript
import { EXRLoader } from "three/examples/jsm/loaders/EXRLoader.js";

const loader = new EXRLoader();
loader.load("environment.exr", (texture) => {
  texture.mapping = THREE.EquirectangularReflectionMapping;
  scene.environment = texture;
});
```

### Background Options

```javascript
scene.background = texture;
scene.backgroundBlurriness = 0.5; // 0-1, blur background
scene.backgroundIntensity = 1.0; // Brightness
scene.backgroundRotation.y = Math.PI; // Rotate background
```

## Material Texture Maps

### PBR Texture Set

```javascript
const material = new THREE.MeshStandardMaterial({
  // Base color (sRGB)
  map: colorTexture,

  // Surface detail (Linear)
  normalMap: normalTexture,
  normalScale: new THREE.Vector2(1, 1),

  // Roughness (Linear, grayscale)
  roughnessMap: roughnessTexture,
  roughness: 1, // Multiplier

  // Metalness (Linear, grayscale)
  metalnessMap: metalnessTexture,
  metalness: 1, // Multiplier

  // Ambient occlusion (Linear, uses uv2)
  aoMap: aoTexture,
  aoMapIntensity: 1,

  // Self-illumination (sRGB)
  emissiveMap: emissiveTexture,
  emissive: 0xffffff,
  emissiveIntensity: 1,

  // Vertex displacement (Linear)
  displacementMap: displacementTexture,
  displacementScale: 0.1,
  displacementBias: 0,

  // Alpha (Linear)
  alphaMap: alphaTexture,
  transparent: true,
});

// Don't forget UV2 for AO
geometry.setAttribute("uv2", geometry.attributes.uv);
```

### Normal Map Types

```javascript
// OpenGL style normals (default)
material.normalMapType = THREE.TangentSpaceNormalMap;

// Object space normals
material.normalMapType = THREE.ObjectSpaceNormalMap;
```

## Performance Tips

1. **Use power-of-2 dimensions**: 256, 512, 1024, 2048
2. **Compress textures**: KTX2/Basis for web delivery
3. **Use texture atlases**: Reduce texture switches
4. **Enable mipmaps**: For distant objects
5. **Limit texture size**: 2048 usually sufficient for web
6. **Reuse textures**: Same texture = better batching

```javascript
// Check texture memory
console.log(renderer.info.memory.textures);

// Optimize for mobile
const maxSize = renderer.capabilities.maxTextureSize;
const isMobile = /iPhone|iPad|Android/i.test(navigator.userAgent);
const textureSize = isMobile ? 1024 : 2048;
```

## References

- `references/advanced-textures.md` — DataTexture, CanvasTexture, VideoTexture, KTX2 compressed, render targets, CubeCamera, UV mapping, texture atlas, procedural textures, and memory management

## See Also

- `threejs-materials` - Applying textures to materials
- `threejs-loaders` - Loading texture files
- `threejs-shaders` - Custom texture sampling
