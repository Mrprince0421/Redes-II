#!/usr/bin/env python3
"""
Cliente de Transferência de Arquivos - TCP e R-UDP
Autor: Marcos Eduardo Barbosa Pachêco
Matrícula: 20199017697
X-Custom-Auth: 748f5c7c1914895503dba4813493766019f387f108138a1d333a9b42d7dec340
"""

import socket
import struct
import hashlib
import os
import time
import json
import logging
import argparse
import csv
import zlib

# ── Constantes ──────────────────────────────────────────────────────────────
MATRICULA  = "20199017697"
NOME       = "Marcos Eduardo Barbosa Pachêco"
AUTH_HASH  = hashlib.sha256((MATRICULA + NOME).encode("utf-8")).hexdigest()

CHUNK_SIZE = 1400
TIMEOUT    = 2.0
MAX_RETRIES = 20

HEADER_FMT  = "!IIB4sH64s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("client")

# ── Utilitários ──────────────────────────────────────────────────────────────

def compute_checksum(data: bytes) -> bytes:
    return struct.pack("!I", zlib.crc32(data) & 0xFFFFFFFF)


def make_packet(seq: int, ack: int, flags: int, payload: bytes) -> bytes:
    auth = AUTH_HASH.encode("utf-8")[:64].ljust(64, b"\x00")
    chk  = compute_checksum(payload)
    hdr  = struct.pack(HEADER_FMT, seq, ack, flags, chk, len(payload), auth)
    return hdr + payload


def parse_packet(data: bytes):
    if len(data) < HEADER_SIZE:
        return None
    seq, ack, flags, chk, plen, auth = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
    payload = data[HEADER_SIZE: HEADER_SIZE + plen]
    expected = compute_checksum(payload)
    if chk != expected:
        return None
    return seq, ack, flags, payload, auth.decode("utf-8", errors="ignore").rstrip("\x00")


def save_result(csv_path: str, mode: str, scenario: str,
                filesize: int, elapsed: float, throughput: float,
                retransmissions: int = 0):
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "mode", "scenario", "filesize_bytes",
            "elapsed_s", "throughput_kbps", "retransmissions", "timestamp"
        ])
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            "mode":             mode,
            "scenario":         scenario,
            "filesize_bytes":   filesize,
            "elapsed_s":        round(elapsed, 6),
            "throughput_kbps":  round(throughput, 3),
            "retransmissions":  retransmissions,
            "timestamp":        time.strftime("%Y-%m-%dT%H:%M:%S")
        })


# ── Cliente TCP ──────────────────────────────────────────────────────────────

