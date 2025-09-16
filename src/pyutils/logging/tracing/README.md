# Structlog + OpenTelemetry Tracing

A comprehensive, easy-to-configure structured logging system backed by OpenTelemetry, inspired by Rust's tracing library.

## Features

- **🦀 Rust-like Interface**: Familiar API for those coming from Rust's tracing ecosystem
- **🔧 Easy Configuration**: Simple setup for development and production environments
- **📊 OpenTelemetry Integration**: Built-in support for distributed tracing with OTLP export
- **🎨 Multiple Output Formats**: Pretty console, JSON, key-value, and protocol buffer formats
- **⚡ Performance**: Efficient structured logging with minimal overhead
- **🔍 Rich Context**: Automatic span correlation and structured event data
- **🆔 Trace Context**: Automatic trace_id, span_id, and span_name in every log message
- **🚀 Production Ready**: Battle-tested configuration for production deployments

## Quick Start

### Development Setup

```python
from pyutils.logging.tracing_2 import setup_dev, get_logger, span, instrument

# Quick development setup
setup_dev(service_name="my-app", log_level="DEBUG")

# Get a logger (similar to Rust's tracing)
logger = get_logger("my_module")

# Log structured events
logger.info("User logged in", user_id=123, username="alice")
logger.error("Database connection failed", error="timeout", retry_count=3)
```

### Production Setup

```python
from pyutils.logging.tracing_2 import setup_prod

# Production setup with OTLP export
setup_prod(
    service_name="my-production-service",
    otlp_endpoint="http://jaeger-collector:4317",
    log_level="INFO"
)
```

### Tracing with Spans

```python
from pyutils.logging.tracing_2 import get_logger, span, instrument

logger = get_logger("user_service")

# Manual span creation
with span("process_user_request", user_id=456, operation="create_account"):
    logger.info("Starting user account creation")
    
    with span("validate_input", field_count=5):
        logger.debug("Validating user input")
        # ... validation logic
    
    with span("database_insert", table="users"):
        logger.debug("Inserting user into database")
        # ... database logic
    
    logger.info("User account created successfully")

# Function instrumentation (like Rust's #[tracing::instrument])
@instrument(name="calculate_user_score")
def calculate_score(user_id: int, factors: dict) -> float:
    logger = get_logger("scoring")
    logger.debug("Calculating score", user_id=user_id, factors=factors)
    # ... calculation logic
    return score
```

## Trace Context Integration

Every log message automatically includes trace context when inside a span:

```python
from pyutils.logging.tracing import get_logger, span

logger = get_logger("order_service")

# Log outside span - no trace context
logger.info("Application started")  
# Output: 2024-01-15T10:00:00.000Z [info] Application started [order_service]

with span("process_order", order_id=12345):
    logger.info("Processing customer order") 
    # Output: 2024-01-15T10:00:01.000Z [info] Processing customer order [order_service] 
    #         trace_id=0xabc123... span_id=0xdef456... span_name=process_order
    
    with span("validate_payment", method="credit_card"):
        logger.info("Validating payment")
        # Output: 2024-01-15T10:00:02.000Z [info] Validating payment [order_service] 
        #         trace_id=0xabc123... span_id=0x789abc... span_name=validate_payment
```

**Trace Context Fields:**
- `trace_id`: Links all logs from the same request/workflow
- `span_id`: Identifies the specific operation context  
- `span_name`: Shows exactly which operation generated the log

This makes it easy to correlate log messages with distributed trace spans in your observability platform.

## Configuration

### Simple Configurations

```python
from pyutils.logging.tracing_2 import (
    setup_dev, setup_prod, setup_json_console
)

# Development: Pretty console output
setup_dev(service_name="my-app", log_level="DEBUG")

# Production: JSON + OTLP export
setup_prod(
    service_name="my-service",
    otlp_endpoint="http://collector:4317",
    log_level="INFO"
)

# Containers: JSON to console
setup_json_console(service_name="my-container-app")
```

### Advanced Configuration

```python
from pyutils.logging.tracing_2 import (
    configure_logging, LoggingConfig, StructlogConfig, OtelConfig,
    OutputFormat, ExportTarget, LogLevel
)

config = LoggingConfig(
    output_format=OutputFormat.JSON,
    export_target=ExportTarget.OTLP,
    structlog_config=StructlogConfig(
        log_level=LogLevel.INFO,
        add_logger_name=True,
        add_log_level=True,
        include_stdlib=True,
    ),
    otel_config=OtelConfig(
        service_name="advanced-service",
        service_version="1.2.3",
        service_instance_id="instance-001",
        endpoint="https://api.honeycomb.io:443",
        headers={"x-honeycomb-team": "your-api-key"},
        insecure=False,
    )
)

configure_logging(config)
```

