"""Teste de integração end-to-end SEM Mininet.

Gera conteúdo MPEG-DASH real com ffmpeg a partir de media/input.mp4, serve
por HTTP em localhost e roda o cliente DASH. Valida o caminho completo
(MPD real do ffmpeg -> parsing -> ABR -> QoE) e o efeito de banda limitada,
que é exatamente o que a Etapa 2 mede — só que aqui sem o namespace de rede
do Mininet (que exige root).

Pulado automaticamente se não houver ffmpeg ou media/input.mp4.
"""

import functools
import http.server
import os
import socket
import subprocess
import threading
import time

import pytest

from experiments import dash_client as dc

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT = os.path.join(PROJECT_DIR, "media", "input.mp4")


def _ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        from shutil import which
        return which("ffmpeg")


def _can_bind_localhost():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
        return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not os.path.exists(INPUT) or _ffmpeg_exe() is None or not _can_bind_localhost(),
    reason="requer media/input.mp4, ffmpeg e permissao para abrir localhost",
)


@pytest.fixture(scope="module")
def dash_dir(tmp_path_factory):
    """Gera DASH real (3 qualidades, 6s) uma vez para o módulo."""
    out = tmp_path_factory.mktemp("dash")
    mpd = str(out / "output.mpd")
    cmd = [
        _ffmpeg_exe(), "-y", "-t", "12", "-i", INPUT,
        "-map", "0:v", "-b:v:0", "300k", "-s:v:0", "426x240",
        "-map", "0:v", "-b:v:1", "800k", "-s:v:1", "640x360",
        "-map", "0:v", "-b:v:2", "1500k", "-s:v:2", "1280x720",
        "-seg_duration", "2", "-use_timeline", "1", "-use_template", "1",
        "-f", "dash", mpd,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert os.path.exists(mpd), "ffmpeg falhou:\n" + proc.stderr[-2000:]
    return str(out)


class _ThrottledHandler(http.server.SimpleHTTPRequestHandler):
    rate_bps = None  # bytes/s; None = sem limite

    def copyfile(self, source, outputfile):
        if not self.rate_bps:
            return super().copyfile(source, outputfile)
        chunk = 8192
        while True:
            block = source.read(chunk)
            if not block:
                break
            outputfile.write(block)
            outputfile.flush()
            time.sleep(len(block) / self.rate_bps)

    def log_message(self, *args):
        pass


def _serve(directory, rate_bps=None):
    handler = functools.partial(_ThrottledHandler, directory=directory)
    _ThrottledHandler.rate_bps = rate_bps
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    return httpd, "http://127.0.0.1:%d/output.mpd" % port


def test_end_to_end_baseline_high_quality(dash_dir):
    httpd, url = _serve(dash_dir)
    try:
        m = dc.run_client(url, timeout=20)
    finally:
        httpd.shutdown()
    assert m["segments_played"] > 0
    assert m["rebuffer_events"] == 0          # localhost rápido: sem travar
    assert m["avg_bitrate_kbps"] >= 800       # ABR sobe de qualidade
    assert m["total_bytes"] > 0


def test_end_to_end_low_bandwidth_drops_quality(dash_dir):
    # ~500 kbps: só a representação de 300 kbps cabe com folga.
    httpd, url = _serve(dash_dir, rate_bps=500_000 / 8)
    try:
        m_low = dc.run_client(url, timeout=30)
    finally:
        httpd.shutdown()

    httpd2, url2 = _serve(dash_dir)
    try:
        m_full = dc.run_client(url2, timeout=20)
    finally:
        httpd2.shutdown()

    # Banda baixa deve reproduzir bitrate menor que o cenário sem limite.
    assert m_low["avg_bitrate_kbps"] < m_full["avg_bitrate_kbps"]
    assert m_low["mean_throughput_mbps"] < 1.0
