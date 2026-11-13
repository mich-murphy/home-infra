# Anonymous pinned-image metadata inspection

Inspection time (UTC): 2026-11-12T06:59:13.250337+00:00

## Decision: offline paths established; live availability remains HOLD

This independent inspection concerns only diagnostic profile `e0a056fa`: serial `/usr/bin/timeout 2 /bin/cat /sys/fs/cgroup/<fixedfile>` inside the pinned PostgreSQL 384Mi and Redis 64Mi containers. It neither changes nor approves that command, the image pins, or limits. No image binaries or containers were executed. No proof/production API, SSH, private proof state, credentials, receipts, or fixtures were accessed. Parent retains acceptance and all grants. The original failed-run/backend-forensics gap is unchanged.

Verified metadata is NOT live exec availability, a successful cgroup read, runtime permissions, ABI acceptance, resource-limit acceptance, or proof/production authorization. No kernel, cgroup mount, deployed architecture, container security context, runtime user, dynamic-library dependency closure, symbol versions, or live signal behavior was tested. All such conclusions remain HOLD.

## Acquisition and reconstruction

Public GitHub repository searches and GNU documentation were consulted before registry acquisition. Requests used Python HTTPS directly, without Docker/GitHub credential consultation. Docker Hub anonymous pull bearer tokens stayed in memory and were not printed or saved. An initial malformed anonymous scope produced HTTP 401; the corrected public repository scope succeeded. No authenticated account was used. Registry response digest equality was checked locally rather than trusting response headers.

For each exact index digest, selected the sole linux/amd64 descriptor, verified manifest and config SHA-256 and descriptor sizes, checked config platform, downloaded layers in manifest order, checked compressed SHA-256 and size, and checked SHA-256 of the complete decompressed tar against each config DiffID. Reconstructed a virtual filesystem in memory: no tar extraction into host paths; absolute/parent-traversal archive names rejected; whiteouts applied to prior-layer entries before additions; opaque-whiteout handling implemented (none observed); replacement semantics preserve merged directories. Hardlinks bind to earlier node objects; all observed hardlinks had existing targets, none occur in requested paths. Relative and absolute symlink targets are walked component by component, including every directory ancestor, with a 40-link bound.

All three relevant regular files occur exactly once per image, in layer 0; subsequent layers do not replace them. Root `/` is an explicit layer-0 directory, uid/gid 0:0, mode 0755, in both images. All final directory ancestors in the published resolution traces are uid/gid 0:0 mode 0755. Symlinks are uid/gid 0:0 mode 0777. Root ancestry is recorded separately in the audit below.

## Common final file facts

| Requested / resolved file | Type/mode | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `/usr/bin/timeout` → `/usr/bin/timeout` | regular 0755, uid/gid 0:0 | 47984 | `6ca1891dfc0b05d7680770c2884c0391b92467c7bb6500a5c84677e6481739f1` |
| `/bin/cat` → `/usr/bin/cat` | regular 0755, uid/gid 0:0 | 47592 | `8a5c20c3400a4058a487cd806111cc5138ef4d0fbc6714ff67c9432e38c2705a` |
| `/lib64/ld-linux-x86-64.so.2` → `/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2` | regular 0755, uid/gid 0:0 | 225672 | `c8438e4fde1934e61c88311633f00949ff645d5c04cdb8671fa3d78164d2f307` |

These bytes are identical across both pinned images. `timeout` and `cat` are ELF64 little-endian, machine 62 (x86-64); both request interpreter `/lib64/ld-linux-x86-64.so.2`. That resolves through `/lib64 -> usr/lib64` and `/usr/lib64/ld-linux-x86-64.so.2 -> ../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2` to the regular executable x86-64 ELF loader above (no PT_INTERP on loader). `/bin -> usr/bin`, hence `/bin/cat -> /usr/bin/cat`. `/usr/bin/timeout` is directly regular, not an applet link.

The layer package database in both images reports `coreutils 9.7-3` and `libc6 2.41-12+deb13u4`, architecture amd64, installed. This is package-database evidence, not a rebuilt-binary/source equivalence claim. GNU coreutils v9.7 source and documentation describe `timeout [OPTION] DURATION COMMAND [ARG]...`, default seconds, default TERM, and forwarding command arguments via execvp. Accordingly `2 /bin/cat /sys/fs/cgroup/<fixedfile>` has the expected upstream syntax. No shell expansion is required for these operands. **Plain `timeout 2` is not a guaranteed hard two-second kill deadline**: it sends TERM by default, has no kill-after escalation, and actual timing depends on system conditions. Nothing here establishes a live successful invocation or changes the prescribed command.

## Exact chains, ordered layers, final resolutions

Registry source URL for each manifest/config/layer is `https://registry-1.docker.io/v2/library/<image>/manifests/<digest>` or `/blobs/<digest>` as applicable. The records below publish metadata only; config ENV and history contents are intentionally omitted. Layer ordinals are zero-based; all listed digest/DiffID pairs were verified.

### docker.io/library/postgres

