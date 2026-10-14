# ADR 0004: durable, SSRF-safe career-source discovery

Status: accepted for Phase 3.

## Context

Users need to locate a company's public careers source without trusting stored URLs as network authorization. Discovery can outlive an API request, must survive broker restarts, and may receive duplicate deliveries. A name alone is insufficient evidence of an official domain.

## Decision

PostgreSQL owns scan state and results. Starting or continuing a scan writes `discovery_scans` and `scan_outbox` in one transaction. A dispatcher publishes due rows to a password-protected Redis broker. Celery workers use late acknowledgement, prefetch one, bounded concurrency, deterministic task IDs, database leases, and idempotent terminal writes. Redis stores only broker data and short hostname-rate leases.

Name-only companies never trigger network access. A conservative normalized `.com` guess may be shown with low confidence, but the user must select it or enter a URL. Discovery never rewrites the company record.

Every request uses the single safe HTTP transport. It accepts normalized HTTP(S) hostnames on standard ports, resolves immediately before connection, rejects all results unless every address is globally routable, connects to a validated address, verifies the peer, preserves the original host for HTTP and TLS, and repeats validation for every redirect. Proxies, automatic redirects, cookies, unbounded bodies, and unbounded sitemap traversal are disabled.

The worker reads robots directives, the selected page, bounded career links, and at most three bounded sitemap documents. It stores evidence codes and identifies generic pages plus Greenhouse, Lever, and Workday sources. It stores no fetched HTML, headers, cookies, DNS answers, or job records.

## Consequences

The outbox and database leases add dispatcher and worker runtime roles but close the commit/publish gap and make redelivery safe. Static HTTP discovery will mark some JavaScript-only sites unsupported. Exact-host rate limiting permits independent subdomains, while scan-wide response and byte budgets bound fan-out. Phase 4 must make a separate decision for any browser rendering or job extraction.
