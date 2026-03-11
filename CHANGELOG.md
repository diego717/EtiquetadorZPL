# Changelog - EtiquetadorZPL

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] - 2024-XX-XX

### Added

#### New Modules
- **`src/constants.py`**: Centralized constants for the entire application
  - Application settings
  - File size limits
  - Error and success messages
  - ZPL forbidden commands
  - Default configurations
  - Retry settings

- **`src/exceptions.py`**: Custom exception classes
  - Base `EtiquetadorZPLException` class
  - File exceptions (FileNotFoundException, FileTooLargeException, etc.)
  - Printer exceptions
  - ZPL exceptions
  - Database exceptions
  - API exceptions
  - Configuration exceptions
  - Permission exceptions
  - Centralized `ExceptionHandler` for consistent error handling

- **`src/utils.py`**: Utility functions and decorators
  - `@retry` decorator with exponential backoff
  - `@async_retry` decorator for async functions
  - `@log_call` decorator for logging function calls
  - `@timing` decorator for measuring execution time
  - `@synchronized` decorator for thread synchronization
  - `@deprecated` decorator for marking obsolete functions
  - `Timer` context manager for measuring execution time
  - Various helper functions (safe_filename, format_bytes, etc.)

- **`src/rate_limiter.py`**: Rate limiting and circuit breaker
  - `TokenBucket` implementation for rate limiting
  - `RateLimiter` class for IP-based rate limiting
  - `CircuitBreaker` pattern implementation
  - `CircuitBreakerManager` for managing multiple breakers
  - Configurable rate limits and circuit breaker thresholds

- **`src/__init__.py`**: Module initialization
  - Clean imports for all new modules
  - Re-exports for easy access

#### Database Improvements
- **`src/database.py`**: Enhanced database module
  - Singleton `DatabaseConnection` with thread-local connections
  - WAL mode enabled for better concurrency
  - Database indexes for improved query performance
  - New fields: `priority`, `retry_count`, `completed_at`
  - New methods: `get_pending_jobs`, `get_printer_statistics`, `delete_old_jobs`
  - Metrics history table for system monitoring
  - Configuration table for persistent settings

### Testing
- **`tests/test_improvements.py`**: New comprehensive test suite
  - Tests for constants
  - Tests for exceptions
  - Tests for utilities
  - Tests for rate limiter
  - Tests for circuit breaker
  - Tests for database

---

## [1.0.0] - Previous Version

### Original Features
- File monitoring with watchdog
- ZPL, TXT, PDF, and ZIP file processing
- Multiple folder monitoring (up to 3 folders)
- Printer management
- File history tracking
- PDF cropping with Poppler
- API with FastAPI
- Electron app integration
- GUI with Tkinter
- Notifications system
- Backup system
- Security validation
- System monitoring

---

## Migration Guide

### Using New Constants
```python
# Before
MAX_FILE_SIZE = 200 * 1024 * 1024

# After
from constants import MAX_FILE_SIZE_BYTES
```

### Using New Exceptions
```python
# Before
raise ValueError("File not found")

# After
from exceptions import FileNotFoundException
raise FileNotFoundException("/path/to/file")
```

### Using Retry Decorator
```python
from utils import retry

@retry(max_attempts=3, backoff_factor=2)
def unreliable_function():
    # Function that might fail
    pass
```

### Using Rate Limiter
```python
from rate_limiter import rate_limiter

# Check if request is allowed
allowed, retry_after = rate_limiter.check_rate_limit("client_ip")
if not allowed:
    print(f"Try again in {retry_after} seconds")
```

### Using Circuit Breaker
```python
from rate_limiter import get_circuit_breaker

cb = get_circuit_breaker("printer_1")

if cb.can_execute():
    try:
        result = print_job()
        cb.record_success()
    except Exception:
        cb.record_failure()
else:
    print("Printer unavailable")
```

---

## Coming Soon (Planned)

### Phase 2
- [ ] Enhanced API documentation
- [ ] More comprehensive tests
- [ ] Performance optimizations
- [ ] Async job processing
- [ ] Job queue with priorities

### Phase 3
- [ ] Web dashboard improvements
- [ ] Mobile notifications
- [ ] Multi-language support
- [ ] Plugin system
- [ ] REST API v2

---

## Credits

Developed with ❤️ for label printing automation.