```json
{
  "image": "docker.io/library/postgres",
  "index_digest": "sha256:e3d24f6906d0760bf4da0dae872415391ededefad23fd471c47dc53b0ddf3c42",
  "index_media_type": "application/vnd.oci.image.index.v1+json",
  "platform_descriptor": {
    "annotations": {
      "com.docker.official-images.bashbrew.arch": "amd64",
      "org.opencontainers.image.base.digest": "sha256:7378260c0a098d27ac206225db5e7d92b8c7c84ea7afccc86eeb513756bbd392",
      "org.opencontainers.image.base.name": "debian:trixie-slim",
      "org.opencontainers.image.created": "2026-11-05T07:29:27Z",
      "org.opencontainers.image.revision": "e00e1bd34ec5c8a8e7ad89b273b3d42efaf6d5bc",
      "org.opencontainers.image.source": "https://github.com/docker-library/postgres.git#e00e1bd34ec5c8a8e7ad89b273b3d42efaf6d5bc:18/trixie",
      "org.opencontainers.image.url": "https://hub.docker.com/_/postgres",
      "org.opencontainers.image.version": "18.6"
    },
    "digest": "sha256:e923a22ac074261dd73970c57edf659475bf0497cb9456f17d98ed7cdd3ca913",
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "platform": {
      "architecture": "amd64",
      "os": "linux"
    },
    "size": 3439
  },
  "manifest_digest": "sha256:e923a22ac074261dd73970c57edf659475bf0497cb9456f17d98ed7cdd3ca913",
  "manifest_media_type": "application/vnd.oci.image.manifest.v1+json",
  "config_descriptor": {
    "mediaType": "application/vnd.oci.image.config.v1+json",
    "digest": "sha256:8bca9649e52d948114ccc8164b55b7ab26b64e729893e420114bb5c87bf7c7cc",
    "size": 10046
  },
  "config_platform": {
    "os": "linux",
    "architecture": "amd64"
  },
  "layers": [
    {
      "ordinal": 0,
      "digest": "sha256:37fb86c2a767b88d500c6872195f88078f64765fe0d2f9cc375cc2efbd4c0a41",
      "size": 29856132,
      "diff_id": "sha256:dd57f90311a2567b55ff22eeacff1602fd04ad7566e315957731359eab173b90",
      "uncompressed_size": 81295360,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 1,
      "digest": "sha256:e9dd37612d7b4ff5055c29761c1f0749046cd441a0c25bcea140668c96e90e8b",
      "size": 1168,
      "diff_id": "sha256:52f3071f1d7131bfad2863427c8052c8c0baee5e1e815ae3ef8f4ff2eb0379c2",
      "uncompressed_size": 12288,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 2,
      "digest": "sha256:369949eb022916f3146429477ecab4755d31a11fcce70162eda5bc5e1dd5c3c6",
      "size": 6443006,
      "diff_id": "sha256:1929700ecc572e7f07e0840e13c801be17117ac4eb1f4c90acdb966a943616a4",
      "uncompressed_size": 16135680,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 3,
      "digest": "sha256:7e0f86eb8508984ab8e61d55b8dbfe900c95ef73de1b45b505f87bb6c17a907f",
      "size": 1256763,
      "diff_id": "sha256:ba31e8ee45fa238f04327ce641175b8f57bee130331e6decca89a6394d89014e",
      "uncompressed_size": 3652096,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 4,
      "digest": "sha256:da434b32d4803cadad93923bc2dc4ab9f85685873a5999c91264edf23f5e409e",
      "size": 8203863,
      "diff_id": "sha256:67a43fd9d744630058b2aaf927bf2547187ca7c08e94171f7cbac5c62b6037c0",
      "uncompressed_size": 26182144,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 5,
      "digest": "sha256:bcc75ab4e0104e18cb8684dbd012d05e5bd9bdefbd5da7c93bf41fe931446680",
      "size": 1311723,
      "diff_id": "sha256:570b9e7408889eb4320c65e3be7d4499d8027eb6f8163e40b9c1b549d63058bf",
      "uncompressed_size": 3484160,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 6,
      "digest": "sha256:a28de24f57c01d5ed53c5a829b762171f2c37369a391a403b4fdd3304b8e0c5b",
      "size": 116,
      "diff_id": "sha256:eeb35168bedc1d6b84401a53e6529661888887edfee58e88ba9e41f5f1e6b48d",
      "uncompressed_size": 1536,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 7,
      "digest": "sha256:6d141360b363af231c3eddeac824438fc2268e983e9cbc0194c43d2d861aecf4",
      "size": 3145,
      "diff_id": "sha256:bfd4e1dec4b56a5feb5aad6ed280d1f0bbb7b570d9460e072ad87ce9e10bf59c",
      "uncompressed_size": 7680,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 8,
      "digest": "sha256:fcd0e951406297ac5814e0485ac62a981805fe202829537876931bc18b8e10e5",
      "size": 115397881,
      "diff_id": "sha256:f7d777c83930b6268325bab35eac40394b9908a2a4c8b39eaa9ee35bbee9980d",
      "uncompressed_size": 333103104,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 9,
      "digest": "sha256:cbe0afc9eb7bab5cc2b78d0a6d2157d77364a2f6322e34d76614a12fc8c9d33a",
      "size": 19426,
      "diff_id": "sha256:84f7b9d615df09c4f0806a9cd350d49506758c8e10a6217d8815d6c8f0ef2989",
      "uncompressed_size": 74752,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 10,
      "digest": "sha256:fc6c21aca07c567e2b19461ec7c62c0e8b4303c10f9ceb0ffd8e80bc67aa533b",
      "size": 127,
      "diff_id": "sha256:bf568845251574b5f9ffc9406d30a32384bfcbfdc6094f0fbdd9afdef91a5d58",
      "uncompressed_size": 2048,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 11,
      "digest": "sha256:2a59118cca0e865fbccc1e706069b45dc9210c9d9fc4e58644645fbf24f17d57",
      "size": 6107,
      "diff_id": "sha256:3cb025fd61e9b7c661c94fda31e8224d1b3092fac4542caf4f2f944b7cfee5b5",
      "uncompressed_size": 20992,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 12,
      "digest": "sha256:eac25292b61391b522f697b80462618b0975d82274583089e3152f9eab8400e0",
      "size": 184,
      "diff_id": "sha256:9cce6a5076c5cc5246708c4a0277c34a090f063be96e7012523c7398bc4f87ce",
      "uncompressed_size": 3072,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    }
  ],
  "whiteouts": [
    {
      "layer": 2,
      "path": "etc/alternatives/.wh.pager.1.gz",
      "kind": "remove"
    },
    {
      "layer": 4,
      "path": "var/lib/apt/lists/.wh.auxfiles",
      "kind": "remove"
    }
  ],
  "hardlinks": [
    {
      "layer": 0,
      "path": "usr/bin/perl5.40.1",
      "target": "usr/bin/perl",
      "resolved_at_entry": true
    },
    {
      "layer": 8,
      "path": "usr/bin/perlthanks",
      "target": "usr/bin/perlbug",
      "resolved_at_entry": true
    }
  ],
  "targets": [
    {
      "requested": "/usr/bin/timeout",
      "resolution": [
        {
          "type": "directory",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 12,
          "path": "usr"
        },
        {
          "type": "directory",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 8,
          "path": "usr/bin"
        },
        {
          "type": "regular",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 47984,
          "layer": 0,
          "path": "usr/bin/timeout"
        }
      ],
      "final": {
        "type": "regular",
        "mode": "0o755",
        "uid": 0,
        "gid": 0,
        "size": 47984,
        "layer": 0,
        "path": "usr/bin/timeout"
      },
      "sha256": "6ca1891dfc0b05d7680770c2884c0391b92467c7bb6500a5c84677e6481739f1",
      "bytes": 47984,
      "executable_mode": true,
      "elf": {
        "class": 2,
        "machine": 62,
        "architecture": "x86-64",
        "interpreter": "/lib64/ld-linux-x86-64.so.2"
      },
      "loader": {
        "requested": "/lib64/ld-linux-x86-64.so.2",
        "resolution": [
          {
            "type": "symlink",
            "mode": "0o777",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "lib64",
            "target": "usr/lib64"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 12,
            "path": "usr"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib64"
          },
          {
            "type": "symlink",
            "mode": "0o777",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib64/ld-linux-x86-64.so.2",
            "target": "../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 8,
            "path": "usr/lib"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 8,
            "path": "usr/lib/x86_64-linux-gnu"
          },
          {
            "type": "regular",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 225672,
            "layer": 0,
            "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
          }
        ],
        "final": {
          "type": "regular",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 225672,
          "layer": 0,
          "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
        },
        "sha256": "c8438e4fde1934e61c88311633f00949ff645d5c04cdb8671fa3d78164d2f307",
        "bytes": 225672,
        "executable_mode": true,
        "elf": {
          "class": 2,
          "machine": 62,
          "architecture": "x86-64"
        }
      }
    },
    {
      "requested": "/bin/cat",
      "resolution": [
        {
          "type": "symlink",
          "mode": "0o777",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 0,
          "path": "bin",
          "target": "usr/bin"
        },
        {
          "type": "directory",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 12,
          "path": "usr"
        },
        {
          "type": "directory",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 8,
          "path": "usr/bin"
        },
        {
          "type": "regular",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 47592,
          "layer": 0,
          "path": "usr/bin/cat"
        }
      ],
      "final": {
        "type": "regular",
        "mode": "0o755",
        "uid": 0,
        "gid": 0,
        "size": 47592,
        "layer": 0,
        "path": "usr/bin/cat"
      },
      "sha256": "8a5c20c3400a4058a487cd806111cc5138ef4d0fbc6714ff67c9432e38c2705a",
      "bytes": 47592,
      "executable_mode": true,
      "elf": {
        "class": 2,
        "machine": 62,
        "architecture": "x86-64",
        "interpreter": "/lib64/ld-linux-x86-64.so.2"
      },
      "loader": {
        "requested": "/lib64/ld-linux-x86-64.so.2",
        "resolution": [
          {
            "type": "symlink",
            "mode": "0o777",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "lib64",
            "target": "usr/lib64"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 12,
            "path": "usr"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib64"
          },
          {
            "type": "symlink",
            "mode": "0o777",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib64/ld-linux-x86-64.so.2",
            "target": "../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 8,
            "path": "usr/lib"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 8,
            "path": "usr/lib/x86_64-linux-gnu"
          },
          {
            "type": "regular",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 225672,
            "layer": 0,
            "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
          }
        ],
        "final": {
          "type": "regular",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 225672,
          "layer": 0,
          "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
        },
        "sha256": "c8438e4fde1934e61c88311633f00949ff645d5c04cdb8671fa3d78164d2f307",
        "bytes": 225672,
        "executable_mode": true,
        "elf": {
          "class": 2,
          "machine": 62,
          "architecture": "x86-64"
        }
      }
    }
  ],
  "packages": [
    {
      "Package": "coreutils",
      "Version": "9.7-3",
      "Architecture": "amd64",
      "Status": "install ok installed"
    },
    {
      "Package": "libc6",
      "Version": "2.41-12+deb13u4",
      "Architecture": "amd64",
      "Status": "install ok installed"
    }
  ],
  "final_node_count": 9663
}
```

