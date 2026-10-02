# Packaging validation

Validated 2026-10-02:

- Python AST parsing for both benchmark scripts and the model verifier passed
- All 30 retained result rows match the original console JSON rows
- Each condition retains five measured wall-clock runs; medians and RTF arithmetic check out
- Both pinned ONNX models passed SHA-256 verification
- Both scripts completed end-to-end using the already-installed original measurement dependencies and compiled classic module: 15 conditions each
- Context diagnostics reproduced exactly: 8 kHz max/mean difference 0.9911231696605682 / 0.3970406587634768; 16 kHz 0.6065110564231873 / 0.10526469882045474; identical no-context controls have zero difference in both cases
- No model, compiled library, or audio fixture is included in the repository

A clean-room dependency installation was not rerun. The original compiler invocation is unavailable. New rerun timing values are machine-local checks, not replacements for historical measurements. No other backend was benchmarked during packaging.
