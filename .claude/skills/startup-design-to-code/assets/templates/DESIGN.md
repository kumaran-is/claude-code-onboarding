---
version: alpha
name: Unapproved Product System
description: "Skeleton only. Tokens stay omitted until approved screens exist. status: unapproved"
omitted:
  - colors
  - typography
  - spacing
  - rounded
  - components
---

# DESIGN.md — <product>

> Canonical visual contract. Token code implements it; disagreement is a drift finding.
> status: unapproved — do not treat this skeleton as brand.

## Overview

Brand personality, audience, and the feeling the UI should evoke. Not a product requirements dump.

## Colors

Semantic roles and when each is used. Light and dark pairs. Fill `{colors.*}` from approved screens, never from this skeleton.

## Typography

Type roles, license/delivery, fallbacks. Map to `{typography.*}`.

## Layout

Grid, density, breakpoints, spacing scale (`{spacing.*}`).

## Elevation & Depth

What is raised, what is flat, and why.

## Shapes

Radius scale (`{rounded.*}`). One family.

## Motion & Micro-interaction

Native/CSS is the default. Name Lottie or Rive here before adding a package (`DS-ANIM-DECISION`). Reduced motion collapses durations and stops loops.

## Voice & Content Strategy

Tone, error copy, empty-state voice. No enums or UUIDs in the UI.

## Components

Atomic tiers, variants, states. Shared library path. Line-1 `// Tier:`.

## Do's and Don'ts

## Icons

Family: <one library> via <wrapper>; sizes; decorative icons hidden from assistive tech.

## States

Follow the async-state contract (cold load skeleton, refresh in place, empty, filtered-empty, error, offline, pending mutation). See `design-system/reference/interaction-contracts.md` §6b.

## Refresh

| Screen | Source | Strategy | Accessible equivalent |
|---|---|---|---|

## Accessibility

Contrast ≥ 4.5:1 text / 3:1 large text and UI; targets ≥ 44 px web / 48 dp Flutter; 200% text.

## Gap policy

No token fits → stop and propose a DESIGN.md change first.

## Approved screens

Link inventory IDs only. Do not paste generated HTML into this file.