### docker.io/library/redis

```json
{
  "image": "docker.io/library/redis",
  "index_digest": "sha256:1f88291b4c57bdf249f02eb085a8669889b2d2954e91d4de5118a5da6b78dd53",
  "index_media_type": "application/vnd.oci.image.index.v1+json",
  "platform_descriptor": {
    "annotations": {
      "com.docker.official-images.bashbrew.arch": "amd64",
      "org.opencontainers.image.base.digest": "sha256:7378260c0a098d27ac206225db5e7d92b8c7c84ea7afccc86eeb513756bbd392",
      "org.opencontainers.image.base.name": "debian:trixie-slim",
      "org.opencontainers.image.created": "2026-11-05T07:30:42Z",
      "org.opencontainers.image.revision": "8fd1238a62e5a6090d826e6d5fc53de6ce5f8a82",
      "org.opencontainers.image.source": "https://github.com/redis/docker-library-redis.git#8fd1238a62e5a6090d826e6d5fc53de6ce5f8a82:debian",
      "org.opencontainers.image.url": "https://hub.docker.com/_/redis",
      "org.opencontainers.image.version": "8.10.3"
    },
    "digest": "sha256:e2728231060693472a8efb488dd139a8142a01bd0612ae70429bf5b5be924be1",
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "platform": {
      "architecture": "amd64",
      "os": "linux"
    },
    "size": 2287
  },
  "manifest_digest": "sha256:e2728231060693472a8efb488dd139a8142a01bd0612ae70429bf5b5be924be1",
  "manifest_media_type": "application/vnd.oci.image.manifest.v1+json",
  "config_descriptor": {
    "mediaType": "application/vnd.oci.image.config.v1+json",
    "digest": "sha256:978293674c6b207a799aa6003064828846a7771cd521603c41e9a4c7f28ec4dc",
    "size": 6762
  },
  "config_platform": {
    "os": "linux",
    "architecture": "amd64"
  },
  "layers": [
    {
      "ordinal": 0,
      "digest": "sha256:37fb86c2a767b88d500c6872195f88078f64765fe0d2f9cc375cc2efbd4c0a41",
      "size": 29856132,
      "diff_id": "sha256:dd57f90311a2567b55ff22eeacff1602fd04ad7566e315957731359eab173b90",
      "uncompressed_size": 81295360,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 1,
      "digest": "sha256:e7012240c0fb4c5ab49ce37e865ffdff3c6aabd499ee9cdaae9ecde5e34a0fc8",
      "size": 1103,
      "diff_id": "sha256:1f6a841b63ec62fb17c7a6a80f37eb8529d014c19705b8a3fdfa18f5afecbafc",
      "uncompressed_size": 10752,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 2,
      "digest": "sha256:f0edb8c45951dafb7d29775303430976f3e5e6c995c80bfb99d5e8b8f9633b6a",
      "size": 828,
      "diff_id": "sha256:12ff63ac704dd1e6bc5789455d5512da098dc3520d495d87d5120afbb6866c4f",
      "uncompressed_size": 10240,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 3,
      "digest": "sha256:3e1ffb902068b145dd5d419e81206615f67fbf52a289686c21b2e408faa3ba26",
      "size": 25739188,
      "diff_id": "sha256:87c683a16d253f57007710cfd3bbcc9814617f4888d8493f9fd7f553fb6bd99c",
      "uncompressed_size": 67239424,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 4,
      "digest": "sha256:3ecf3ccdb02db4299c79f6d13b71885e59b6ba90acff1803bce4a40a7350224b",
      "size": 96,
      "diff_id": "sha256:cf17b92ffb9ae632e9f0df1b95d67295bca4ad1d38aff9762f95f648ada0d150",
      "uncompressed_size": 1536,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 5,
      "digest": "sha256:4f4fb700ef54461cfa02571ae0db9a0dc1e0cdb5577484a6d75e68dc38e8acc1",
      "size": 32,
      "diff_id": "sha256:5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef",
      "uncompressed_size": 1024,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    },
    {
      "ordinal": 6,
      "digest": "sha256:85b5f7d2996b3258898c504b45349fde4565af41e104d4d659a171a5b4093200",
      "size": 2108,
      "diff_id": "sha256:b74a5b51fa8821afc556015feabfeac1624d69796b9ab5591f89e38ffaaf02c8",
      "uncompressed_size": 8192,
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip"
    }
  ],
  "whiteouts": [
    {
      "layer": 3,
      "path": "var/cache/debconf/.wh.config.dat",
      "kind": "remove"
    },
    {
      "layer": 3,
      "path": "var/cache/debconf/.wh.config.dat-old",
      "kind": "remove"
    },
    {
      "layer": 3,
      "path": "var/cache/debconf/.wh.passwords.dat",
      "kind": "remove"
    },
    {
      "layer": 3,
      "path": "var/cache/debconf/.wh.templates.dat",
      "kind": "remove"
    },
    {
      "layer": 3,
      "path": "var/cache/debconf/.wh.templates.dat-old",
      "kind": "remove"
    },
    {
      "layer": 3,
      "path": "var/cache/debconf/.wh.tmp.ci",
      "kind": "remove"
    }
  ],
  "hardlinks": [
    {
      "layer": 0,
      "path": "usr/bin/perl5.40.1",
      "target": "usr/bin/perl",
      "resolved_at_entry": true
    }
  ],
  "targets": [
    {
      "requested": "/usr/bin/timeout",
      "resolution": [
        {
          "type": "directory",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 6,
          "path": "usr"
        },
        {
          "type": "directory",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 0,
          "path": "usr/bin"
        },
        {
          "type": "regular",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 47984,
          "layer": 0,
          "path": "usr/bin/timeout"
        }
      ],
      "final": {
        "type": "regular",
        "mode": "0o755",
        "uid": 0,
        "gid": 0,
        "size": 47984,
        "layer": 0,
        "path": "usr/bin/timeout"
      },
      "sha256": "6ca1891dfc0b05d7680770c2884c0391b92467c7bb6500a5c84677e6481739f1",
      "bytes": 47984,
      "executable_mode": true,
      "elf": {
        "class": 2,
        "machine": 62,
        "architecture": "x86-64",
        "interpreter": "/lib64/ld-linux-x86-64.so.2"
      },
      "loader": {
        "requested": "/lib64/ld-linux-x86-64.so.2",
        "resolution": [
          {
            "type": "symlink",
            "mode": "0o777",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "lib64",
            "target": "usr/lib64"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 6,
            "path": "usr"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib64"
          },
          {
            "type": "symlink",
            "mode": "0o777",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib64/ld-linux-x86-64.so.2",
            "target": "../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib/x86_64-linux-gnu"
          },
          {
            "type": "regular",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 225672,
            "layer": 0,
            "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
          }
        ],
        "final": {
          "type": "regular",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 225672,
          "layer": 0,
          "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
        },
        "sha256": "c8438e4fde1934e61c88311633f00949ff645d5c04cdb8671fa3d78164d2f307",
        "bytes": 225672,
        "executable_mode": true,
        "elf": {
          "class": 2,
          "machine": 62,
          "architecture": "x86-64"
        }
      }
    },
    {
      "requested": "/bin/cat",
      "resolution": [
        {
          "type": "symlink",
          "mode": "0o777",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 0,
          "path": "bin",
          "target": "usr/bin"
        },
        {
          "type": "directory",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 6,
          "path": "usr"
        },
        {
          "type": "directory",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 0,
          "layer": 0,
          "path": "usr/bin"
        },
        {
          "type": "regular",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 47592,
          "layer": 0,
          "path": "usr/bin/cat"
        }
      ],
      "final": {
        "type": "regular",
        "mode": "0o755",
        "uid": 0,
        "gid": 0,
        "size": 47592,
        "layer": 0,
        "path": "usr/bin/cat"
      },
      "sha256": "8a5c20c3400a4058a487cd806111cc5138ef4d0fbc6714ff67c9432e38c2705a",
      "bytes": 47592,
      "executable_mode": true,
      "elf": {
        "class": 2,
        "machine": 62,
        "architecture": "x86-64",
        "interpreter": "/lib64/ld-linux-x86-64.so.2"
      },
      "loader": {
        "requested": "/lib64/ld-linux-x86-64.so.2",
        "resolution": [
          {
            "type": "symlink",
            "mode": "0o777",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "lib64",
            "target": "usr/lib64"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 6,
            "path": "usr"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib64"
          },
          {
            "type": "symlink",
            "mode": "0o777",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib64/ld-linux-x86-64.so.2",
            "target": "../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib"
          },
          {
            "type": "directory",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 0,
            "layer": 0,
            "path": "usr/lib/x86_64-linux-gnu"
          },
          {
            "type": "regular",
            "mode": "0o755",
            "uid": 0,
            "gid": 0,
            "size": 225672,
            "layer": 0,
            "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
          }
        ],
        "final": {
          "type": "regular",
          "mode": "0o755",
          "uid": 0,
          "gid": 0,
          "size": 225672,
          "layer": 0,
          "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2"
        },
        "sha256": "c8438e4fde1934e61c88311633f00949ff645d5c04cdb8671fa3d78164d2f307",
        "bytes": 225672,
        "executable_mode": true,
        "elf": {
          "class": 2,
          "machine": 62,
          "architecture": "x86-64"
        }
      }
    }
  ],
  "packages": [
    {
      "Package": "coreutils",
      "Version": "9.7-3",
      "Architecture": "amd64",
      "Status": "install ok installed"
    },
    {
      "Package": "libc6",
      "Version": "2.41-12+deb13u4",
      "Architecture": "amd64",
      "Status": "install ok installed"
    }
  ],
  "final_node_count": 3302
}
```

