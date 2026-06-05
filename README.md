# Redes de Computadores II – Avaliação 2026-1
**Aluno:** Marcos Eduardo Barbosa Pachêco  
**Matrícula:** 20199017697  
**X-Custom-Auth:** `748f5c7c1914895503dba4813493766019f387f108138a1d333a9b42d7dec340`

---

## Estrutura do Projeto

```
redes2/
├── tcp_rudp/
│   ├── server.py        # Servidor TCP + R-UDP
│   └── client.py        # Cliente TCP + R-UDP (com batch de execuções)
├── analysis/
│   └── analyze.py       # Análise estatística (Pandas + Matplotlib)
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── run_tests.sh         # Script de automação completo
└── README.md
```

---

## Pré-requisitos

- Docker + Docker Compose v2
- Python 3.10+ (para execução local)
- `pip install pandas matplotlib numpy`

---

## Como Executar

### 1. Subir o ambiente Docker

```bash
cd docker
docker compose up -d server client
```

### 2. Rodar todos os testes automaticamente

```bash
chmod +x run_tests.sh
./run_tests.sh
```

O script:
1. Cria arquivo de teste de 1 MB
2. Para cada cenário (A, B, C) aplica `tc qdisc netem`
3. Inicia captura `tcpdump` (.pcap)
4. Roda 20 execuções TCP + 20 execuções R-UDP
5. Gera análise estatística e gráficos

### 3. Execução manual individual

```bash
# Servidor
docker exec redes2_server python3 server.py both

# Cliente TCP – Cenário B – 20 execuções
docker exec redes2_client python3 client.py tcp /app/testfile/test_1mb.bin \
    --host 172.28.0.10 --scenario B --runs 20

# Cliente R-UDP – Cenário C – 20 execuções
docker exec redes2_client python3 client.py rudp /app/testfile/test_1mb.bin \
    --host 172.28.0.10 --scenario C --runs 20
```

### 4. Aplicar condições de rede manualmente

```bash
# Cenário A: 0% perda, 10ms
docker exec redes2_client tc qdisc add dev eth0 root netem loss 0% delay 10ms

# Cenário B: 5% perda, 50ms
docker exec redes2_client tc qdisc replace dev eth0 root netem loss 5% delay 50ms

# Cenário C: 10% perda, 100ms
docker exec redes2_client tc qdisc replace dev eth0 root netem loss 10% delay 100ms

# Remover
docker exec redes2_client tc qdisc del dev eth0 root
```

### 5. Captura com tcpdump

```bash
# Iniciar captura
docker exec -d redes2_client tcpdump -i eth0 -w /app/logs/capture_A.pcap \
    "port 5001 or port 5002"

# Parar
docker exec redes2_client pkill tcpdump

# Exportar para análise com Wireshark:
# Abrir o arquivo .pcap no Wireshark e filtrar:
#   udp.port == 5002  (R-UDP)
#   tcp.port == 5001  (TCP)
```

### 6. Gerar gráficos a partir do CSV

```bash
python3 analysis/analyze.py logs/results.csv
# Gráficos salvos em: analysis/
```

---

## Protocolo R-UDP – Cabeçalho

| Campo       | Tamanho | Descrição                              |
|-------------|---------|----------------------------------------|
| seq         | 4 bytes | Número de sequência                    |
| ack         | 4 bytes | Número de confirmação                  |
| flags       | 1 byte  | SYN=0x01, FIN=0x02, ACK=0x04, DATA=0x08|
| checksum    | 4 bytes | CRC-32 do payload                      |
| len         | 2 bytes | Tamanho do payload                     |
| X-Custom-Auth| 64 bytes| SHA-256(matrícula+nome) em ASCII      |
| **Total**   | **79 bytes** |                                  |

---

## Cenários de Teste

| Cenário | Perda | Delay  | tc qdisc                          |
|---------|-------|--------|-----------------------------------|
| A       | 0%    | 10 ms  | `netem loss 0% delay 10ms`        |
| B       | 5%    | 50 ms  | `netem loss 5% delay 50ms`        |
| C       | 10%   | 100 ms | `netem loss 10% delay 100ms`      |

---

## Critérios de Avaliação Atendidos

- [x] Ambiente Docker + tc qdisc (1.0 pt)
- [x] Protocolo R-UDP com Stop-and-Wait, timeout, retransmissão, checksum CRC-32 (2.5 pt)
- [x] X-Custom-Auth SHA-256 em todos os pacotes – visível no Wireshark (1.5 pt)
- [x] Análise estatística: min, média, máx, desvio padrão, gráficos (2.0 pt)
- [x] Integração de dados Python ↔ Wireshark/tcpdump (1.0 pt)
- [x] Relatório SBC (1.0 pt)
- [x] Vídeo demonstrativo (1.0 pt)
