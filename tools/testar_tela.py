"""Testa e mede as tecnologias da aba Tela sem placa de captura e sem abrir janela.

    python tools/testar_tela.py            # testes de qualidade + tempo na sua placa de vídeo
    python tools/testar_tela.py --rapido   # só confere se tudo compila e dá o resultado esperado

O que é conferido:
  - ampliação (bilinear, FSR 1 EASU e Lanczos): a imagem ampliada fica mais perto do original do que
    a bilinear simples;
  - RCAS (nitidez), limpeza de faixas (deband) e o ajuste de cor;
  - RIFE (fluidez com IA): o quadro do meio entre duas imagens deslocadas fica no lugar certo, bem melhor do
    que só misturar as duas;
  - tempo de cada passo na placa de vídeo (com --rapido, não mede).
"""
import os
import sys
import time

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))


def criar_contexto():
    import moderngl
    erros = []
    for versao in (430, 330):
        for backend in ((None, "egl") if sys.platform.startswith("linux") else (None,)):
            try:
                kw = {"backend": backend} if backend else {}
                return moderngl.create_standalone_context(require=versao, **kw)
            except Exception as e:
                erros.append(f"{versao}/{backend}: {e}")
    raise RuntimeError("não consegui criar o OpenGL: " + "; ".join(erros))


def imagem_teste(w, h, semente=1):
    """Imagem com bordas, texto fino, degradês e ruído suave, parecida com um jogo."""
    rng = np.random.default_rng(semente)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), np.float32)
    img[..., 0] = 0.5 + 0.4 * np.sin(x / 37.0) * np.cos(y / 53.0)
    img[..., 1] = 0.35 + 0.3 * (x / w)
    img[..., 2] = 0.3 + 0.5 * (y / h)
    for _ in range(40):                                   # retângulos de cores fortes (bordas)
        x0, y0 = rng.integers(0, w - 40), rng.integers(0, h - 40)
        ww, hh = rng.integers(8, 120), rng.integers(8, 120)
        img[y0:y0 + hh, x0:x0 + ww] = rng.random(3)
    for _ in range(60):                                   # linhas finas (fios, texto)
        x0, y0 = rng.integers(0, max(1, w - 200)), rng.integers(0, h - 4)
        img[y0:y0 + 1, x0:x0 + rng.integers(20, 200)] = rng.random(3)
    cx, cy = w * 0.7, h * 0.3                              # círculo com borda curva
    img[(x - cx) ** 2 + (y - cy) ** 2 < (h * 0.12) ** 2] = (0.95, 0.85, 0.2)
    return np.clip(img, 0, 1)


def reduzir(img, fator):
    import cv2
    h, w = img.shape[:2]
    return cv2.resize(img, (round(w / fator), round(h / fator)), interpolation=cv2.INTER_AREA)


def psnr(a, b, borda=4):
    a, b = a[borda:-borda, borda:-borda], b[borda:-borda, borda:-borda]
    mse = float(np.mean((a.astype(np.float64) - b) ** 2))
    return 99.0 if mse <= 1e-12 else 10 * np.log10(1.0 / mse)


class Tela:
    """Os mesmos shaders da tela cheia, rodando numa textura fora da tela."""

    def __init__(self, ctx):
        import moderngl
        import pstudo
        self.ctx, self.mgl, self.ps = ctx, moderngl, pstudo
        self.progs = {n: ctx.program(vertex_shader=pstudo.VS_TELA, fragment_shader=fs)
                      for n, fs in pstudo.SHADERS_TELA.items()}
        self.vaos = {n: ctx.vertex_array(p, []) for n, p in self.progs.items()}

    def tex(self, img=None, tam=None, dtype="f4"):
        h, w = img.shape[:2] if img is not None else (tam[1], tam[0])
        dados = None if img is None else np.ascontiguousarray(img, np.float32 if dtype == "f4" else np.uint8)
        t = self.ctx.texture((w, h), 3 if img is not None else 4, dados.tobytes() if dados is not None else None,
                             dtype=dtype)
        t.filter = (self.mgl.LINEAR, self.mgl.LINEAR)
        t.repeat_x = t.repeat_y = False
        return t

    def rodar(self, nome, destino, texs, **unis):
        f = self.ctx.framebuffer(color_attachments=[destino])
        f.use()
        self.ctx.viewport = (0, 0) + destino.size
        p = self.progs[nome]
        for k, v in unis.items():
            if k in p:
                p[k] = v
        for i, t in texs:
            t.use(i)
        self.vaos[nome].render(self.mgl.TRIANGLES, vertices=3)
        f.release()

    @staticmethod
    def ler(t):
        w, h = t.size
        return np.frombuffer(t.read(), np.float32).reshape(h, w, 4)[..., :3].copy()

    def ampliar(self, img, w, h, modo, nitidez=0.0, faixa=0, deband=0.0):
        """modo 0 = bilinear, 1 = FSR 1 EASU, 2 = Lanczos. Devolve a imagem (h, w, 3)."""
        ps = self.ps
        src = self.tex(img)
        ih, iw = img.shape[:2]
        if deband > 0:
            limpo = self.tex(tam=(iw, ih))
            self.rodar("limpa", limpo, [(0, src)], src=0, tam=(float(iw), float(ih)), forca=float(deband))
            src.release()
            src = limpo
        meio = self.tex(tam=(w, h))
        self.rodar("escala", meio, [(0, src)], src=0, tam_in=(float(iw), float(ih)), tam_out=(float(w), float(h)),
                   origem=(0.0, 0.0), virar=0.0, modo=int(modo), faixa=int(faixa), **ps.unis_cor({}))
        fim = self.tex(tam=(w, h))
        self.rodar("rcas", fim, [(0, meio)], src=0, tam=(float(w), float(h)), origem=(0.0, 0.0), virar=0.0,
                   nitidez=float(nitidez))
        r = self.ler(fim)
        for t in (src, meio, fim):
            t.release()
        return r


