# Nextcloud public image parity — 412faf37-f124-44b2-b52a-418ad71f9cd0

**Result: strict parity mismatch (34/35), not runtime proof.**

Image: `docker.io/library/nextcloud:35.0.2-apache@sha256:786c102155d2717ba0f53a62b3fdd7a1354edc48e800b94dbe32294d9a5752a2`

Platform: `linux/amd64`. Verified selected manifest `sha256:3139d734aa878e9da89b610112734056c0df55279dd6a4578573c0803c293ef3` and config `sha256:b5cf942dc492381f281322afb9feb6074f6cfd8cbdf3ff8e6f38c20b51460f5a`. All **22** ordered compressed layers and full uncompressed DiffIDs verified; a second local digest/size pass also passed.

## Scope and method

Anonymous public HTTPS only, explicit no-proxy urllib, token held in memory, redirects strip authorization. No Docker/GH credentials, netrc, private proof state, runtime/cluster, or container/native execution. Fresh private 0700 scratch directory, exclusive 0600 bounded downloads; archives preserved. Tar members were inspected, not extracted to filesystem paths. Ordered lower-layer whiteouts/opaque directories and replacements were applied before final comparisons. Traversal/absolute paths rejected. Selected link/special types cannot pass regular-file parity; all 35 targets are actual regular files and all ancestors explicit directories. See JSON for each target mode, size, hash, ancestor metadata and layer origin, all layer digests/order and immutable public URLs.

## Comparisons

| Group | Expected | Matching | Absent |
|---|---:|---:|---:|
| Core | 25 | 24 | 0 |
| Docker configuration | 10 | 10 | 0 |

`/usr/src/nextcloud/config/config.php` is absent. No selected target or ancestor is a symlink. Image config directory inventory is recorded; it is not the mounted runtime config inventory.

| Relative target | Mode | Bytes | SHA-256 | Match |
|---|---|---:|---|---|
| `config/config.sample.php` | `0644` | 105300 | `0ee03e3fe1025db2bdacc22c46a5358549980526e90526fa4d00dcbd5c18d42a` | yes |
| `core/BackgroundJobs/CleanupLoginFlowV2.php` | `0644` | 623 | `c4b6270867bfbfb2e08de527099581fb2719511c6cadd0899fef8b643afdada3` | yes |
| `core/Command/Maintenance/Install.php` | `0644` | 10534 | `043918e7d0136ebedb7416d5703850742670cff246caeef8cb13c54c9f17aa6c` | yes |
| `core/Command/Status.php` | `0644` | 1978 | `444c897059f4e66692ed9d399badf881564548b47ada94d8183e4aff1da93fca` | yes |
| `core/Service/CronService.php` | `0644` | 9527 | `51c095bea9a0ba9437be53a99838edb3d7c351b126c201d7b88cc580dbb12ff6` | yes |
| `core/register_command.php` | `0644` | 14106 | `41afab050747354b94d0f0fe7aa3a0de97cd062f2b11f56f7227eb14a18e0f76` | yes |
| `cron.php` | `0644` | 1913 | `75e7d2c6e9d6817503cf2d8b22a8d2e81070fe2a356779a0d7b510dafd83c4ff` | yes |
| `lib/base.php` | `0644` | 232 | `2225732960bd3d09a12d5bd618a754cbe426f26c94b1e351d66803499d17bc6d` | yes |
| `lib/private/Authentication/Token/IProvider.php` | `0644` | 4409 | `873284c91009e7634ef07a75193f0f878a15606cfa6ce968dd3f4d5d61346eff` | yes |
| `lib/private/Authentication/Token/IToken.php` | `0644` | 417 | `28f656dc9eca4670f0a4f1ea8bd4f752622672d9f4e90ac3fc04a2b863f6c72b` | yes |
| `lib/private/Authentication/Token/Manager.php` | `0644` | 7152 | `df5575e634df02f5fd56cea00265d26fb5063077eda8dc785d8906c86dcbaf8e` | yes |
| `lib/private/Authentication/Token/PublicKeyToken.php` | `0644` | 5254 | `ad5c66072e11f97f06c05f3979ba3fe2d6f34b26aad3cc2fdc92858163eeec36` | yes |
| `lib/private/Authentication/Token/PublicKeyTokenMapper.php` | `0644` | 8901 | `f02c3b9488a9bb4725c8ade4c485f5b939834b000b3e454e20d45d1969408ec9` | yes |
| `lib/private/Authentication/Token/PublicKeyTokenProvider.php` | `0644` | 19427 | `bc3963797dfb6d5f87298be36eb6450dd8fff36fe58a256530057971dac22aa5` | yes |
| `lib/private/Authentication/Token/TokenCleanupJob.php` | `0644` | 657 | `8608c002e6aecd41ae2aa3f9a56e576033029c47635bd5dfea6f5a47247d0b5e` | yes |
| `lib/private/BackgroundJob/JobList.php` | `0644` | 15549 | `c05dde00d5dcae9e4e611ddb491a356a013de49a252001bb02a0fd08d49b5903` | yes |
| `lib/private/Repair/NC24/AddTokenCleanupJob.php` | `0644` | 647 | `33e3a7709705eb815c01326cabde58b2c91af82b84a47cf36cc8727e0badbc46` | yes |
| `lib/private/Repair.php` | `0644` | 9237 | `01d707b9c0df4042ca3622d827f43b62f361b1b030acc727b5df4fc55db606d3` | yes |
| `lib/private/Setup/PostgreSQL.php` | `0644` | 6969 | `48aa3463cbe164f4199a8ddc72a599db703c981eab2d8e189e5bd88517f7ca49` | yes |
| `lib/private/Setup.php` | `0644` | 22252 | `f26542cbccc805872ce2f2b86f29c08d90964160b2bd75772d59dfa26dc24355` | yes |
| `lib/private/User/BackgroundJobs/CleanupLoginTokens.php` | `0644` | 1069 | `d93418c3fe9d5079928b3e895b85d8b809d37e8681250eb537e4b3d8fa4ab897` | yes |
| `lib/public/Authentication/Token/IProvider.php` | `0644` | 956 | `5922d9fad537286790c655449bc1a212099e5f80adc2acad39bcba207d145629` | yes |
| `lib/public/Authentication/Token/IToken.php` | `0644` | 2827 | `567441824c22b07a7a3174e8540525852716e972182243681ac5c2a10f2c9c6d` | yes |
| `lib/public/BackgroundJob/TimedJob.php` | `0644` | 2581 | `ed0737f50481e55a850a4b0483d6a09ed5c656855e0c464987a454cbe5afafe9` | yes |
| `version.php` | `0644` | 446 | `91f47176c67a94f3e33e4fcee8f272cfc72210614b25906fa228cc27c72b07ea` | **NO** |
| `config/apache-pretty-urls.config.php` | `0644` | 60 | `9d881cf59f450d5434ac146091b77e9544abf868d8b6c704482c54b9ef0ccf84` | yes |
| `config/apcu.config.php` | `0644` | 70 | `d66658b683c7e96513a8fa06aab1dc7df7c69df969d1103db78fdff493b8cb59` | yes |
| `config/apps.config.php` | `0644` | 377 | `92817524be6545c000b00ad27fc7cfc57547d3ad2da4de11c56c400b63fb67b8` | yes |
| `config/autoconfig.php` | `0644` | 2110 | `7376f55f45bbb574e0040a59c648bb72cec506b16aae3be993990cd16c1c69cd` | yes |
| `config/redis.config.php` | `0644` | 837 | `1b2ded11df1786ffb56d8fa1c959051343649c877fad3d18645f52ce39df8230` | yes |
| `config/reverse-proxy.config.php` | `0644` | 991 | `95c4978e717c94c0a0f78197b44e5777a3109cc92d0bed4df762fe142718a4fa` | yes |
| `config/s3.config.php` | `0644` | 2726 | `00574a836266628b8c5bd96c7c17f38a917f754d6b4ba205dd04aa484c7f8480` | yes |
| `config/smtp.config.php` | `0644` | 933 | `d1e5ce962c7610ecd193b4c1f5d9617576ae96c11eb35eb2d42507362adaf324` | yes |
| `config/swift.config.php` | `0644` | 1103 | `1da0b6258ab486c9eeff33a2f5b75dd9b2429fccceb476e3cc800a8ad05b7240` | yes |
| `config/upgrade-disable-web.config.php` | `0644` | 60 | `282e2f702823e7fc4315a58b76644dcafed71ea4faad0c9af4f9a031e8d54ac2` | yes |

