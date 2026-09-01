# Kthena

Experimental tooling for predictive autoscaling with Kthena.

## AASP Metrics Adapter

See [`aasp-metrics-adapter/README.md`](aasp-metrics-adapter/README.md).

Polls the AASP `infer-recommendations` API, aggregates prediction peaks (`max` over the window), and exposes Prometheus gauges for Kthena Autoscaler Pod metric scraping.
