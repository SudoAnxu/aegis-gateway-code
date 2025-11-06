package telemetry

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracehttp"
	"go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"
	semconv "go.opentelemetry.io/otel/semconv/v1.21.0"
	"go.opentelemetry.io/otel/trace"
)

// Telemetry manages OpenTelemetry and logging
type Telemetry struct {
	tracer     trace.Tracer
	logFile    *os.File
	logDir     string
	serviceName string
}

// DecisionLog represents a structured audit log entry
type DecisionLog struct {
	Timestamp    string            `json:"timestamp"`
	AgentID      string            `json:"agent.id"`
	ToolName     string            `json:"tool.name"`
	ToolAction   string            `json:"tool.action"`
	Decision     string            `json:"decision.allow"` // "true" or "false"
	Reason       string            `json:"reason,omitempty"`
	PolicyVersion string           `json:"policy.version,omitempty"`
	ParamsHash   string            `json:"params.hash"`
	LatencyMS    int64             `json:"latency.ms"`
	TraceID      string            `json:"trace.id"`
	SpanID       string            `json:"span.id"`
}

// NewTelemetry initializes OpenTelemetry and logging
func NewTelemetry(serviceName, logDir string) (*Telemetry, error) {
	// Ensure log directory exists
	if err := os.MkdirAll(logDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create log directory: %w", err)
	}

	logPath := filepath.Join(logDir, "aegis.log")
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return nil, fmt.Errorf("failed to open log file: %w", err)
	}

	// Initialize OTLP exporter
	exporter, err := otlptracehttp.New(context.Background(),
		otlptracehttp.WithEndpoint("localhost:4318"),
		otlptracehttp.WithInsecure(),
	)
	if err != nil {
		// Fallback to no-op if exporter fails (for local dev)
		fmt.Printf("WARNING: Failed to initialize OTLP exporter: %v\n", err)
		exporter = nil
	}

	var tp *sdktrace.TracerProvider
	if exporter != nil {
		resource, _ := resource.New(context.Background(),
			resource.WithAttributes(semconv.ServiceName(serviceName)),
		)

		tp = sdktrace.NewTracerProvider(
			sdktrace.WithBatcher(exporter),
			sdktrace.WithResource(resource),
		)
		otel.SetTracerProvider(tp)
	}

	tracer := otel.Tracer(serviceName)

	return &Telemetry{
		tracer:      tracer,
		logFile:     logFile,
		logDir:      logDir,
		serviceName: serviceName,
	}, nil
}

// HashParams creates a SHA-256 hash of request parameters
func HashParams(params interface{}) string {
	data, err := json.Marshal(params)
	if err != nil {
		return "hash_error"
	}
	hash := sha256.Sum256(data)
	return hex.EncodeToString(hash[:])
}

// LogDecision creates a span and logs the decision
func (t *Telemetry) LogDecision(ctx context.Context, agentID, tool, action string, allowed bool, reason string, paramsHash string, latencyMS int64) (context.Context, trace.Span) {
	ctx, span := t.tracer.Start(ctx, "policy.evaluate",
		trace.WithAttributes(
			attribute.String("agent.id", agentID),
			attribute.String("tool.name", tool),
			attribute.String("tool.action", action),
			attribute.Bool("decision.allow", allowed),
			attribute.String("params.hash", paramsHash),
			attribute.Int64("latency.ms", latencyMS),
		),
	)

	decisionStr := "false"
	if allowed {
		decisionStr = "true"
	}

	logEntry := DecisionLog{
		Timestamp:  time.Now().UTC().Format(time.RFC3339),
		AgentID:    agentID,
		ToolName:   tool,
		ToolAction: action,
		Decision:   decisionStr,
		Reason:     reason,
		ParamsHash: paramsHash,
		LatencyMS:  latencyMS,
		TraceID:    span.SpanContext().TraceID().String(),
		SpanID:     span.SpanContext().SpanID().String(),
	}

	if !allowed {
		logEntry.Reason = reason
	}

	// Write to log file
	logJSON, _ := json.Marshal(logEntry)
	t.logFile.WriteString(string(logJSON) + "\n")

	// Also write to stdout
	fmt.Println(string(logJSON))

	return ctx, span
}

// LogForwardedCall logs a forwarded call to a tool
func (t *Telemetry) LogForwardedCall(ctx context.Context, tool, action string, latencyMS int64) trace.Span {
	_, span := t.tracer.Start(ctx, "tool.forward",
		trace.WithAttributes(
			attribute.String("tool.name", tool),
			attribute.String("tool.action", action),
			attribute.Int64("latency.ms", latencyMS),
		),
	)
	return span
}

// Close closes the log file
func (t *Telemetry) Close() error {
	return t.logFile.Close()
}

