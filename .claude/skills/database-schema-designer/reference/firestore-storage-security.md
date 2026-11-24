# Firestore Security Rules + Cloud Storage Signed URLs

## Firestore Security Rules

### Principle: User-Scoped by Default

Every Firestore document containing user data MUST have security rules that restrict access to the owning user. Client-side code can bypass UI guards — Firestore rules are the ONLY real enforcement layer.

### Base Template

```javascript
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {

    // Helper: is the user authenticated?
    function isAuth() {
      return request.auth != null;
    }

    // Helper: does the user own this resource?
    function isOwner() {
      return request.auth.uid == resource.data.userId;
    }

    // Helper: is the user creating a resource they will own?
    function isCreatingOwned() {
      return request.auth.uid == request.resource.data.userId;
    }

    // User profiles — users can only read/write their own
    match /users/{userId} {
      allow read, update, delete: if request.auth.uid == userId;
      allow create: if request.auth.uid == userId;
    }

    // User-owned collections — scoped by userId field
    match /orders/{orderId} {
      allow read: if isAuth() && isOwner();
      allow create: if isAuth() && isCreatingOwned();
      allow update: if isAuth() && isOwner();
      allow delete: if false; // Soft-delete only
    }

    // Subcollections inherit parent auth check
    match /users/{userId}/settings/{settingId} {
      allow read, write: if request.auth.uid == userId;
    }

    // Public read, authenticated write
    match /products/{productId} {
      allow read: if true;
      allow write: if isAuth() && request.auth.token.admin == true;
    }

    // Default deny — NEVER add a blanket allow rule
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

### Common Mistakes to Flag

| Mistake | Why It's Dangerous |
|---------|-------------------|
| `allow read, write: if true;` | Anyone can read/write all data |
| `allow read, write: if request.auth != null;` | Any authenticated user can access any other user's data |
| Missing `userId` check on user-owned data | IDOR vulnerability — users can access each other's records |
| No default deny rule | New collections are open by default |
| `allow delete: if true;` on user data | Malicious user can delete others' data |
| `allow update` checks only `resource.data.userId` | The caller can rewrite `userId` (or a role, status or price field) to anything: owner check passes on the old document. Pin it: `request.resource.data.userId == resource.data.userId`, and allowlist editable fields with `request.resource.data.diff(resource.data).affectedKeys().hasOnly([...])` |
| `allow read` used where `list` matters | `read` = `get` + `list`: a rule that is safe for one document id can expose a whole collection to a query. Rules are not filters: a query must carry the same constraint (`where('userId', '==', uid)`) or it is denied, and the rule must require it |
| Server-only fields writable from clients | Counters, approvals, payment state and notification recipients belong to the Admin SDK (which bypasses rules); deny client writes to them with `!affectedKeys().hasAny([...])` |

### Red-team the rules in the emulator (required for any rules change)

Write one denial test per attack, run against the Firestore emulator with `@firebase/rules-unit-testing` (modular API: `initializeTestEnvironment`, `authenticatedContext`, `unauthenticatedContext`, `withSecurityRulesDisabled` for seeding, `assertFails` / `assertSucceeds`; source: firebase.google.com/docs/rules/unit-tests, checked 2026-11-24). Minimum set per user-owned collection:

1. unauthenticated get, list and write → `assertFails`;
2. user B gets, lists, updates and deletes user A's document → `assertFails`;
3. user A updates their own document but changes `userId` (ownership transfer) or a server-only field → `assertFails`;
4. user A creates a document with `userId` = B → `assertFails`;
5. an unscoped `list` query on the collection → `assertFails`; the same query with `where('userId','==','alice')` → `assertSucceeds` (positive control: proves the rules load and the emulator is reachable).

Seed with `withSecurityRulesDisabled`, clear data between tests (`clearFirestore()`), and use a `demo-` project id so nothing can reach production. A suite with only `assertSucceeds` proves nothing about access control.

### Validation Rules

```javascript
// Validate data shape on write
match /orders/{orderId} {
  allow create: if isAuth()
    && isCreatingOwned()
    && request.resource.data.keys().hasAll(['userId', 'amount', 'status', 'createdAt'])
    && request.resource.data.amount is number
    && request.resource.data.amount > 0
    && request.resource.data.status == 'pending';
}
```

## Cloud Storage (GCS) — Signed URLs

### Why Signed URLs

Never expose GCS bucket contents directly. Use signed URLs for:
- Time-limited access (expires after N minutes)
- No public bucket required
- Per-object access control
- Audit trail via Cloud Audit Logs

### NestJS Implementation

```typescript
import { Storage } from '@google-cloud/storage';

