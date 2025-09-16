# Usage Guide: Structlog + OpenTelemetry Tracing

## Quick Start

### 1. Basic Development Setup

```python
from pyutils.logging.tracing_2 import setup_dev, get_logger

# One-line setup for development
setup_dev(service_name="my-app", log_level="DEBUG")

# Get a logger and start logging
logger = get_logger("user_service")
logger.info("User login attempt", user_id=123, ip="192.168.1.1")
```

### 2. Production Setup

```python
from pyutils.logging.tracing_2 import setup_prod
import os

# Production setup with environment variables
setup_prod(
    service_name=os.getenv("SERVICE_NAME", "my-service"),
    otlp_endpoint=os.getenv("OTLP_ENDPOINT", "http://jaeger:4317"),
    log_level="INFO"
)
```

### 3. Container/Docker Setup

```python
from pyutils.logging.tracing_2 import setup_json_console

# JSON output for log aggregation
setup_json_console(service_name="my-container-app", log_level="INFO")
```

## Common Patterns

### Web Request Tracing

```python
from pyutils.logging.tracing_2 import get_logger, span, instrument
from flask import Flask, request

app = Flask(__name__)
logger = get_logger("web_service")

@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    with span("http_request", 
              method=request.method, 
              path=request.path, 
              user_id=user_id):
        
        logger.info("Processing user request", 
                   user_id=user_id, 
                   ip=request.remote_addr)
        
        try:
            user = fetch_user_from_db(user_id)
            logger.info("User found", user_id=user_id, username=user.name)
            return {"user": user.to_dict()}
        except UserNotFound:
            logger.warning("User not found", user_id=user_id)
            return {"error": "User not found"}, 404
```

### Database Operations

```python
@instrument(name="database_query")
def fetch_user_from_db(user_id: int):
    logger = get_logger("database")
    
    with span("db_connection", table="users", operation="select"):
        logger.debug("Connecting to database")
        
        with span("sql_query", user_id=user_id):
            logger.debug("Executing query", user_id=user_id)
            # Your database logic here
            return user_data
```

### Background Jobs

```python
from pyutils.logging.tracing_2 import get_logger, span
import time

def process_email_queue():
    logger = get_logger("email_worker")
    
    while True:
        with span("process_batch", batch_size=10):
            emails = get_pending_emails(limit=10)
            
            if not emails:
                time.sleep(5)
                continue
            
            logger.info("Processing email batch", count=len(emails))
            
            for email in emails:
                with span("send_email", email_id=email.id, recipient=email.to):
                    try:
                        send_email(email)
                        logger.info("Email sent", email_id=email.id)
                    except Exception as e:
                        logger.error("Email failed", 
                                   email_id=email.id, 
                                   error=str(e))
```

### Async Operations

```python
import asyncio
from pyutils.logging.tracing_2 import get_logger, instrument, span

@instrument
async def process_user_data(user_ids: list):
    logger = get_logger("async_processor")
    
    with span("batch_process", total_users=len(user_ids)):
        logger.info("Starting batch processing", user_count=len(user_ids))
        
        tasks = [process_single_user(user_id) for user_id in user_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful = len([r for r in results if not isinstance(r, Exception)])
        logger.info("Batch completed", 
                   successful=successful, 
                   failed=len(results) - successful)

@instrument
async def process_single_user(user_id: int):
    logger = get_logger("user_processor")
    
    with span("user_processing", user_id=user_id):
        logger.debug("Processing user", user_id=user_id)
        
        # Simulate async work
        await asyncio.sleep(0.1)
        
        logger.debug("User processed", user_id=user_id)
```

## Configuration Examples

### Environment-Based Configuration

```python
import os
from pyutils.logging.tracing_2 import (
    setup_dev, setup_prod, setup_json_console, 
    configure_logging, LoggingConfig, StructlogConfig, OtelConfig,
    OutputFormat, ExportTarget, LogLevel
)

def setup_logging():
    env = os.getenv("ENVIRONMENT", "development")
    
    if env == "development":
        setup_dev(
            service_name="my-app",
            log_level=LogLevel.DEBUG
        )
    
    elif env == "production":
        setup_prod(
            service_name=os.getenv("SERVICE_NAME", "my-service"),
            otlp_endpoint=os.getenv("OTLP_ENDPOINT"),
            log_level=LogLevel.INFO
        )
    
    elif env == "staging":
        setup_json_console(
            service_name="my-service-staging",
            log_level=LogLevel.DEBUG
        )
    
    else:
        # Custom configuration
        custom_config = LoggingConfig(
            output_format=OutputFormat.KEY_VALUE,
            export_target=ExportTarget.CONSOLE,
            structlog_config=StructlogConfig(
                log_level=LogLevel.INFO,
                add_logger_name=True,
            )
        )
        configure_logging(custom_config)
```

