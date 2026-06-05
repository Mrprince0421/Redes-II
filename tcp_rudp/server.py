#!/usr/bin/env python3
"""
Servidor de Transferência de Arquivos - TCP e R-UDP
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
import threading

# ── Constantes ──────────────────────────────────────────────────────────────
MATRICULA   = "20199017697"
NOME        = "Marcos Eduardo Barbosa Pachêco"
AUTH_HASH   = hashlib.sha256((MATRICULA + NOME).encode("utf-8")).hexdigest()

CHUNK_SIZE  = 1400          # bytes de payload por pacote R-UDP
TIMEOUT     = 2.0           # segundos para retransmissão
MAX_RETRIES = 20

# Formato do cabeçalho R-UDP: seq(4) | ack(4) | flags(1) | checksum(4) | len(2) | auth(64s)
# flags: 0x01=SYN, 0x02=FIN, 0x04=ACK, 0x08=DATA
HEADER_FMT  = "!IIB4sH64s"
HEADER_SIZE = struct.calcsize(HEADER_FMT)   # 79 bytes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("server")

# ── Utilitários ──────────────────────────────────────────────────────────────

def compute_checksum(data: bytes) -> bytes:
    import zlib
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
    import zlib
    expected = struct.pack("!I", zlib.crc32(payload) & 0xFFFFFFFF)
    if chk != expected:
        return None
    return seq, ack, flags, payload, auth.decode("utf-8", errors="ignore").rstrip("\x00")


# ── Servidor TCP ─────────────────────────────────────────────────────────────

class TCPServer:
    def __init__(self, host="0.0.0.0", port=5001, save_dir="received"):
        self.host     = host
        self.port     = port
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)

    def handle_client(self, conn, addr):
        log.info(f"[TCP] Conexão de {addr}")
        try:
            # Recebe cabeçalho JSON de tamanho fixo (256 bytes)
            raw_hdr = b""
            while len(raw_hdr) < 256:
                raw_hdr += conn.recv(256 - len(raw_hdr))
            meta = json.loads(raw_hdr.decode().strip("\x00"))

            auth  = meta.get("X-Custom-Auth", "")
            fname = os.path.basename(meta["filename"])
            fsize = meta["filesize"]
            log.info(f"[TCP] Arquivo: {fname}  Tamanho: {fsize}  Auth: {auth[:16]}…")

            # ACK do cabeçalho
            conn.sendall(b"OK")

            start = time.time()
            received = 0
            path = os.path.join(self.save_dir, fname)
            with open(path, "wb") as f:
                while received < fsize:
                    chunk = conn.recv(min(65536, fsize - received))
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
            elapsed   = time.time() - start
            throughput = (received / elapsed / 1024) if elapsed > 0 else 0

            conn.sendall(b"DONE")
            log.info(f"[TCP] Recebido {received} bytes em {elapsed:.3f}s  ({throughput:.1f} KB/s)")
        except Exception as e:
            log.error(f"[TCP] Erro: {e}")
        finally:
            conn.close()

    def run(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.host, self.port))
            s.listen(5)
            log.info(f"[TCP] Escutando em {self.host}:{self.port}")
            while True:
                conn, addr = s.accept()
                threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()


# ── Servidor R-UDP (Stop-and-Wait) ────────────────────────────────────────────

class RUDPServer:
    def __init__(self, host="0.0.0.0", port=5002, save_dir="received"):
        self.host     = host
        self.port     = port
        self.save_dir = save_dir
        os.makedirs(save_dir, exist_ok=True)

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self.host, self.port))
        sock.settimeout(30)
        log.info(f"[R-UDP] Escutando em {self.host}:{self.port}")

        while True:
            try:
                self._handle_session(sock)
            except socket.timeout:
                continue
            except Exception as e:
                log.error(f"[R-UDP] Erro na sessão: {e}")

    def _handle_session(self, sock):
        # Espera SYN
        data, addr = sock.recvfrom(65535)
        pkt = parse_packet(data)
        if pkt is None:
            return
        seq, ack, flags, payload, auth = pkt
        if flags != 0x01:   # SYN
            return

        meta  = json.loads(payload.decode())
        fname = os.path.basename(meta["filename"])
        fsize = meta["filesize"]
        log.info(f"[R-UDP] SYN de {addr}  Arquivo: {fname}  Auth: {auth[:16]}…")

        # SYN-ACK
        syn_ack = make_packet(0, seq + 1, 0x01 | 0x04, b"")
        sock.sendto(syn_ack, addr)

        # Recebe dados
        expected_seq = 1
        received     = 0
        start        = time.time()
        path         = os.path.join(self.save_dir, fname)

        with open(path, "wb") as f:
            while received < fsize:
                sock.settimeout(TIMEOUT * 5)
                try:
                    data, raddr = sock.recvfrom(HEADER_SIZE + CHUNK_SIZE + 64)
                except socket.timeout:
                    log.warning("[R-UDP] Timeout aguardando pacote de dados")
                    return

                pkt = parse_packet(data)
                if pkt is None:
                    log.warning("[R-UDP] Checksum inválido, ignorando")
                    continue

                seq, ack, flags, payload, _ = pkt

                if flags & 0x02:   # FIN
                    ack_pkt = make_packet(0, seq + 1, 0x04 | 0x02, b"")
                    sock.sendto(ack_pkt, raddr)
                    break

                if seq == expected_seq:
                    f.write(payload)
                    received     += len(payload)
                    expected_seq += 1
                    ack_pkt = make_packet(0, seq, 0x04, b"")
                    sock.sendto(ack_pkt, raddr)
                else:
                    # Reenviar ACK do último recebido
                    ack_pkt = make_packet(0, expected_seq - 1, 0x04, b"")
                    sock.sendto(ack_pkt, raddr)

        elapsed    = time.time() - start
        throughput = (received / elapsed / 1024) if elapsed > 0 else 0
        log.info(f"[R-UDP] Recebido {received} bytes em {elapsed:.3f}s  ({throughput:.1f} KB/s)")


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor TCP / R-UDP")
    parser.add_argument("mode", choices=["tcp", "rudp", "both"], default="both", nargs="?")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--tcp-port",  type=int, default=5001)
    parser.add_argument("--rudp-port", type=int, default=5002)
    parser.add_argument("--save-dir",  default="received")
    args = parser.parse_args()

    threads = []
    if args.mode in ("tcp", "both"):
        t = threading.Thread(target=TCPServer(args.host, args.tcp_port, args.save_dir).run, daemon=True)
        t.start()
        threads.append(t)
    if args.mode in ("rudp", "both"):
        t = threading.Thread(target=RUDPServer(args.host, args.rudp_port, args.save_dir).run, daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
