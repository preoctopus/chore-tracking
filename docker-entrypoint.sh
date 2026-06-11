#!/bin/sh
set -e

# docker-entrypoint.sh
#
# This entrypoint promotes certain Docker secrets into environment variables
# so that application code (and glinet_blacklist.py) can access them via
# os.environ without needing to know about the Docker secrets filesystem layout.
#
# Currently supported:
#   /run/secrets/router_password  ->  GLINET_ROUTER_PASS
#
# If the secret file does not exist (e.g. during local development when the
# router integration is not yet configured), we simply skip setting the var.

if [ -f /run/secrets/router_password ]; then
    pw="$(cat /run/secrets/router_password | tr -d '\r\n')"
    # Only export if we have a non-empty, non-placeholder value
    case "$pw" in
        ""|"your-router-admin-password-here")
            ;;
        *)
            export GLINET_ROUTER_PASS="$pw"
            ;;
    esac
fi

# Hand off to the original command (gunicorn, python, etc.)
exec "$@"