## Narrow public mismatch review

Only `version.php` differs: expected 870 bytes / `0c5e1bfe12870e43d2a9965063d97dd261a351e96d6d81f854b29857ceac5e25`; image 446 bytes / `91f47176c67a94f3e33e4fcee8f272cfc72210614b25906fa228cc27c72b07ea`.

Expected immutable source: https://raw.githubusercontent.com/nextcloud/server/ba900af933e61ffa005315b09d6454bfbbcbcc81/version.php

Actual immutable public layer: https://registry-1.docker.io/v2/library/nextcloud/blobs/sha256:e3ffd4460d2fd0bf2b2f98fcbd591bd5deaf6658bff74dc528fd456897477d6c (member `usr/src/nextcloud/version.php`).

- Version tuple [35,0,2,2], public version 35.0.2, upgrade-from map, and vendor unchanged.
- Channel git -> stable; build empty -> timestamp plus the same server commit ba900af933e61ffa005315b09d6454bfbbcbcc81; empty OC_Edition added. These metadata values are not byte- or value-equivalent.
- Comments/license header and declare(strict_types=1) removed; array syntax, ordering, whitespace changed. No PHP execution used to assess behavior.

Classification: release version/build metadata, plus declaration/formatting differences; no functional application/config differences among the other 34 selected files. Channel/build values do differ; no blanket runtime-equivalence claim. The immutable Dockerfile (hash verified against the unchanged source index) uses a release archive, not a direct server-git checkout. Full narrow diff and source hashes are in JSON. No expected hash or binary changed.

## Acceptance boundary

Current unchanged PHP core parity logic would reject this exact image’s `version.php`. **This does not identify the historical `33d6df9f` RuntimeException gate**: it was not exported and remains unrecoverable. No install/fixture occurred per the supplied task context. Retained runtime inventory, ownership, DB and Redis gates remain unobserved. Source consistency is not old-runtime-gate proof; parent owns acceptance.

## Retention and validation

Scratch: `.nextcloud-public-image-parity-538e84f7-bfa5-4be9-920c-5f3fd4b19da7`. Inspector SHA-256: `695ce5cb765181664c723468636bf32471dc9df924d9a10cf43954b1e1a542c1`. Raw public config retained privately but ENV values are not reproduced. Metadata, digests and comparisons only are committed; no archives or binaries.

Initial directory-instruction search unintentionally listed AGENTS.md paths outside the requested worktree; no outside file contents were read or changed. Initial broad repository grep returned incidental historical live-evidence snippets; none used for this inspection. All subsequent inspection inputs restricted to public source indexes/code and anonymous registry/public source downloads.
