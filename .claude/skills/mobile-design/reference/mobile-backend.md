# Mobile Backend Patterns

Backend and API patterns specific to mobile Flutter clients. Generic backend patterns live in `nestjs-api` and `python-dev` skills. Mobile backend is NOT the same as web backend — different constraints, different patterns.

**Firebase note:** This workspace uses Firebase Firestore and FCM (Firebase Cloud Messaging) as described in the `flutter-mobile` skill. Where this file references generic REST APIs, adapt the patterns to Firestore where applicable.

---

## Mobile Backend Mindset

```
Mobile clients are DIFFERENT from web clients:
+-- Unreliable network (2G, subway, elevator)
+-- Battery constraints (minimize wake-ups)
+-- Limited storage (can't cache everything)
+-- Interrupted sessions (calls, notifications)
+-- Diverse devices (old phones to flagships)
+-- Binary updates are slow (App Store review)
```

Your backend must compensate for ALL of these.

---

## AI Mobile Backend Anti-Patterns

| AI Default | Why It's Wrong | Mobile-Correct |
|------------|----------------|----------------|
| Same API for web and mobile | Mobile needs compact responses | Separate mobile endpoints OR field selection |
| Full object responses | Wastes bandwidth, battery | Partial responses, pagination |
| No offline consideration | App crashes without network | Offline-first design, sync queues |
| WebSocket for everything | Battery drain | Push notifications + polling fallback |
| No app versioning | Can't force updates, breaking changes | Version headers, minimum version check |
| Generic error messages | Users can't fix issues | Mobile-specific error codes + recovery actions |
| Session-based auth | Mobile apps restart | Token-based with refresh (Firebase Auth handles this) |
| Ignore device info | Can't debug issues | Device ID, app version in headers |

---

## 1. Push Notifications (Firebase Cloud Messaging)

### Architecture

```
+---------------------------------------------------------------+
|                    YOUR BACKEND                                |
+---------------------------------------------------------------+
|                         |                                      |
|              +----------+---------+                            |
|              v                    v                            |
|    +-----------------+   +-----------------+                   |
|    |   FCM (Google)  |   |  APNs (Apple)   |                   |
|    |   Firebase      |   |  Via FCM        |                   |
|    +--------+--------+   +--------+--------+                   |
|             |                     |                             |
|             v                     v                             |
|    +-----------------+   +-----------------+                   |
|    | Android Device  |   |   iOS Device    |                   |
|    +-----------------+   +-----------------+                   |
+---------------------------------------------------------------+
```

FCM handles both Android and iOS when you configure APNs keys in the Firebase Console. This workspace uses `firebase_messaging` package.

### Push Types

| Type | Use Case | User Sees |
|------|----------|-----------|
| **Display** | New message, order update | Notification banner |
| **Silent** | Background sync, content update | Nothing (background) |
| **Data** | Custom handling by app | Depends on app logic |

### Anti-Patterns

| Never | Always |
|-------|--------|
| Send sensitive data in push payload | Push says "New message", app fetches content |
| Overload with pushes | Batch, dedupe, respect quiet hours |
| Same message to all users | Segment by user preference, timezone |
| Ignore failed tokens | Clean up invalid tokens regularly |
| Skip APNs configuration for iOS | FCM alone does not guarantee iOS delivery |

### Token Management in Flutter

Register with Firebase Installation IDs (`register()` + `onRegistered`); `getToken()` / `onTokenRefresh` are the deprecated registration-token API. The full lifecycle (iOS APNs-token precondition, re-register on resume, `unregister()` at sign-out, server-side cleanup of dead registrations, dropping taps meant for another user) lives in one place: `flutter-mobile/reference/flutter-security-client-trust.md` §8.

Multiple devices: store one registration per device under the user, e.g. `/users/{userId}/fcmRegistrations/{id}`.

### Token Lifecycle

```
+-- App registers -> Get token -> Send to backend
+-- Token can change -> App must re-register on start
+-- Token expires -> Clean from Firestore
+-- User uninstalls -> Token becomes invalid (detect via error response from FCM)
+-- Multiple devices -> Store multiple tokens per user
```

---

## 2. Offline Sync and Conflict Resolution

### Firestore Offline Support

