#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
version=$(tr -d '[:space:]' < "$project_root/VERSION")
output_dir=${1:-"$project_root/dist"}
package_name="powersifu_${version}_all.deb"
stage=$(mktemp -d)
chmod 0755 "$stage"

cleanup() {
    rm -rf -- "$stage"
}
trap cleanup EXIT INT TERM

mkdir -p "$output_dir"
install -Dm644 "$project_root/packaging/control" "$stage/DEBIAN/control"
install -Dm755 "$project_root/bin/powersifu" "$stage/usr/bin/powersifu"

find "$project_root/src/powersifu" -maxdepth 1 -type f -name '*.py' -print | while IFS= read -r source; do
    install -Dm644 "$source" "$stage/usr/lib/python3/dist-packages/powersifu/$(basename "$source")"
done

install -Dm644 "$project_root/data/io.github.tpluharik.PowerSifu.desktop" \
    "$stage/usr/share/applications/io.github.tpluharik.PowerSifu.desktop"
install -Dm644 "$project_root/data/io.github.tpluharik.PowerSifu-autostart.desktop" \
    "$stage/etc/xdg/autostart/io.github.tpluharik.PowerSifu.desktop"
install -Dm644 "$project_root/data/io.github.tpluharik.PowerSifu.metainfo.xml" \
    "$stage/usr/share/metainfo/io.github.tpluharik.PowerSifu.metainfo.xml"

for size in 16 24 32 48 64 128 256 512; do
    install -Dm644 "$project_root/assets/icons/hicolor/${size}x${size}/apps/powersifu.png" \
        "$stage/usr/share/icons/hicolor/${size}x${size}/apps/powersifu.png"
done

install -Dm644 "$project_root/README.md" "$stage/usr/share/doc/powersifu/README.md"
install -Dm644 "$project_root/LICENSE" "$stage/usr/share/doc/powersifu/copyright"
install -Dm644 "$project_root/packaging/changelog" "$stage/usr/share/doc/powersifu/changelog"
install -Dm644 "$project_root/docs/powersifu.1" "$stage/usr/share/man/man1/powersifu.1"
gzip -9n "$stage/usr/share/doc/powersifu/changelog"
gzip -9n "$stage/usr/share/man/man1/powersifu.1"
install -Dm644 "$project_root/packaging/conffiles" "$stage/DEBIAN/conffiles"
(
    cd "$stage"
    find etc usr -type f -print0 | LC_ALL=C sort -z | xargs -0 md5sum
) > "$stage/DEBIAN/md5sums"

dpkg-deb --build --root-owner-group "$stage" "$output_dir/$package_name"
printf 'Built %s\n' "$output_dir/$package_name"