## API Reference

### Core Functions

#### `get_logger(name: Optional[str] = None) -> structlog.BoundLogger`

Get a structured logger instance. If no name is provided, automatically infers from the calling module.

```python
logger = get_logger("my_component")
logger = get_logger()  # Auto-infers name
```

#### `span(name: str, **attributes) -> ContextManager`

Create a distributed tracing span with optional attributes.

```python
with span("database_query", table="users", query_type="select"):
    # Your code here
    pass
```

#### `instrument(func=None, *, name=None, **attributes) -> Decorator`

Decorator to automatically instrument functions with tracing spans.

```python
@instrument(name="custom_name")
def my_function():
    pass

@instrument  # Auto-generates name from function
async def async_function():
    pass
```

### Configuration Classes

#### `LoggingConfig`

Main configuration class.

```python
LoggingConfig(
    output_format: OutputFormat = OutputFormat.PRETTY,
    export_target: ExportTarget = ExportTarget.CONSOLE,
    file_path: Optional[str] = None,
    structlog_config: StructlogConfig = StructlogConfig(),
    otel_config: Optional[OtelConfig] = None,
)
```

#### `OutputFormat`

Available output formats:
- `PRETTY`: Colorized console output for development
- `JSON`: Machine-readable JSON format
- `KEY_VALUE`: Simple key=value format
- `PROTO`: Protocol buffer format (for OTLP)

#### `ExportTarget`

Available export targets:
- `CONSOLE`: Output to console/stdout
- `OTLP`: Export to OpenTelemetry collector
- `FILE`: Export to file (planned)

#### `LogLevel`

Standard log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

### Setup Functions

#### `setup_dev(service_name=None, log_level=LogLevel.DEBUG)`

Quick setup for development with pretty console output.

#### `setup_prod(service_name, otlp_endpoint, log_level=LogLevel.INFO)`

Quick setup for production with OTLP export.

#### `setup_json_console(service_name=None, log_level=LogLevel.INFO)`

Setup JSON output to console (ideal for containerized environments).

## Usage Patterns

### Basic Logging

```python
from pyutils.logging.tracing_2 import setup_dev, get_logger

setup_dev("my-service")
logger = get_logger("authentication")

# Structured logging with context
logger.info("Authentication attempt", 
           user_id=123, 
           ip_address="192.168.1.1",
           user_agent="Mozilla/5.0...")

# Error logging with exception info
try:
    dangerous_operation()
except Exception:
    logger.error("Operation failed", 
                operation="user_creation",
                exc_info=True)
```

### Distributed Tracing

```python
from pyutils.logging.tracing_2 import get_logger, span

logger = get_logger("order_service")

def process_order(order_id: int):
    with span("process_order", order_id=order_id):
        logger.info("Processing order", order_id=order_id)
        
        # Each major operation gets its own span
        with span("validate_payment", order_id=order_id):
            validate_payment(order_id)
        
        with span("reserve_inventory", order_id=order_id):
            reserve_items(order_id)
        
        with span("send_confirmation", order_id=order_id):
            send_email(order_id)
        
        logger.info("Order processed successfully", order_id=order_id)
```

### Function Instrumentation

```python
from pyutils.logging.tracing_2 import instrument, get_logger

# Automatic instrumentation
@instrument
def calculate_tax(amount: float, rate: float) -> float:
    logger = get_logger("tax_service")
    logger.debug("Calculating tax", amount=amount, rate=rate)
    return amount * rate

# Custom span name and attributes
@instrument(name="user_lookup", cache_enabled=True)
async def get_user_by_id(user_id: int) -> User:
    logger = get_logger("user_service")
    logger.debug("Looking up user", user_id=user_id)
    # ... async database lookup
    return user
```

### Error Handling and Observability

```python
from pyutils.logging.tracing_2 import get_logger, span

logger = get_logger("payment_service")

def process_payment(payment_data: dict):
    with span("process_payment", 
              amount=payment_data["amount"], 
              currency=payment_data["currency"]) as current_span:
        
        try:
            logger.info("Starting payment processing", **payment_data)
            
            # Your payment logic here
            result = charge_card(payment_data)
            
            logger.info("Payment processed successfully", 
                       transaction_id=result["transaction_id"],
                       amount=payment_data["amount"])
            
            return result
            
        except PaymentDeclinedException as e:
            # Span automatically records the exception
            logger.warning("Payment declined", 
                          reason=e.reason,
                          **payment_data)
            raise
            
        except PaymentServiceException as e:
            logger.error("Payment service error", 
                        error=str(e),
                        **payment_data)
            raise
```

