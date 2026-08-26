FROM python:3.11-slim

# Устанавливаем MinGW для кросс-компиляции
RUN apt-get update && apt-get install -y \
    g++ \
    mingw-w64 \
    upx-ucl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Python зависимости
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY . .

# Создаём папку для сборки
RUN mkdir -p /tmp/build

# Открываем порт
EXPOSE 5000

# Запускаем приложение
CMD ["python", "app.py"]