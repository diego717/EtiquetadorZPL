"""
Rate Limiter y Circuit Breaker para EtiquetadorZPL
"""

import time
import threading
import logging
from typing import Dict, Optional, Callable, Any
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuración de rate limiting"""
    max_requests: int = 100  # Máximo requests en ventana
    window_seconds: int = 60  # Ventana de tiempo en segundos
    block_duration_seconds: int = 300  # Duración de bloqueo tras exceder


@dataclass 
class CircuitBreakerConfig:
    """Configuración de circuit breaker"""
    failure_threshold: int = 5  # Fallos antes de abrir
    success_threshold: int = 2  # Éxitos para cerrar
    timeout_seconds: int = 60  # Tiempo antes de intentar de nuevo


class TokenBucket:
    """Implementación de Token Bucket para rate limiting"""
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # Tokens por segundo
        self.last_refill = time.time()
        self.lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """Intentar consumir tokens"""
        with self.lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def _refill(self):
        """Rellenar tokens según tiempo transcurrido"""
        now = time.time()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.refill_rate
        
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now
    
    def get_available_tokens(self) -> float:
        """Obtener tokens disponibles"""
        with self.lock:
            self._refill()
            return self.tokens


class RateLimiter:
    """Rate limiter por IP/identificador"""
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self.buckets: Dict[str, TokenBucket] = {}
        self.blocked: Dict[str, datetime] = {}
        self.request_counts: Dict[str, list] = defaultdict(list)
        self.lock = threading.Lock()
    
    def _get_client_key(self, identifier: str) -> str:
        """Obtener clave única para el cliente"""
        return identifier
    
    def _is_blocked(self, client_key: str) -> bool:
        """Verificar si cliente está bloqueado"""
        if client_key in self.blocked:
            blocked_until = self.blocked[client_key]
            if datetime.now() < blocked_until:
                return True
            else:
                # Desbloquear
                del self.blocked[client_key]
                if client_key in self.request_counts:
                    self.request_counts[client_key] = []
        return False
    
    def _cleanup_old_requests(self, client_key: str):
        """Limpiar requests antiguos"""
        cutoff = time.time() - self.config.window_seconds
        self.request_counts[client_key] = [
            t for t in self.request_counts[client_key] if t > cutoff
        ]
    
    def check_rate_limit(self, identifier: str) -> tuple[bool, Optional[int]]:
        """
        Verificar si request está dentro del límite
        
        Returns:
            (allowed, retry_after_seconds)
        """
        client_key = self._get_client_key(identifier)
        
        with self.lock:
            # Verificar si está bloqueado
            if self._is_blocked(client_key):
                blocked_until = self.blocked[client_key]
                retry_after = int((blocked_until - datetime.now()).total_seconds())
                return False, retry_after
            
            # Limpiar requests antiguos
            self._cleanup_old_requests(client_key)
            
            # Verificar límite
            request_count = len(self.request_counts[client_key])
            
            if request_count >= self.config.max_requests:
                # Bloquear temporalmente
                self.blocked[client_key] = datetime.now() + timedelta(
                    seconds=self.config.block_duration_seconds
                )
                logger.warning(f"Rate limit excedido para {identifier}, bloqueado por {self.config.block_duration_seconds}s")
                return False, self.config.block_duration_seconds
            
            # Registrar request
            self.request_counts[client_key].append(time.time())
            
            # Crear bucket si no existe
            if client_key not in self.buckets:
                self.buckets[client_key] = TokenBucket(
                    capacity=self.config.max_requests,
                    refill_rate=self.config.max_requests / self.config.window_seconds
                )
            
            return True, None
    
    def allow_request(self, identifier: str) -> bool:
        """Verificar si request está permitido"""
        allowed, _ = self.check_rate_limit(identifier)
        return allowed
    
    def reset(self, identifier: Optional[str] = None):
        """Resetear límites"""
        with self.lock:
            if identifier:
                client_key = self._get_client_key(identifier)
                self.buckets.pop(client_key, None)
                self.blocked.pop(client_key, None)
                self.request_counts.pop(client_key, None)
            else:
                self.buckets.clear()
                self.blocked.clear()
                self.request_counts.clear()


class CircuitBreaker:
    """
    Circuit Breaker pattern implementation
    
    Estados:
    - CLOSED: Normal, permite requests
    - OPEN: Demasiados fallos, rechaza requests
    - HALF_OPEN: Probando si el servicio recoveró
    """
    
    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        self.state = self.STATE_CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.lock = threading.Lock()
    
    def _should_attempt_reset(self) -> bool:
        """Verificar si debe intentar resetear"""
        if self.last_failure_time is None:
            return False
        
        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.config.timeout_seconds
    
    def can_execute(self) -> bool:
        """Verificar si se puede ejecutar"""
        with self.lock:
            if self.state == self.STATE_CLOSED:
                return True
            
            if self.state == self.STATE_OPEN:
                if self._should_attempt_reset():
                    self.state = self.STATE_HALF_OPEN
                    self.success_count = 0
                    logger.info(f"Circuit breaker {self.name} transitioned to HALF_OPEN")
                    return True
                return False
            
            # HALF_OPEN permite un intento
            return True
    
    def record_success(self):
        """Registrar éxito"""
        with self.lock:
            if self.state == self.STATE_HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = self.STATE_CLOSED
                    self.failure_count = 0
                    logger.info(f"Circuit breaker {self.name} transitioned to CLOSED")
            elif self.state == self.STATE_CLOSED:
                self.failure_count = 0
    
    def record_failure(self):
        """Registrar fallo"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == self.STATE_HALF_OPEN:
                self.state = self.STATE_OPEN
                logger.warning(f"Circuit breaker {self.name} reopened after failure in HALF_OPEN")
            elif self.state == self.STATE_CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    self.state = self.STATE_OPEN
                    logger.warning(f"Circuit breaker {self.name} opened after {self.failure_count} failures")
    
    def execute(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """Ejecutar función con circuit breaker"""
        if not self.can_execute():
            raise CircuitBreakerOpenError(
                f"Circuit breaker {self.name} is OPEN"
            )
        
        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise
    
    def get_state(self) -> str:
        """Obtener estado actual"""
        with self.lock:
            return self.state
    
    def reset(self):
        """Resetear circuit breaker"""
        with self.lock:
            self.state = self.STATE_CLOSED
            self.failure_count = 0
            self.success_count = 0
            self.last_failure_time = None


class CircuitBreakerOpenError(Exception):
    """Error cuando circuit breaker está abierto"""
    pass


class CircuitBreakerManager:
    """Gestor de múltiples circuit breakers"""
    
    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.lock = threading.Lock()
    
    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Obtener o crear circuit breaker"""
        with self.lock:
            if name not in self.breakers:
                self.breakers[name] = CircuitBreaker(name, config)
            return self.breakers[name]
    
    def remove_breaker(self, name: str):
        """Remover circuit breaker"""
        with self.lock:
            self.breakers.pop(name, None)
    
    def get_all_states(self) -> Dict[str, str]:
        """Obtener estados de todos los breakers"""
        with self.lock:
            return {name: breaker.get_state() for name, breaker in self.breakers.items()}


# Instancias globales
rate_limiter = RateLimiter()
circuit_breaker_manager = CircuitBreakerManager()


def get_rate_limiter() -> RateLimiter:
    """Obtener instancia de rate limiter"""
    return rate_limiter


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Obtener circuit breaker por nombre"""
    return circuit_breaker_manager.get_breaker(name, config)

