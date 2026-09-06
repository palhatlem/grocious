#!/bin/sh
set -eu
result=0
for provider in rema trumf; do
    docker run --rm --name "grocious-${provider}-archive" \
        -v /srv/docker/grocery/data:/data \
        -v /srv/docker/stacks/grocery/app:/app:ro \
        -e PYTHONPATH=/app -e GROCERY_DATA=/data \
        grocery-web python /app/provider_archive.py "$provider" --incremental || result=1
done
docker run --rm --name grocious-trumf-images \
    -v /srv/docker/grocery/data:/data \
    -v /srv/docker/stacks/grocery/app:/app:ro \
    -e PYTHONPATH=/app -e GROCERY_DATA=/data \
    grocery-login /app/trumf_images.py || result=1
exit "$result"
