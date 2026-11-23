---
name: three-dart-materials
allowed-tools: Read, Glob
description: three_dart materials — MeshStandardMaterial, MeshBasicMaterial, MeshPhongMaterial, ShaderMaterial, transparency, wireframe in Flutter. Use when applying materials to 3D objects in Flutter three_dart scenes.
metadata:
  triggers: three_dart material, MeshStandardMaterial Flutter, ShaderMaterial Flutter, transparency Flutter 3D, wireframe Flutter
---

# three_dart Materials

## Iron Law

**Always set material.needsUpdate = true after changing maps or transparency at runtime — three_dart caches the compiled shader program and will not recompile without it.**

## Material Types

```dart
import 'package:three_dart/three_dart.dart' as THREE;

// PBR — use for realistic rendering (recommended default)
final standard = THREE.MeshStandardMaterial({
  'color': 0xff6600,
  'roughness': 0.5,    // 0 = mirror, 1 = fully rough
  'metalness': 0.0,    // 0 = non-metal, 1 = metallic
});

// Physical — extends Standard with more PBR controls
final physical = THREE.MeshPhysicalMaterial({
  'color': 0xffffff,
  'roughness': 0.2,
  'metalness': 0.8,
  'clearcoat': 1.0,       // car paint effect
  'clearcoatRoughness': 0.1,
});

// Phong — cheaper, good for low-end mobile
final phong = THREE.MeshPhongMaterial({
  'color': 0x00ff00,
  'shininess': 100,
  'specular': THREE.Color(0x111111),
});

// Basic — unlit, no lighting calculations
final basic = THREE.MeshBasicMaterial({'color': 0xffffff});

// Lambert — diffuse only, no specular
final lambert = THREE.MeshLambertMaterial({'color': 0x888888});

// Toon — cel-shaded
final toon = THREE.MeshToonMaterial({'color': 0xff0000});

// Wireframe
final wireframe = THREE.MeshBasicMaterial({
  'color': 0x00ff00,
  'wireframe': true,
});
```

## Transparency

```dart
final transparent = THREE.MeshStandardMaterial({
  'color': 0x0088ff,
  'transparent': true,
  'opacity': 0.5,
  // Side: FrontSide, BackSide, DoubleSide
  'side': THREE.DoubleSide,
});
```

## Textures with Materials

```dart
final loader = THREE.TextureLoader();
loader.load('assets/textures/brick.jpg', (texture) {
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(4, 4);

  final material = THREE.MeshStandardMaterial({
    'map': texture,             // albedo / color map
    'roughnessMap': roughTex,   // roughness from texture
    'normalMap': normalTex,     // normal map for surface detail
    'aoMap': aoTex,             // ambient occlusion
  });
});
```

## ShaderMaterial

```dart
final shader = THREE.ShaderMaterial({
  'uniforms': {
    'time': {'value': 0.0},
    'color': {'value': THREE.Color(0xff0000)},
  },
  'vertexShader': '''
    void main() {
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  ''',
  'fragmentShader': '''
    uniform vec3 color;
    void main() {
      gl_FragColor = vec4(color, 1.0);
    }
  ''',
});

// Update uniform in animate callback
shader.uniforms['time']['value'] = elapsedTime;
```

## Material Updates

```dart
// After changing material properties at runtime
material.color = THREE.Color(0xff0000);
material.needsUpdate = true;  // required when changing maps or transparency
```

## See Also

- `three-dart-fundamentals` — attaching materials to meshes
- `three-dart-geometry` — geometry to pair with materials
