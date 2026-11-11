from incubia_orchestrator.foundation.telemetry import HttpMetrics


def test_http_metrics_are_bounded_and_scoped():
    metrics = HttpMetrics("deployment", "tenant")
    metrics.started()
    metrics.started()
    metrics.finished(200, 40)
    metrics.finished(503, 9000)
    snapshot = metrics.snapshot()
    assert snapshot["deployment_id"] == "deployment"
    assert snapshot["tenant_id"] == "tenant"
    assert snapshot["requests"] == 2
    assert snapshot["server_errors"] == 1
    assert snapshot["in_flight"] == 0
    assert snapshot["peak_in_flight"] == 2
    assert snapshot["latency_ms_buckets"][50] == 1
    assert snapshot["latency_ms_buckets"]["+Inf"] == 1
