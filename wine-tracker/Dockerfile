ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python + pip deps
RUN apk add --no-cache python3 py3-pip py3-pillow ca-certificates \
    && update-ca-certificates
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# Copy app
WORKDIR /app
COPY app/ /app/

EXPOSE 5050
ENV DATA_DIR=/share/wine-tracker-di
CMD ["python3", "app.py"]
