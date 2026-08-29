# Orchestrator tracing

The component exports OpenTelemetry traces over OTLP HTTP, which Jaeger accepts
on its OTLP port.

For a local Jaeger all-in-one instance:

```text
OTEL_SERVICE_NAME=orchestrator
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:4318/v1/traces
OTEL_SDK_DISABLED=false
```

Set `OTEL_CONSOLE_EXPORTER=true` to print spans locally instead of exporting
them. Set `OTEL_SDK_DISABLED=true` to disable tracing without changing code.

The application creates spans for WebSocket turns, Nexus runner turns, plan
execution, and A2A agent requests. Existing `AgentInvocation`, `AgentEvent`,
and `AgentDependency` records remain the durable workflow/audit source.

Install the exporter and optional auto-instrumentation dependencies with:

```text
uv sync
```
