---
name: three-dart-geometry
allowed-tools: Read, Glob
description: three_dart geometry — BoxGeometry, SphereGeometry, BufferGeometry, custom geometry, instancing in Flutter. Use when creating 3D shapes, building custom meshes, or using instanced rendering in a Flutter three_dart scene.
metadata:
  triggers: three_dart geometry, BoxGeometry Flutter, BufferGeometry Flutter, custom mesh Flutter, instancing Flutter
---

# three_dart Geometry

## Iron Law

**Always call geometry.computeVertexNormals() after building custom BufferGeometry — without normals, MeshStandardMaterial renders as flat black.**

## Built-in Geometries

```dart
import 'package:three_dart/three_dart.dart' as THREE;

// Box
final box = THREE.BoxGeometry(1, 1, 1);                        // width, height, depth
final boxSeg = THREE.BoxGeometry(2, 2, 2, 4, 4, 4);           // with segments

// Sphere
final sphere = THREE.SphereGeometry(1, 32, 16);               // radius, widthSeg, heightSeg

// Cylinder
final cylinder = THREE.CylinderGeometry(0.5, 0.5, 2, 32);    // radiusTop, radiusBottom, height, segments

// Plane
final plane = THREE.PlaneGeometry(5, 5, 10, 10);              // width, height, wSeg, hSeg

// Torus
final torus = THREE.TorusGeometry(1, 0.4, 16, 100);           // radius, tube, radSeg, tubeSeg

// Circle
final circle = THREE.CircleGeometry(1, 32);

// Cone
final cone = THREE.ConeGeometry(0.5, 2, 32);
```

## BufferGeometry — Custom Mesh

```dart
final geometry = THREE.BufferGeometry();

// Vertices (Float32Array equivalent)
final vertices = THREE.Float32Array.fromList([
  -1.0, -1.0, 0.0,  // vertex 0
   1.0, -1.0, 0.0,  // vertex 1
   0.0,  1.0, 0.0,  // vertex 2
]);

// Normals
final normals = THREE.Float32Array.fromList([
  0, 0, 1,
  0, 0, 1,
  0, 0, 1,
]);

// UVs
final uvs = THREE.Float32Array.fromList([
  0, 0,
  1, 0,
  0.5, 1,
]);

geometry.setAttribute('position', THREE.BufferAttribute(vertices, 3));
geometry.setAttribute('normal',   THREE.BufferAttribute(normals, 3));
geometry.setAttribute('uv',       THREE.BufferAttribute(uvs, 2));

// Indexed geometry
final indices = THREE.Uint16Array.fromList([0, 1, 2]);
geometry.setIndex(THREE.BufferAttribute(indices, 1));

geometry.computeVertexNormals();
```

## Geometry Utilities

```dart
// Bounding box/sphere
geometry.computeBoundingBox();
geometry.computeBoundingSphere();
final box3 = geometry.boundingBox!;

// Center geometry at origin
geometry.center();

// Merge geometries
final merged = THREE.BufferGeometryUtils.mergeBufferGeometries([geo1, geo2]);

// Clone
final clone = geometry.clone();
```

## InstancedMesh — Batch Rendering

Use for many identical objects (trees, particles, crowds). Single draw call.

```dart
final geometry = THREE.SphereGeometry(0.1, 8, 8);
final material = THREE.MeshStandardMaterial({'color': 0xffffff});
final count = 1000;

final instancedMesh = THREE.InstancedMesh(geometry, material, count);

final matrix = THREE.Matrix4();
final position = THREE.Vector3();
final quaternion = THREE.Quaternion();
final scale = THREE.Vector3(1, 1, 1);

for (int i = 0; i < count; i++) {
  position.set(
    (math.Random().nextDouble() - 0.5) * 20,
    (math.Random().nextDouble() - 0.5) * 20,
    (math.Random().nextDouble() - 0.5) * 20,
  );
  matrix.compose(position, quaternion, scale);
  instancedMesh.setMatrixAt(i, matrix);
}
instancedMesh.instanceMatrix.needsUpdate = true;
scene.add(instancedMesh);
```

## See Also

- `three-dart-fundamentals` — scene setup and renderer
- `three-dart-materials` — apply materials to geometry
