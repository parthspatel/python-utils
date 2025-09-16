"""Example usage of the structlog + OpenTelemetry tracing system."""

import asyncio
import time
from typing import Dict, Any

# Import our tracing interface
from . import (
    get_logger,
    span,
    instrument,
    setup_dev,
    setup_prod,
    setup_json_console,
    configure_logging,
    dev_config,
    prod_config,
    LogLevel,
    OutputFormat,
    ExportTarget,
    LoggingConfig,
    StructlogConfig,
    OtelConfig,
)


def basic_logging_example():
    """Basic logging example - Rust-like interface."""
    print("\n=== Basic Logging Example ===")

    # Get a logger (similar to Rust's tracing)
    logger = get_logger("example.basic")

    # Log at different levels
    logger.debug("This is a debug message", user_id=123, action="login")
    logger.info("User authenticated", user_id=123, username="alice")
    logger.warning("Rate limit approaching", user_id=123, requests_remaining=5)
    logger.error("Failed to process request", user_id=123, error_code="TIMEOUT")
    logger.critical("Database connection lost", retry_count=3)


def span_tracing_example():
    """Example using spans for distributed tracing."""
    print("\n=== Span Tracing Example ===")

    logger = get_logger("example.spans")

    # Manual span creation
    with span("process_user_request", user_id=456, operation="create_account"):
        logger.info("Starting user account creation")

        with span("validate_input", field_count=5):
            logger.debug("Validating user input")
            time.sleep(0.1)  # Simulate work

        with span("database_insert", table="users"):
            logger.debug("Inserting user into database")
            time.sleep(0.2)  # Simulate database work

        logger.info("User account created successfully")


@instrument(name="calculate_fibonacci")
def fibonacci(n: int) -> int:
    """Example of function instrumentation."""
    logger = get_logger("example.fibonacci")

    if n <= 1:
        logger.debug("Base case reached", n=n)
        return n

    logger.debug("Calculating fibonacci", n=n)
    result = fibonacci(n - 1) + fibonacci(n - 2)
    logger.debug("Fibonacci calculated", n=n, result=result)
    return result


@instrument
async def async_operation(duration: float) -> Dict[str, Any]:
    """Example of async function instrumentation."""
    logger = get_logger("example.async")

    logger.info("Starting async operation", duration=duration)
    await asyncio.sleep(duration)

    result = {"status": "completed", "duration": duration, "timestamp": time.time()}
    logger.info("Async operation completed", **result)
    return result


def trace_context_example():
    """Example showing trace context (trace_id, span_id, span_name) in logs."""
    print("\n=== Trace Context Example ===")

    logger = get_logger("example.trace_context")

    # Log outside of any span - no trace context
    logger.info("Starting application", service="example-app")

    # Create a top-level business operation span
    with span("process_customer_order", customer_id=12345, order_value=299.99):
        logger.info("Processing customer order", order_id="ORD-001")

        # Nested span for payment processing
        with span("payment_validation", payment_method="credit_card"):
            logger.info("Validating payment method", card_type="visa")
            logger.info("Payment validation successful", authorized_amount=299.99)

        # Nested span for inventory check
        with span("inventory_check", warehouse="east-coast"):
            logger.info("Checking inventory availability", items_requested=3)
            logger.warning("Low stock detected", remaining_stock=2)

        # Nested span for shipping calculation
        with span("shipping_calculation", destination_zip="10001"):
            logger.info("Calculating shipping cost", shipping_method="express")
            logger.info("Shipping cost calculated", shipping_cost=15.99)

        logger.info("Customer order processed successfully",
                   total_amount=315.98,
                   estimated_delivery="2024-01-15")

    # Back outside span context
    logger.info("Order processing workflow completed", orders_processed=1)

    print("\nNotice how each log message includes:")
    print("• trace_id: Links all logs from the same request/workflow")
    print("• span_id: Identifies the specific operation context")
    print("• span_name: Shows exactly which operation generated the log")
    print("• This makes it easy to correlate logs with distributed traces!")


def error_handling_example():
    """Example of error handling with tracing."""
    print("\n=== Error Handling Example ===")

    logger = get_logger("example.errors")

    try:
        with span("risky_operation", risk_level="high"):
            logger.info("Attempting risky operation")
            raise ValueError("Something went wrong!")
    except ValueError as e:
        logger.error("Operation failed", error=str(e), exc_info=True)


