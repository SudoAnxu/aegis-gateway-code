FROM golang:1.21-alpine AS builder

WORKDIR /build

# Copy all files first
COPY . .

# Download dependencies and generate go.sum
RUN go mod download && go mod tidy

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -o aegis ./cmd/aegis

FROM alpine:latest

RUN apk --no-cache add ca-certificates netcat-openbsd

WORKDIR /app

COPY --from=builder /build/aegis .
COPY --from=builder /build/policies ./policies

# Create logs directory
RUN mkdir -p logs

EXPOSE 8080

CMD ["./aegis", "-gateway-port=8080", "-payments-port=8081", "-files-port=8082", "-policies-dir=./policies", "-log-dir=./logs"]