@Injectable()
export class StorageService {
  private readonly storage = new Storage();
  private readonly bucket = this.storage.bucket(process.env.GCS_BUCKET);
  private readonly logger = new Logger(StorageService.name);

  async generateUploadUrl(
    userId: string,
    fileName: string,
    contentType: string,
  ): Promise<string> {
    const objectPath = `users/${userId}/${Date.now()}_${fileName}`;
    const [url] = await this.bucket.file(objectPath).getSignedUrl({
      version: 'v4',
      action: 'write',
      expires: Date.now() + 15 * 60 * 1000, // 15 minutes
      contentType,
    });
    this.logger.log(`Upload URL generated for user ${userId}: ${objectPath}`);
    return url;
  }

  async generateDownloadUrl(
    userId: string,
    objectPath: string,
  ): Promise<string> {
    // Verify user owns this file (path starts with users/{userId}/)
    if (!objectPath.startsWith(`users/${userId}/`)) {
      throw new ForbiddenException('Access denied to this file');
    }
    const [url] = await this.bucket.file(objectPath).getSignedUrl({
      version: 'v4',
      action: 'read',
      expires: Date.now() + 60 * 60 * 1000, // 1 hour
    });
    return url;
  }
}
```

### Spring Boot Implementation

```java
@Service
@RequiredArgsConstructor
public class StorageService {
    private static final Logger log = LoggerFactory.getLogger(StorageService.class);
    private final Storage storage;

    public String generateUploadUrl(UUID userId, String fileName, String contentType) {
        String objectPath = "users/%s/%d_%s".formatted(userId, System.currentTimeMillis(), fileName);
        BlobInfo blobInfo = BlobInfo.newBuilder(bucketName, objectPath)
            .setContentType(contentType)
            .build();
        URL url = storage.signUrl(blobInfo, 15, TimeUnit.MINUTES,
            Storage.SignUrlOption.httpMethod(HttpMethod.PUT),
            Storage.SignUrlOption.withV4Signature());
        log.info("Upload URL generated for user {}: {}", userId, objectPath);
        return url.toString();
    }
}
```

### Firebase Storage Rules (Alternative)

If using Firebase Storage directly from mobile/web clients:

```javascript
rules_version = '2';

service firebase.storage {
  match /b/{bucket}/o {
    // User files — scoped to authenticated user
    match /users/{userId}/{allPaths=**} {
      allow read: if request.auth.uid == userId;
      allow write: if request.auth.uid == userId
        && request.resource.size < 10 * 1024 * 1024  // 10MB max
        && request.resource.contentType.matches('image/.*|application/pdf');
    }

    // Default deny
    match /{allPaths=**} {
      allow read, write: if false;
    }
  }
}
```

## Checklist

- [ ] Firestore rules enforce `request.auth.uid == resource.data.userId` on user-owned collections
- [ ] Updates pin the owner field and allowlist editable fields (`affectedKeys().hasOnly`); server-only fields are not client-writable
- [ ] Emulator red-team suite (5 denial cases above + 1 positive control) passes for every changed rule
- [ ] Default deny rule exists (`allow read, write: if false;` on `/{document=**}`)
- [ ] No blanket `allow read, write: if true;` rules in production
- [ ] GCS buckets are NOT publicly accessible
- [ ] Signed URLs used for all file access (upload and download)
- [ ] Signed URLs have short expiry (15 min upload, 1 hour download)
- [ ] File path includes userId to prevent IDOR (`users/{userId}/...`)
- [ ] File type and size validated in storage rules or application layer
- [ ] Firebase Storage rules enforce user-scoped access
