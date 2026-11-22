# Git and CI/CD Structure

A submodule is an independent repository. The root repository records one exact commit from it, so frontend and backend evolve independently while the root pins a compatible pair.

`ash
git submodule add <frontend-repository> frontend
git submodule add <backend-repository> backend
git submodule update --init --recursive
`

Use develop for development, staging for test deployment, and main for production approval. Secrets and environment values belong in GitHub Secrets and Variables, never in Git. A workflow starts from a trigger, runs jobs on a runner, and each job contains steps. GITHUB_TOKEN should have the least permission required; read-only CI normally needs contents: read.
