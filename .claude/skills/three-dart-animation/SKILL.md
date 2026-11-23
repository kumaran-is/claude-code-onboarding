---
name: three-dart-animation
allowed-tools: Read, Glob
description: three_dart animation — AnimationMixer, AnimationClip, AnimationAction, keyframe tracks, procedural animation in Flutter. Use when animating 3D objects, playing GLTF animations, or blending animations in a Flutter three_dart scene.
metadata:
  triggers: three_dart animation, AnimationMixer, AnimationClip, GLTF animation Flutter, blend animations Flutter 3D
---

# three_dart Animation

## Iron Law

**Always call mixer.update(delta) inside the onAnimate callback — the AnimationMixer does not advance on its own, even when actions are playing.**

## Procedural Animation (Simple)

```dart
// In onAnimate callback — delta is seconds since last frame
void onAnimate(double delta) {
  mesh.rotation.y += delta;
  mesh.position.y = math.sin(clock.getElapsedTime()) * 0.5;
  renderer.render(scene, camera);
}
```

## AnimationMixer (Keyframe / GLTF Animations)

```dart
late THREE.AnimationMixer mixer;

// After loading a GLTF model (see three-dart-loaders):
void setupAnimations(THREE.Object3D model, List<THREE.AnimationClip> clips) {
  mixer = THREE.AnimationMixer(model);

  // Play first clip
  final action = mixer.clipAction(clips[0]);
  action.play();
}

// In onAnimate — MUST update mixer each frame
void onAnimate(double delta) {
  mixer.update(delta);
  renderer.render(scene, camera);
}
```

## AnimationAction Controls

```dart
final action = mixer.clipAction(clip);

action.play();
action.stop();
action.pause();
action.reset();

// Looping
action.setLoop(THREE.LoopRepeat, double.infinity);   // loop forever
action.setLoop(THREE.LoopOnce, 1);                   // play once then stop
action.clampWhenFinished = true;                     // hold last frame

// Speed / weight
action.timeScale = 2.0;     // 2x speed
action.weight = 0.5;        // blend weight (0–1)
```

## Crossfade Between Animations

```dart
void crossFadeTo(THREE.AnimationAction from, THREE.AnimationAction to, double duration) {
  to.reset();
  to.play();
  from.crossFadeTo(to, duration, false);
}

// Example: walk → run over 0.3 seconds
crossFadeTo(walkAction, runAction, 0.3);
```

## Custom Keyframe Clip

```dart
// Bounce animation on Y axis
final times = [0.0, 0.5, 1.0];
final values = [0.0, 1.5, 0.0];

final track = THREE.NumberKeyframeTrack('.position[y]', times, values);
final clip = THREE.AnimationClip('bounce', 1.0, [track]);

final mixer = THREE.AnimationMixer(mesh);
mixer.clipAction(clip).play();
```

### Track Types

```dart
THREE.NumberKeyframeTrack('.material.opacity', times, [1, 0, 1])
THREE.VectorKeyframeTrack('.position', times, [0,0,0, 0,2,0, 0,0,0])
THREE.QuaternionKeyframeTrack('.quaternion', times, quaternionValues)
THREE.ColorKeyframeTrack('.material.color', times, colorValues)
THREE.BooleanKeyframeTrack('.visible', times, [true, false])
```

## Listen for Animation End

```dart
mixer.addEventListener('finished', (event) {
  final action = event['action'] as THREE.AnimationAction;
  // action completed one loop
});
```

## See Also

- `three-dart-loaders` — loading GLTF models with embedded animation clips
- `three-dart-fundamentals` — animation loop setup
