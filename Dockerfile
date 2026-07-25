FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (if any are needed in the future)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies using pyproject.toml
COPY pyproject.toml .
# Create a dummy src/hexmaster/__init__.py to satisfy pip install .
RUN mkdir -p src/hexmaster && touch src/hexmaster/__init__.py
RUN pip install --no-cache-dir .

# Copy the rest of the application
COPY . .

# Re-install the project to include actual source code
RUN pip install --no-cache-dir .

# Start the bot
CMD ["python", "-m", "hexmaster.bot.main"]
