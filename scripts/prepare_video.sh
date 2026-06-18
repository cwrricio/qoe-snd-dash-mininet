#!/bin/bash

set -e

INPUT="media/input.mp4"
OUTPUT_DIR="media/dash"

if [ ! -f "$INPUT" ]; then
    echo "[ERRO] Arquivo $INPUT não encontrado."
    echo "Coloque um vídeo em media/input.mp4 antes de executar este script."
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "[INFO] Removendo arquivos DASH antigos..."
rm -f "$OUTPUT_DIR"/*

echo "[INFO] Gerando MPEG-DASH..."
# -seg_duration 2 + use_timeline/use_template geram vários segmentos curtos
# (~2s), o que permite ao cliente adaptar a qualidade (ABR) ao longo da
# reprodução — essencial para a caracterização de QoE na Etapa 2.
ffmpeg -y -i "$INPUT" \
    -map 0:v -b:v:0 300k -s:v:0 426x240 \
    -map 0:v -b:v:1 800k -s:v:1 640x360 \
    -map 0:v -b:v:2 1500k -s:v:2 1280x720 \
    -map 0:a -b:a 128k \
    -seg_duration 2 -use_timeline 1 -use_template 1 \
    -f dash "$OUTPUT_DIR/output.mpd"

echo "[OK] Arquivo DASH gerado em $OUTPUT_DIR/output.mpd"