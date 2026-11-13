# WOPI native ODT browser path: offline review after eighth failure

**No new activation or browser trial.** Seven TXT failures plus the first ODT
failure are retained. The ODT genuinely loaded with docLoaded:true, a real doc
layer and edit permission; no marker input, accepted PutFile, save, reopen or host
denial passed. The private failure screenshot shows a session-warning modal
**above** the welcome tour. Source changes below are offline only.

## Ordered interaction contract

1. Verify receipt/document format and actual discovery edit/odt action. Verify
   certificate CA and hostname before deriving exact leaf SPKI. Install exact
   browser HTTP and WS origin guards **before the first navigation**. No TLS
   ignore, proxy, Origin stripping or broad Internet fallback.
2. Use the discovered native editor action through the fixture's form POST and
   real CODE iframe/WSS. The locally fulfilled host wrapper is only the WOPI
   embedder, not an editor or fabricated document/save result.
3. Wait for the real document canvas. Capture bounded structural editor state,
   not full DOM text, URLs, document bytes or credential-bearing debug data.
4. Check the exact observed notice:
   `Your session will end in 10 minutes. Refresh the page to continue.`
   If visible, click the exact **Close** button in its containing native dialog,
   then require the notice hidden. Do not refresh, extend tokens, alter UI state
   through JS or dismiss every dialog indiscriminately.
5. Only then dismiss the known welcome tour using observed `#welcome-close` in
   its dedicated known frame, or the existing known welcome-dialog wrapper close
   control. Broad close-element scanning and guessed coordinate clicks have been
   removed. Missing known close control fails. A session notice above the tour
   must never be interpreted as a disabled document or wrong editing permission.
6. Recheck the exact session notice after tour dismissal. If the real **Viewing**
   selector is visible, select exact **Editing Mode**. Already-editable ODT does
   not need a forced toggle. For TXT only, handle the exact previously observed
   format-loss warning with its exact **Continue editing** button; do not apply
   that handler to ODT or unrelated conversion/loss prompts.
7. Recheck the exact session notice after mode transitions; wait bounded45seconds
   for docLoaded:true + actual doc layer + permission:edit. Require no visible
   native role=dialog or known welcome wrapper before marker input. Unknown
   overlays fail closed and retain failure state/screenshot; no general modal
   clicker, Escape loop, arbitrary text match or blind CSS deletion is allowed.
8. Focus the **observed native `#clipboard-area`**, require exactly one match,
   content-editability and actual activeElement equality. Type the random marker
   with real browser keyboard input at the current caret. No innerHTML/textContent,
   DOM value assignment, synthetic input event or fixture write. Cursor movement
   is unnecessary for the content-marker proof, so generic Control+End was removed.
9. Record actual browser navigator.platform structurally. Use a **visible enabled
   native button named exactly Save**, never the hidden first matching button or
   a guessed Control+S. Native Save UI avoids Mac/Linux modifier ambiguity. No
   generic keyboard shortcut is present in this path. A disabled/missing Save
   control fails; selecting menu items or invoking UNO JS directly is not a
   fallback.
10. Browser dispatch is not acceptance. Independently require an accepted real
    CODE PutFile, parsed ODT content.xml marker, all real callbacks, and then
    close/reopen through a new browser process. Reopen may run only the loading
    and overlay path, not type/save again. Its status no longer says keyboard
    input/save was dispatched when edit:false.
11. Independently compare exact saved bytes and parsed content.xml marker after
    reopening. A comment/ZIP-member decoy or rejected wrong-lock409 is not a save.
12. Only after successful positive editing/reopen controls, exercise native host
    denial using alternate K8s DNS spelling of the same running fixture, canonical
    and alternate network-positive controls, explicit native denial UI and actual
    callback/byte evidence. No dead DNS or endpoint timeout may earn denial PASS.

## Offline checks and remaining uncertainty

Static regression checks protect guard-before-navigation ordering, exact HTTPS/WSS
origins, ignoreHTTPSErrors:false, observed warning/control strings, removal of
keyboard shortcut guesses and coordinate fallback, focus checks and visible
native Save selection. These are source contracts, **not browser execution**.

The complete intended overlay sequence is reviewed, but no offline reasoning can
establish that another build/state will not introduce a new modal, delayed overlay,
focus steal, menu variant or different accessibility tree. In particular, the
new session-warning locator and close ordering remain untested. Unknowns must
produce evidence-backed failure, not a broad auto-dismiss workaround. A modal
without accessible role=dialog may require further observed evidence; the code
does not claim an exhaustive universal overlay detector. Save success and native
host-denial semantics also remain unproven. All eight failures remain failures.

The supervisor still performs **one suite then cleanup**. A receipt allowing two
browser-suite attempts does not make this runner retry in one activation, and
must never be worked around by reactivation. No live receipt currently exists.
