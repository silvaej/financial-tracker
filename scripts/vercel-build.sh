#!/bin/sh
# Downloads the standalone tailwindcss binary and compiles app/static/css/style.css.
# Lives in its own file (rather than inline in vercel.json's buildCommand) so its
# quoting/escaping is normal shell syntax, not a JSON string -- see issue #126:
# every deployment failed after a checksum-verification step was first added
# inline to buildCommand, and the leading suspect is Vercel wrapping buildCommand
# in its own outer quoting that a `'...'`-containing one-liner could collide with.
set -e

curl -sLo tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.0.0/tailwindcss-linux-x64

expected=09c1a5997d68f5e0127d9737593e7dc658fc96dc1851d782a78983d0d6a03c7c
actual=$(sha256sum tailwindcss | cut -d " " -f1)
if [ "$actual" != "$expected" ]; then
  echo "tailwindcss checksum mismatch: expected $expected, got $actual" >&2
  exit 1
fi

chmod +x tailwindcss
./tailwindcss -i app/static/css/input.css -o app/static/css/style.css
