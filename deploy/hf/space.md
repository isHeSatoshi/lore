---
title: Lore
sdk: gradio
sdk_version: 6.32.0
python_version: "3.12"
app_file: app.py
startup_duration_timeout: 30m
license: mit
---

# Lore

Text-to-SQL meanings learned from verified corrections, on HydraDB and SelfGraph.
The main application is at `/`; `/hosting` is the Gradio hosting information page.

This deployment is intended for eligible free Gradio/ZeroGPU hosting. It does
not request GPU work. CPU Basic Docker Space creation is not available to a
free account under the current hosting rules.

The application uses the owner's configured MiniMax API. Free hosting does
not make those model calls free. Only runtime Secrets should contain API keys.

HydraDB 0.4.0 is downloaded unchanged from its pinned public OCI image and is
accessible only inside the Space. Its original filesystem and notices are
retained. HydraDB is separately licensed under the
[Elastic License 2.0](https://github.com/hydra-db/hydradb/blob/v0.4.0/LICENSE);
Lore does not expose a general database-as-a-service endpoint.

Free hosting is ephemeral. Trained graph seeds are restored on startup;
visitor graphs, cached answers and rate-limit counters can reset when the
Space is replaced. Forwarded client-IP headers are not trusted: visitors
behind the same hosting proxy may share the stricter hourly call limit.

Code is MIT licensed. BIRD source and derived data have separate
CC BY-SA 4.0 notices in `DATA_LICENSE.md`. See `PROJECT_README.md` for measured
results and limitations.
