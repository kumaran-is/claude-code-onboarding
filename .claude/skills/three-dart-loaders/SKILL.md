---
name: three-dart-loaders
allowed-tools: Read, Glob
description: three_dart loaders — GLTFLoader, loading GLTF/GLB models, textures, async patterns, Flutter asset loading. Use when loading 3D models, textures, or external assets into a Flutter three_dart scene.
metadata:
  triggers: three_dart loader, GLTFLoader Flutter, load GLB Flutter, load 3D model Flutter, texture loading Flutter
---

# three_dart Loaders

## Iron Law

**Always provide an error callback in every loader.load() call and surface it to the UI — silent load failures are the number one cause of blank 3D screens in Flutter.**

## GLTFLoader — Load GLTF/GLB Models

```dart
import 'package:three_dart/three_dart.dart' as THREE;
import 'package:three_dart_jsm/three_dart_jsm/loaders/GLTFLoader.dart';

final loader = GLTFLoader(null);

// Load from Flutter assets
loader.load(
  'assets/models/character.glb',
  (gltf) {
    final model = gltf['scene'] as THREE.Group;
    scene.add(model);

    // Access animations
    final clips = gltf['animations'] as List<THREE.AnimationClip>;
    if (clips.isNotEmpty) {
      final mixer = THREE.AnimationMixer(model);
      mixer.clipAction(clips[0]).play();
    }
  },
  (progress) {
    final percent = (progress['loaded'] / progress['total'] * 100).toStringAsFixed(0);
    debugPrint('Loading: $percent%');
  },
  (error) {
    debugPrint('GLTF load error: $error');
    // Never swallow — show error state to user
  },
);
```

## pubspec.yaml Asset Registration

```yaml
flutter:
  assets:
    - assets/models/
    - assets/textures/
```

## TextureLoader

```dart
final loader = THREE.TextureLoader(null);

loader.load(
  'assets/textures/wood.jpg',
  (texture) {
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(2, 2);

    material.map = texture;
    material.needsUpdate = true;
  },
  null,
  (error) => debugPrint('Texture load error: $error'),
);
```

## Loading Manager — Track Multiple Assets

```dart
final manager = THREE.LoadingManager(
  onLoad: () => debugPrint('All assets loaded'),
  onProgress: (url, loaded, total) =>
    debugPrint('$loaded/$total — $url'),
  onError: (url) => debugPrint('Failed: $url'),
);

final gltfLoader = GLTFLoader(manager);
final texLoader = THREE.TextureLoader(manager);
// Both report to the same manager
```

## Async Pattern (with Completer)

```dart
Future<THREE.Group> loadModel(String path) {
  final completer = Completer<THREE.Group>();
  final loader = GLTFLoader(null);

  loader.load(
    path,
    (gltf) => completer.complete(gltf['scene'] as THREE.Group),
    null,
    (error) => completer.completeError(Exception('Load failed: $error')),
  );

  return completer.future;
}

// Usage
final model = await loadModel('assets/models/building.glb');
scene.add(model);
```

## Draco Compressed Models

```dart
import 'package:three_dart_jsm/three_dart_jsm/loaders/DRACOLoader.dart';

final dracoLoader = DRACOLoader(null);
dracoLoader.setDecoderPath('assets/draco/');  // copy draco WASM to assets

final gltfLoader = GLTFLoader(null);
gltfLoader.setDRACOLoader(dracoLoader);
```

## Performance Tips

- Prefer `.glb` (binary) over `.gltf` + separate files — single asset, faster load
- Use Draco compression for meshes > 100k triangles — 10x size reduction
- Reuse materials and geometries across instances — don't create duplicates
- Dispose unused textures: `texture.dispose()` when switching scenes

## See Also

- `three-dart-animation` — playing AnimationClips from loaded GLTF
- `three-dart-fundamentals` — adding loaded models to scene
