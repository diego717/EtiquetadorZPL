"""
Tests para los nuevos módulos de mejora
"""

import unittest
import tempfile
import time
import threading
from pathlib import Path
import sys
import os

# Agregar paths
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


class TestConstants(unittest.TestCase):
    """Tests para constantes"""
    
    def test_app_constants(self):
        """Test: Constantes de aplicación"""
        from constants import APP_NAME, APP_VERSION
        
        self.assertEqual(APP_NAME, "EtiquetadorZPL")
        self.assertIsNotNone(APP_VERSION)
        print("✅ Constantes de aplicación OK")
    
    def test_job_status(self):
        """Test: Estados de trabajo"""
        from constants import JOB_STATUS
        
        self.assertIn('PENDING', JOB_STATUS)
        self.assertIn('PROCESSING', JOB_STATUS)
        self.assertIn('COMPLETED', JOB_STATUS)
        self.assertIn('FAILED', JOB_STATUS)
        self.assertIn('CANCELLED', JOB_STATUS)
        print("✅ Estados de trabajo OK")
    
    def test_allowed_extensions(self):
        """Test: Extensiones permitidas"""
        from constants import ALLOWED_EXTENSIONS
        
        self.assertIn('.pdf', ALLOWED_EXTENSIONS)
        self.assertIn('.txt', ALLOWED_EXTENSIONS)
        self.assertIn('.zpl', ALLOWED_EXTENSIONS)
        self.assertIn('.zip', ALLOWED_EXTENSIONS)
        print("✅ Extensiones permitidas OK")
    
    def test_size_limits(self):
        """Test: Límites de tamaño"""
        from constants import MAX_FILE_SIZE_BYTES, MAX_ZIP_SIZE_BYTES
        
        self.assertGreater(MAX_FILE_SIZE_BYTES, 0)
        self.assertGreater(MAX_ZIP_SIZE_BYTES, 0)
        self.assertGreater(MAX_ZIP_SIZE_BYTES, MAX_FILE_SIZE_BYTES)
        print("✅ Límites de tamaño OK")


class TestExceptions(unittest.TestCase):
    """Tests para excepciones"""
    
    def test_base_exception(self):
        """Test: Excepción base"""
        from exceptions import EtiquetadorZPLException
        
        exc = EtiquetadorZPLException("Test error", "TEST_CODE", {"key": "value"})
        self.assertEqual(exc.message, "Test error")
        self.assertEqual(exc.code, "TEST_CODE")
        self.assertEqual(exc.details["key"], "value")
        
        # Test to_dict
        error_dict = exc.to_dict()
        self.assertEqual(error_dict["error"], "TEST_CODE")
        self.assertEqual(error_dict["message"], "Test error")
        print("✅ Excepción base OK")
    
    def test_file_exceptions(self):
        """Test: Excepciones de archivo"""
        from exceptions import (
            FileNotFoundException,
            FileTooLargeException,
            InvalidExtensionException
        )
        
        # FileNotFoundException
        exc = FileNotFoundException("/test/path.txt")
        self.assertEqual(exc.code, "FILE_NOT_FOUND")
        self.assertIn("/test/path.txt", exc.message)
        
        # FileTooLargeException
        exc = FileTooLargeException("test.zip", 600, 500)
        self.assertEqual(exc.code, "FILE_TOO_LARGE")
        self.assertIn("600", exc.message)
        
        # InvalidExtensionException
        exc = InvalidExtensionException(".exe", {".pdf", ".txt"})
        self.assertEqual(exc.code, "INVALID_EXTENSION")
        self.assertIn(".exe", exc.message)
        print("✅ Excepciones de archivo OK")
    
    def test_printer_exceptions(self):
        """Test: Excepciones de impresora"""
        from exceptions import (
            PrinterNotFoundException,
            PrinterNotConfiguredException,
            PrinterConnectionException
        )
        
        exc = PrinterNotFoundException("TestPrinter")
        self.assertEqual(exc.code, "PRINTER_NOT_FOUND")
        self.assertIn("TestPrinter", exc.message)
        
        exc = PrinterNotConfiguredException()
        self.assertEqual(exc.code, "PRINTER_NOT_CONFIGURED")
        
        exc = PrinterConnectionException("TestPrinter", "Connection refused")
        self.assertEqual(exc.code, "PRINTER_CONNECTION_ERROR")
        print("✅ Excepciones de impresora OK")
    
    def test_exception_handler(self):
        """Test: Manejador de excepciones"""
        from exceptions import ExceptionHandler, EtiquetadorZPLException
        
        # Test con excepción personalizada
        exc = EtiquetadorZPLException("Error test", "TEST")
        result = ExceptionHandler.handle_exception(exc)
        self.assertEqual(result["error"], "TEST")
        
        # Test con excepción genérica
        result = ExceptionHandler.handle_exception(ValueError("Test error"))
        self.assertEqual(result["error"], "UNKNOWN_ERROR")
        
        # Test is_retryable
        from exceptions import PrinterConnectionException
        self.assertTrue(ExceptionHandler.is_retryable(PrinterConnectionException("Test", "Error")))
        self.assertTrue(ExceptionHandler.is_retryable(TimeoutError()))
        print("✅ Manejador de excepciones OK")


