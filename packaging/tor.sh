#!/bin/sh
# Maintainer build container. Endpoint machines only receive completed files.
set -eu
apk add --no-cache build-base pkgconf linux-headers ca-certificates libcap-dev \
  libevent-dev libseccomp-dev openssl-dev xz-dev zlib-dev zstd-dev
mkdir -p /tmp/source /out/tor/bin /out/tor/lib /out/notices
tar -xzf /inputs/tor.tar.gz -C /tmp/source --strip-components=1
cd /tmp/source
./configure --prefix=/usr --sysconfdir=/etc --localstatedir=/var \
  --enable-gpl --disable-html-manual --disable-manpage --disable-asciidoc
make -j2 src/app/tor
cp src/app/tor /out/tor/bin/tor
cp -R doc /out/notices/tor-doc
cp -R /lib/apk/db /out/notices/alpine-db
case "$(uname -m)" in
  x86_64) MUSL_ARCH=x86_64 ;;
  aarch64) MUSL_ARCH=aarch64 ;;
  armv7l|armv8l) MUSL_ARCH=armhf ;;
  *) exit 1 ;;
esac
cp -L "/lib/ld-musl-$MUSL_ARCH.so.1" "/out/tor/lib/ld-musl-$MUSL_ARCH.so.1"
ldd /out/tor/bin/tor > /tmp/libraries
while read -r name arrow library rest; do
  [ "$arrow" = '=>' ] || continue
  case "$library" in /lib/*|/usr/lib/*) ;; *) exit 1 ;; esac
  cp -L "$library" "/out/tor/lib/$name"
done < /tmp/libraries
ln -s "ld-musl-$MUSL_ARCH.so.1" "/out/tor/lib/libc.musl-$MUSL_ARCH.so.1"
chown -R "$OUT_UID:$OUT_GID" /out/tor /out/notices