Firestore has built-in offline support — enable it once:

```dart
// Call before any Firestore access (in main.dart)
FirebaseFirestore.instance.settings = const Settings(
  persistenceEnabled: true,
  cacheSizeBytes: Settings.CACHE_SIZE_UNLIMITED,
);

// Reads: automatically from cache when offline
// Writes: queued locally, synced when network returns
// No extra code needed for basic offline support
```

### Sync Strategy Selection

```
WHAT TYPE OF DATA?
        |
        +-- Read-only (news, catalog)
        |   -> Simple Firestore cache + TTL
        |   -> ETag/Last-Modified for REST APIs
        |
        +-- User-owned (notes, todos)
        |   -> Firestore last-write-wins (automatic)
        |   -> Or timestamp-based merge
        |
        +-- Collaborative (shared docs)
        |   -> Firestore real-time listeners handle this
        |   -> Consider transaction for atomic updates
        |
        +-- Critical (payments, inventory)
            -> Server is source of truth
            -> Optimistic UI + server confirmation
```

### Conflict Resolution Strategies

| Strategy | How It Works | Best For |
|----------|--------------|----------|
| **Last-write-wins** | Latest timestamp overwrites | Simple data, single user |
| **Server-wins** | Firestore transaction | Critical transactions |
| **Client-wins** | Offline changes prioritized | Offline-heavy apps |
| **Merge** | Combine changes field-by-field | Documents, rich content |

---

## 3. Mobile API Optimization

### Response Size Reduction

| Technique | Savings | Implementation |
|-----------|---------|----------------|
| **Field selection** | 30-70% | Firestore `.select()` or REST `?fields=` |
| **Compression** | 60-80% | gzip/brotli (Dio handles this automatically) |
| **Pagination** | Varies | Cursor-based (Firestore `.startAfterDocument()`) |
| **Delta sync** | 80-95% | Firestore `updatedAt > lastSync` query |

### Pagination: Cursor vs Offset

```
OFFSET (Bad for mobile):
+-- Page 1: skip 0, take 20
+-- Page 2: skip 20, take 20
+-- Problem: New item added -> duplicates!
+-- Problem: Large skip = slow query

CURSOR (Good for mobile — use Firestore's approach):
+-- First: .limit(20)
+-- Next: .startAfterDocument(lastDocument).limit(20)
+-- No duplicates on data changes
+-- Consistent performance regardless of position
```

```dart
// Firestore cursor pagination
Query<Map<String, dynamic>> query = FirebaseFirestore.instance
    .collection('items')
    .orderBy('createdAt', descending: true)
    .limit(20);

// Next page:
query = query.startAfterDocument(lastDocumentSnapshot);
```

---

## 4. App Versioning

### Version Check Endpoint Pattern

```
GET /api/app-config
Headers:
  X-App-Version: 2.1.0
  X-Platform: ios
  X-Device-ID: abc123

Response:
{
  "minimum_version": "2.0.0",
  "latest_version": "2.3.0",
  "force_update": false,
  "update_url": "https://apps.apple.com/...",
  "feature_flags": {
    "new_feature": true
  },
  "maintenance": false
}
```

### Version Comparison Logic

```
CLIENT VERSION vs MINIMUM VERSION:
+-- client >= minimum -> Continue normally
+-- client < minimum -> Show force update screen, block app
+-- client < latest -> Show optional update prompt

FEATURE FLAGS:
+-- Enable/disable features without app update
+-- A/B testing by version/device
+-- Gradual rollout (10% -> 50% -> 100%)
```

---

## 5. Authentication for Mobile (Firebase Auth)

Firebase Auth handles token management automatically. Key patterns:

### Token Strategy

```
Firebase Auth provides:
+-- ID Token: Short-lived (1 hour), auto-refreshed by SDK
+-- Refresh Token: Long-lived, stored securely by Firebase SDK
+-- User persists across app restarts automatically

No manual token management needed for Firebase Auth.
Use firebaseUser.getIdToken() when calling your own backend.
```

### Silent Re-authentication

```dart
// Firebase Auth streams handle this automatically
FirebaseAuth.instance.authStateChanges().listen((user) {
  if (user == null) {
    // Session expired or logged out -> route to login
  } else {
    // User authenticated -> route to home
  }
});

// For backend API calls: token is auto-refreshed
final idToken = await FirebaseAuth.instance.currentUser?.getIdToken();
```