def medir(ctx, func, vezes=5):
    func()
    ctx.finish()
    t0 = time.perf_counter()
    for _ in range(vezes):
        func()
    ctx.finish()
    return (time.perf_counter() - t0) / vezes * 1000


def testar_ampliacao(tela, rapido):
    print("\n== Ampliação (720p -> 1080p, como o PS3 na maioria dos jogos)")
    w, h = (480, 270) if rapido else (1920, 1080)
    orig = imagem_teste(w, h)
    peq = reduzir(orig, 1.5)
    res = {}
    for nome, modo in (("bilinear", 0), ("FSR 1 EASU", 1), ("Lanczos", 2)):
        out = tela.ampliar(peq, w, h, modo)
        res[nome] = psnr(out, orig)
        print(f"   {nome:<12} PSNR {res[nome]:.2f} dB")
    out = tela.ampliar(peq, w, h, 1, nitidez=0.5)
    print(f"   FSR 1 + RCAS PSNR {psnr(out, orig):.2f} dB (com nitidez 50%)")
    assert res["FSR 1 EASU"] > res["bilinear"] + 0.3, "o FSR 1 deveria ficar melhor que o bilinear"
    assert res["Lanczos"] > res["bilinear"], "o Lanczos deveria ficar melhor que o bilinear"
    # imagem do mesmo tamanho: nada muda (sem FSR)
    igual = tela.ampliar(orig, w, h, 0)
    assert psnr(igual, orig) > 45, "no mesmo tamanho a imagem deveria sair igual"
    print("   ok")


def testar_cor(tela):
    print("\n== Faixa de cor, deband e ajuste de cor")
    ps = tela.ps
    lim = np.full((64, 64, 3), 16 / 255, np.float32)
    lim[:, 32:] = 235 / 255
    out = tela.ampliar(lim, 64, 64, 0, faixa=1)
    assert abs(out[:, :30].mean()) < 0.01 and abs(out[:, 34:].mean() - 1) < 0.01, "16-235 deveria virar 0-255"
    print("   RGB limitado 16-235 -> 0-255: ok")
    # degradê com degraus (banding de 8 bits/MJPEG): o deband deve suavizar sem borrar a borda forte
    x = np.linspace(0.2, 0.4, 512, dtype=np.float32)
    deg = np.repeat(np.repeat((np.round(x * 127.5) / 127.5)[None, :, None], 64, 0), 3, 2)   # degraus de 2/255
    deg[:, 400:] = 0.9                       # borda forte que tem de continuar nítida
    out = tela.ampliar(deg, 512, 64, 0, deband=1.0)
    suave = np.abs(np.diff(out[32, 20:380, 0])).max()
    antes = np.abs(np.diff(deg[32, 20:380, 0])).max()
    borda = out[32, 402, 0] - out[32, 397, 0]
    print(f"   deband: maior degrau {antes * 255:.1f} -> {suave * 255:.1f} (em 0-255); borda {borda * 255:.0f}")
    assert suave < antes * 0.75, "o deband deveria diminuir os degraus"
    assert borda > 0.4, "o deband não pode borrar bordas fortes"
    # ajuste de cor neutro = nada muda; saturação no mínimo = cinza
    img = imagem_teste(64, 64)
    neutro = tela.ampliar(img, 64, 64, 0)
    assert psnr(neutro, img) > 45
    p = tela.progs["escala"]
    for k, v in ps.unis_cor({"saturacao": -1.0}).items():
        p[k] = v
    src, dst = tela.tex(img), tela.tex(tam=(64, 64))
    tela.rodar("escala", dst, [(0, src)], src=0, tam_in=(64.0, 64.0), tam_out=(64.0, 64.0), origem=(0.0, 0.0),
               virar=0.0, modo=0, faixa=0)
    cinza = tela.ler(dst)
    assert np.abs(cinza[..., 0] - cinza[..., 1]).max() < 0.01, "saturação no mínimo deveria deixar a imagem cinza"
    for k, v in ps.unis_cor({}).items():
        p[k] = v
    print("   ajuste de cor: ok")


