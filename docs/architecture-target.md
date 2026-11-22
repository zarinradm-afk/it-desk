# Target Architecture for IT Desk

Current demo: FastAPI, SQLAlchemy, Jinja, Docker Compose, and GitHub Actions.

Target structure:

`	ext
it-desk/
├── docs/
├── overmind/
├── deploy/
├── frontend/   # Git Submodule: React + shadcn/ui
└── backend/    # Git Submodule: Django + Django REST Framework
`

Migration: move API/models to Django/DRF, move Jinja pages to React, create independent repositories, connect them as submodules, then add separate CI/CD workflows and protected deployment environments. The current FastAPI/Jinja version remains the runnable reference until migration is complete.