def configuration_examples():
    """Examples of different configurations."""
    print("\n=== Configuration Examples ===")

    # 1. Development configuration (pretty console)
    print("\n--- Development Config (Pretty) ---")
    configure_logging(dev_config(
        service_name="my-service",
        log_level=LogLevel.DEBUG,
        output_format=OutputFormat.PRETTY
    ))
    get_logger("config.dev").info("Development logging with pretty output")

    # 2. JSON console configuration (good for containers)
    print("\n--- JSON Console Config ---")
    setup_json_console(service_name="my-service", log_level=LogLevel.INFO)
    get_logger("config.json").info("JSON logging to console", environment="production")

    # 3. Advanced custom configuration
    print("\n--- Custom Advanced Config ---")
    custom_config = LoggingConfig(
        output_format=OutputFormat.KEY_VALUE,
        export_target=ExportTarget.CONSOLE,
        structlog_config=StructlogConfig(
            log_level=LogLevel.INFO,
            add_logger_name=True,
            add_log_level=True,
            include_stdlib=True,
        ),
        otel_config=OtelConfig(
            service_name="advanced-service",
            service_version="1.2.3",
            service_instance_id="instance-001"
        )
    )
    configure_logging(custom_config)
    get_logger("config.advanced").info("Advanced custom configuration", feature="custom_processors")


def production_simulation():
    """Simulate production configuration (without actual OTLP endpoint)."""
    print("\n=== Production Configuration Simulation ===")

    # This would normally connect to an actual OTLP collector
    # For demo purposes, we'll just show the configuration
    try:
        # This will warn and fall back to console since we don't have a real endpoint
        prod_config_example = prod_config(
            service_name="production-service",
            otlp_endpoint="http://localhost:4317",  # This doesn't exist
            log_level=LogLevel.WARNING,
            headers={"api-key": "secret-key"}
        )

        print("Production config created (would export to OTLP in real environment):")
        print(f"- Service: {prod_config_example.otel_config.service_name}")
        print(f"- Endpoint: {prod_config_example.otel_config.endpoint}")
        print(f"- Format: {prod_config_example.output_format}")

    except Exception as e:
        logger = get_logger("example.prod_simulation")
        logger.warning("Production config simulation", error=str(e))


async def comprehensive_example():
    """Comprehensive example showing all features together."""
    print("\n=== Comprehensive Example ===")

    # Setup with pretty dev config
    setup_dev(service_name="comprehensive-example", log_level=LogLevel.DEBUG)

    logger = get_logger("example.comprehensive")

    # Start a top-level operation
    with span("user_journey", user_type="premium", session_id="abc123"):
        logger.info("Starting user journey")

        # Synchronous instrumented function
        fib_result = fibonacci(5)
        logger.info("Fibonacci calculation completed", result=fib_result)

        # Asynchronous instrumented function
        async_result = await async_operation(0.5)
        logger.info("Async operation completed", result=async_result)

        # Nested spans with different contexts
        with span("data_processing", batch_size=100):
            logger.debug("Processing data batch")

            for i in range(3):
                with span("process_item", item_id=i):
                    logger.debug("Processing item", item_id=i)
                    if i == 1:
                        # Simulate an error in one item
                        try:
                            raise ConnectionError("Network timeout")
                        except ConnectionError:
                            logger.warning("Item processing failed",
                                         item_id=i,
                                         exc_info=True,
                                         will_retry=True)

        logger.info("User journey completed successfully")


def main():
    """Run all examples."""
    print("🔍 Structlog + OpenTelemetry Tracing Examples")
    print("=" * 50)

    # Setup development logging (pretty console output)
    setup_dev(service_name="example-service", log_level=LogLevel.DEBUG)

    # Basic examples
    basic_logging_example()
    span_tracing_example()
    trace_context_example()
    error_handling_example()

    # Configuration examples
    configuration_examples()
    production_simulation()

    # Run comprehensive async example
    print("\n=== Running Comprehensive Async Example ===")
    asyncio.run(comprehensive_example())

    print("All examples completed!")
    print("Note: In a real application, you would:")
    print("1. Set up logging once at application startup")
    print("2. Use get_logger() throughout your codebase")
    print("3. Use @instrument decorator on important functions")
    print("4. Use span() context manager for logical operations")
    print("5. Configure OTLP export for production monitoring")


if __name__ == "__main__":
    main()
