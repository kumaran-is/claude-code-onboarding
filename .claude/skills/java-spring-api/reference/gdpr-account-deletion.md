# GDPR Account Deletion Pattern — Spring Boot

> **Stack:** the code samples here are **Spring WebFlux** (use it only when justified: `docs/adr/0001-java25-spring-boot-4-mvc-default.md`). Spring MVC, the default, is covered by the tested code in `spring-boot-templates.md` → Spring MVC.

## Overview

Same flow as NestJS: request -> confirm -> grace period -> process deletion.
GDPR Article 17 requires all PII removed within 30 days of request.

## Flyway Migration

```sql
-- V__add_deletion_request.sql
CREATE TABLE deletion_request (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES app_user(id),
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    scheduled_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    processed_at TIMESTAMPTZ,
    CONSTRAINT chk_status CHECK (status IN ('PENDING','CANCELLED','PROCESSING','COMPLETED'))
);
```

## Service Pattern

```java
@Service
@RequiredArgsConstructor
public class AccountDeletionService {
    private static final Logger log = LoggerFactory.getLogger(AccountDeletionService.class);
    private final DeletionRequestRepository deletionRepo;
    private final UserRepository userRepo;
    private final AuditLogRepository auditRepo;
    private final TransactionalOperator txOp;
    private final EmailService emailService;

    public Mono<DeletionRequest> requestDeletion(UUID userId) {
        var scheduledAt = Instant.now().plus(Duration.ofDays(7));
        var request = new DeletionRequest(userId, scheduledAt);
        return deletionRepo.save(request)
            .flatMap(req -> emailService.sendDeletionConfirmation(userId, scheduledAt)
                .thenReturn(req))
            .doOnSuccess(req -> log.info("Deletion requested for user {}, scheduled {}", userId, scheduledAt));
    }

    public Mono<Void> cancelDeletion(UUID userId) {
        return deletionRepo.findByUserId(userId)
            .flatMap(req -> {
                req.setStatus(DeletionStatus.CANCELLED);
                return deletionRepo.save(req);
            })
            .doOnSuccess(v -> log.info("Deletion cancelled for user {}", userId))
            .then();
    }

    @Scheduled(fixedRate = 3600000) // every hour
    public void processPendingDeletions() {
        deletionRepo.findByStatusAndScheduledAtBefore(DeletionStatus.PENDING, Instant.now())
            .flatMap(req -> txOp.transactional(
                auditRepo.anonymizeByUserId(req.getUserId())
                    .then(userRepo.deleteById(req.getUserId()))
                    .then(deletionRepo.markCompleted(req.getId()))
            ).doOnSuccess(v -> log.info("Deletion completed for user {}", req.getUserId())))
            .subscribe();
    }
}
```

## Checklist

- [ ] Deletion request endpoint (POST /api/v1/account/delete)
- [ ] Confirmation email with cancel link
- [ ] 7-day grace period
- [ ] Cancel endpoint (POST /api/v1/account/delete/cancel)
- [ ] PII anonymized in audit logs
- [ ] Cascade delete user + related data
- [ ] Scheduled job processes expired requests
- [ ] External service cleanup (Stripe, Firebase Auth)