## Root and second-pass archive audit

```json
[
  {
    "image": "postgres",
    "root_entries": [
      {
        "layer": 0,
        "type": "directory",
        "mode": "0o755",
        "uid": 0,
        "gid": 0
      }
    ],
    "target_entries": [
      {
        "layer": 0,
        "path": "usr/bin/cat",
        "sha256": "8a5c20c3400a4058a487cd806111cc5138ef4d0fbc6714ff67c9432e38c2705a",
        "size": 47592
      },
      {
        "layer": 0,
        "path": "usr/bin/timeout",
        "sha256": "6ca1891dfc0b05d7680770c2884c0391b92467c7bb6500a5c84677e6481739f1",
        "size": 47984
      },
      {
        "layer": 0,
        "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
        "sha256": "c8438e4fde1934e61c88311633f00949ff645d5c04cdb8671fa3d78164d2f307",
        "size": 225672
      }
    ],
    "manifest_and_config_descriptor_sizes_verified": true,
    "all_archive_hardlink_targets_bound_at_entry": true
  },
  {
    "image": "redis",
    "root_entries": [
      {
        "layer": 0,
        "type": "directory",
        "mode": "0o755",
        "uid": 0,
        "gid": 0
      }
    ],
    "target_entries": [
      {
        "layer": 0,
        "path": "usr/bin/cat",
        "sha256": "8a5c20c3400a4058a487cd806111cc5138ef4d0fbc6714ff67c9432e38c2705a",
        "size": 47592
      },
      {
        "layer": 0,
        "path": "usr/bin/timeout",
        "sha256": "6ca1891dfc0b05d7680770c2884c0391b92467c7bb6500a5c84677e6481739f1",
        "size": 47984
      },
      {
        "layer": 0,
        "path": "usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
        "sha256": "c8438e4fde1934e61c88311633f00949ff645d5c04cdb8671fa3d78164d2f307",
        "size": 225672
      }
    ],
    "manifest_and_config_descriptor_sizes_verified": true,
    "all_archive_hardlink_targets_bound_at_entry": true
  }
]
```

