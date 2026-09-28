# Media licenses: demo video, screenshots and site

Everything that appears in the demo video, the screenshots or the project site, with its source, license and the
evidence checked. Verified on **2026-09-28**.

## Background music (video only)

| Field | Value |
|---|---|
| Track | **Airport Lounge** |
| Creator | **Kevin MacLeod** |
| Publisher / download source | incompetech.com: https://incompetech.com/music/royalty-free/mp3-royaltyfree/Airport%20Lounge.mp3 |
| Catalogue entry | incompetech `pieces.json`: title "Airport Lounge", ISRC **USUAN1100806**, 5:08, bass, drum kit, electric piano, vibraphone; feel "Bouncy, Calming, Relaxed"; "Light and airy, this piece is guaranteed not to steal focus."; uploaded 2011-03-07 |
| Downloaded file | `Airport Lounge.mp3`, 12,309,016 bytes, 320 kb/s, sha256 `e20d316b541c72690a3b0311c9f3d40fd00717359ab7567d7df82a9316c1dec4`; ID3 title "Airport Lounge", artist "Kevin MacLeod", album "Royalty Free". Kept in the git-ignored `.cache/music/` and **not committed**. `tools/make_video.py` refuses any other file. |
| License | **Creative Commons Attribution 4.0 International (CC BY 4.0)**: https://creativecommons.org/licenses/by/4.0/ |
| Required attribution (publisher's format) | Airport Lounge Kevin MacLeod (incompetech.com)<br>Licensed under Creative Commons: By Attribution 4.0<br>https://creativecommons.org/licenses/by/4.0/ |
| Changes (disclosure required) | An excerpt from the start of the track, trimmed to the video length, lowered to background level and automatically ducked (side-chain compression) under the narration, with a 3 s fade-in and 4 s fade-out, re-encoded to AAC and mixed with the narration. The narration, captions and everything on screen are this project's; the music is Kevin MacLeod's. The measured level under the voice is in `site/media/demo.json` (`audio_levels`). |

**Evidence that this use is permitted** (all checked on the verification date):

- incompetech FAQ (https://incompetech.com/music/royalty-free/faq.html), on videos: "Yes, AND you can monetize the
  videos. Be sure to credit me."
  - Placement: the credit must be placed so that "a person who wants to know where the music came from should have
    no difficulty in finding it"; for video, "in the video description or in the video itself".
  - Edits: "You can sing over, chop, splice, compress, lengthen, and add instruments to anything you like. You MUST
    make it clear in the credits which parts are yours, and which parts are mine."
  - The credit format above is quoted from the FAQ, which names the license "Creative Commons: By Attribution 4.0".
- incompetech licensing page (https://incompetech.com/music/royalty-free/licenses/): the Creative Commons option is
  "No charge. Requires that you credit the music."
- CC BY 4.0: allows sharing and adapting for any purpose, provided there is appropriate credit, a link to the
  license, and an indication of changes.

**Residual risk.** The track's page on the publisher's licensing platform
(`incompetech.filmmusic.io/song/3347-airport-lounge/`) redirects to `ende.app/song/3347-airport-lounge/`, which
returned **404** on the verification date. The license was therefore verified from the publisher's FAQ, its
licensing page, its catalogue data and the file's own tags. Automated content matching on video platforms can flag
CC music; the credit above is the basis for a dispute. Only the mixed video is distributed.

**Where the credit appears:** the end card of the video, under the video on the project site and in its footer, the
README credits, and this file.

## Narration

Synthetic speech generated locally with **Kokoro-82M v1.0** (hexgrad; Apache-2.0 weights,
https://huggingface.co/hexgrad/Kokoro-82M) through **kokoro-onnx** 0.6.1 (MIT, https://github.com/thewh1teagle/kokoro-onnx),
voice `af_heart`. Model files: `kokoro-v1.0.onnx` sha256 `beb0d184…f0df3a` and `voices-v1.0.bin` sha256
`bca610b8…1fbf7d`, from the kokoro-onnx `model-files-v1.0` release, kept in the git-ignored `.cache/kokoro/`.
Apache-2.0 allows use and redistribution. The model card credits CC BY training data (Koniwa, CC BY 3.0; SIWIS,
CC BY 4.0), and we repeat that credit. The video and site say the voice is synthetic. No real person's voice is used.

## Screenshots and video frames

All are of this project's own application running locally, captured by `tools/capture_demo.py` during **one** live
run on sample r30. The model inference is real. The reviewer's clicks and typing are scripted with Playwright, and
the video's opening card says so. The receipts are synthetic ([sample-provenance.md](sample-provenance.md)).

## Fonts on the site

The site loads Inter and JetBrains Mono (SIL Open Font License) from Google Fonts, matching the owner's portfolio.
The app itself loads no external fonts.
