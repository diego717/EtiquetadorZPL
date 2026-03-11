"""
Constantes centralizadas para EtiquetadorZPL
"""

# ============================================
# CONFIGURACIÓN DE APLICACIÓN
# ============================================

APP_NAME = "EtiquetadorZPL"
APP_VERSION = "1.0.0"

# ============================================
# EXTENSIONES DE ARCHIVOS
# ============================================

ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.zpl', '.zip', '.png', '.jpg', '.jpeg'}
ALLOWED_ZPL_EXTENSIONS = {'.txt', '.zpl'}
ALLOWED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg'}

# ============================================
# LÍMITES DE TAMAÑO
# ============================================

MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200MB
MAX_ZIP_SIZE_BYTES = 500 * 1024 * 1024   # 500MB
MAX_TXT_SIZE_BYTES = 500 * 1024          # 500KB
MAX_ZPL_SIZE_BYTES = 1024 * 1024         # 1MB
MAX_ZPL_LINES = 1000
MAX_CONCURRENT_FILES = 10

# ============================================
# CONFIGURACIÓN DE IMPRESIÓN
# ============================================

DEFAULT_COPIES = 1
MAX_COPIES = 10
MIN_COPIES = 1

# ============================================
# CONFIGURACIÓN DE MONITOREO
# ============================================

FILE_CHECK_INTERVAL = 1.0  # segundos
MAX_FILE_WAIT_ATTEMPTS = 20
QUEUE_MAXSIZE = 100

# ============================================
# CONFIGURACIÓN DE API
# ============================================

API_TIMEOUT = 30  # segundos
API_PORT_DEFAULT = 8002
API_CACHE_TIME = 30  # segundos for printer cache

# ============================================
# ESTADOS DE TRABAJO
# ============================================

JOB_STATUS = {
    'PENDING': 'pending',
    'PROCESSING': 'processing',
    'COMPLETED': 'completed',
    'FAILED': 'failed',
    'CANCELLED': 'cancelled'
}

# ============================================
# MENSAJES DE ERROR
# ============================================

ERROR_MESSAGES = {
    'FILE_NOT_FOUND': 'Archivo no encontrado',
    'FILE_TOO_LARGE': 'Archivo demasiado grande',
    'INVALID_EXTENSION': 'Extensión de archivo no permitida',
    'INVALID_PRINTER': 'Impresora no válida o no disponible',
    'PRINTER_NOT_CONFIGURED': 'Impresora no configurada',
    'PERMISSION_DENIED': 'Permiso denegado',
    'DATABASE_ERROR': 'Error de base de datos',
    'NETWORK_ERROR': 'Error de red',
    'TIMEOUT': 'Tiempo de espera agotado',
    'INVALID_ZPL': 'Contenido ZPL inválido',
    'ZPL_SANITIZE_FAILED': 'No se pudo sanitizar el contenido ZPL',
    'HISTORY_ERROR': 'Error al mover archivo al historial',
    'API_ERROR': 'Error de API',
    'UNKNOWN_ERROR': 'Error desconocido'
}

# ============================================
# MENSAJES DE ÉXITO
# ============================================

SUCCESS_MESSAGES = {
    'PRINT_SUCCESS': 'Impresión completada exitosamente',
    'FILE_PROCESSED': 'Archivo procesado correctamente',
    'CONFIG_SAVED': 'Configuración guardada correctamente',
    'BACKUP_CREATED': 'Backup creado exitosamente',
    'JOB_COMPLETED': 'Trabajo completado'
}

# ============================================
# CONFIGURACIÓN DE LOGGING
# ============================================

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB
LOG_BACKUP_COUNT = 5

ERROR_LOG_MAX_BYTES = 2 * 1024 * 1024  # 2MB
ERROR_LOG_BACKUP_COUNT = 3

# ============================================
# CONFIGURACIÓN DE RECURSOS
# ============================================

MAX_MEMORY_PERCENT = 95
MAX_CPU_PERCENT = 98
MAX_DISK_PERCENT = 90

# ============================================
# NOMBRES DE ARCHIVO PELIGROSOS (Windows)
# ============================================

DANGEROUS_FILENAMES = {
    'con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4', 'com5',
    'com6', 'com7', 'com8', 'com9', 'lpt1', 'lpt2', 'lpt3', 'lpt4',
    'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
}

# ============================================
# CARACTERES PELIGROSOS EN NOMBRES
# ============================================

DANGEROUS_FILENAME_CHARS = ['<', '>', ':', '"', '|', '?', '*', '\0']

# ============================================
# COMANDOS ZPL PROHIBIDOS
# ============================================

FORBIDDEN_ZPL_COMMANDS = {
    '^ID',  # Borrar memoria
    '^JU',  # Configuración de red
    '^NC',  # Cambiar configuración
    '^WD',  # Descargar objetos
    '^XF',  # Recall format
    '^DF',  # Download format
}

# ============================================
# CONFIGURACIÓN DE RETRY
# ============================================

MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_FACTOR = 2
RETRY_INITIAL_DELAY = 1  # segundos

# ============================================
# CONFIGURACIÓN DE MONITOREO DEL SISTEMA
# ============================================

METRICS_COLLECTION_INTERVAL = 60  # segundos
MAX_METRICS_STORED = 100
MAX_ALERTS_STORED = 50

# ============================================
# CONFIGURACIÓN DE RESPALDO
# ============================================

DEFAULT_KEEP_DAILY = 7
DEFAULT_KEEP_WEEKLY = 4
BACKUP_FILENAME_FORMAT = "%Y%m%d_%H%M%S"

# ============================================
# RUTAS POR DEFECTO
# ============================================

DEFAULT_INPUT_PATH = "C:/EtiquetasFlex"
DEFAULT_OUTPUT_PATH = "C:/EtiquetasFlex/Salida"
DEFAULT_HISTORY_PATH = "C:/EtiquetasFlex/Historial"
DEFAULT_PRINTER = "Godex GE300"

# ============================================
# ETIQUETAS POR DEFECTO
# ============================================

DEFAULT_LABEL_WIDTH_MM = 100
DEFAULT_LABEL_HEIGHT_MM = 150

# ============================================
# CONFIGURACIÓN DE NOTIFICACIONES
# ============================================

NOTIFICATION_DEFAULTS = {
    "desktop_enabled": True,
    "email_enabled": False,
    "notify_on_error": True,
    "notify_on_success": False,
    "notify_on_warning": True
}

