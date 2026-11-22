# Constraints and Relationships

Define data integrity rules and relationship patterns to prevent invalid data at the database level.

---

## Primary Keys

```sql
-- Auto-increment (simple, sequential)
id INT AUTO_INCREMENT PRIMARY KEY

-- UUID (distributed systems, no sequential exposure)
id CHAR(36) PRIMARY KEY DEFAULT (UUID())

-- BIGINT auto-increment (large scale)
id BIGINT AUTO_INCREMENT PRIMARY KEY

-- Composite (junction tables)
PRIMARY KEY (student_id, course_id)
```

### Choosing a Primary Key Strategy

| Strategy | Best For | Trade-off |
|----------|----------|-----------|
| INT AUTO_INCREMENT | Small-medium apps, single DB | Sequential, guessable |
| BIGINT AUTO_INCREMENT | Large scale, single DB | 8 bytes vs 4 |
| UUID | Distributed systems, microservices | Larger, random (index fragmentation) |
| UUIDv7 | Distributed + sorted inserts | Newer standard, less tooling |

---

## Foreign Keys

```sql
FOREIGN KEY (customer_id) REFERENCES customers(id)
  ON DELETE CASCADE     -- Delete children with parent
  ON DELETE RESTRICT    -- Prevent deletion if referenced
  ON DELETE SET NULL    -- Set to NULL when parent deleted
  ON UPDATE CASCADE     -- Update children when parent changes
```

### ON DELETE Strategy Guide

| Strategy | Use When | Example |
|----------|----------|---------|
| CASCADE | Dependent data that has no meaning without parent | order_items when order deleted |
| RESTRICT | Important references that should prevent accidental deletion | orders referencing customers |
| SET NULL | Optional relationships | employee.manager_id when manager leaves |
| NO ACTION | Same as RESTRICT (checked at transaction end) | Default in most databases |

**Rule:** Always explicitly define ON DELETE strategy. Do not rely on defaults.

---

## Other Constraints

### UNIQUE

```sql
-- Single column unique
email VARCHAR(255) UNIQUE NOT NULL

-- Composite unique (combination must be unique)
UNIQUE (student_id, course_id)

-- Partial unique (PostgreSQL)
CREATE UNIQUE INDEX idx_active_email ON users(email)
WHERE is_active = true;
```

Partitioned tables: a unique constraint or index must include the partition key (verified on PostgreSQL 16: `unique constraint on partitioned table must include all partitioning columns`),
and a foreign key to a partitioned table must reference the full primary key including the partition key (a single-column FK failed with "no unique constraint matching given keys").
Take the partition-key value from the loaded parent row; for replay/idempotency keys use a small side table instead of a unique index on the partitioned table.

### CHECK

```sql
-- Value range
price DECIMAL(10,2) CHECK (price >= 0)
discount INT CHECK (discount BETWEEN 0 AND 100)

-- Enum-like constraint
status VARCHAR(20) CHECK (status IN ('active', 'inactive', 'suspended'))

-- Cross-column constraint
CHECK (end_date > start_date)
```

### NOT NULL

```sql
-- Required fields
name VARCHAR(100) NOT NULL
email VARCHAR(255) NOT NULL

-- With default
is_active BOOLEAN NOT NULL DEFAULT TRUE
created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
```

### DEFAULT

```sql
-- Static defaults
status VARCHAR(20) DEFAULT 'pending'
is_active BOOLEAN DEFAULT TRUE

-- Dynamic defaults
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
id CHAR(36) DEFAULT (UUID())
```

---

## Relationship Patterns

### One-to-Many

The most common relationship. The "many" side holds a foreign key to the "one" side.

```sql
CREATE TABLE orders (
  id INT PRIMARY KEY,
  customer_id INT NOT NULL REFERENCES customers(id)
);

CREATE TABLE order_items (
  id INT PRIMARY KEY,
  order_id INT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  product_id INT NOT NULL,
  quantity INT NOT NULL
);
```

### Many-to-Many

Use a junction (join) table with composite primary key.

```sql
CREATE TABLE enrollments (
  student_id INT REFERENCES students(id) ON DELETE CASCADE,
  course_id INT REFERENCES courses(id) ON DELETE CASCADE,
  enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (student_id, course_id)
);
```

**Tip:** Add extra columns to the junction table for relationship metadata (enrolled_at, role, status).

### Self-Referencing

A table that references itself for hierarchical data.

```sql
CREATE TABLE employees (
  id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  manager_id INT REFERENCES employees(id)
);

CREATE TABLE categories (
  id INT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  parent_id INT REFERENCES categories(id)
);
```

### Polymorphic Associations

When a row can belong to one of several different parent tables.

```sql
-- Approach 1: Separate FKs (stronger integrity, limited parents)
CREATE TABLE comments (
  id INT PRIMARY KEY,
  content TEXT NOT NULL,
  post_id INT REFERENCES posts(id),
  photo_id INT REFERENCES photos(id),
  CHECK (
    (post_id IS NOT NULL AND photo_id IS NULL) OR
    (post_id IS NULL AND photo_id IS NOT NULL)
  )
);

-- Approach 2: Type + ID (flexible, weaker integrity)
CREATE TABLE comments (
  id INT PRIMARY KEY,
  content TEXT NOT NULL,
  commentable_type VARCHAR(50) NOT NULL,
  commentable_id INT NOT NULL
);
```

| Approach | Pros | Cons |
|----------|------|------|
| Separate FKs | Database-enforced integrity | Limited number of parent types |
| Type + ID | Unlimited parent types, flexible | No FK constraint, app must enforce |

---

## Constraint Best Practices

1. **Enforce at the database level** -- application bugs can skip validation, the database cannot
2. **Name your constraints** -- `CONSTRAINT chk_positive_price CHECK (price >= 0)` for clear error messages
3. **Use CHECK over application validation** -- for simple rules, database constraints are more reliable
4. **Always define ON DELETE** -- explicit intent prevents surprises
5. **Index foreign keys** -- required for JOIN performance and cascading delete performance