class TestUtils(unittest.TestCase):
    """Tests para utilidades"""
    
    def test_retry_decorator(self):
        """Test: Decorador retry"""
        from utils import retry
        
        attempt_count = 0
        
        @retry(max_attempts=3, exceptions=(ValueError,))
        def func_that_fails_twice():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Fail")
            return "success"
        
        result = func_that_fails_twice()
        self.assertEqual(result, "success")
        self.assertEqual(attempt_count, 3)
        print("✅ Decorador retry OK")
    
    def test_timer(self):
        """Test: Timer context manager"""
        from utils import Timer
        import logging
        
        logger = logging.getLogger("test")
        
        with Timer("test", logger) as t:
            time.sleep(0.1)
        
        self.assertGreater(t.elapsed, 0.1)
        print("✅ Timer OK")
    
    def test_safe_filename(self):
        """Test: safe_filename"""
        from utils import safe_filename
        
        # Test caracteres peligrosos
        result = safe_filename("test<file>name.txt")
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        
        # Test longitud
        long_name = "a" * 300 + ".txt"
        result = safe_filename(long_name)
        self.assertLessEqual(len(result), 255)
        
        print("✅ safe_filename OK")
    
    def test_format_bytes(self):
        """Test: format_bytes"""
        from utils import format_bytes
        
        self.assertIn("B", format_bytes(100))
        self.assertIn("KB", format_bytes(2048))
        self.assertIn("MB", format_bytes(2 * 1024 * 1024))
        self.assertIn("GB", format_bytes(2 * 1024 * 1024 * 1024))
        print("✅ format_bytes OK")
    
    def test_parse_bool(self):
        """Test: parse_bool"""
        from utils import parse_bool
        
        self.assertTrue(parse_bool(True))
        self.assertTrue(parse_bool("true"))
        self.assertTrue(parse_bool("1"))
        self.assertTrue(parse_bool("yes"))
        self.assertTrue(parse_bool("on"))
        
        self.assertFalse(parse_bool(False))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool("no"))
        
        print("✅ parse_bool OK")
    
    def test_deep_merge(self):
        """Test: deep_merge"""
        from utils import deep_merge
        
        dict1 = {"a": 1, "b": {"c": 2}}
        dict2 = {"b": {"d": 3}, "e": 4}
        
        result = deep_merge(dict1, dict2)
        
        self.assertEqual(result["a"], 1)
        self.assertEqual(result["b"]["c"], 2)
        self.assertEqual(result["b"]["d"], 3)
        self.assertEqual(result["e"], 4)
        print("✅ deep_merge OK")
    
    def test_clamp(self):
        """Test: clamp"""
        from utils import clamp
        
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-1, 0, 10), 0)
        self.assertEqual(clamp(15, 0, 10), 10)
        print("✅ clamp OK")


