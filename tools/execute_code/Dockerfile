# Gunakan Python versi slim agar ringan
FROM python:3.9-slim

# Set folder kerja di dalam container
WORKDIR /app

# Copy requirements dulu (agar caching docker efisien)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server script kita
COPY sandbox_server.py .

# Buka port 5000
EXPOSE 5000

# Jalankan server saat container nyala
CMD ["python", "sandbox_server.py"]