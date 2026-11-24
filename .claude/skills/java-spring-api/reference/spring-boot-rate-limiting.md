# Inbound Rate Limiting — Spring Boot

> **Stack:** the code samples here are **Spring WebFlux** (use it only when justified: `docs/adr/0001-java25-spring-boot-4-mvc-default.md`). Spring MVC, the default, is covered by the tested code in `spring-boot-templates.md` → Spring MVC. On MVC the same bucket logic runs in a servlet `Filter` (`OncePerRequestFilter`).

## Layer 1: GCP Cloud Armor (Edge)

Configure Cloud Armor security policy on the GCP Load Balancer in front of Cloud Run:
- Rate limit: 100 req/min per IP (adjust per endpoint)
- Geo-blocking for non-target regions
- OWASP ModSecurity Core Rule Set (CRS) enabled

Terraform example (add to `terraform-specialist` module):

```hcl
resource "google_compute_security_policy" "api_policy" {
  name = "${var.service_name}-policy"

  rule {
    action   = "throttle"
    priority = 1000
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
    rate_limit_options {
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
      conform_action = "allow"
      exceed_action  = "deny(429)"
    }
  }
}
```

## Layer 2: Bucket4j (Application)

Add `bucket4j-spring-boot-starter` for per-route limits:

```xml
<dependency>
  <groupId>com.bucket4j</groupId>
  <artifactId>bucket4j-spring-boot-starter</artifactId>
  <version>0.14.0</version>
</dependency>
```

WebFilter example:

```java
@Component
public class RateLimitFilter implements WebFilter {
    private final Map<String, Bucket> buckets = new ConcurrentHashMap<>();

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, WebFilterChain chain) {
        String ip = Objects.requireNonNull(exchange.getRequest().getRemoteAddress())
            .getAddress().getHostAddress();
        Bucket bucket = buckets.computeIfAbsent(ip, k -> createBucket());
        if (bucket.tryConsume(1)) {
            return chain.filter(exchange);
        }
        exchange.getResponse().setStatusCode(HttpStatus.TOO_MANY_REQUESTS);
        return exchange.getResponse().setComplete();
    }

    private Bucket createBucket() {
        return Bucket.builder()
            .addLimit(Bandwidth.classic(10, Refill.greedy(10, Duration.ofSeconds(1))))   // 10/sec burst
            .addLimit(Bandwidth.classic(200, Refill.greedy(200, Duration.ofMinutes(1)))) // 200/min sustained
            .build();
    }
}
```

## Auth Endpoint Stricter Limits

For login/register/password-reset, use tighter limits:
- Login: 5 attempts per IP per minute
- Password reset: 3 per email per hour (track by email, not just IP)
- Register: 3 per IP per hour

## Key Rules

- Edge rate limiting (Cloud Armor) catches volumetric attacks before they hit your app
- Application rate limiting (Bucket4j) catches per-route abuse patterns
- For multi-instance Cloud Run, use Redis-backed Bucket4j (`bucket4j-redis`) so instances share state
- NEVER rely on application-level rate limiting alone — edge protection is mandatory for production
