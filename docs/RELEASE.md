# Release checklist

PowerSifu releases are Debian packages that must be published through immutable GitHub Releases.
The application updater uses the latest non-draft release and accepts only a correctly named
`_all.deb` accompanied by its Ed25519-signed canonical manifest.

## Prepare

1. Update `VERSION`, `src/powersifu/__init__.py`, and `packaging/control` to the same version.
2. Add release entries to `CHANGELOG.md`, `packaging/changelog`, and the AppStream metadata.
3. Update the version shown in the manual page and any version-specific README links.
4. Keep dependency changes synchronized between `packaging/control`, `README.md`, and
   `docs/DEVELOPMENT.md`.
5. Keep the release-signing private key outside the repository with mode `0600`. Confirm that its
   public half matches `data/update-signing-key.pem`. Losing this key requires a normal package
   release that rotates the pinned public key; never silently replace the repository key.

## Validate

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
./tests/test_launcher.sh
python3 -m compileall -q src
appstreamcli validate --no-net data/io.github.tpluharik.PowerSifu.metainfo.xml
./packaging/build-deb.sh
dpkg-deb --info dist/powersifu_VERSION_all.deb
apt-get -s install ./dist/powersifu_VERSION_all.deb
./scripts/sign-update.py dist/powersifu_VERSION_all.deb \
  --private-key /secure/path/update-signing-ed25519.pem
/usr/bin/openssl pkeyutl -verify -rawin -pubin \
  -inkey data/update-signing-key.pem \
  -sigfile dist/powersifu_VERSION_all.deb.manifest.json.sig \
  -in dist/powersifu_VERSION_all.deb.manifest.json
python3 scripts/check-action-pins.py
```

Replace `VERSION` with the release number. Confirm that the package name, version, architecture,
dependencies, desktop launcher, icons, application metadata, manual page, Python sources, privileged
helper, polkit policy, and pinned public key are present in the archive. Inspect the signed manifest
and confirm its filename, version, size, and SHA-256 match the package.

## Publish

1. Replace the previous tracked package and signed manifest pair in `dist/` with the new files.
2. Commit the source, documentation, metadata, package, manifest, and signature together, then push
   `main`. Never commit the private key.
3. Wait for the **Build Debian package** GitHub Actions workflow to pass for that commit.
4. Create a draft `vVERSION` GitHub release targeting the verified commit and attach the package,
   `.manifest.json`, and `.manifest.json.sig` files.
5. Publish the draft with repository release immutability enabled. Confirm GitHub marks the release
   immutable and reports the expected package size and SHA-256 digest.
6. Use the previous PowerSifu release to check, download, authenticate, and install the new release
   through the same updater path users will run. Confirm that the updater selects each asset's
   repository-scoped GitHub API URL and still succeeds when the browser URL returns an HTTP error.
7. During a disposable-VM test, replace the user-cached package while the authorization prompt is
   open. The privileged helper must reject the replacement and leave the installed version unchanged.

Never replace an asset on an existing tag. Publish a new patch version so updater verification and
release history remain reproducible.
