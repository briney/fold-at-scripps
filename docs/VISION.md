# fold@Scripps — Vision

> A high-level statement of purpose and the architectural principles this project
> should adhere to. This document is intentionally light on technical detail;
> concrete architecture and implementation decisions live elsewhere.

## Purpose

**fold@Scripps is a browser-based front-end that makes the institute's advanced
biological-modeling tools usable by any researcher, while turning a single shared
GPU node into a fairly-managed, tracked resource.**

It removes the operational barriers — the command line, Docker, GPU scheduling,
config files — that stand between researchers and state-of-the-art models for
structure prediction, generative protein and antibody design, inverse folding,
protein/antibody language-model embeddings, scoring, and simulation.

The division of labor is deliberate and central to everything below:

- [`autobio`](https://github.com/briney/autobio) does the computing. It owns the
  containerized model implementations, their inputs and outputs, and their
  execution.
- **fold@Scripps makes that computing accessible and shared.** It is the
  multi-user front-end, job orchestration, and usage-tracking layer wrapped
  around autobio.

## Who it's for

Researchers at the institute, across the full spectrum of computational
experience — from bench scientists who have never opened a terminal to power
users who want fine control. The application is served over the institute's
intranet and is not exposed to the public internet.

## Core principles

1. **Accessibility first.** Guided interfaces with sensible defaults are the
   norm; the full power of each tool is available but never required. Using the
   application demands no knowledge of the command line, Docker, or GPUs.

2. **Fair shared access.** Lightweight authentication, per-user usage tracking,
   and quotas let a single node serve many people without contention. Runs and
   their outputs are scoped to their owner. Authentication exists for
   attribution, quotas, and showing each user the right results — *not* for
   hardened security.

3. **Simplicity over sophistication (YAGNI).** A simple, single-node job queue
   and a minimal set of moving parts. We deliberately avoid heavyweight
   infrastructure — cluster schedulers like SLURM, multi-node orchestration,
   elaborate retry/management frameworks — until there is a real need for it.

4. **`autobio` is the source of truth for execution.** The application
   orchestrates and presents; it never reimplements model logic. New tools and
   categories originate in autobio, and integrating one into the web app should
   be a small, well-bounded change — ideally driven by the schemas autobio
   already exposes.

5. **Build simple, but don't wall off growth.** We make simple near-term choices
   that keep future doors open without building behind them today. The key
   enabler is a clean **transport-agnostic service layer** at the system's core —
   the domain logic for submitting jobs, tracking runs, enforcing quotas, and
   managing users — that knows nothing about how it is invoked. The web UI is a
   thin client of that core. This is what keeps each growth axis below an
   *additive* change rather than a rewrite.

## Scope

### v1 — the core loop

Authenticate → browse and select a tool → fill out a guided form → submit →
queue → watch status → retrieve and download results. Everything is scoped to
the user and tracked against quotas. The model outputs (structures, sequences,
embeddings, scores) are the product.

### Near-term, post-v1 (leave architectural room; do not build in v1)

- **In-browser result visualization** — 3D structure viewers, sequence and score
  plots — so users do not need to download files and open them locally.
- **Run history and organization** — browse past runs and organize them
  (e.g., into projects).

Side-by-side comparison of runs is a possible later refinement of the above, but
is explicitly deprioritized.

### Explicit non-goals (for now)

These are possible futures, not current goals. We will not build them now, and we
will not preclude them.

- Chained or automated multi-tool pipelines (e.g., design → inverse fold →
  predict → score).
- Multi-node scheduling and orchestration.
- A public programmatic API.
- Hardened, security-critical authentication and authorization.

## Growth axes

The application should be able to grow along these axes without rearchitecting.
None are built now; each is kept in mind so that today's decisions do not
foreclose them.

- **New models and tool categories.** As autobio gains tools, integrating one
  into the web app should be a small, well-bounded, schema-driven change.

- **Compute scale.** If demand outgrows the single node, we may move to a
  multi-node setup. The job/execution boundary should be drawn so that "where a
  job runs" can later become "which node runs it" without disturbing the rest of
  the system.

- **A programmatic API.** We may eventually want an API alongside the web
  interface. Because all domain logic lives in the transport-agnostic service
  layer and the web UI is merely a thin client of it, a future API is a new
  *adapter* over the same core — not new functionality and not a rewrite.

## Guiding tensions

- **Simple now vs. flexible later.** We favor simplicity in implementation, but
  enforce clean boundaries between concerns — authentication, the job queue,
  execution, storage, and presentation — so that growth is additive rather than
  disruptive.

- **Lower the barrier vs. serve power users.** Guided by default, advanced on
  demand.