---

## 6. Error Handling for Mobile

### Mobile-Specific Error Format

```json
{
  "error": {
    "code": "PAYMENT_DECLINED",
    "message": "Your payment was declined",
    "user_message": "Please check your card details or try another payment method",
    "action": {
      "type": "navigate",
      "destination": "payment_methods"
    },
    "retry": {
      "allowed": true,
      "after_seconds": 5
    }
  }
}
```

### Error Categories

| Code Range | Category | Mobile Handling |
|------------|----------|-----------------|
| 400-499 | Client error | Show message, user action needed |
| 401 | Auth expired | Firebase auto-refreshes; re-login if refresh fails |
| 403 | Forbidden | Show upgrade/permission screen |
| 404 | Not found | Remove from local Firestore cache |
| 409 | Conflict | Show sync conflict UI |
| 429 | Rate limit | Retry after header, exponential backoff |
| 500-599 | Server error | Retry with backoff, show "try later" |
| Network | No connection | Use Firestore offline cache, queue for sync |

---

## 7. Media and Binary Handling

### Image Optimization

```
Request images at display size (never full resolution):
GET /images/{id}?w=400&h=300&q=80&format=webp

Server should:
+-- Resize on-the-fly OR use CDN (Cloudflare, Firebase Storage)
+-- WebP for Android (smaller)
+-- HEIC for iOS 14+ (if supported)
+-- JPEG fallback
+-- Cache-Control: max-age=31536000

Firebase Storage URLs support image resize via extension:
https://firebasestorage.googleapis.com/...?width=400&height=300
```

### Firebase Storage Upload

```dart
// Chunked upload handled by Firebase Storage SDK automatically
final ref = FirebaseStorage.instance.ref('uploads/${filename}');
final uploadTask = ref.putFile(file);

// Progress monitoring
uploadTask.snapshotEvents.listen((snapshot) {
  final progress = snapshot.bytesTransferred / snapshot.totalBytes;
});

final downloadUrl = await uploadTask.then((snapshot) => snapshot.ref.getDownloadURL());
```

---

## 8. Security for Mobile

### Rate Limiting

```
MOBILE-SPECIFIC LIMITS:
+-- Per device (X-Device-ID)
+-- Per user (after auth)
+-- Per endpoint (stricter for sensitive)
+-- Sliding window preferred

HEADERS to return:
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1609459200
Retry-After: 60 (when 429)
```

### Required Headers from Mobile

```
Every mobile request should include:
+-- X-App-Version: 2.1.0
+-- X-Platform: ios | android
+-- X-OS-Version: 17.0
+-- X-Device-ID: uuid (persistent, stored in flutter_secure_storage)
+-- X-Request-ID: uuid (per request, for tracing)
+-- Accept-Language: en-US
+-- X-Timezone: America/Los_Angeles
```

---

## Mobile Backend Checklist

### Before API Design

- [ ] Identified mobile-specific requirements?
- [ ] Planned offline behavior (Firestore persistence enabled)?
- [ ] Designed sync strategy for conflict scenarios?
- [ ] Considered bandwidth constraints (field selection, pagination)?

### For Every Endpoint

- [ ] Response as small as possible?
- [ ] Pagination cursor-based (Firestore startAfterDocument)?
- [ ] Proper caching headers on REST endpoints?
- [ ] Mobile error format with user_message and action?

### Authentication (Firebase Auth)

- [ ] authStateChanges() stream hooked into GoRouter?
- [ ] ID token passed to backend API calls?
- [ ] Multi-device logout implemented (revokeRefreshTokens on backend)?

### Push Notifications (FCM)

- [ ] FCM + APNs configured in Firebase Console?
- [ ] Token lifecycle managed (refresh listener in app)?
- [ ] Silent vs display push defined for each use case?
- [ ] Sensitive data NOT in push payload (fetch on open)?

---

> **Remember:** Mobile backend must be resilient to bad networks, respect battery life, and handle interrupted sessions gracefully. The client cannot be trusted, but it also cannot be hung up — provide offline capabilities and clear error recovery paths.
