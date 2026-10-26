# Third-party notices

- `vendor/convlog`: unmodified source from [Equim-chan/mjai-reviewer](https://github.com/Equim-chan/mjai-reviewer), commit `2dc5ec5c8b28517cfb45f57eb21536d9a8f67aa9`. Apache License 2.0, full license at `vendor/convlog/LICENSE`. Upstream attribution retained in Cargo.toml.
- Example replay fixtures: same upstream and license; see `tests/fixtures/README.md`.
- Runtime Python dependencies: see `uv.lock`; mahjong and tensoul are MIT. Dependency licenses remain their owners'.
- UnityPy: MIT, [K0lb3/UnityPy](https://github.com/K0lb3/UnityPy), used to read the official client's public version metadata. No game scripts are executed. The dependency version is locked in `uv.lock`.
- Mortal: external optional process, AGPL-3.0-or-later code, no checkpoint or source bundled. Review the upstream license when combining or distributing a deployment, including network service obligations.
- Community Mortal checkpoint: optional installer downloads [VoidShine/mortal-298k](https://huggingface.co/VoidShine/mortal-298k), revision `dbbea7e3d34f99ec43fc4834ab7f2aaaed70b6ee`, published under AGPL-3.0. Its original model card and LICENSE are preserved locally in `models/mortal-298k/`. Checkpoint files are not committed or baked into the Docker image. This community training run is not the official online Mortal model; no absolute strength claim is made by XMahjong.
- Akochan: external optional process, custom [Japanese usage terms](https://github.com/critter-mj/akochan/blob/master/LICENSE), not MIT/GPL/Apache. Local Docker build downloads unmodified upstream. Redistribution, modifications and commercial use are subject to those terms. This repository does not distribute its binary or model parameters.
