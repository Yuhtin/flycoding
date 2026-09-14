# Original release verification

Local verification on September 13, 2026, after fixes in `751c3c9`.

- `rtk proxy .venv/bin/python -m pytest`: **77 tests passed** in 15.33 seconds. Tests were synthetic and sent no instructions to Codex.
- `rtk proxy uv build`: source distribution and wheel built successfully. Neural resources, C++ kernel, and dashboard assets were present; datasets and sessions were excluded.
- Wheel extracted outside Git: import, help, and `status` worked. Source verification rejected the noneditable installation with an explicit diagnostic, without loading the graph or executing Codex.
- Genuine dashboard checked at 1440 px and 390 px, with no JavaScript errors or horizontal overflow. The selected image matched the hash and response of the displayed historical attempt.
- All 18 public PNG/RGB hash pairs matched the published images.
- An independent automated whole-branch review found five minor issues. A scoped re-review confirmed all five fixed, with no outstanding findings.

The genuine pilot ran earlier on clean source revision
`a16e1713f340a15a4e87f2d5651536f03aa9fe3a`. Later presentation, export, and
installation fixes were not treated as a new execution. The report preserves
that original revision, six successes, and nine calls. No additional calls
were made to complete the release.

The flybody/English update is a later presentation change. This historical
verification record describes the original release, not tests of the new
body viewer.

## Recorded review decision

An intermediate review of evaluator fixes was automatically blocked twice
for possible security risk, including a request for defensive static-only
inspection. The coordinator performed local static inspection and used the
existing test evidence. The cost was losing an independent perspective at
that stage. Independent whole-branch and final scoped reviews completed
subsequently.
