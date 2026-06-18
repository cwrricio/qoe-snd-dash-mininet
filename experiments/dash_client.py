#!/usr/bin/env python3
"""Cliente DASH headless para medir QoE (Etapa 2).

Este cliente baixa o manifesto MPEG-DASH (gerado pelo FFmpeg na Etapa 1),
escolhe a qualidade de cada segmento com um algoritmo ABR baseado em
throughput e simula um buffer de reprodução. A partir disso, extrai as
métricas de QoE pedidas no enunciado:

  - tempo de início (startup delay): tempo até encher o buffer inicial;
  - buffering: número de eventos de rebuffering e tempo total parado;
  - bitrate: bitrate médio reproduzido e número de trocas de qualidade.

Usa apenas a biblioteca padrão do Python, para poder rodar dentro de
qualquer host do Mininet sem instalar dependências.
"""

import argparse
import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

# O MPD do ffmpeg usa o namespace padrão do DASH.
DASH_NS = "urn:mpeg:dash:schema:mpd:2011"


def _tag(elem):
    """Nome da tag sem o prefixo de namespace."""
    return elem.tag.split("}", 1)[-1]


def _findall(parent, name):
    return [c for c in parent.iter() if _tag(c) == name]


def _children(parent, name):
    return [c for c in list(parent) if _tag(c) == name]


def http_get(url, timeout):
    """Baixa uma URL e devolve (bytes, segundos_de_download)."""
    t0 = time.monotonic()
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = resp.read()
    return data, time.monotonic() - t0


def fill_template(template, rep_id, number=None):
    """Resolve um SegmentTemplate do ffmpeg ($RepresentationID$, $Number%0Nd$)."""
    out = template.replace("$RepresentationID$", str(rep_id))
    if number is not None:
        # Suporta $Number$ e $Number%05d$ (formato usado pelo ffmpeg).
        if "$Number%" in out:
            start = out.index("$Number%")
            end = out.index("$", start + 1)
            fmt = out[start + len("$Number"):end]  # ex.: "%05d"
            out = out[:start] + (fmt % number) + out[end + 1:]
        else:
            out = out.replace("$Number$", str(number))
    return out


def _parse_representation(root, mpd_url, rep, set_template):
    """Extrai uma Representation (URLs de init/segmentos, duração) do MPD."""
    template = (_children(rep, "SegmentTemplate") or [set_template])[0]
    if template is None:
        raise RuntimeError("Representation sem SegmentTemplate (formato não suportado).")

    rep_id = rep.get("id")
    bandwidth = int(rep.get("bandwidth", "0"))
    timescale = int(template.get("timescale", "1"))
    start_number = int(template.get("startNumber", "1"))

    # Conta segmentos e duração via SegmentTimeline (formato do ffmpeg).
    timeline = (_children(template, "SegmentTimeline") or [None])[0]
    seg_count = 0
    total_ticks = 0
    if timeline is not None:
        for s in _children(timeline, "S"):
            rep_count = int(s.get("r", "0")) + 1
            dur = int(s.get("d", "0"))
            seg_count += rep_count
            total_ticks += dur * rep_count
    else:
        # SegmentTemplate com atributo duration (sem timeline).
        dur = int(template.get("duration", "0"))
        media_dur = _media_presentation_seconds(root)
        if dur and media_dur:
            seg_count = max(1, int(round(media_dur * timescale / dur)))
            total_ticks = dur * seg_count

    seg_duration = (total_ticks / timescale / seg_count) if seg_count else 2.0

    init_tpl = template.get("initialization", "")
    media_tpl = template.get("media", "")
    init_url = urljoin(mpd_url, fill_template(init_tpl, rep_id))
    segment_urls = [
        urljoin(mpd_url, fill_template(media_tpl, rep_id, start_number + i))
        for i in range(seg_count)
    ]

    return {
        "id": rep_id,
        "bandwidth": bandwidth,
        "width": int(rep.get("width", "0")),
        "height": int(rep.get("height", "0")),
        "init_url": init_url,
        "segment_urls": segment_urls,
        "seg_duration": seg_duration,
    }


