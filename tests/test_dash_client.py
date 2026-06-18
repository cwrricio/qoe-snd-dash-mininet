"""Testes do cliente DASH: parsing do MPD, ABR e modelo de buffer/QoE."""

import pytest

from experiments import dash_client as dc


def make_mpd(nseg=8, seg_ticks=2000, timescale=1000):
    """MPD sintético no formato do ffmpeg (3 vídeos + 1 áudio)."""
    reps = []
    for rid, bw, w, h in [(0, 300000, 426, 240),
                          (1, 800000, 640, 360),
                          (2, 1500000, 1280, 720)]:
        reps.append(f"""
      <Representation id="{rid}" bandwidth="{bw}" width="{w}" height="{h}">
        <SegmentTemplate timescale="{timescale}" initialization="init-stream$RepresentationID$.m4s" media="chunk-stream$RepresentationID$-$Number%05d$.m4s" startNumber="1">
          <SegmentTimeline><S t="0" d="{seg_ticks}" r="{nseg - 1}"/></SegmentTimeline>
        </SegmentTemplate>
      </Representation>""")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT0H0M16.0S" minBufferTime="PT4.0S">
  <Period id="0" start="PT0.0S">
    <AdaptationSet id="0" contentType="video" mimeType="video/mp4">{''.join(reps)}
    </AdaptationSet>
    <AdaptationSet id="1" contentType="audio" mimeType="audio/mp4">
      <Representation id="3" bandwidth="128000">
        <SegmentTemplate timescale="{timescale}" initialization="init-stream$RepresentationID$.m4s" media="chunk-stream$RepresentationID$-$Number%05d$.m4s" startNumber="1">
          <SegmentTimeline><S t="0" d="{seg_ticks}" r="{nseg - 1}"/></SegmentTimeline>
        </SegmentTemplate>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>""".encode()


def make_mpd_ffmpeg_layout(nseg=8, seg_ticks=2000, timescale=1000):
    """MPD no layout REAL do ffmpeg: cada qualidade em seu próprio
    AdaptationSet (um por Representation)."""
    sets = []
    for rid, bw, w, h in [(0, 300000, 426, 240),
                          (1, 800000, 640, 360),
                          (2, 1500000, 1280, 720)]:
        sets.append(f"""
    <AdaptationSet id="{rid}" contentType="video" mimeType="video/mp4">
      <Representation id="{rid}" bandwidth="{bw}" width="{w}" height="{h}">
        <SegmentTemplate timescale="{timescale}" initialization="init-stream$RepresentationID$.m4s" media="chunk-stream$RepresentationID$-$Number%05d$.m4s" startNumber="1">
          <SegmentTimeline><S t="0" d="{seg_ticks}" r="{nseg - 1}"/></SegmentTimeline>
        </SegmentTemplate>
      </Representation>
    </AdaptationSet>""")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011" type="static" mediaPresentationDuration="PT0H0M16.0S" minBufferTime="PT4.0S">
  <Period id="0" start="PT0.0S">{''.join(sets)}
  </Period>
</MPD>""".encode()


BASE = "http://10.0.0.1:8000/output.mpd"


# ---------- template / parsing ----------

def test_fill_template_number_padding():
    out = dc.fill_template("chunk-stream$RepresentationID$-$Number%05d$.m4s", "2", 7)
    assert out == "chunk-stream2-00007.m4s"


def test_fill_template_plain_number():
    out = dc.fill_template("seg-$Number$.m4s", "0", 3)
    assert out == "seg-3.m4s"


def test_parse_mpd_excludes_audio_and_sorts_by_bandwidth():
    reps = dc.parse_mpd(BASE, make_mpd())
    assert [r["bandwidth"] for r in reps] == [300000, 800000, 1500000]
    assert all(r["id"] != "3" for r in reps)  # áudio (id=3) excluído


