FROM python:3.12-slim
WORKDIR /app
RUN useradd --uid 10001 --create-home fleet && mkdir /data && chown fleet:fleet /data
COPY --chown=fleet:fleet fleet /app/fleet
USER fleet
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["python", "-m", "fleet", "serve", "--host", "0.0.0.0", "--data", "/data"]

