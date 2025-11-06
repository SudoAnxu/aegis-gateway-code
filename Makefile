.PHONY: build run clean test demo deps

# Build the gateway
build:
	go build -o bin/aegis ./cmd/aegis
	go build -o bin/payments ./cmd/payments
	go build -o bin/files ./cmd/files

# Run the gateway locally
run:
	go run cmd/aegis/main.go

# Download dependencies
deps:
	go mod download
	go mod tidy

# Clean build artifacts
clean:
	rm -rf bin/
	rm -rf logs/
	rm -f *.log

# Run demo script
demo:
	chmod +x scripts/demo.sh
	./scripts/demo.sh

# Run tests
test:
	go test ./...

# Run tests with coverage
test-coverage:
	go test -cover ./...
	go test -coverprofile=coverage.out ./...
	go tool cover -html=coverage.out

# Run tests with verbose output
test-verbose:
	go test -v ./...

# Run integration tests (requires gateway to be running)
test-integration:
	chmod +x test_integration.sh
	./test_integration.sh

# Build Docker images
docker-build:
	docker-compose build

# Run with Docker Compose
docker-up:
	docker-compose up --build

# Stop Docker Compose
docker-down:
	docker-compose down

