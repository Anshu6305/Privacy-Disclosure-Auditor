# Runtime asset manifest

SHA-256 of every file the running system opens. Generated 18 November 2026.
Verify a copy with:  `shasum -a 256 -c runtime_assets.sha256`

**27 files, 0.81 GB total.**

| Asset group | Path | Size | SHA-256 |
|---|---|---:|---|
| F-11 baseline classifier (M5) | `ml/checkpoints/classifier-baseline-v1/metadata.json` | 0.01 MB | `3e67a5474f38c992c8e75543fa29eea9…` |
|  | `ml/checkpoints/classifier-baseline-v1/model.joblib` | 2.61 MB | `37ae7b3d21343398d1800100282d1e78…` |
| F-11 improved classifier | `ml/checkpoints/improved_classifier/config.json` | 0.00 MB | `782e198c9fc4298b5e7a1c5094bf244f…` |
|  | `ml/checkpoints/improved_classifier/metadata.json` | 0.01 MB | `20fa23f937ad1b94e1d19b89c079fcc9…` |
|  | `ml/checkpoints/improved_classifier/model.safetensors` | 255.45 MB | `5c433a51938c83f8e51622835d6dc2d2…` |
|  | `ml/checkpoints/improved_classifier/tokenizer.json` | 0.68 MB | `0d3aef594edd5f9b53e7f814277a9171…` |
|  | `ml/checkpoints/improved_classifier/tokenizer_config.json` | 0.00 MB | `e1c2a61a99bda00f6c55303a210b30e2…` |
| F-12 span extractor | `ml/checkpoints/span-extractor-v1/config.json` | 0.00 MB | `0e382964d4c35674d3708209a465ea5b…` |
|  | `ml/checkpoints/span-extractor-v1/labels.json` | 0.00 MB | `fc787a0a9880dd1f96a1790a6f191e22…` |
|  | `ml/checkpoints/span-extractor-v1/metadata.json` | 0.00 MB | `11542c704826a3a938a342078fc54686…` |
|  | `ml/checkpoints/span-extractor-v1/model.safetensors` | 253.33 MB | `ec695acfc2d9072c6de3cd8e55ce4013…` |
|  | `ml/checkpoints/span-extractor-v1/special_tokens_map.json` | 0.00 MB | `b6d346be366a7d1d48332dbc9fdf3bf8…` |
|  | `ml/checkpoints/span-extractor-v1/tokenizer.json` | 0.68 MB | `91f1def9b9391fdabe028cd3f3fcc4ef…` |
|  | `ml/checkpoints/span-extractor-v1/tokenizer_config.json` | 0.00 MB | `32fbafc9a97ea9f01b2fef65c5df3a84…` |
|  | `ml/checkpoints/span-extractor-v1/vocab.txt` | 0.22 MB | `07eced375cec144d27c900241f3e3394…` |
| F-18 zero-shot NLI aligner | `ml/checkpoints/nli-mnli-v1/config.json` | 0.00 MB | `901e9df7328199db94c0ff94013d14d4…` |
|  | `ml/checkpoints/nli-mnli-v1/merges.txt` | 0.44 MB | `1ce1664773c50f3e0cc8842619a93edc…` |
|  | `ml/checkpoints/nli-mnli-v1/model.safetensors` | 313.28 MB | `9df3eb5d37118f952f4ba4fb46fde688…` |
|  | `ml/checkpoints/nli-mnli-v1/special_tokens_map.json` | 0.00 MB | `75cbec71553267dadc77a583ef15122c…` |
|  | `ml/checkpoints/nli-mnli-v1/tokenizer.json` | 3.39 MB | `2bb1a22cfbe25b8e5a232b7fc4d7fc50…` |
|  | `ml/checkpoints/nli-mnli-v1/tokenizer_config.json` | 0.00 MB | `87111eee3eed2bc8b8e774bc30d9c23e…` |
|  | `ml/checkpoints/nli-mnli-v1/vocab.json` | 0.76 MB | `ed19656ea1707df69134c4af35c8ceda…` |
| Model evaluation metrics | `ml/runs/classifier-baseline-v1-metrics.json` | 0.01 MB | `c66c1f8f43231f7c56706020456f913a…` |
|  | `ml/runs/improved-classifier-v1-metrics.json` | 0.01 MB | `20fa23f937ad1b94e1d19b89c079fcc9…` |
|  | `ml/runs/span-extractor-v1-metrics.json` | 0.00 MB | `110429866428cfb365743bfe77b6277b…` |
| Collected application corpus | `data/corpus/apps/com.spotify.music/record.json` | 0.01 MB | `5ba75341a322c3762feaac063709c884…` |
|  | `data/corpus/raw/policies/13089e7b1972c6e4f6019f5a16f465f716881c3c2b5a5783a37f5fec41fa4ea8.html` | 0.19 MB | `13089e7b1972c6e4f6019f5a16f465f7…` |
