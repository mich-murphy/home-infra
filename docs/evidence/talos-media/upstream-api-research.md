# Public upstream API research checkpoint

Read-only public GitHub repository metadata/tree discovery followed by raw source HTTPS fetches. No cluster Internet allowance, source Docker access or live mutation. These are implementation references, **not functional pass evidence**.

## qbitwebui v2.44.2

- https://github.com/mkbula/qbitwebui/blob/v2.44.2/src/server/routes/auth.ts
- https://github.com/mkbula/qbitwebui/blob/v2.44.2/src/server/routes/instances.ts
- https://github.com/mkbula/qbitwebui/blob/v2.44.2/src/server/db/index.ts
- https://github.com/mkbula/qbitwebui/blob/v2.44.2/src/server/utils/crypto.ts
- https://github.com/mkbula/qbitwebui/blob/v2.44.2/src/server/index.ts

Hono routes mount at `/api/auth` and `/api/instances`. Auth POST `/login` consumes `{username,password}` and sets session cookie; GET `/me` checks session. POST `/password` uses `{currentPassword,newPassword}`. Registration-disabled fresh boot generates a random admin password and prints it: do NOT rely on raw log collection. Safe planned initialization: same pinned Bun image initContainer creates only the upstream users schema in the fresh PVC and inserts a proof user's bcrypt hash using `Bun.password.hash(password,{algorithm:'bcrypt',cost:12})`; consume password from Secret, never arguments/stdout. Main application then creates remaining tables and sees a nonempty user table, avoiding generated-password log exposure. This initializer is not yet implemented or live validated.

Instance CRUD: POST `/api/instances/` with `{label,url,qbt_username,qbt_password,skip_auth:false,agent_enabled:false}`; PUT `/:id` updates label/settings; POST `/:id/test` checks stored credentials, returns `{success:true,version}`; GET `/stats` returns per-instance online/queue stats; DELETE `/:id` removes. Test target must be proof qBittorrent service only. This requires an explicitly leased small dependency batch, not an Internet exception. Keep a known instance through restart for persistence, then delete a separate temporary CRUD instance. No actual torrent is needed for connection/settings proof; local fixture transfer remains a separate acceptance test.

## Audiobookshelf v2.37.2

- https://github.com/advplyr/audiobookshelf/blob/v2.37.2/server/Server.js
- https://github.com/advplyr/audiobookshelf/blob/v2.37.2/server/Auth.js
- https://github.com/advplyr/audiobookshelf/blob/v2.37.2/server/routers/ApiRouter.js
- https://github.com/advplyr/audiobookshelf/blob/v2.37.2/server/controllers/LibraryController.js
- https://github.com/advplyr/audiobookshelf/blob/v2.37.2/server/controllers/MeController.js

GET `/status` exposes `isInit`. Fresh POST `/init` body is **`{newRoot:{username,password}}`**, returns text status (read raw). POST `/login` returns `user.accessToken` (optional request header `x-return-tokens:true`); use Bearer authorization. POST `/api/libraries` takes `{name,folders:[{fullPath:'/data/audiobooks'}],mediaType:'book',settings:{...}}`. Local library default provider exists but external network stays denied; disable auto scan/watcher/metadata lookups where supported. POST `/api/libraries/:id/scan` responds text status; GET `/api/libraries/:id/items` obtains scanned fixture.

GET `/api/me/progress/:id`; PATCH `/api/me/progress/:libraryItemId` creates/updates progress. POST `/api/me/item/:id/bookmark` body `{time,title}`; PATCH same edits; DELETE suffix `/:time`. GET `/api/me/bookmarks/:libraryItemId` verifies. Need inspect `SessionController`/`LibraryItemController` playback routing to complete exact checksum streaming test; no guess-based pass.

## Pinchflat v2025.6.6

- https://github.com/kieraneglin/pinchflat/blob/v2025.6.6/lib/pinchflat_web/router.ex
- https://github.com/kieraneglin/pinchflat/blob/v2025.6.6/test/pinchflat_web/controllers/media_profile_controller_test.exs

Phoenix HTML resource `/media_profiles` supports new/show/create/edit/update/delete, with browser-session CSRF protection. Upstream minimal valid profile fields: `name`, `output_path_template` (e.g. `proof.{{ ext }}`). Fetch `/media_profiles/new`, retain cookies and CSRF token, form-POST nested `media_profile[...]` fields; parse redirected ID, verify show text, update with form method override, read back, and delete without `delete_files=true`. No Source/YouTube URL is needed for profile CRUD, so no downloads are triggered. Onboarding mode can redirect creation to `/?onboarding=1` instead of the new ID; either finish fresh onboarding safely or identify the unique fixture profile on index. Actual CSRF/form behavior still requires live validation.

## Tautulli v2.18.2 and helpers

- https://github.com/Tautulli/Tautulli/blob/v2.18.2/plexpy/api2.py
- https://github.com/Tautulli/Tautulli/blob/v2.18.2/plexpy/webserve.py

API `get_settings` returns config sections with secret keys redacted by upstream; never print full results nonetheless. Need inspect the config-update form/API and proof-local unclaimed Plex handling before implementing settings/session acceptance. Kometa/Recyclarr/jellyplex-watched nonempty dry-runs remain unimplemented, not accepted from empty or invalid configurations.

## Next implementation steps

1. Finish the version-specific functional implementations above and additional Plex/Seerr/Tautulli tests through the verified Gateway TLS client.
2. Resolve proposed fresh shared `proof-media-pipeline` trust group/path topology with parent; no namespace/storage mutation yet.
3. Add fixtures (local Mac ffmpeg was not found in PATH), real restart/read-before-write checks and a clean fresh-PVC restore test.
4. Wait for coordinator-issued private lease with actual node UID and a fresh memory measurement. No lease exists in this checkpoint; no live mutation is authorized.
