#!/bin/zsh
# Loads the cleaned data into Supabase and saves the agent's connection string to .env.local.
#
#   zsh pipeline/load_supabase.sh <project-ref> <pooler-host>
#
# The database password is read without echoing and passed through PGPASSWORD, so it never appears
# in a command line, a URL, or your shell history. Rerunning rotates the read-only role's password.
set -euo pipefail

ref=${1:?usage: load_supabase.sh <project-ref> <pooler-host>}
pooler=${2:?usage: load_supabase.sh <project-ref> <pooler-host>}
cd "${0:A:h}/.."

read -rs "PGPASSWORD?Supabase database password (hidden): "
echo
export PGPASSWORD

# The owner connection uses the session pooler, because COPY and SET need one session throughout.
export DATABASE_URL="postgresql://postgres.${ref}@${pooler}:5432/postgres?sslmode=require"
# Hex, so it is safe inside a URL.
export AGENT_DB_PASSWORD="$(openssl rand -hex 32)"

uv run --project pipeline python pipeline/build.py --raw ..

# The app connects through the transaction pooler, the mode for serverless functions.
umask 077
print -r -- "AGENT_DATABASE_URL=postgresql://uzex_agent.${ref}:${AGENT_DB_PASSWORD}@${pooler}:6543/postgres?sslmode=require" > .env.local
echo "Saved the agent connection to .env.local. Reply \"loaded\" to have it verified."
