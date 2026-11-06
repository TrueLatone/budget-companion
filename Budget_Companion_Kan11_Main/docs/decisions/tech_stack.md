# ADR-001: Flask Monolith + Jinja2 + Bootstrap + SQLAlchemy + Supabase

**Date:** 20/10/2026  
**Status:** Proposed / update to Accepted after team confirms in Jira  
**Decision owner:** Thịnh / Group 10

## Context

Vision v1.0 requires a responsive student-budgeting web application and does not mandate a specific framework. Project Plan v1.0 assigns work to five feature owners. First demo is planned for 01/11/2026; limited setup time and parallel development are important.

## Decision

- Python 3.11+ and Flask, organized with an Application Factory + Blueprints.
- Jinja2 template rendering with Bootstrap 5 and vanilla JavaScript; React not required for Sprint 2.
- Flask-SQLAlchemy for database operations; Flask-Migrate for schema changes.
- Supabase managed PostgreSQL, connected using server-side SQLAlchemy via `DATABASE_URL` (not supabase-py/REST).
- pytest for smoke tests, GitHub Actions for pull request checks.