## Public sources (response hashes; mutable search results are discovery only)

```json
[
  {
    "url": "https://api.github.com/search/repositories?q=docker-library+postgres",
    "status": 200,
    "sha256": "fc103eeb94f6c4f661b56fd3ebb8640da85b706d4bc376d762495d058de4dbaf",
    "bytes": 49057
  },
  {
    "url": "https://api.github.com/search/repositories?q=docker-library+redis",
    "status": 200,
    "sha256": "b5425c73d1a9169017f5050e439651e8976203aa165ae4486cb11d754f1fcb61",
    "bytes": 43109
  },
  {
    "url": "https://www.gnu.org/software/coreutils/manual/html_node/timeout-invocation.html",
    "status": 200,
    "sha256": "8e0c74666b842b0f745455f9e853ba65f82776f379d57640d26291555e85259c",
    "bytes": 11813
  },
  {
    "url": "https://raw.githubusercontent.com/docker-library/postgres/master/18/bookworm/Dockerfile",
    "status": 200,
    "sha256": "ea58330e69627cb7b626043c7da44bc227ccd935126c239ceb33c8b4ddf745c2",
    "bytes": 10140
  },
  {
    "url": "https://raw.githubusercontent.com/redis/docker-library-redis/master/8.0/debian/Dockerfile",
    "error": "HTTP Error 404: Not Found"
  },
  {
    "url": "https://raw.githubusercontent.com/coreutils/coreutils/v9.7/src/timeout.c",
    "sha256": "e11dc2897e468a2fc4bcf44dc3643f08f9ae063b7ce03b88def9dd866250c8ad",
    "bytes": 19329
  },
  {
    "url": "https://raw.githubusercontent.com/coreutils/coreutils/v9.7/doc/coreutils.texi",
    "sha256": "39b126752866fff675e462bd44d76f3e034abafe462a069cebd53ef39fc53eca",
    "bytes": 667701
  },
  {
    "url": "https://raw.githubusercontent.com/docker-library/postgres/e00e1bd34ec5c8a8e7ad89b273b3d42efaf6d5bc/18/trixie/Dockerfile",
    "sha256": "5015df2bb657087d0b65204b6abb809c6ca7bbac472e5d21c1246c718087dacf",
    "bytes": 10146
  },
  {
    "url": "https://raw.githubusercontent.com/redis/docker-library-redis/8fd1238a62e5a6090d826e6d5fc53de6ce5f8a82/debian/Dockerfile",
    "sha256": "8bf74f53f5298b996f08960e0425e187eacf7406eb4e97eb0aaf64c8e6391bb8",
    "bytes": 5597
  },
  {
    "url": "https://raw.githubusercontent.com/opencontainers/image-spec/v1.1.1/layer.md",
    "sha256": "5d65842c37a770fdd7e76993facea8c3e7256a0c0241ca38884dd52f67fb3e0f",
    "bytes": 15214
  }
]
```

