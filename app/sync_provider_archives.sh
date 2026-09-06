#!/bin/sh
set -eu
app_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime_dir=${GROCIOUS_HOME:-"$app_dir/.."}
result=0
for provider in rema trumf; do
    docker run --rm --name "grocious-${provider}-archive" \
        -v "$runtime_dir/data:/data" \
        -v "$app_dir:/app:ro" \
        -e PYTHONPATH=/app -e GROCERY_DATA=/data \
        grocery-web python /app/provider_archive.py "$provider" --incremental || result=1
done
docker run --rm --name grocious-trumf-images \
    -v "$runtime_dir/data:/data" \
    -v "$app_dir:/app:ro" \
    -e PYTHONPATH=/app -e GROCERY_DATA=/data \
    grocery-login /app/trumf_images.py || result=1
exit "$result"
