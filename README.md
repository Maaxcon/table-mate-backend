# Table-Mate Backend

Backend service for the Table-Mate spatial editor. Built with Django and Django Channels.

---

## Prerequisites

* **uv**: `brew install uv`
* **Python 3.12**: Managed automatically by uv.
* **Redis**: `brew install redis`

---

## Installation and Setup

**1. Initialize Environment**
Build the virtual environment and install all dependency groups (Base, Dev, and Prod):

```bash
uv sync --all-groups

```

**2. Install Git Hooks**
Required for linting and security checks before committing:

```bash
uv run pre-commit install

```

**3. Database Migrations**

```bash
uv run python manage.py migrate

```

---

## Local Development

**Start Redis**

```bash
brew services start redis

```

**Start Django Server**

```bash
uv run python manage.py runserver

```

**Run Tests**

```bash
uv run python manage.py test

```

---

## Dependency Management

| Action | Command |
| --- | --- |
| **Add Production Dependency** | `uv add <package>` |
| **Add Development Dependency** | `uv add --dev <package>` |
| **Add Production-only Group** | `uv add --group prod <package>` |
| **Sync Environment** | `uv sync` |

---

## Troubleshooting: Rust Compiler Error

If `uv sync` fails with `error: can't find Rust compiler` (common for packages like `cbor2` or `cryptography` when pre-built wheels are unavailable), install the Rust toolchain:

```bash
brew install rust

```

After installation, retry:

```bash
uv sync

```

---

## Deployment

To install only production dependencies (excluding dev tools):

```bash
uv sync --no-dev --group prod

```
