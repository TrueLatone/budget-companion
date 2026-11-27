# ADR-001: Flask Monolith + Jinja2 + Bootstrap + SQLAlchemy + Supabase

**Date:** 20/10/2026  
**Status:** Proposed

## Context

Budget Companion is a responsive budgeting web application. A shared stack supports parallel work across feature modules and keeps the local setup small.

## Decision

- Python 3.11+ and Flask, organized with an Application Factory + Blueprints.
- Jinja2 template rendering with Bootstrap 5 and vanilla JavaScript.
- Flask-SQLAlchemy for database operations; Flask-Migrate for schema changes.
- Supabase managed PostgreSQL, connected using server-side SQLAlchemy via `DATABASE_URL` (not supabase-py/REST).
- pytest for smoke tests, with GitHub Actions proposed for pull request checks.