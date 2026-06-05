#!/usr/bin/env bash
# run_tests.sh – Automatiza os testes TCP e R-UDP nos 3 cenários
# Autor: Marcos Eduardo Barbosa Pachêco | 20199017697

set -euo pipefail

SERVER_IP="172.28.0.10"
CLIENT_CONTAINER="redes2_client"
RUNS=20                        # execuções por combinação (modo + cenário)
TESTFILE="/app/testfile/test_1mb.bin"
CSV_LOG="/app/logs/results.csv"
PCAP_DIR="/app/logs"

# ── Criar arquivo de teste (~1 MB) se não existir ────────────────────────────
mkdir -p testfile
if [ ! -f testfile/test_1mb.bin ]; then
    dd if=/dev/urandom of=testfile/test_1mb.bin bs=1M count=1 2>/dev/null
    echo "[✓] Arquivo de teste criado: testfile/test_1mb.bin"
fi

mkdir -p logs received

# ── Função: aplicar tc qdisc no container cliente ────────────────────────────
apply_tc() {
    local container=$1
    local loss=$2      # e.g. "0%"
    local delay=$3     # e.g. "10ms"

    docker exec "$container" tc qdisc del dev eth0 root 2>/dev/null || true
    docker exec "$container" tc qdisc add dev eth0 root netem \
        loss "$loss" delay "$delay"
    echo "[tc] Container=$container  loss=$loss  delay=$delay"
}

# ── Função: iniciar captura tcpdump ──────────────────────────────────────────
start_capture() {
    local container=$1
    local pcap_file=$2
    docker exec -d "$container" \
        tcpdump -i eth0 -w "$pcap_file" \
        "port 5001 or port 5002" 2>/dev/null
    echo "[tcpdump] Captura iniciada: $pcap_file"
}

stop_capture() {
    local container=$1
    docker exec "$container" pkill tcpdump 2>/dev/null || true
    sleep 1
}

# ── Subir os containers ───────────────────────────────────────────────────────
echo "=== Subindo containers ==="
cd docker
docker compose up -d server client
cd ..
sleep 3

# ── Esperar servidor ficar pronto ─────────────────────────────────────────────
echo "=== Aguardando servidor ==="
for i in $(seq 1 15); do
    if docker exec "$CLIENT_CONTAINER" \
           python3 -c "import socket; s=socket.create_connection(('$SERVER_IP',5001),2); s.close()" \
           2>/dev/null; then
        echo "[✓] Servidor TCP pronto"
        break
    fi
    echo "  Tentativa $i/15…"
    sleep 2
done

# ════════════════════════════════════════════════════════════════════════════
# CENÁRIOS
# ════════════════════════════════════════════════════════════════════════════

declare -A SCENARIOS=(
    [A]="loss=0% delay=10ms"
    [B]="loss=5% delay=50ms"
    [C]="loss=10% delay=100ms"
)

for SC in A B C; do
    read -r _ LOSS_PART DELAY_PART <<< "$(echo "${SCENARIOS[$SC]}" | tr '=' ' ' | tr ' ' '\n' | paste - - - -)"
    LOSS="${SCENARIOS[$SC]}"
    # Extrair valores
    LOSS_VAL=$(echo "${SCENARIOS[$SC]}" | grep -oP 'loss=\K[^ ]+')
    DELAY_VAL=$(echo "${SCENARIOS[$SC]}" | grep -oP 'delay=\K[^ ]+')

    echo ""
    echo "══════════════════════════════════════════"
    echo " CENÁRIO $SC  |  perda=$LOSS_VAL  delay=$DELAY_VAL"
    echo "══════════════════════════════════════════"

    apply_tc "$CLIENT_CONTAINER" "$LOSS_VAL" "$DELAY_VAL"

    # Iniciar captura
    PCAP="${PCAP_DIR}/capture_${SC}.pcap"
    start_capture "$CLIENT_CONTAINER" "$PCAP"
    sleep 1

    # ── TCP ──────────────────────────────────────────────────────────────────
    echo "--- TCP ($RUNS execuções) ---"
    docker exec "$CLIENT_CONTAINER" python3 client.py tcp "$TESTFILE" \
        --host "$SERVER_IP" --scenario "$SC" \
        --runs "$RUNS" --csv-log "$CSV_LOG"

    sleep 2

    # ── R-UDP ────────────────────────────────────────────────────────────────
    echo "--- R-UDP ($RUNS execuções) ---"
    docker exec "$CLIENT_CONTAINER" python3 client.py rudp "$TESTFILE" \
        --host "$SERVER_IP" --scenario "$SC" \
        --runs "$RUNS" --csv-log "$CSV_LOG"

    stop_capture "$CLIENT_CONTAINER"
    echo "[✓] Cenário $SC concluído  →  $PCAP"
done

# ── Remover tc ────────────────────────────────────────────────────────────────
docker exec "$CLIENT_CONTAINER" tc qdisc del dev eth0 root 2>/dev/null || true

# ── Análise estatística ───────────────────────────────────────────────────────
echo ""
echo "=== Gerando análise estatística ==="
cd docker
docker compose --profile analyze up --no-start 2>/dev/null || true
cd ..
docker exec "$CLIENT_CONTAINER" python3 analyze.py "$CSV_LOG"

echo ""
echo "══════════════════════════════════════════"
echo " TESTES CONCLUÍDOS"
echo " Logs CSV   : logs/results.csv"
echo " Capturas   : logs/capture_A.pcap  B  C"
echo " Gráficos   : analysis/"
echo "══════════════════════════════════════════"
