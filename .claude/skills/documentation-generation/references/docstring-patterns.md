# Docstring Patterns

Stack-specific docstring formats for public APIs in this workspace. Always match the existing style in the file. If the file has no existing docstrings, use these patterns.

---

## Java — Javadoc (Spring Boot / WebFlux)

### Controller endpoint

```java
/**
 * Retrieves a paginated list of users.
 *
 * @param page zero-based page index (default: 0)
 * @param size number of items per page (default: 20, max: 100)
 * @return {@link Mono} emitting a {@link Page} of {@link UserResponse}
 * @throws ResourceNotFoundException if no users exist
 */
@GetMapping("/users")
public Mono<Page<UserResponse>> getUsers(
    @RequestParam(defaultValue = "0") int page,
    @RequestParam(defaultValue = "20") int size) {
```

### Service method

```java
/**
 * Creates a new user and sends a verification email.
 *
 * <p>Validates uniqueness of the email before persisting. Publishes a
 * {@code UserCreatedEvent} on success for downstream consumers.
 *
 * @param command the user creation command with email, name, and role
 * @return {@link Mono} emitting the created {@link UserResponse}
 * @throws DuplicateResourceException if the email is already registered
 */
public Mono<UserResponse> createUser(CreateUserCommand command) {
```

### Repository method

```java
/**
 * Finds users by role and active status.
 *
 * @param role   the user role to filter by (must not be null)
 * @param active true to return only active accounts
 * @return {@link Flux} emitting matching {@link UserEntity} records
 */
Flux<UserEntity> findByRoleAndActive(UserRole role, boolean active);
```

---

## TypeScript — JSDoc + NestJS (NestJS / Angular)

### NestJS controller

```typescript
/**
 * List all active users with pagination.
 *
 * @param page - Zero-based page index
 * @param limit - Items per page (max 100)
 * @returns Paginated list of users
 *
 * @throws {NotFoundException} When no users exist for the given criteria
 */
@ApiOperation({ summary: 'List users' })
@ApiResponse({ status: 200, type: UserListResponse })
@Get()
async findAll(
  @Query('page') page = 0,
  @Query('limit') limit = 20,
): Promise<UserListResponse> {
```

### Angular service

```typescript
/**
 * Fetch user details by ID.
 *
 * Emits the user object once, then completes. Errors propagate to the
 * subscriber — callers are responsible for error handling.
 *
 * @param id - UUID of the user to retrieve
 * @returns Observable emitting a single {@link User}
 */
getUser(id: string): Observable<User> {
```

### Angular component method

```typescript
/**
 * Handle form submission.
 *
 * Validates the form, calls the user service, and navigates to the
 * success page on completion. Shows a snackbar on failure.
 */
onSubmit(): void {
```

---

## Python — Google-style docstrings (FastAPI / LangChain)

### FastAPI route handler

```python
@router.get("/users", response_model=UserListResponse)
async def list_users(
    page: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """Return a paginated list of active users.

    Args:
        page: Zero-based page index.
        limit: Number of items per page (max 100).
        db: Injected async database session.

    Returns:
        Paginated response with user objects and total count.

    Raises:
        HTTPException: 404 if no users exist for the query.
    """
```

### Pydantic model

```python
class CreateUserRequest(BaseModel):
    """Request body for user creation.

    Attributes:
        email: Unique user email address. Must be valid RFC 5322 format.
        name: Display name, 2-100 characters.
        role: User role determining access level (default: USER).
    """
    email: EmailStr
    name: str = Field(min_length=2, max_length=100)
    role: UserRole = UserRole.USER
```

### LangChain tool

```python
def search_documents(query: str, k: int = 5) -> list[Document]:
    """Search the vector store for documents relevant to the query.

    Args:
        query: Natural language search query.
        k: Number of documents to return (default 5).

    Returns:
        List of Document objects ordered by relevance score descending.

    Raises:
        VectorStoreError: If the vector store is unavailable.
    """
```

---

## Dart — Triple-slash comments (Flutter)

### Widget

```dart
/// A card that displays user profile information.
///
/// Shows the user's avatar, name, and role. Tapping the card navigates
/// to the profile detail screen.
///
/// Example:
/// ```dart
/// UserProfileCard(
///   user: currentUser,
///   onTap: () => context.push('/profile/${user.id}'),
/// )
/// ```
class UserProfileCard extends StatelessWidget {
```

### Riverpod provider

```dart
/// Watches the current authenticated user's profile.
///
/// Returns [AsyncValue.loading] during initial fetch,
/// [AsyncValue.data] with the [UserProfile] on success, and
/// [AsyncValue.error] if the fetch fails.
///
/// Automatically refreshes when [authProvider] emits a new user.
@riverpod
Future<UserProfile> userProfile(Ref ref) async {
```

### Service method

```dart
/// Fetch a paginated list of users from the API.
///
/// [page] is zero-based. [limit] defaults to 20 and is capped at 100.
///
/// Throws [ApiException] on network failure or non-2xx status.
Future<UserListResponse> getUsers({int page = 0, int limit = 20}) async {
```

---

## Rules

- Document all `public` / `exported` / `@riverpod` / `@router.*` symbols
- Do NOT document private helpers (`_method`, `__init__` bodies, internal utils)
- One-liner docstrings are acceptable for obvious getters/setters
- Always include `@throws` / `Raises` / `throws` for methods that can error
- `Args` / `@param` entries must match the actual parameter names exactly