def parse_mpd(mpd_url, mpd_bytes):
    """Extrai as representações de vídeo e a lista de segmentos de cada uma.

    Devolve uma lista de dicts ordenada por bandwidth crescente:
        {id, bandwidth, width, height, init_url, segment_urls, seg_duration}
    """
    root = ET.fromstring(mpd_bytes)

    # O ffmpeg gera cada qualidade em um AdaptationSet próprio (um por
    # Representation), mas o DASH também permite várias Representations em um
    # único AdaptationSet. Tratamos os dois casos coletando TODOS os
    # AdaptationSets de vídeo.
    video_sets = []
    for aset in _findall(root, "AdaptationSet"):
        ctype = aset.get("contentType", "") + aset.get("mimeType", "")
        if "video" in ctype:
            video_sets.append(aset)
    if not video_sets:
        # Fallback: AdaptationSets cujas Representations têm largura (vídeo).
        for aset in _findall(root, "AdaptationSet"):
            if any(r.get("width") for r in _children(aset, "Representation")):
                video_sets.append(aset)
    if not video_sets:
        raise RuntimeError("Nenhum AdaptationSet de vídeo encontrado no MPD.")

    reps = []
    for video_set in video_sets:
        # SegmentTemplate pode estar no AdaptationSet ou em cada Representation.
        set_template = (_children(video_set, "SegmentTemplate") or [None])[0]
        for rep in _children(video_set, "Representation"):
            reps.append(_parse_representation(root, mpd_url, rep, set_template))

    reps.sort(key=lambda r: r["bandwidth"])
    if not reps:
        raise RuntimeError("Nenhuma Representation de vídeo encontrada.")
    return reps


def _media_presentation_seconds(root):
    raw = root.get("mediaPresentationDuration")
    if not raw or not raw.startswith("PT"):
        return None
    raw = raw[2:]
    seconds = 0.0
    for unit, factor in (("H", 3600), ("M", 60), ("S", 1)):
        if unit in raw:
            value, raw = raw.split(unit, 1)
            seconds += float(value) * factor
    return seconds


def choose_rep(reps, throughput_bps, safety=0.9):
    """ABR por throughput: maior qualidade que cabe na banda estimada."""
    if throughput_bps <= 0:
        return reps[0]
    budget = throughput_bps * safety
    choice = reps[0]
    for rep in reps:
        if rep["bandwidth"] <= budget:
            choice = rep
    return choice


