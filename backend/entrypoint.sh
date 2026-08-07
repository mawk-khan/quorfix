#!/bin/sh
# Production image entrypoint (backend/Dockerfile's `production` stage).
#
# Deliberately does NOT run migrations, seed_demo, or anything destructive —
# those stay explicit operator actions (`make prod-migrate`, documented in
# the Makefile). This script only proves the process can safely start:
#
#   1. `manage.py check` — runs Django's system checks, including every
#      apps.core.checks quorfix.E0xx production check from Phase 6 Chunk B.
#      Neither gunicorn nor celery invoke this on their own, so without this
#      step a misconfigured production container would start "successfully"
#      and only fail at runtime, defeating the point of those checks.
#   2. `manage.py check_attachment_storage` — proves ATTACHMENTS_LOCAL_ROOT
#      is usable before the app starts accepting traffic or tasks.
#
# `exec "$@"` replaces this script's process with the real command (gunicorn
# or celery) as PID 1, so it receives SIGTERM/SIGINT directly — no signal is
# ever swallowed by an intermediate shell.

set -eu

python manage.py check
python manage.py check_attachment_storage

exec "$@"
