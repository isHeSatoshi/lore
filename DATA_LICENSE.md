# Benchmark and demo data

Lore's MIT code license does not replace the license of its benchmark data.

Original data and attribution:

- **BIRD benchmark contributors:** [BIRD](https://bird-bench.github.io/).
- **BIRD Mini-Dev release:** [dataset and upstream notices](https://huggingface.co/datasets/birdsql/bird_mini_dev).
- **License for BIRD data and derived benchmark/seed data:** [Creative Commons
  Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/).

Keep this attribution and the upstream license notices with redistributed
source or derived data. The repository records download URLs and hashes in
`results/data/sources.json`.

Lore normalizes schema metadata and paths, filters a learning-stream subset,
and produces profiles, verified examples, model-generated meanings and
evaluation reports. These are modifications or derived artifacts, not an
unmodified BIRD release. Model-generated meanings can be wrong.

Downloaded SQLite databases are not committed to Git. The portable demo
bundle copies its selected database files unchanged and includes this notice
inside `data/bird/`. Code remains separately MIT licensed.