def simulate_playback(reps, total_segments, download,
                      startup_segments=2, safety=0.9, clock=time.monotonic):
    """Simula a reprodução e devolve as métricas de QoE.

    `download(url)` deve devolver (n_bytes, segundos_de_download) ou levantar
    exceção (tratada como stall). Separar o download do modelo de buffer
    permite testar a lógica de ABR/rebuffering de forma determinística.
    """
    init_downloaded = set()  # init baixado uma vez por representação

    buffer_s = 0.0
    play_started = False
    startup_time = None
    rebuffer_events = 0
    rebuffer_time = 0.0
    bitrate_switches = 0
    last_rep_id = None
    selected_bandwidths = []
    total_bytes = 0
    total_dl_time = 0.0
    throughput_bps = 0.0

    wall_start = clock()

    for i in range(total_segments):
        rep = choose_rep(reps, throughput_bps, safety)
        seg_dur = rep["seg_duration"]

        if last_rep_id is not None and rep["id"] != last_rep_id:
            bitrate_switches += 1
        last_rep_id = rep["id"]
        selected_bandwidths.append(rep["bandwidth"])

        try:
            if rep["id"] not in init_downloaded:
                init_bytes, init_dt = download(rep["init_url"])
                total_bytes += init_bytes
                total_dl_time += init_dt
                init_downloaded.add(rep["id"])

            if i >= len(rep["segment_urls"]):
                break
            nbytes, dt = download(rep["segment_urls"][i])
        except Exception as exc:  # falha de rede conta como stall severo
            rebuffer_events += 1
            rebuffer_time += seg_dur
            buffer_s = 0.0
            sys.stderr.write("[WARN] falha no segmento %d: %s\n" % (i, exc))
            continue

        total_bytes += nbytes
        total_dl_time += dt
        if dt > 0:
            throughput_bps = (nbytes * 8) / dt

        if not play_started:
            buffer_s += seg_dur
            if buffer_s >= startup_segments * seg_dur:
                play_started = True
                startup_time = clock() - wall_start
        else:
            # Durante o download (dt), a reprodução drena o buffer.
            if dt > buffer_s:
                rebuffer_events += 1
                rebuffer_time += (dt - buffer_s)
                buffer_s = 0.0
            else:
                buffer_s -= dt
            buffer_s += seg_dur

    if startup_time is None:
        startup_time = clock() - wall_start

    n = len(selected_bandwidths)
    avg_bitrate_kbps = (sum(selected_bandwidths) / n / 1000.0) if n else 0.0
    mean_throughput_mbps = ((total_bytes * 8) / total_dl_time / 1e6) if total_dl_time else 0.0

    return {
        "segments_played": n,
        "startup_time_s": round(startup_time, 3),
        "rebuffer_events": rebuffer_events,
        "rebuffer_time_s": round(rebuffer_time, 3),
        "avg_bitrate_kbps": round(avg_bitrate_kbps, 1),
        "bitrate_switches": bitrate_switches,
        "mean_throughput_mbps": round(mean_throughput_mbps, 3),
        "total_bytes": total_bytes,
        "wall_time_s": round(clock() - wall_start, 3),
        "representations_kbps": [round(r["bandwidth"] / 1000.0, 1) for r in reps],
    }


def run_client(mpd_url, startup_segments=2, max_segments=0,
               timeout=15.0, safety=0.9):
    """Baixa o MPD, reproduz via HTTP real e devolve as métricas de QoE."""
    mpd_bytes, _ = http_get(mpd_url, timeout)
    reps = parse_mpd(mpd_url, mpd_bytes)

    total_segments = max(len(r["segment_urls"]) for r in reps)
    if max_segments > 0:
        total_segments = min(total_segments, max_segments)

    def download(url):
        data, dt = http_get(url, timeout)
        return len(data), dt

    metrics = simulate_playback(reps, total_segments, download,
                                startup_segments=startup_segments, safety=safety)
    metrics["mpd_url"] = mpd_url
    return metrics


def main():
    ap = argparse.ArgumentParser(description="Cliente DASH headless para medir QoE.")
    ap.add_argument("--url", required=True, help="URL do manifesto .mpd")
    ap.add_argument("--out", help="Arquivo JSON de saída (default: stdout)")
    ap.add_argument("--startup-segments", type=int, default=2,
                    help="Segmentos para encher o buffer inicial (default: 2)")
    ap.add_argument("--max-segments", type=int, default=0,
                    help="Limite de segmentos (0 = vídeo inteiro)")
    ap.add_argument("--timeout", type=float, default=15.0,
                    help="Timeout por requisição HTTP em segundos")
    ap.add_argument("--safety", type=float, default=0.9,
                    help="Fator de segurança do ABR (default: 0.9)")
    args = ap.parse_args()

    metrics = run_client(
        args.url,
        startup_segments=args.startup_segments,
        max_segments=args.max_segments,
        timeout=args.timeout,
        safety=args.safety,
    )

    text = json.dumps(metrics, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        sys.stderr.write("[OK] QoE salva em %s\n" % args.out)
    else:
        print(text)


if __name__ == "__main__":
    main()