## Production Deployment

### With Jaeger

```python
from pyutils.logging.tracing_2 import setup_prod

setup_prod(
    service_name="my-production-service",
    otlp_endpoint="http://jaeger-collector:4317",
    log_level="INFO"
)
```

### With Honeycomb

```python
from pyutils.logging.tracing_2 import prod_config, configure_logging

config = prod_config(
    service_name="my-service",
    otlp_endpoint="https://api.honeycomb.io:443",
    headers={"x-honeycomb-team": "your-write-key"},
    log_level="INFO"
)

configure_logging(config)
```

### With Custom OTLP Collector

```python
from pyutils.logging.tracing_2 import prod_config, configure_logging

config = prod_config(
    service_name="my-service",
    otlp_endpoint="https://your-collector.example.com:4317",
    headers={"authorization": "Bearer your-token"},
    log_level="WARNING"
)

configure_logging(config)
```

### Docker/Kubernetes

For containerized environments, use JSON output:

```python
from pyutils.logging.tracing_2 import setup_json_console
import os

# Configure based on environment
if os.getenv("ENVIRONMENT") == "production":
    setup_json_console(
        service_name=os.getenv("SERVICE_NAME", "my-service"),
        log_level="INFO"
    )
else:
    setup_dev(service_name="my-service", log_level="DEBUG")
```

## Advanced Usage

### Custom Processors

```python
import structlog
from pyutils.logging.tracing_2 import configure_logging, LoggingConfig, StructlogConfig

def add_custom_context(logger, method_name, event_dict):
    """Add custom context to all log events."""
    event_dict["environment"] = "production"
    event_dict["version"] = "1.2.3"
    return event_dict

config = LoggingConfig(
    structlog_config=StructlogConfig(
        processors=[
            add_custom_context,
            structlog.processors.JSONRenderer(),
        ]
    )
)

configure_logging(config)
```

### Integration with Existing Logging

```python
import logging
from pyutils.logging.tracing_2 import setup_dev, get_logger

# Setup structured logging
setup_dev("my-service")

# Structured logger
struct_logger = get_logger("my_module")

# Standard library logger still works
stdlib_logger = logging.getLogger("legacy_module")

# Both will be formatted consistently
struct_logger.info("Structured log", user_id=123)
stdlib_logger.info("Standard log message")
```

## Comparison with Rust's Tracing

This library provides a Python equivalent to Rust's popular tracing ecosystem:

| Rust | Python (this library) |
|------|----------------------|
| `tracing::info!` | `logger.info()` |
| `#[tracing::instrument]` | `@instrument` |
| `tracing::Span` | `span()` context manager |
| `tracing_subscriber` | Configuration system |
| `tracing_opentelemetry` | Built-in OpenTelemetry |

### Rust Example
```rust
use tracing::{info, instrument, Span};

#[instrument]
async fn process_request(user_id: u64) -> Result<String> {
    let span = tracing::span!(Level::INFO, "database_query", user_id);
    let _enter = span.enter();
    
    info!(user_id, "Processing request");
    // ... processing logic
    Ok("success".to_string())
}
```

### Python Equivalent
```python
from pyutils.logging.tracing_2 import get_logger, instrument, span

@instrument
async def process_request(user_id: int) -> str:
    logger = get_logger()
    
    with span("database_query", user_id=user_id):
        logger.info("Processing request", user_id=user_id)
        # ... processing logic
        return "success"
```

## Troubleshooting

### Common Issues

1. **"Logging already configured" warning**
   - This happens when `configure_logging()` is called multiple times
   - Solution: Only configure once at application startup

2. **No output appearing**
   - Check log level configuration
   - Ensure logger name matches your expectations
   - Verify output format is appropriate for your environment

3. **OTLP export failures**
   - Verify collector endpoint is reachable
   - Check authentication headers
   - Ensure network connectivity

### Debug Mode

```python
from pyutils.logging.tracing_2 import setup_dev, LogLevel

# Enable maximum verbosity
setup_dev(log_level=LogLevel.DEBUG)

# Or configure specific components
import logging
logging.getLogger("opentelemetry").setLevel(logging.DEBUG)
```

### Performance Considerations

- Use appropriate log levels in production (`INFO` or `WARNING`)
- Consider sampling for high-throughput applications
- Batch export configuration for OTLP (handled automatically)
- Avoid expensive operations in span attribute values

## License

[Add your license information here]

## Contributing

[Add contributing guidelines here]