The initially fetched PostgreSQL master/bookworm Dockerfile is background only, not the pinned image build. The Redis guessed master path returned 404; pinned revision URLs obtained from verified index annotations were subsequently fetched successfully. Path conclusions rely on verified final layers, never Dockerfile inference.

## Private artifact custody and hashes

Artifacts remain only in newly created directory `/tmp/talos-image-inspection-dcef7369-5621-4882-baf2-84a8fdc61db8` outside Git, mode 0700. Current permissions of every file were checked as 0600. Downloads, manifests, source responses, corrected helper and reports used O_EXCL create and flush/fsync; previous artifact files were not overwritten. Important manifests/configs and completed layer files were fsynced. No token artifact exists.

**Procedural limitation:** the initial helper `inspect.py` was created through the editor tool (rather than an explicitly O_EXCL/0600 creation) and immediately chmodded to 0600 before use; the enclosing directory was already 0700 throughout. The corrected `inspect-v2.py` and all acquisition artifacts used explicit O_EXCL/0600. Thus this does not claim literal full compliance with the requested creation primitive for that initial helper.

Raw fetched config/layer/source artifacts are not committed. Their hashes below permit local corroboration without publishing image ENV values, raw binaries, or encoded data. SHA-256 is over exact stored bytes.

| Private artifact basename | Bytes | SHA-256 |
| --- | ---: | --- |
| `audit.json` | 1799 | `71a3a747e9bdb41d407fcd477be50b8d66e97cda9b9c10083bb735c87b42e11b` |
| `inspect-v2.py` | 7852 | `2d281ce9f1ce9422a24832cfa1192afa8691d11d9c4eb63764fbd9415b432ced` |
| `inspect.py` | 7852 | `2d84de383b85f31a9aaf96308170539c7cd8ef63ae38b6adb14986684d4577f5` |
| `postgres-layer-0.blob` | 29856132 | `37fb86c2a767b88d500c6872195f88078f64765fe0d2f9cc375cc2efbd4c0a41` |
| `postgres-layer-0.tar` | 81295360 | `dd57f90311a2567b55ff22eeacff1602fd04ad7566e315957731359eab173b90` |
| `postgres-layer-1.blob` | 1168 | `e9dd37612d7b4ff5055c29761c1f0749046cd441a0c25bcea140668c96e90e8b` |
| `postgres-layer-1.tar` | 12288 | `52f3071f1d7131bfad2863427c8052c8c0baee5e1e815ae3ef8f4ff2eb0379c2` |
| `postgres-layer-10.blob` | 127 | `fc6c21aca07c567e2b19461ec7c62c0e8b4303c10f9ceb0ffd8e80bc67aa533b` |
| `postgres-layer-10.tar` | 2048 | `bf568845251574b5f9ffc9406d30a32384bfcbfdc6094f0fbdd9afdef91a5d58` |
| `postgres-layer-11.blob` | 6107 | `2a59118cca0e865fbccc1e706069b45dc9210c9d9fc4e58644645fbf24f17d57` |
| `postgres-layer-11.tar` | 20992 | `3cb025fd61e9b7c661c94fda31e8224d1b3092fac4542caf4f2f944b7cfee5b5` |
| `postgres-layer-12.blob` | 184 | `eac25292b61391b522f697b80462618b0975d82274583089e3152f9eab8400e0` |
| `postgres-layer-12.tar` | 3072 | `9cce6a5076c5cc5246708c4a0277c34a090f063be96e7012523c7398bc4f87ce` |
| `postgres-layer-2.blob` | 6443006 | `369949eb022916f3146429477ecab4755d31a11fcce70162eda5bc5e1dd5c3c6` |
| `postgres-layer-2.tar` | 16135680 | `1929700ecc572e7f07e0840e13c801be17117ac4eb1f4c90acdb966a943616a4` |
| `postgres-layer-3.blob` | 1256763 | `7e0f86eb8508984ab8e61d55b8dbfe900c95ef73de1b45b505f87bb6c17a907f` |
| `postgres-layer-3.tar` | 3652096 | `ba31e8ee45fa238f04327ce641175b8f57bee130331e6decca89a6394d89014e` |
| `postgres-layer-4.blob` | 8203863 | `da434b32d4803cadad93923bc2dc4ab9f85685873a5999c91264edf23f5e409e` |
| `postgres-layer-4.tar` | 26182144 | `67a43fd9d744630058b2aaf927bf2547187ca7c08e94171f7cbac5c62b6037c0` |
| `postgres-layer-5.blob` | 1311723 | `bcc75ab4e0104e18cb8684dbd012d05e5bd9bdefbd5da7c93bf41fe931446680` |
| `postgres-layer-5.tar` | 3484160 | `570b9e7408889eb4320c65e3be7d4499d8027eb6f8163e40b9c1b549d63058bf` |
| `postgres-layer-6.blob` | 116 | `a28de24f57c01d5ed53c5a829b762171f2c37369a391a403b4fdd3304b8e0c5b` |
| `postgres-layer-6.tar` | 1536 | `eeb35168bedc1d6b84401a53e6529661888887edfee58e88ba9e41f5f1e6b48d` |
| `postgres-layer-7.blob` | 3145 | `6d141360b363af231c3eddeac824438fc2268e983e9cbc0194c43d2d861aecf4` |
| `postgres-layer-7.tar` | 7680 | `bfd4e1dec4b56a5feb5aad6ed280d1f0bbb7b570d9460e072ad87ce9e10bf59c` |
| `postgres-layer-8.blob` | 115397881 | `fcd0e951406297ac5814e0485ac62a981805fe202829537876931bc18b8e10e5` |
| `postgres-layer-8.tar` | 333103104 | `f7d777c83930b6268325bab35eac40394b9908a2a4c8b39eaa9ee35bbee9980d` |
| `postgres-layer-9.blob` | 19426 | `cbe0afc9eb7bab5cc2b78d0a6d2157d77364a2f6322e34d76614a12fc8c9d33a` |
| `postgres-layer-9.tar` | 74752 | `84f7b9d615df09c4f0806a9cd350d49506758c8e10a6217d8815d6c8f0ef2989` |
| `postgres-result.json` | 13843 | `234e259712c6be12c6248728d31dc99b8a4bb1d71dc16127f473a0e13fea8a4c` |
| `postgres-sha256-8bca9649e52d948114ccc8164b55b7ab26b64e729893e420114bb5c87bf7c7cc.json` | 10046 | `8bca9649e52d948114ccc8164b55b7ab26b64e729893e420114bb5c87bf7c7cc` |
| `postgres-sha256-e3d24f6906d0760bf4da0dae872415391ededefad23fd471c47dc53b0ddf3c42.json` | 10229 | `e3d24f6906d0760bf4da0dae872415391ededefad23fd471c47dc53b0ddf3c42` |
| `postgres-sha256-e923a22ac074261dd73970c57edf659475bf0497cb9456f17d98ed7cdd3ca913.json` | 3439 | `e923a22ac074261dd73970c57edf659475bf0497cb9456f17d98ed7cdd3ca913` |
| `redis-layer-0.blob` | 29856132 | `37fb86c2a767b88d500c6872195f88078f64765fe0d2f9cc375cc2efbd4c0a41` |
| `redis-layer-0.tar` | 81295360 | `dd57f90311a2567b55ff22eeacff1602fd04ad7566e315957731359eab173b90` |
| `redis-layer-1.blob` | 1103 | `e7012240c0fb4c5ab49ce37e865ffdff3c6aabd499ee9cdaae9ecde5e34a0fc8` |
| `redis-layer-1.tar` | 10752 | `1f6a841b63ec62fb17c7a6a80f37eb8529d014c19705b8a3fdfa18f5afecbafc` |
| `redis-layer-2.blob` | 828 | `f0edb8c45951dafb7d29775303430976f3e5e6c995c80bfb99d5e8b8f9633b6a` |
| `redis-layer-2.tar` | 10240 | `12ff63ac704dd1e6bc5789455d5512da098dc3520d495d87d5120afbb6866c4f` |
| `redis-layer-3.blob` | 25739188 | `3e1ffb902068b145dd5d419e81206615f67fbf52a289686c21b2e408faa3ba26` |
| `redis-layer-3.tar` | 67239424 | `87c683a16d253f57007710cfd3bbcc9814617f4888d8493f9fd7f553fb6bd99c` |
| `redis-layer-4.blob` | 96 | `3ecf3ccdb02db4299c79f6d13b71885e59b6ba90acff1803bce4a40a7350224b` |
| `redis-layer-4.tar` | 1536 | `cf17b92ffb9ae632e9f0df1b95d67295bca4ad1d38aff9762f95f648ada0d150` |
| `redis-layer-5.blob` | 32 | `4f4fb700ef54461cfa02571ae0db9a0dc1e0cdb5577484a6d75e68dc38e8acc1` |
| `redis-layer-5.tar` | 1024 | `5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef` |
| `redis-layer-6.blob` | 2108 | `85b5f7d2996b3258898c504b45349fde4565af41e104d4d659a171a5b4093200` |
| `redis-layer-6.tar` | 8192 | `b74a5b51fa8821afc556015feabfeac1624d69796b9ab5591f89e38ffaaf02c8` |
| `redis-result.json` | 12093 | `9b732ab91a7215559725c296c2eea2a44d0ca1e233e36c97e65be37eb368f578` |
| `redis-sha256-1f88291b4c57bdf249f02eb085a8669889b2d2954e91d4de5118a5da6b78dd53.json` | 10213 | `1f88291b4c57bdf249f02eb085a8669889b2d2954e91d4de5118a5da6b78dd53` |
| `redis-sha256-978293674c6b207a799aa6003064828846a7771cd521603c41e9a4c7f28ec4dc.json` | 6762 | `978293674c6b207a799aa6003064828846a7771cd521603c41e9a4c7f28ec4dc` |
| `redis-sha256-e2728231060693472a8efb488dd139a8142a01bd0612ae70429bf5b5be924be1.json` | 2287 | `e2728231060693472a8efb488dd139a8142a01bd0612ae70429bf5b5be924be1` |
| `results.json` | 27746 | `82d1620ac210609a34df406f7fd49eb2fd709be8ed468e2359dd94518f818cb0` |
| `source-0` | 49057 | `fc103eeb94f6c4f661b56fd3ebb8640da85b706d4bc376d762495d058de4dbaf` |
| `source-1` | 43109 | `b5425c73d1a9169017f5050e439651e8976203aa165ae4486cb11d754f1fcb61` |
| `source-2` | 11813 | `8e0c74666b842b0f745455f9e853ba65f82776f379d57640d26291555e85259c` |
| `source-3` | 10140 | `ea58330e69627cb7b626043c7da44bc227ccd935126c239ceb33c8b4ddf745c2` |
| `sources.json` | 1031 | `0877beeb8ab518cea4d74e2268c7db3f3b0bf5a19325bc1a3268afceb1b31ef8` |
| `versioned-source-0` | 19329 | `e11dc2897e468a2fc4bcf44dc3643f08f9ae063b7ce03b88def9dd866250c8ad` |
| `versioned-source-1` | 667701 | `39b126752866fff675e462bd44d76f3e034abafe462a069cebd53ef39fc53eca` |
| `versioned-source-2` | 10146 | `5015df2bb657087d0b65204b6abb809c6ca7bbac472e5d21c1246c718087dacf` |
| `versioned-source-3` | 5597 | `8bf74f53f5298b996f08960e0425e187eacf7406eb4e97eb0aaf64c8e6391bb8` |
| `versioned-source-4` | 15214 | `5d65842c37a770fdd7e76993facea8c3e7256a0c0241ca38884dd52f67fb3e0f` |
| `versioned-sources.json` | 1089 | `9926a9d4ee3bd8004bb9d4ef5d3c66af2dad9c60983dfcf4cecb6db92c140f32` |

## Scope and delivery checks

Only this new UUID evidence leaf is authorized for repository writes. Existing `docs/talos-proof-delivery.md` was already modified at startup and is not part of this change. No code/root documentation changes, image/limit/command changes, tool installs, push, or CI watch are part of this inspection. A path-scoped diff check and local commit identify the delivered leaf; no acceptance is implied by the commit.
