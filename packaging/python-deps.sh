#!/bin/sh
set -eu
PYTHON=/out/python/bin/python3
if [ "$RDZV_ARCH" = armv7l ]; then
  "$PYTHON" -I -m pip --isolated install --disable-pip-version-check --require-hashes \
    --only-binary=:all: -r /src/packaging/build-requirements.lock
  export LDFLAGS='-Wl,-rpath,$ORIGIN/../..'
  "$PYTHON" -I -m pip --isolated install --disable-pip-version-check --require-hashes \
    --only-binary=:all: --no-binary=cffi --no-build-isolation -r /src/requirements.lock
  cp -L /usr/lib/arm-linux-gnueabihf/libffi.so.8 /out/python/lib/libffi.so.8
  cp /usr/share/doc/libffi8/copyright /out/notices/libffi-copyright.txt
  "$PYTHON" -I -m pip --isolated uninstall --disable-pip-version-check -y setuptools wheel
else
  "$PYTHON" -I -m pip --isolated install --disable-pip-version-check --require-hashes \
    --only-binary=:all: -r /src/requirements.lock
fi