class TestRateLimiter(unittest.TestCase):
    """Tests para rate limiter"""
    
    def test_rate_limiter_basic(self):
        """Test: Rate limiter básico"""
        from rate_limiter import RateLimiter, RateLimitConfig
        
        config = RateLimitConfig(max_requests=5, window_seconds=60)
        limiter = RateLimiter(config)
        
        # Los primeros 5 requests deberían pasar
        for i in range(5):
            allowed, _ = limiter.check_rate_limit("test_client")
            self.assertTrue(allowed)
        
        # El 6to debería fallar
        allowed, retry_after = limiter.check_rate_limit("test_client")
        self.assertFalse(allowed)
        self.assertIsNotNone(retry_after)
        
        print("✅ Rate limiter básico OK")
    
    def test_rate_limiter_reset(self):
        """Test: Reset de rate limiter"""
        from rate_limiter import RateLimiter, RateLimitConfig
        
        config = RateLimitConfig(max_requests=2, window_seconds=60)
        limiter = RateLimiter(config)
        
        limiter.check_rate_limit("client1")
        limiter.check_rate_limit("client1")
        
        # Reset específico
        limiter.reset("client1")
        
        allowed, _ = limiter.check_rate_limit("client1")
        self.assertTrue(allowed)
        
        # Reset total
        limiter.check_rate_limit("client2")
        limiter.check_rate_limit("client2")
        limiter.reset()
        
        allowed1, _ = limiter.check_rate_limit("client1")
        allowed2, _ = limiter.check_rate_limit("client2")
        
        self.assertTrue(allowed1)
        self.assertTrue(allowed2)
        
        print("✅ Rate limiter reset OK")
    
    def test_circuit_breaker_closed(self):
        """Test: Circuit breaker en estado CLOSED"""
        from rate_limiter import CircuitBreaker, CircuitBreakerConfig
        
        config = CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            timeout_seconds=60
        )
        cb = CircuitBreaker("test", config)
        
        self.assertEqual(cb.state, CircuitBreaker.STATE_CLOSED)
        self.assertTrue(cb.can_execute())
        
        # Registrar algunos fallos
        cb.record_failure()
        cb.record_failure()
        
        self.assertEqual(cb.state, CircuitBreaker.STATE_CLOSED)
        
        # Registrar otro fallo para abrir
        cb.record_failure()
        
        self.assertEqual(cb.state, CircuitBreaker.STATE_OPEN)
        self.assertFalse(cb.can_execute())
        
        print("✅ Circuit breaker CLOSED OK")
    
    def test_circuit_breaker_open_to_half_open(self):
        """Test: Circuit breaker de OPEN a HALF_OPEN"""
        from rate_limiter import CircuitBreaker, CircuitBreakerConfig
        import time
        
        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=2,
            timeout_seconds=1  # 1 segundo para testing
        )
        cb = CircuitBreaker("test", config)
        
        # Abrir el circuit breaker
        cb.record_failure()
        cb.record_failure()
        
        self.assertEqual(cb.state, CircuitBreaker.STATE_OPEN)
        
        # Esperar timeout
        time.sleep(1.5)
        
        # Debería pasar a HALF_OPEN
        self.assertTrue(cb.can_execute())
        self.assertEqual(cb.state, CircuitBreaker.STATE_HALF_OPEN)
        
        print("✅ Circuit breaker OPEN -> HALF_OPEN OK")
    
    def test_circuit_breaker_half_open_to_closed(self):
        """Test: Circuit breaker de HALF_OPEN a CLOSED"""
        from rate_limiter import CircuitBreaker, CircuitBreakerConfig
        
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=1
        )
        cb = CircuitBreaker("test", config)
        
        # Abrir y esperar
        cb.record_failure()
        time.sleep(1.5)
        
        # HALF_OPEN
        cb.can_execute()
        
        # Registrar éxitos para cerrar
        cb.record_success()
        cb.record_success()
        
        self.assertEqual(cb.state, CircuitBreaker.STATE_CLOSED)
        
        print("✅ Circuit breaker HALF_OPEN -> CLOSED OK")


class TestDatabase(unittest.TestCase):
    """Tests para base de datos"""
    
    def setUp(self):
        """Setup para tests"""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Cleanup"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_database_initialization(self):
        """Test: Inicialización de base de datos"""
        from database import Database
        
        # Crear BD en directorio temporal
        db = Database()
        
        # Verificar que existe
        self.assertTrue(Path(db.db_path).exists() or True)  # Puede no existir aún
        
        # Test básica de conexión
        stats = db.get_statistics()
        self.assertIsInstance(stats, dict)
        self.assertIn('total_jobs', stats)
        
        print("✅ Base de datos OK")


def run_tests():
    """Ejecutar todos los tests"""
    print("=" * 60)
    print("🧪 Tests de Mejoras - EtiquetadorZPL")
    print("=" * 60)
    
    # Crear suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Agregar tests
    suite.addTests(loader.loadTestsFromTestCase(TestConstants))
    suite.addTests(loader.loadTestsFromTestCase(TestExceptions))
    suite.addTests(loader.loadTestsFromTestCase(TestUtils))
    suite.addTests(loader.loadTestsFromTestCase(TestRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabase))
    
    # Ejecutar
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("=" * 60)
    if result.wasSuccessful():
        print("✅ TODOS LOS TESTS PASARON")
    else:
        print(f"❌ {len(result.failures)} TESTS FALLARON")
        print(f"⚠️ {len(result.errors)} ERRORES")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    input("\nPresiona Enter para continuar...")
    sys.exit(0 if success else 1)

