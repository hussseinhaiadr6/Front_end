# 1. Specify the base image (Python 3.11.7 slim version)
FROM python:3.11.7-slim

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy the requirements file first (for better layer caching)
COPY requirements.txt .

# 4. Install Python dependencies from requirements.txt
#    --no-cache-dir helps keep the image size smaller
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your application files into the working directory
#    (Make sure app.py and the 'templates' folder are in the same directory as the Dockerfile)
COPY . .

EXPOSE 8000

# 7. Specify the command to run the application using Waitress
#    app:app: Tells Waitress to run the 'app' instance from the 'app.py' file
CMD ["sh", "-c", "waitress-serve --host=0.0.0.0 --port=$PORT app:app"]

# --- Alternative CMD for Flask development server (NOT recommended for production) ---
# CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
