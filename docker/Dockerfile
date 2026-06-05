FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    iproute2 \
    tcpdump \
    iputils-ping \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir pandas matplotlib numpy

WORKDIR /app

COPY tcp_rudp/server.py .
COPY tcp_rudp/client.py .
COPY analysis/analyze.py .

RUN mkdir -p received logs analysis

EXPOSE 5001/tcp 5002/udp

CMD ["python3", "server.py", "both"]