def testar_rife(ctx, rapido):
    print("\n== Fluidez com IA (RIFE 4.6)")
    from pstudo_ia import RifeGL, VS, FS_MONTA
    import moderngl
    w, h = (256, 160) if rapido else (1280, 720)
    base = imagem_teste(w + 64, h, semente=3)
    desloc = 24 if not rapido else 12
    a = base[:, 0:w]
    b = base[:, desloc:desloc + w]
    tex = []
    for img in (a, b):
        t = ctx.texture((w, h), 3, np.ascontiguousarray(img, np.float32).tobytes(), dtype="f4")
        t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        t.repeat_x = t.repeat_y = False
        tex.append(t)
    monta = ctx.program(vertex_shader=VS.replace("{ver}", "330"), fragment_shader=FS_MONTA)
    vao = ctx.vertex_array(monta, [])
    saida = ctx.texture((w, h), 4, dtype="f4")
    fbo = ctx.framebuffer(color_attachments=[saida])
    larguras = (w, w * 3 // 4, w) if rapido else (640, 960, 1280)   # troca de tamanho e volta (bug antigo)
    caminhos = (False, True) if ctx.version_code >= 430 else (True,)
    for forcar_330 in caminhos:
        rede = RifeGL(ctx, vagas=2, forcar_330=forcar_330)
        print(f"   pesos na {'memória de shader (OpenGL 4.3)' if rede.ssbo else 'textura (OpenGL 3.3)'}")
        for lw in (larguras if not forcar_330 else larguras[:2]):
            lh = max(32, int(round(lw * h / w / 2)) * 2)
            rede.preparar(lw, lh)
            for i, t in enumerate(tex):
                rede.carregar_quadro(i, t)
            for t_ in ((0.5,) if rapido else (0.5, 0.25)):
                def rodar(t_=t_):
                    rede.inferir(0, 1, t_)
                    fbo.use()
                    ctx.viewport = (0, 0, w, h)
                    tex[0].use(0)
                    tex[1].use(1)
                    rede.estado.use(2)
                    monta["A"], monta["B"], monta["S"] = 0, 1, 2
                    monta["rede"] = tuple(float(v) for v in rede.tam)
                    monta["conteudo"] = tuple(float(v) for v in rede.conteudo)
                    monta["tam_fonte"] = (float(w), float(h))
                    vao.render(moderngl.TRIANGLES, vertices=3)
                ms = medir(ctx, rodar, 1 if rapido else 3)
                out = np.frombuffer(saida.read(), np.float32).reshape(h, w, 4)[..., :3]
                d = round(desloc * t_)
                certo = base[:, d:d + w]                    # o certo: t do caminho
                mistura = a * (1 - t_) + b * t_
                borda = desloc + 4                          # as bordas laterais não têm de onde vir
                p_ia = psnr(out[:, borda:-borda], certo[:, borda:-borda])
                p_mix = psnr(mistura[:, borda:-borda], certo[:, borda:-borda])
                print(f"   rede {lw}×{lh}, t={t_}: PSNR {p_ia:.2f} dB (só misturar: {p_mix:.2f} dB) • "
                      f"{ms:.1f} ms por quadro")
                assert p_ia > p_mix + 4, "o RIFE deveria acertar o movimento bem melhor do que misturar"
        rede.liberar()
    print("   ok")


def testar_tempo(tela):
    print("\n== Tempo na placa de vídeo (1080p na tela)")
    ctx = tela.ctx
    peq = imagem_teste(1280, 720).astype(np.float32)
    src = tela.tex(peq)
    meio, fim = tela.tex(tam=(1920, 1080)), tela.tex(tam=(1920, 1080))
    for nome, modo in (("bilinear", 0), ("FSR 1 EASU", 1), ("Lanczos", 2)):
        def f(modo=modo):
            tela.rodar("escala", meio, [(0, src)], src=0, tam_in=(1280.0, 720.0), tam_out=(1920.0, 1080.0),
                       origem=(0.0, 0.0), virar=0.0, modo=modo, faixa=0, **tela.ps.unis_cor({}))
        print(f"   {nome:<12} {medir(ctx, f):.2f} ms")
    rcas = medir(ctx, lambda: tela.rodar("rcas", fim, [(0, meio)], src=0, tam=(1920.0, 1080.0), origem=(0.0, 0.0),
                                         virar=0.0, nitidez=0.5))
    print(f"   RCAS         {rcas:.2f} ms")
    limpo = tela.tex(tam=(1280, 720))
    limpa = medir(ctx, lambda: tela.rodar("limpa", limpo, [(0, src)], src=0, tam=(1280.0, 720.0), forca=0.5))
    print(f"   limpeza      {limpa:.2f} ms")


def main():
    rapido = "--rapido" in sys.argv
    ctx = criar_contexto()
    print(f"Placa de vídeo: {ctx.info.get('GL_RENDERER')} • OpenGL {ctx.version_code}")
    tela = Tela(ctx)
    testar_ampliacao(tela, rapido)
    testar_cor(tela)
    testar_rife(ctx, rapido)
    if not rapido:
        testar_tempo(tela)
    print("\nTudo certo.")


if __name__ == "__main__":
    main()
