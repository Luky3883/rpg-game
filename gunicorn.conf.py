import multiprocessing

# Базовые настройки
bind = "0.0.0.0:80"
workers = 1  # Для SocketIO нужен 1 воркер
worker_class = "eventlet"  # Используем eventlet для WebSocket
timeout = 120
keepalive = 5

# Логирование
accesslog = "-"
errorlog = "-"
loglevel = "info"