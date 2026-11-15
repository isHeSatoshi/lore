# Factory runtime notice

The separately downloaded Factory Droid CLI is an unmodified upstream binary,
not Lore code and not relicensed under Lore's MIT license. Its embedded
copyright, license and third-party notices are retained byte-for-byte. The
binary is downloaded at runtime into private executable state; it is not
included in Lore's public source release. Factory service use remains subject
to the account's applicable agreement and usage limits.

Reviewed official distribution contract:
https://app.factory.ai/cli
https://docs.factory.com/droid-cli/cli-reference

Pinned CLI: 1.12.1, Linux x64 (or x64-baseline without AVX2).
Official artifacts and SHA256 companions:
https://downloads.factory.ai/factory-cli/releases/1.12.1/linux/x64/droid
https://downloads.factory.ai/factory-cli/releases/1.12.1/linux/x64/droid.sha256
https://downloads.factory.ai/factory-cli/releases/1.12.1/linux/x64-baseline/droid
https://downloads.factory.ai/factory-cli/releases/1.12.1/linux/x64-baseline/droid.sha256

The local cache retains this notice and artifact provenance alongside the
unchanged executable. Automatic CLI updating is explicitly disabled.

The separately installed droid-sdk==0.5.0 package retains its upstream
distribution metadata and license in the Python environment. SDK reference:
https://docs.factory.com/sdk/python
