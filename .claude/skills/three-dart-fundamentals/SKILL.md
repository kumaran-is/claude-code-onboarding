---
name: three-dart-fundamentals
allowed-tools: Read, Glob
description: three_dart scene setup, WebGL renderer in Flutter, Scene, PerspectiveCamera, WebGLRenderer, Object3D hierarchy, animation loop. Use when setting up 3D scenes in Flutter with three_dart, creating cameras, configuring renderers, or managing 3D object transforms in a Flutter app.
metadata:
  triggers: three_dart, Flutter 3D scene, three_dart renderer, PerspectiveCamera Flutter, Object3D Flutter
---

# three_dart Fundamentals

## Iron Law

**Always call renderer.dispose() in the widget dispose() method — failing to do so leaks the WebGL context, causing a crash after ~8 widget recreations on mobile.**

Flutter uses the `three_dart` package — a Dart port of Three.js. API concepts are identical
to Three.js; only syntax changes (Dart instead of JavaScript).

## pubspec.yaml

```yaml
dependencies:
  three_dart: ^0.0.15
  flutter_gl: ^0.0.10  # required — OpenGL bindings
```

## Quick Start

```dart
import 'package:flutter/material.dart';
import 'package:three_dart/three_dart.dart' as THREE;
import 'package:three_dart_jsm/three_dart_jsm.dart' as THREE_JSM;

class ThreeDScene extends StatefulWidget {
  const ThreeDScene({super.key});
  @override
  State<ThreeDScene> createState() => _ThreeDSceneState();
}

class _ThreeDSceneState extends State<ThreeDScene> {
  late THREE.WebGLRenderer renderer;
  late THREE.Scene scene;
  late THREE.PerspectiveCamera camera;
  late THREE.Mesh cube;

  @override
  void initState() {
    super.initState();
    _initScene();
  }

  void _initScene() {
    scene = THREE.Scene();

    camera = THREE.PerspectiveCamera(75, 1.0, 0.1, 1000);
    camera.position.z = 5;

    final geometry = THREE.BoxGeometry(1, 1, 1);
    final material = THREE.MeshStandardMaterial({'color': 0x00ff00});
    cube = THREE.Mesh(geometry, material);
    scene.add(cube);

    scene.add(THREE.AmbientLight(0xffffff, 0.5));
    final dirLight = THREE.DirectionalLight(0xffffff, 1.0);
    dirLight.position.set(5, 5, 5);
    scene.add(dirLight);
  }

  void _animate(double delta) {
    cube.rotation.x += 0.01;
    cube.rotation.y += 0.01;
    renderer.render(scene, camera);
  }

  @override
  Widget build(BuildContext context) {
    return THREE_JSM.ThreeDartWidget(
      onSetupRenderer: (r) => renderer = r,
      onAnimate: _animate,
      scene: scene,
      camera: camera,
    );
  }

  @override
  void dispose() {
    renderer.dispose();
    super.dispose();
  }
}
```

## Core Classes

### Scene
```dart
final scene = THREE.Scene();
scene.background = THREE.Color(0x222222);
scene.fog = THREE.Fog(0x222222, 10, 100);
```

### PerspectiveCamera
```dart
// PerspectiveCamera(fov, aspect, near, far)
final camera = THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
camera.position.set(0, 2, 5);
camera.lookAt(THREE.Vector3(0, 0, 0));
```

### WebGLRenderer
```dart
// Renderer is created by ThreeDartWidget — configure via onSetupRenderer
void onSetupRenderer(THREE.WebGLRenderer r) {
  renderer = r;
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
}
```

## Object3D Hierarchy

```dart
final group = THREE.Group();
group.add(mesh1);
group.add(mesh2);
scene.add(group);

// Transforms
mesh.position.set(1, 2, 3);
mesh.rotation.y = math.pi / 4;
mesh.scale.setScalar(2.0);
```

## Key Difference from JS Three.js

| JavaScript Three.js | Dart three_dart |
|---------------------|-----------------|
| `new THREE.Scene()` | `THREE.Scene()` |
| `material.color.set(0xff0000)` | `material.color = THREE.Color(0xff0000)` |
| `import * as THREE from 'three'` | `import 'package:three_dart/three_dart.dart' as THREE` |
| `requestAnimationFrame` loop | `onAnimate` callback via `ThreeDartWidget` |
| `window.innerWidth` | Flutter widget `constraints.maxWidth` |

## See Also

- `three-dart-geometry` — geometry types and custom meshes
- `three-dart-materials` — PBR and standard materials
- `three-dart-animation` — AnimationMixer, keyframe clips
- `three-dart-loaders` — GLTF/GLB model loading
