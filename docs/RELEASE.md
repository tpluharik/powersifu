# Release checklist

PowerSifu releases are Debian packages published through GitHub Releases. The application updater
uses the latest non-draft GitHub release and accepts only a correctly named `_all.deb` asset.

## Prepare

1. Update `VERSION`, `src/powersifu/__init__.py`, and `packaging/control` to the same version.
2. Add release entries to `CHANGELOG.md`, `packaging/changelog`, and the AppStream metadata.
3. Update the version shown in the manual page and any version-specific README links.
4. Keep dependency changes synchronized between `packaging/control`, `README.md`, and
   `docs/DEVELOPMENT.md`.

## Validate

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
./tests/test_launcher.sh
python3 -m compileall -q src
appstreamcli validate --no-net data/io.github.tpluharik.PowerSifu.metainfo.xml
./packaging/build-deb.sh
dpkg-deb --info dist/powersifu_VERSION_all.deb
apt-get -s install ./dist/powersifu_VERSION_all.deb
```

Replace `VERSION` with the release number. Confirm that the package name, version, architecture,
dependencies, desktop launcher, icons, application metadata, manual page, and Python sources are
present in the archive.

## Publish

1. Replace the previous tracked package in `dist/` with the new package.
2. Commit the source, documentation, metadata, and package together, then push `main`.
3. Wait for the **Build Debian package** GitHub Actions workflow to pass for that commit.
4. Create a `vVERSION` GitHub release targeting the verified commit and attach the package.
5. Confirm that GitHub reports the expected package size and SHA-256 digest.
6. Use the previous PowerSifu release to check, download, and verify the new release through the
   same updater path users will run.

Never replace an asset on an existing tag. Publish a new patch version so updater verification and
release history remain reproducible.
