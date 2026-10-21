# Contributing to StateDyne

Thanks for improving this project. Focus on evidence-backed, general-purpose improvements rather than hard-coding an answer to a familiar case.

1. Open an issue with a reproducible problem and an expected observable result. Avoid uploading private transcripts, credentials, or sensitive runtime traces.
2. Keep method changes, execution/adapter changes and presentation changes separate. Explain any alteration to worker routing, state, or validation contracts.
3. Add synthetic positive and negative regression cases; distinguish engineering validation from actual cross-model evaluation.
4. Run `python scripts/validate_skill.py --strict-bytes` and `python -m unittest discover -s tests -q` before proposing changes. If the manifest needs regeneration, update `references/source-map.json` consistently.
5. Do not claim an independent model call unless supported by actual execution receipts. Do not convert a plausible explanation into a verified causal fact without evidence.

Apache-2.0 applies to contributions unless separately agreed. Please use project issues and pull requests; no private contact address is assumed.
