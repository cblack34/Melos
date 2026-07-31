# Third-Party Notices

Melos is intended to remain separately licensed and closed source. The licenses below apply only to the identified third-party components and do not change the license of Melos source files.

When an externally distributed Melos artifact contains one of these components, include this notice with the artifact or its accompanying documentation. Installed package license files must remain intact. If an MPL-covered component is distributed in executable form, recipients must be told where its corresponding source is available. If a covered file is modified, that modified file must remain available under MPL-2.0.

The authoritative Mozilla Public License 2.0 text is available at <https://www.mozilla.org/MPL/2.0/>.

## Runtime dependencies

### certifi 2026.7.22

- License: Mozilla Public License 2.0
- Use: unmodified transitive backend dependency used by the HTTP/OpenAI transport
- Corresponding source: <https://pypi.org/project/certifi/2026.7.22/> and <https://github.com/certifi/python-certifi>
- License notice: <https://github.com/certifi/python-certifi/blob/master/LICENSE>
- Modified by Melos: no

### tqdm 4.70.0

- License: MPL-2.0 AND MIT, as declared by the package metadata and `LICENCE`
- Use: unmodified transitive backend dependency of the OpenAI SDK
- Corresponding source: <https://github.com/tqdm/tqdm/tree/v4.70.0>
- License notice: <https://github.com/tqdm/tqdm/blob/v4.70.0/LICENCE>
- Modified by Melos: no

## Build dependencies

### Lightning CSS 1.33.0

- License: Mozilla Public License 2.0
- Use: unmodified frontend build dependency of Vite; it is not application runtime code in the static `dist` output
- Corresponding source: <https://github.com/parcel-bundler/lightningcss/tree/v1.33.0>
- License notice: <https://github.com/parcel-bundler/lightningcss/blob/v1.33.0/LICENSE>
- Modified by Melos: no

## Distribution checklist

Before distributing a Docker image, installer, archive, or on-premises package outside the operating organization:

1. Re-audit both lockfiles for license or version changes.
2. Update this file to match the exact distributed versions.
3. Include this file in the distributed artifact or its accompanying documentation.
4. Preserve the third-party packages' own license and copyright notices.
5. Confirm the exact corresponding source locations remain available to recipients; retain an internal copy of each distributed version.
6. Publish any modifications to MPL-covered files under MPL-2.0. Do not copy MPL-covered code into Melos source files.

Hosted use that does not deliver server code or container images to users is not an external distribution of those server components. Browser-delivered assets are distributed to users and must be reviewed separately; Lightning CSS itself is not included in the current static `dist` output.