### Advanced Custom Configuration

```python
import structlog
from pyutils.logging.tracing_2 import configure_logging, LoggingConfig, StructlogConfig

def add_custom_fields(logger, method_name, event_dict):
    """Add custom fields to all log entries."""
    event_dict["service_version"] = "1.2.3"
    event_dict["environment"] = os.getenv("ENV", "unknown")
    return event_dict

def filter_sensitive_data(logger, method_name, event_dict):
    """Remove sensitive data from logs."""
    for key in ["password", "token", "secret"]:
        if key in event_dict:
            event_dict[key] = "[REDACTED]"
    return event_dict

# Custom configuration with processors
config = LoggingConfig(
    output_format=OutputFormat.JSON,
    export_target=ExportTarget.CONSOLE,
    structlog_config=StructlogConfig(
        processors=[
            add_custom_fields,
            filter_sensitive_data,
            structlog.processors.JSONRenderer()
        ],
        log_level=LogLevel.INFO
    )
)

configure_logging(config)
```

## Production Deployment

### Docker Container

```python
# app.py
import os
from pyutils.logging.tracing_2 import setup_json_console, get_logger

def setup_container_logging():
    """Setup logging for containerized environment."""
    setup_json_console(
        service_name=os.getenv("SERVICE_NAME", "my-service"),
        log_level=os.getenv("LOG_LEVEL", "INFO")
    )

if __name__ == "__main__":
    setup_container_logging()
    
    logger = get_logger("main")
    logger.info("Application starting", 
               version=os.getenv("VERSION", "unknown"),
               environment=os.getenv("ENVIRONMENT", "production"))
    
    # Your application code
```

### Kubernetes with Jaeger

```python
# config.py
import os
from pyutils.logging.tracing_2 import prod_config, configure_logging

def setup_k8s_logging():
    """Setup logging for Kubernetes deployment with Jaeger."""
    
    # Environment variables set by Kubernetes
    service_name = os.getenv("SERVICE_NAME")
    jaeger_endpoint = os.getenv("JAEGER_ENDPOINT", "http://jaeger-collector:4317")
    
    if not service_name:
        raise ValueError("SERVICE_NAME environment variable required")
    
    config = prod_config(
        service_name=service_name,
        otlp_endpoint=jaeger_endpoint,
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        headers={
            "x-service-version": os.getenv("VERSION", "unknown"),
        }
    )
    
    configure_logging(config)
```

### Honeycomb.io Integration

```python
from pyutils.logging.tracing_2 import prod_config, configure_logging
import os

def setup_honeycomb_logging():
    """Setup logging with Honeycomb.io."""
    
    api_key = os.getenv("HONEYCOMB_API_KEY")
    if not api_key:
        raise ValueError("HONEYCOMB_API_KEY environment variable required")
    
    config = prod_config(
        service_name=os.getenv("SERVICE_NAME", "my-service"),
        otlp_endpoint="https://api.honeycomb.io:443",
        headers={
            "x-honeycomb-team": api_key,
            "x-honeycomb-dataset": os.getenv("HONEYCOMB_DATASET", "production")
        },
        log_level="INFO"
    )
    
    configure_logging(config)
```

## Error Handling Best Practices

### Structured Error Logging

```python
from pyutils.logging.tracing_2 import get_logger, span

logger = get_logger("payment_service")

def process_payment(payment_data):
    with span("payment_processing", 
              amount=payment_data["amount"],
              currency=payment_data["currency"]) as current_span:
        
        try:
            logger.info("Processing payment", **payment_data)
            
            # Payment processing logic
            result = charge_card(payment_data)
            
            logger.info("Payment successful", 
                       transaction_id=result["id"],
                       amount=payment_data["amount"])
            
            return result
            
        except PaymentDeclined as e:
            # Span automatically records exception
            logger.warning("Payment declined", 
                          reason=e.reason,
                          decline_code=e.code,
                          **payment_data)
            raise
            
        except Exception as e:
            logger.error("Payment processing failed", 
                        error=str(e),
                        error_type=type(e).__name__,
                        **payment_data)
            raise
```

### Retry Logic with Tracing

