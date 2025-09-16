"""Tests for the structlog + OpenTelemetry tracing configuration."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock
import structlog

from pyutils.logging.tracing import (
    get_logger,
    span,
    instrument,
    setup_dev,
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


class TestConfiguration:
    """Test configuration creation and validation."""

    def test_dev_config_creation(self):
        """Test development configuration creation."""
        config = dev_config(
            service_name="test-service",
            log_level=LogLevel.DEBUG,
            output_format=OutputFormat.PRETTY
        )

        assert config.output_format == OutputFormat.PRETTY
        assert config.export_target == ExportTarget.CONSOLE
        assert config.structlog_config.log_level == LogLevel.DEBUG
        assert config.otel_config.service_name == "test-service"

    def test_prod_config_creation(self):
        """Test production configuration creation."""
        config = prod_config(
            service_name="prod-service",
            otlp_endpoint="http://localhost:4317",
            log_level=LogLevel.INFO,
            headers={"api-key": "secret"}
        )

        assert config.output_format == OutputFormat.JSON
        assert config.export_target == ExportTarget.OTLP
        assert config.structlog_config.log_level == LogLevel.INFO
        assert config.otel_config.service_name == "prod-service"
        assert config.otel_config.endpoint == "http://localhost:4317"
        assert config.otel_config.headers == {"api-key": "secret"}

    def test_custom_config_creation(self):
        """Test custom configuration creation."""
        config = LoggingConfig(
            output_format=OutputFormat.KEY_VALUE,
            export_target=ExportTarget.CONSOLE,
            structlog_config=StructlogConfig(
                log_level=LogLevel.WARNING,
                add_logger_name=False,
            ),
            otel_config=OtelConfig(
                service_name="custom-service",
                service_version="2.0.0"
            )
        )

        assert config.output_format == OutputFormat.KEY_VALUE
        assert config.structlog_config.log_level == LogLevel.WARNING
        assert config.structlog_config.add_logger_name is False
        assert config.otel_config.service_name == "custom-service"
        assert config.otel_config.service_version == "2.0.0"


class TestLoggingSetup:
    """Test logging setup and configuration."""

    def setup_method(self):
        """Reset configuration state before each test."""
        # Reset the global configuration state
        from pyutils.logging.tracing.config import _configured, _logger_cache
        import pyutils.logging.tracing.config as config_module
        config_module._configured = False
        config_module._logger_cache.clear()

    def test_setup_dev(self):
        """Test development setup."""
        setup_dev(service_name="test-dev", log_level=LogLevel.DEBUG)

        logger = get_logger("test.dev")
        assert logger is not None
        assert hasattr(logger, 'info')
        assert hasattr(logger, 'debug')
        assert hasattr(logger, 'error')

    def test_setup_json_console(self):
        """Test JSON console setup."""
        setup_json_console(service_name="test-json", log_level=LogLevel.INFO)

        logger = get_logger("test.json")
        assert logger is not None

    def test_get_logger_auto_config(self):
        """Test that get_logger auto-configures if not already configured."""
        logger = get_logger("test.auto")
        assert logger is not None

        # Should be able to call logging methods
        logger.info("test message", key="value")

    def test_get_logger_with_name(self):
        """Test getting logger with explicit name."""
        setup_dev()

        logger1 = get_logger("explicit.name")
        logger2 = get_logger("explicit.name")

        # Should return the same cached logger
        assert logger1 is logger2

    def test_get_logger_without_name(self):
        """Test getting logger without explicit name (should infer from caller)."""
        setup_dev()

        logger = get_logger()
        assert logger is not None


class TestSpanContext:
    """Test span context management."""

    def setup_method(self):
        """Setup for span tests."""
        setup_dev(service_name="test-spans")

    def test_basic_span(self):
        """Test basic span creation and usage."""
        logger = get_logger("test.span")

        with span("test_operation", user_id=123, operation="test"):
            logger.info("Inside span", message="test")
            # Span should be active here

    def test_nested_spans(self):
        """Test nested span creation."""
        logger = get_logger("test.nested")

        with span("outer_operation", level="outer"):
            logger.info("In outer span")

            with span("inner_operation", level="inner"):
                logger.info("In inner span")

            logger.info("Back in outer span")

    def test_span_with_exception(self):
        """Test span behavior when exception occurs."""
        logger = get_logger("test.span.error")

        with pytest.raises(ValueError):
            with span("failing_operation", should_fail=True):
                logger.info("About to fail")
                raise ValueError("Test error")


class TestInstrumentation:
    """Test function instrumentation."""

    def setup_method(self):
        """Setup for instrumentation tests."""
        setup_dev(service_name="test-instrument")

    def test_sync_instrumentation(self):
        """Test synchronous function instrumentation."""
        @instrument(name="test_sync_function")
        def sync_function(x: int, y: int) -> int:
            logger = get_logger("test.sync")
            logger.info("Calculating", x=x, y=y)
            return x + y

        result = sync_function(2, 3)
        assert result == 5

    def test_sync_instrumentation_auto_name(self):
        """Test synchronous function instrumentation with auto-generated name."""
        @instrument
        def auto_named_function(value: str) -> str:
            logger = get_logger("test.auto")
            logger.info("Processing", value=value)
            return value.upper()

        result = auto_named_function("hello")
        assert result == "HELLO"

    @pytest.mark.asyncio
    async def test_async_instrumentation(self):
        """Test asynchronous function instrumentation."""
        @instrument(name="test_async_function")
        async def async_function(delay: float) -> str:
            logger = get_logger("test.async")
            logger.info("Starting async work", delay=delay)
            await asyncio.sleep(delay)
            logger.info("Async work completed")
            return "completed"

        result = await async_function(0.01)
        assert result == "completed"

    def test_instrumentation_with_exception(self):
        """Test instrumentation when function raises exception."""
        @instrument(name="failing_function")
        def failing_function():
            raise RuntimeError("Test failure")

        with pytest.raises(RuntimeError):
            failing_function()


class TestOutputFormats:
    """Test different output formats."""

    def setup_method(self):
        """Reset state before each test."""
        from pyutils.logging.tracing.config import _configured
        import pyutils.logging.tracing.config as config_module
        config_module._configured = False
        config_module._logger_cache.clear()

    def test_pretty_format(self):
        """Test pretty format configuration."""
        config = dev_config(output_format=OutputFormat.PRETTY)
        configure_logging(config)

        logger = get_logger("test.pretty")
        logger.info("Pretty formatted message", key="value")

    def test_json_format(self):
        """Test JSON format configuration."""
        config = dev_config(output_format=OutputFormat.JSON)
        configure_logging(config)

        logger = get_logger("test.json")
        logger.info("JSON formatted message", key="value")

    def test_key_value_format(self):
        """Test key-value format configuration."""
        config = dev_config(output_format=OutputFormat.KEY_VALUE)
        configure_logging(config)

        logger = get_logger("test.kv")
        logger.info("Key-value formatted message", key="value")


class TestErrorHandling:
    """Test error handling and edge cases."""

    def setup_method(self):
        """Setup for error tests."""
        setup_dev(service_name="test-errors")

    def test_logging_with_exception_info(self):
        """Test logging with exception information."""
        logger = get_logger("test.exc")

        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.error("An error occurred", exc_info=True, context="test")

    def test_multiple_configuration_attempts(self):
        """Test that multiple configuration attempts are handled gracefully."""
        with patch('warnings.warn') as mock_warn:
            configure_logging(dev_config(service_name="first"))
            configure_logging(dev_config(service_name="second"))  # Should warn

            mock_warn.assert_called_once()

    def test_prod_config_without_endpoint_raises_error(self):
        """Test that production config without OTLP endpoint raises appropriate error."""
        config = LoggingConfig(
            export_target=ExportTarget.OTLP,
            otel_config=None  # Missing config
        )

        with pytest.raises(ValueError, match="OTLP endpoint required"):
            configure_logging(config)


class TestIntegration:
    """Integration tests combining multiple features."""

    def setup_method(self):
        """Setup for integration tests."""
        from pyutils.logging.tracing.config import _configured
        import pyutils.logging.tracing.config as config_module
        config_module._configured = False
        config_module._logger_cache.clear()

    def test_complete_workflow(self):
        """Test a complete workflow with logging, spans, and instrumentation."""
        # Setup
        setup_dev(service_name="integration-test", log_level=LogLevel.DEBUG)

        # Get logger
        logger = get_logger("integration.workflow")

        # Define instrumented function
        @instrument(name="process_data")
        def process_data(data_id: int) -> dict:
            with span("validate_data", data_id=data_id):
                logger.debug("Validating data", data_id=data_id)

            with span("transform_data", data_id=data_id):
                logger.info("Transforming data", data_id=data_id)
                result = {"id": data_id, "processed": True}

            return result

        # Execute workflow
        with span("user_request", user_id=456):
            logger.info("Starting user request processing")

            result = process_data(123)

            logger.info("Request completed", result=result)
            assert result["processed"] is True

    @pytest.mark.asyncio
    async def test_async_workflow(self):
        """Test async workflow with spans and instrumentation."""
        setup_dev(service_name="async-integration-test")

        @instrument
        async def async_process(item_id: int) -> str:
            logger = get_logger("async.process")

            with span("async_operation", item_id=item_id):
                logger.info("Processing async item", item_id=item_id)
                await asyncio.sleep(0.01)  # Simulate async work
                return f"processed-{item_id}"

        # Execute async workflow
        with span("batch_process", batch_size=3):
            logger = get_logger("async.batch")
            logger.info("Starting batch processing")

            tasks = [async_process(i) for i in range(3)]
            results = await asyncio.gather(*tasks)

            logger.info("Batch completed", results=results)
            assert len(results) == 3
            assert all("processed-" in result for result in results)