def test_parse_mpd_ffmpeg_layout_collects_all_adaptationsets():
    # Regressão: o ffmpeg gera um AdaptationSet por qualidade. O parser deve
    # coletar as três, não apenas a primeira.
    reps = dc.parse_mpd(BASE, make_mpd_ffmpeg_layout())
    assert [r["bandwidth"] for r in reps] == [300000, 800000, 1500000]


def test_parse_mpd_segment_count_and_urls():
    reps = dc.parse_mpd(BASE, make_mpd(nseg=8))
    low = reps[0]
    assert len(low["segment_urls"]) == 8
    assert low["seg_duration"] == pytest.approx(2.0)
    assert low["segment_urls"][0] == "http://10.0.0.1:8000/chunk-stream0-00001.m4s"
    assert low["init_url"] == "http://10.0.0.1:8000/init-stream0.m4s"


# ---------- ABR ----------

def test_choose_rep_zero_throughput_picks_lowest():
    reps = dc.parse_mpd(BASE, make_mpd())
    assert dc.choose_rep(reps, 0)["bandwidth"] == 300000


def test_choose_rep_high_throughput_picks_highest():
    reps = dc.parse_mpd(BASE, make_mpd())
    assert dc.choose_rep(reps, 10_000_000)["bandwidth"] == 1500000


def test_choose_rep_respects_safety_factor():
    reps = dc.parse_mpd(BASE, make_mpd())
    # 850 kbps com safety 0.9 => orçamento 765 kbps => fica na de 300k
    assert dc.choose_rep(reps, 850_000, safety=0.9)["bandwidth"] == 300000


# ---------- modelo de buffer / QoE ----------

def fake_network(reps, throughput_bps, seg_dur=2.0):
    """download(url) determinístico: dt = tamanho/banda do enlace simulado."""
    sizes = {}
    for rep in reps:
        sizes[rep["init_url"]] = 1000
        seg_bytes = int(rep["bandwidth"] * seg_dur / 8)
        for u in rep["segment_urls"]:
            sizes[u] = seg_bytes

    def download(url):
        nb = sizes[url]
        return nb, (nb * 8) / throughput_bps

    return download


def test_fast_network_no_rebuffer_high_bitrate():
    reps = dc.parse_mpd(BASE, make_mpd(nseg=8))
    dl = fake_network(reps, throughput_bps=50_000_000)  # 50 Mbps
    m = dc.simulate_playback(reps, 8, dl, clock=_fake_clock())
    assert m["rebuffer_events"] == 0
    assert m["rebuffer_time_s"] == 0.0
    assert m["segments_played"] == 8
    assert m["avg_bitrate_kbps"] > 800  # sobe para a melhor qualidade


def test_low_bandwidth_drops_bitrate():
    reps = dc.parse_mpd(BASE, make_mpd(nseg=8))
    dl = fake_network(reps, throughput_bps=600_000)  # 600 kbps
    m = dc.simulate_playback(reps, 8, dl, clock=_fake_clock())
    assert m["avg_bitrate_kbps"] == 300.0  # só a menor representação cabe


def test_severe_bandwidth_causes_rebuffering():
    reps = dc.parse_mpd(BASE, make_mpd(nseg=8))
    # 200 kbps: até a menor (300 kbps) não cabe -> buffer drena mais que enche
    dl = fake_network(reps, throughput_bps=200_000)
    m = dc.simulate_playback(reps, 8, dl, startup_segments=1, clock=_fake_clock())
    assert m["rebuffer_events"] > 0
    assert m["rebuffer_time_s"] > 0


def test_download_failure_counts_as_stall():
    reps = dc.parse_mpd(BASE, make_mpd(nseg=4))

    def failing_download(url):
        raise OSError("rede caiu")

    m = dc.simulate_playback(reps, 4, failing_download, clock=_fake_clock())
    assert m["rebuffer_events"] == 4
    assert m["total_bytes"] == 0


def _fake_clock():
    """Relógio monotônico falso que avança 0.5s a cada chamada (determinístico)."""
    state = {"t": 0.0}

    def clock():
        state["t"] += 0.5
        return state["t"]

    return clock