```python
import time
from pyutils.logging.tracing_2 import get_logger, span

def with_retry(operation_name, max_retries=3):
    """Decorator for retry logic with tracing."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger("retry_service")
            
            for attempt in range(max_retries + 1):
                with span(f"{operation_name}_attempt", 
                         attempt=attempt + 1, 
                         max_retries=max_retries):
                    
                    try:
                        result = func(*args, **kwargs)
                        if attempt > 0:
                            logger.info("Operation succeeded after retry", 
                                      operation=operation_name,
                                      attempts=attempt + 1)
                        return result
                    
                    except Exception as e:
                        if attempt == max_retries:
                            logger.error("Operation failed after all retries", 
                                       operation=operation_name,
                                       total_attempts=attempt + 1,
                                       final_error=str(e))
                            raise
                        
                        logger.warning("Operation failed, retrying", 
                                     operation=operation_name,
                                     attempt=attempt + 1,
                                     error=str(e),
                                     retry_in=2**attempt)
                        
                        time.sleep(2**attempt)  # Exponential backoff
        return wrapper
    return decorator

@with_retry("database_query")
def query_database(query):
    # Your database query logic
    pass
```

## Performance Monitoring

### Request Duration Tracking

```python
import time
from pyutils.logging.tracing_2 import get_logger, span

def monitor_performance(operation_name):
    """Decorator to monitor operation performance."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger("performance")
            start_time = time.time()
            
            with span(operation_name, function=func.__name__):
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    
                    logger.info("Operation completed", 
                              operation=operation_name,
                              duration_ms=round(duration * 1000, 2),
                              status="success")
                    
                    return result
                    
                except Exception as e:
                    duration = time.time() - start_time
                    
                    logger.error("Operation failed", 
                               operation=operation_name,
                               duration_ms=round(duration * 1000, 2),
                               status="error",
                               error=str(e))
                    raise
        return wrapper
    return decorator

@monitor_performance("user_lookup")
def get_user_profile(user_id):
    # Your user lookup logic
    pass
```

## Testing with Tracing

### Unit Tests

```python
import pytest
from pyutils.logging.tracing_2 import setup_dev, get_logger, span

@pytest.fixture(autouse=True)
def setup_test_logging():
    """Setup logging for tests."""
    setup_dev(service_name="test-service", log_level="DEBUG")

def test_user_creation():
    logger = get_logger("test.user_creation")
    
    with span("test_user_creation", test_case="valid_user"):
        logger.info("Testing user creation")
        
        # Your test logic
        user = create_user({"name": "Test User", "email": "test@example.com"})
        
        assert user.name == "Test User"
        logger.info("User creation test passed", user_id=user.id)
```

### Integration Tests

```python
from pyutils.logging.tracing_2 import get_logger, span, instrument

@instrument(name="integration_test")
def test_complete_workflow():
    logger = get_logger("integration_test")
    
    with span("setup_test_data"):
        # Setup test data
        test_user = create_test_user()
        logger.info("Test data created", user_id=test_user.id)
    
    with span("execute_workflow"):
        # Execute the workflow
        result = process_user_workflow(test_user.id)
        logger.info("Workflow completed", result=result)
    
    with span("verify_results"):
        # Verify results
        assert result.status == "completed"
        logger.info("Integration test passed")
```

## Best Practices

### 1. Consistent Naming

```python
# Good: Consistent naming convention
logger = get_logger("user_service.authentication")
logger = get_logger("user_service.profile")
logger = get_logger("payment_service.processing")

# Good: Consistent span names
with span("http_request", method="POST", endpoint="/api/users"):
    pass

with span("database_query", table="users", operation="insert"):
    pass
```

### 2. Meaningful Context

```python
# Good: Rich context
logger.info("User login successful", 
           user_id=user.id,
           username=user.username,
           login_method="password",
           ip_address=request.ip,
           user_agent=request.headers.get("User-Agent"),
           session_id=session.id)

# Avoid: Minimal context
logger.info("Login successful")
```

### 3. Appropriate Log Levels

```python
# DEBUG: Detailed information for debugging
logger.debug("Processing item", item_id=item.id, step="validation")

# INFO: General information about application flow
logger.info("User registered", user_id=user.id, email=user.email)

# WARNING: Something unexpected but not necessarily an error
logger.warning("API rate limit approaching", 
              user_id=user.id, 
              requests_remaining=5)

# ERROR: Error conditions that need attention
logger.error("Payment processing failed", 
            user_id=user.id, 
            error_code="CARD_DECLINED",
            exc_info=True)
```

### 4. Security Considerations

```python
def sanitize_sensitive_data(event_dict):
    """Remove sensitive data from logs."""
    sensitive_keys = ["password", "token", "api_key", "credit_card"]
    
    for key in sensitive_keys:
        if key in event_dict:
            event_dict[key] = "[REDACTED]"
    
    # Also sanitize nested dictionaries
    for key, value in event_dict.items():
        if isinstance(value, dict):
            event_dict[key] = sanitize_sensitive_data(value)
    
    return event_dict

# Use in your configuration
config = LoggingConfig(
    structlog_config=StructlogConfig(
        processors=[sanitize_sensitive_data, ...]
    )
)
```

This usage guide should help you get started with structured logging and distributed tracing using the Rust-like interface we've created!