class TCPClient:
    def __init__(self, host="127.0.0.1", port=5001):
        self.host = host
        self.port = port

    def send_file(self, filepath: str, scenario: str = "A",
                  csv_log: str = "logs/results.csv") -> dict:
        fsize = os.path.getsize(filepath)
        fname = os.path.basename(filepath)
        log.info(f"[TCP] Enviando '{fname}' ({fsize} bytes) → {self.host}:{self.port}")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.host, self.port))

            # Cabeçalho JSON (256 bytes fixos)
            meta = json.dumps({
                "X-Custom-Auth": AUTH_HASH,
                "filename":      fname,
                "filesize":      fsize
            })
            meta_bytes = meta.encode().ljust(256, b"\x00")
            s.sendall(meta_bytes)

            ack = s.recv(2)
            if ack != b"OK":
                raise RuntimeError("Servidor não confirmou o cabeçalho")

            start = time.time()
            sent  = 0
            with open(filepath, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    s.sendall(chunk)
                    sent += len(chunk)

            done = s.recv(4)
            elapsed    = time.time() - start
            throughput = (sent / elapsed / 1024) if elapsed > 0 else 0

        log.info(f"[TCP] ✓ {sent} bytes em {elapsed:.3f}s  ({throughput:.1f} KB/s)")
        os.makedirs(os.path.dirname(csv_log) or ".", exist_ok=True)
        save_result(csv_log, "TCP", scenario, sent, elapsed, throughput)
        return {"mode": "TCP", "elapsed": elapsed, "throughput": throughput,
                "bytes": sent, "retransmissions": 0}


# ── Cliente R-UDP (Stop-and-Wait) ─────────────────────────────────────────────

class RUDPClient:
    def __init__(self, host="127.0.0.1", port=5002):
        self.host = host
        self.port = port

    def send_file(self, filepath: str, scenario: str = "A",
                  csv_log: str = "logs/results.csv") -> dict:
        fsize = os.path.getsize(filepath)
        fname = os.path.basename(filepath)
        log.info(f"[R-UDP] Enviando '{fname}' ({fsize} bytes) → {self.host}:{self.port}")

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(TIMEOUT)
        addr = (self.host, self.port)
        retransmissions = 0

        # ── Handshake SYN ────────────────────────────────────────────────────
        meta = json.dumps({
            "X-Custom-Auth": AUTH_HASH,
            "filename":      fname,
            "filesize":      fsize
        }).encode()
        syn = make_packet(0, 0, 0x01, meta)

        for attempt in range(MAX_RETRIES):
            sock.sendto(syn, addr)
            try:
                resp, _ = sock.recvfrom(HEADER_SIZE + 64)
                pkt = parse_packet(resp)
                if pkt and (pkt[2] & 0x05) == 0x05:   # SYN+ACK
                    break
            except socket.timeout:
                retransmissions += 1
                log.warning(f"[R-UDP] SYN timeout #{attempt+1}")
        else:
            sock.close()
            raise RuntimeError("Sem resposta ao SYN após múltiplos tentativas")

        # ── Envio de dados (Stop-and-Wait) ────────────────────────────────────
        seq   = 1
        sent  = 0
        start = time.time()

        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break

                pkt = make_packet(seq, 0, 0x08, chunk)  # DATA

                for attempt in range(MAX_RETRIES):
                    sock.sendto(pkt, addr)
                    try:
                        resp, _ = sock.recvfrom(HEADER_SIZE + 64)
                        ack_pkt = parse_packet(resp)
                        if ack_pkt and ack_pkt[1] == seq:
                            break
                    except socket.timeout:
                        retransmissions += 1
                        log.debug(f"[R-UDP] Timeout seq={seq}, retransmitindo ({attempt+1})")
                else:
                    sock.close()
                    raise RuntimeError(f"Sem ACK para seq={seq} após {MAX_RETRIES} tentativas")

                sent += len(chunk)
                seq  += 1

        # ── FIN ──────────────────────────────────────────────────────────────
        fin = make_packet(seq, 0, 0x02, b"")
        for _ in range(MAX_RETRIES):
            sock.sendto(fin, addr)
            try:
                resp, _ = sock.recvfrom(HEADER_SIZE + 64)
                pkt = parse_packet(resp)
                if pkt and (pkt[2] & 0x06):   # FIN+ACK
                    break
            except socket.timeout:
                retransmissions += 1

        elapsed    = time.time() - start
        throughput = (sent / elapsed / 1024) if elapsed > 0 else 0
        sock.close()

        log.info(f"[R-UDP] ✓ {sent} bytes em {elapsed:.3f}s  ({throughput:.1f} KB/s)"
                 f"  retransmissões={retransmissions}")
        os.makedirs(os.path.dirname(csv_log) or ".", exist_ok=True)
        save_result(csv_log, "RUDP", scenario, sent, elapsed, throughput, retransmissions)
        return {"mode": "RUDP", "elapsed": elapsed, "throughput": throughput,
                "bytes": sent, "retransmissions": retransmissions}


# ── Execução em lote (10-30 execuções) ───────────────────────────────────────

def run_batch(mode: str, host: str, port: int, filepath: str,
              scenario: str, runs: int, csv_log: str):
    results = []
    for i in range(1, runs + 1):
        log.info(f"[BATCH] Execução {i}/{runs}  modo={mode}  cenário={scenario}")
        try:
            if mode == "tcp":
                r = TCPClient(host, port).send_file(filepath, scenario, csv_log)
            else:
                r = RUDPClient(host, port).send_file(filepath, scenario, csv_log)
            results.append(r)
        except Exception as e:
            log.error(f"[BATCH] Falha na execução {i}: {e}")
        time.sleep(0.5)
    return results


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cliente TCP / R-UDP")
    parser.add_argument("mode",     choices=["tcp", "rudp"])
    parser.add_argument("filepath", help="Arquivo a enviar")
    parser.add_argument("--host",     default="127.0.0.1")
    parser.add_argument("--port",     type=int, default=0,
                        help="0 = padrão (TCP=5001, RUDP=5002)")
    parser.add_argument("--scenario", default="A",
                        choices=["A", "B", "C"],
                        help="A=0%perda/10ms  B=5%/50ms  C=10%/100ms")
    parser.add_argument("--runs",     type=int, default=1,
                        help="Número de execuções (1-30)")
    parser.add_argument("--csv-log",  default="logs/results.csv")
    args = parser.parse_args()

    if args.port == 0:
        args.port = 5001 if args.mode == "tcp" else 5002

    if args.runs == 1:
        if args.mode == "tcp":
            TCPClient(args.host, args.port).send_file(args.filepath, args.scenario, args.csv_log)
        else:
            RUDPClient(args.host, args.port).send_file(args.filepath, args.scenario, args.csv_log)
    else:
        run_batch(args.mode, args.host, args.port, args.filepath,
                  args.scenario, args.runs, args.csv_log)
