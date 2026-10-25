"""
PSTudo — gerenciador de PS3 com HEN pelo PC (webMAN MOD).
Copyright (C) 2026 MrKitanoX — feito usando o Claude.

Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo sob os termos da
GNU General Public License versão 3, conforme publicada pela Free Software Foundation.
Ele é distribuído na esperança de ser útil, mas SEM NENHUMA GARANTIA. Veja o arquivo LICENSE.
"""

"""
PSTudo — envia jogos do PC para o PS3 pela rede (FTP do webMAN MOD / multiMAN).
Interface escura no estilo dos consoles modernos, com o mínimo de informação técnica.
"""

import ftplib
import json
import math
import os
import queue
import random
import socket
import struct
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageTk

APP_NOME = "PSTudo"
CONFIG = os.path.join(os.path.expanduser("~"), ".pstudo.json")
CONFIG_ANTIGA = os.path.join(os.path.expanduser("~"), ".ps3_transfer.json")   # versões antigas do app
BLOCO = 1024 * 1024
W, H = 960, 600

WIN = sys.platform.startswith("win")
F_LIGHT = "Segoe UI Light" if WIN else "Inter"
F_REG = "Segoe UI" if WIN else "Inter"
F_SEMI = "Segoe UI Semibold" if WIN else "Inter"
F_SYM = "Segoe UI Symbol" if WIN else "DejaVu Sans"

AZUL = (0, 112, 209)
AZUL_HOVER = (24, 136, 240)
BRANCO = "#FFFFFF"
CINZA = "#9AA4B8"
CINZA_ESCURO = "#5D6679"

DESTINOS_AUTO = {".iso": "/dev_hdd0/PS3ISO", ".pkg": "/dev_hdd0/packages",
                 ".bin": "/dev_hdd0/PSXISO", ".cue": "/dev_hdd0/PSXISO"}
DESTINOS = ["Automático", "/dev_hdd0/GAMES", "/dev_hdd0/PS3ISO", "/dev_hdd0/packages",
            "/dev_hdd0/PS2ISO", "/dev_hdd0/PSXISO", "/dev_usb000/GAMES"]


class Cancelado(Exception):
    pass


# =============================================================== utilidades
def formatar_tamanho(b):
    for un in ["B", "KB", "MB", "GB"]:
        if b < 1024:
            return f"{b:.1f} {un}".replace(".", ",")
        b /= 1024
    return f"{b:.1f} TB".replace(".", ",")


def formatar_restante(seg):
    if seg < 60:
        return "Falta menos de 1 minuto"
    m = int(seg // 60)
    if m < 60:
        return f"Faltam cerca de {m} min"
    return f"Faltam cerca de {m // 60} h {m % 60:02d} min"


def titulo_sfo(caminho):
    """Lê o nome do jogo (TITLE) de um PARAM.SFO."""
    try:
        with open(caminho, "rb") as f:
            d = f.read(64 * 1024)
        if d[:4] != b"\0PSF":
            return None
        k_ini, d_ini, n = struct.unpack_from("<III", d, 8)
        for i in range(n):
            k_off, _fmt, d_len, _max, d_off = struct.unpack_from("<HHIII", d, 20 + i * 16)
            fim = d.index(b"\0", k_ini + k_off)
            if d[k_ini + k_off:fim] == b"TITLE":
                bruto = d[d_ini + d_off:d_ini + d_off + d_len]
                return bruto.split(b"\0")[0].decode("utf-8", "ignore").replace("\n", " ").strip()
    except Exception:
        pass
    return None


def nome_amigavel(item):
    if os.path.isdir(item):
        for sfo in ("PS3_GAME/PARAM.SFO", "PARAM.SFO"):
            t = titulo_sfo(os.path.join(item, sfo))
            if t:
                return t
        return os.path.basename(os.path.normpath(item))
    nome = os.path.splitext(os.path.basename(item))[0]
    return nome.replace("_", " ").replace(".", " ").strip()


def tamanho_item(item):
    if os.path.isfile(item):
        return os.path.getsize(item)
    total = 0
    for raiz, _, arqs in os.walk(item):
        for a in arqs:
            try:
                total += os.path.getsize(os.path.join(raiz, a))
            except OSError:
                pass
    return total


def destino_auto(item, escolha):
    if escolha and escolha != "Automático":
        return escolha
    if os.path.isdir(item):
        return "/dev_hdd0/GAMES"
    return DESTINOS_AUTO.get(os.path.splitext(item)[1].lower(), "/dev_hdd0/GAMES")


# =============================================================== rede / FTP
def ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def ips_locais():
    """Todos os IPv4 de rede local deste PC (cabo, Wi-Fi…), começando pelo da rota padrão.
    Adaptadores virtuais (VPN, VirtualBox, WSL…) entram depois, então o PS3 é achado mesmo com eles."""
    ips = []
    principal = ip_local()
    if principal:
        ips.append(principal)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except OSError:
        pass
    if WIN:
        try:
            import subprocess
            saida = subprocess.run(["ipconfig"], capture_output=True, timeout=5,
                                   creationflags=0x08000000).stdout.decode("latin-1", "ignore")
            import re
            ips += re.findall(r"IPv4[^:]*:\s*([\d.]+)", saida)
        except Exception:
            pass

    def privado(ip):
        a, b_ = (int(x) for x in ip.split(".")[:2])
        return a == 10 or (a == 172 and 16 <= b_ <= 31) or (a == 192 and b_ == 168)
    vistos = []
    for ip in ips:
        if ip.count(".") == 3 and privado(ip) and ip not in vistos:
            vistos.append(ip)
    return vistos


# Começo do endereço físico (MAC) das placas de rede da Sony usadas no PS3
MAC_SONY = ("00-04-1f", "00-13-15", "00-15-c1", "00-19-c5", "00-1d-0d", "00-1f-a7", "00-24-8d", "00-d9-d1",
            "28-0d-fc", "70-9e-29", "a8-e3-ee", "f8-d0-ac", "fc-0f-e6", "00-1f-e4", "bc-60-a7", "2c-cc-44",
            "f8-46-1c", "0c-fe-45", "70-66-55", "c8-63-f1", "00-e4-21", "78-c8-81", "5c-84-3c", "00-01-4a")


def ips_sony_arp():
    """IPs da tabela ARP do Windows cujo MAC é da Sony (o PS3 aparece aí depois de responder na rede)."""
    if not WIN:
        return []
    try:
        import re
        import subprocess
        saida = subprocess.run(["arp", "-a"], capture_output=True, timeout=5,
                               creationflags=0x08000000).stdout.decode("latin-1", "ignore").lower()
        return [ip for ip, mac in re.findall(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f-]{17})", saida)
                if mac.startswith(MAC_SONY)]
    except Exception:
        return []


def testar_ftp(ip, porta=21, timeout=1.0):
    """Retorna o banner do FTP se houver um servidor respondendo.
    Se a porta abriu, espera mais pelo banner: o webMAN às vezes demora para cumprimentar."""
    try:
        with socket.create_connection((ip, int(porta)), timeout=timeout) as s:
            s.settimeout(max(3.0, timeout * 2))
            banner = s.recv(256).decode("latin-1", "ignore")
            return banner if banner.startswith("220") else None
    except OSError:
        return None


def testar_webman_http(ip, timeout=2.0):
    """O servidor web do webMAN (porta 80) também denuncia o PS3."""
    try:
        with urllib.request.urlopen(f"http://{ip}/cpursx.ps3", timeout=timeout) as r:
            return "webman" in r.read(4096).decode("latin-1", "ignore").lower()
    except Exception:
        return False


def procurar_ps3(porta=21, ip_salvo=None):
    if ip_salvo and testar_ftp(ip_salvo, porta, 1.5):
        return ip_salvo
    meus = ips_locais()
    # 1º os aparelhos da Sony que o PC já conhece; depois todas as redes do PC
    candidatos = [ip for ip in ips_sony_arp() if ip not in meus]
    for meu in meus:
        base = meu.rsplit(".", 1)[0]
        candidatos += [f"{base}.{i}" for i in range(1, 255) if f"{base}.{i}" not in meus]
    candidatos = list(dict.fromkeys(candidatos))
    if not candidatos:
        return None
    achados = []
    ex = ThreadPoolExecutor(max_workers=128)
    try:
        futs = {ex.submit(testar_ftp, ip, porta): ip for ip in candidatos}
        for fut in as_completed(futs):
            banner = fut.result()
            if banner:
                ip = futs[fut]
                if any(k in banner.lower() for k in ("webman", "multiman", "ps3")):
                    return ip
                achados.append(ip)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    # servidores FTP sem "webMAN" no cumprimento: fica com o que for PS3 pelo site do webMAN ou pelo MAC
    sony = set(ips_sony_arp())
    for ip in achados:
        if ip in sony or testar_webman_http(ip):
            return ip
    return achados[0] if achados else None


def conectar(cfg):
    # O webMAN manda textos fora do UTF-8 (ex.: temperatura com "°" nas respostas).
    # latin-1 aceita qualquer byte e devolve os mesmos bytes ao reenviar.
    # Precisa ser definido ANTES de conectar, pois vale para o canal de comandos.
    ftp = ftplib.FTP(encoding="latin-1")
    ftp.connect(cfg["ip"], int(cfg.get("porta", 21)), timeout=30)
    ftp.login(cfg.get("usuario") or "anonymous", cfg.get("senha") or "")
    ftp.set_pasv(True)
    return ftp


def para_ftp(texto):
    """Nome vindo do PC ou digitado -> forma usada na conexão (bytes UTF-8)."""
    return texto.encode("utf-8").decode("latin-1")


def legivel(texto):
    """Nome vindo do PS3 -> texto bonito para mostrar na tela."""
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def montar_lista(item, destino):
    lista = []
    destino = destino.rstrip("/")
    if os.path.isdir(item):
        base = para_ftp(os.path.basename(os.path.normpath(item)))
        for raiz, _, arquivos in os.walk(item):
            rel = os.path.relpath(raiz, item)
            rel = "" if rel == "." else para_ftp(rel.replace("\\", "/"))
            for nome in arquivos:
                local = os.path.join(raiz, nome)
                remoto = "/".join(p for p in [destino, base, rel, para_ftp(nome)] if p)
                lista.append((local, remoto, os.path.getsize(local)))
    elif os.path.isfile(item):
        lista.append((item, f"{destino}/{para_ftp(os.path.basename(item))}", os.path.getsize(item)))
    return lista


def criar_pastas(ftp, caminho, cache):
    atual = ""
    for parte in caminho.strip("/").split("/")[:-1]:
        atual += "/" + parte
        if atual in cache:
            continue
        try:
            ftp.mkd(atual)
        except ftplib.error_perm:
            pass
        cache.add(atual)


def tamanho_remoto(ftp, caminho):
    try:
        ftp.voidcmd("TYPE I")
        return ftp.size(caminho)
    except ftplib.all_errors:
        return None


def trabalho_envio(fila_jogos, cfg, cancelar, avisar):
    """Roda em outra thread. fila_jogos = [{'item','nome'}]."""
    ftp = None
    try:
        planos = []
        for j in fila_jogos:
            dest = destino_auto(j["item"], cfg.get("destino"))
            planos.append((j["nome"], montar_lista(j["item"], dest)))
        total = sum(t for _, lista in planos for *_, t in lista) or 1
        ftp = conectar(cfg)
        enviado, inicio, cache = 0, time.time(), set()
        pular = cfg.get("pular", True)
        for idx, (nome, lista) in enumerate(planos, 1):
            for local, remoto, tam in lista:
                if cancelar.is_set():
                    raise Cancelado()
                criar_pastas(ftp, remoto, cache)
                if pular and tamanho_remoto(ftp, remoto) == tam:
                    enviado += tam
                    avisar("progresso", (enviado, total, idx, len(planos), nome, inicio))
                    continue

                def cb(dados, _nome=nome, _idx=idx):
                    nonlocal enviado
                    if cancelar.is_set():
                        raise Cancelado()
                    enviado += len(dados)
                    avisar("progresso", (enviado, total, _idx, len(planos), _nome, inicio))

                with open(local, "rb") as f:
                    ftp.storbinary(f"STOR {remoto}", f, blocksize=BLOCO, callback=cb)
        avisar("fim", (len(planos), enviado, time.time() - inicio))
    except Cancelado:
        avisar("cancelado", None)
    except Exception as e:
        avisar("erro", e)
    finally:
        if ftp:
            try:
                ftp.quit()
            except Exception:
                ftp.close()


def mensagem_erro(e):
    txt = str(e)
    if isinstance(e, (ConnectionRefusedError, socket.timeout, TimeoutError)) or "timed out" in txt:
        return "Não consegui falar com o PS3.", "Confira se ele está ligado, com o HEN ativado e na mesma rede."
    if txt.startswith(("452", "552")):
        return "O PS3 ficou sem espaço.", "Libere espaço no HD do console e tente de novo."
    if txt.startswith("530"):
        return "O PS3 recusou o login.", "Confira o usuário e a senha nas configurações."
    return "A conexão caiu no meio do envio.", "Tente de novo: o que já foi enviado não será mandado outra vez."


# =============================================================== desenho
class Pintor:
    """Gera imagens com cantos arredondados, brilho e ícones (supersampling 4x)."""

    def __init__(self, escala):
        self.s = escala
        self.cache = {}

    def px(self, v):
        return int(round(v * self.s))

    def ret(self, w, h, r, fill, outline=None, largura=0, glow=None, glow_r=18, icone=None, icone_y=0.40):
        chave = ("ret", w, h, r, fill, outline, largura, glow, glow_r, icone, icone_y)
        if chave in self.cache:
            return self.cache[chave]
        k = 4
        g = self.px(glow_r) if glow else 0
        W_, H_ = self.px(w) + 2 * g, self.px(h) + 2 * g
        img = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        if glow:
            gl = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
            ImageDraw.Draw(gl).rounded_rectangle([g, g, W_ - g, H_ - g], self.px(r), fill=glow)
            img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(g / 2.2)))
        big = Image.new("RGBA", (W_ * k, H_ * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        lw = max(1, round(self.px(largura) * k)) if outline else 0
        d.rounded_rectangle([g * k, g * k, (W_ - g) * k - 1, (H_ - g) * k - 1], self.px(r) * k,
                            fill=fill, outline=outline, width=lw)
        if icone:
            self._icone(d, icone, W_ * k / 2, (g + self.px(h) * icone_y) * k, self.px(1) * k)
        img = Image.alpha_composite(img, big.resize((W_, H_), Image.LANCZOS))
        foto = ImageTk.PhotoImage(img)
        self.cache[chave] = foto
        return foto

    def _icone(self, d, tipo, cx, cy, u):
        cor = (255, 255, 255, 235)
        lw = int(3.2 * u)
        if tipo == "pasta":
            w, h = 64 * u, 48 * u
            x0, y0 = cx - w / 2, cy - h / 2
            d.rounded_rectangle([x0, y0 - 8 * u, x0 + 26 * u, y0 + 10 * u], 5 * u, outline=cor, width=lw)
            d.rounded_rectangle([x0, y0, x0 + w, y0 + h], 7 * u, fill=(10, 20, 40, 255), outline=cor, width=lw)
            ax = cx
            d.line([ax, y0 + 13 * u, ax, y0 + 36 * u], fill=cor, width=lw)
            d.line([ax - 10 * u, y0 + 23 * u, ax, y0 + 13 * u, ax + 10 * u, y0 + 23 * u], fill=cor, width=lw, joint="curve")
        elif tipo == "disco":
            r = 30 * u
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=cor, width=lw)
            r2 = 8 * u
            d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=cor, width=lw)
            d.arc([cx - 20 * u, cy - 20 * u, cx + 20 * u, cy + 20 * u], 200, 250, fill=(255, 255, 255, 140), width=lw)
        elif tipo == "check":
            r = 34 * u
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(52, 211, 153, 255), width=lw)
            d.line([cx - 15 * u, cy + 1 * u, cx - 4 * u, cy + 12 * u, cx + 16 * u, cy - 11 * u],
                   fill=(52, 211, 153, 255), width=int(4 * u), joint="curve")
        elif tipo == "alerta":
            r = 34 * u
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(248, 113, 113, 255), width=lw)
            d.line([cx, cy - 16 * u, cx, cy + 5 * u], fill=(248, 113, 113, 255), width=int(4 * u))
            d.ellipse([cx - 3 * u, cy + 11 * u, cx + 3 * u, cy + 17 * u], fill=(248, 113, 113, 255))
        elif tipo == "iso":
            r = 26 * u
            dx = -10 * u
            d.ellipse([cx + dx - r, cy - r, cx + dx + r, cy + r], outline=cor, width=lw)
            d.ellipse([cx + dx - 7 * u, cy - 7 * u, cx + dx + 7 * u, cy + 7 * u], outline=cor, width=lw)
            ax = cx + 26 * u
            d.line([ax - 10 * u, cy - 26 * u, ax + 14 * u, cy - 26 * u], fill=cor, width=lw)
            d.line([ax + 6 * u, cy - 34 * u, ax + 14 * u, cy - 26 * u, ax + 6 * u, cy - 18 * u], fill=cor,
                   width=lw, joint="curve")
        elif tipo == "chave":
            cor2 = (255, 255, 255, 235)
            r = 15 * u
            kx, ky = cx - 18 * u, cy
            d.ellipse([kx - r, ky - r, kx + r, ky + r], outline=cor2, width=lw)
            d.ellipse([kx - 4 * u, ky - 4 * u, kx + 4 * u, ky + 4 * u], fill=cor2)
            d.line([kx + r, ky, cx + 32 * u, ky], fill=cor2, width=lw)
            d.line([cx + 22 * u, ky, cx + 22 * u, ky + 11 * u], fill=cor2, width=lw)
            d.line([cx + 31 * u, ky, cx + 31 * u, ky + 8 * u], fill=cor2, width=lw)
        elif tipo.startswith("ponto"):
            cores = {"ponto_ok": (52, 211, 153, 255), "ponto_busca": (251, 191, 36, 255), "ponto_erro": (248, 113, 113, 255)}
            r = 4.5 * u
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cores[tipo])

    def fundo(self, w, h):
        W_, H_ = self.px(w), self.px(h)
        rnd = random.Random(7)
        # gradiente base
        grad = Image.new("RGB", (1, 256))
        for y in range(256):
            t = y / 255
            grad.putpixel((0, y), (int(9 - 6 * t), int(24 - 18 * t), int(58 - 46 * t)))
        img = grad.resize((W_, H_)).convert("RGBA")
        # brilho azul no canto
        gl = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        dg = ImageDraw.Draw(gl)
        dg.ellipse([W_ * 0.45, -H_ * 0.55, W_ * 1.35, H_ * 0.55], fill=(0, 112, 209, 110))
        dg.ellipse([-W_ * 0.3, H_ * 0.65, W_ * 0.35, H_ * 1.4], fill=(40, 70, 160, 55))
        img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(self.px(120))))
        # ondas suaves
        ondas = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        do = ImageDraw.Draw(ondas)
        for n in range(7):
            amp = H_ * (0.05 + n * 0.012)
            fase = n * 0.55
            base_y = H_ * (0.62 + n * 0.035)
            pts = [(x, base_y + amp * math.sin(x / W_ * 2.4 * math.pi + fase)
                    + amp * 0.4 * math.sin(x / W_ * 5.1 * math.pi + fase * 2))
                   for x in range(-10, W_ + 10, 6)]
            do.line(pts, fill=(120, 180, 255, 16 + n * 4), width=max(1, self.px(1.4)))
        img = Image.alpha_composite(img, ondas.filter(ImageFilter.GaussianBlur(self.px(0.8))))
        # partículas
        part = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        dp = ImageDraw.Draw(part)
        for _ in range(38):
            x, y = rnd.uniform(0, W_), rnd.uniform(0, H_)
            r = rnd.uniform(1, 3.5) * self.s
            dp.ellipse([x - r, y - r, x + r, y + r], fill=(180, 215, 255, rnd.randint(25, 90)))
        img = Image.alpha_composite(img, part.filter(ImageFilter.GaussianBlur(self.px(1.2))))
        return ImageTk.PhotoImage(img)


def icone_app(tam=256):
    """Ícone próprio: quadrado azul arredondado com seta de envio."""
    k = 4
    T = tam * k
    img = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    grad = Image.new("RGBA", (1, 256))
    for y in range(256):
        t = y / 255
        grad.putpixel((0, y), (int(24 - 20 * t), int(140 - 90 * t), int(255 - 120 * t), 255))
    grad = grad.resize((T, T))
    mask = Image.new("L", (T, T), 0)
    ImageDraw.Draw(mask).rounded_rectangle([T * 0.04, T * 0.04, T * 0.96, T * 0.96], T * 0.22, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    lw = int(T * 0.075)
    cx = T / 2
    d.line([cx, T * 0.25, cx, T * 0.62], fill="white", width=lw)
    d.line([cx - T * 0.17, T * 0.41, cx, T * 0.25, cx + T * 0.17, T * 0.41], fill="white", width=lw, joint="curve")
    d.rounded_rectangle([T * 0.24, T * 0.70, T * 0.76, T * 0.76], T * 0.03, fill="white")
    return img.resize((tam, tam), Image.LANCZOS)


# =============================================================== widgets no canvas
class Botao:
    def __init__(self, app, x, y, w, h, texto, acao, estilo="primario", tag="view", tamanho_fonte=15):
        self.app, self.acao, self.estilo = app, acao, estilo
        self.ativo = True
        c, p = app.c, app.p
        self.w, self.h = w, h
        self.tag = f"btn{id(self)}"
        if estilo == "primario":
            self.img_n = p.ret(w, h, h / 2, AZUL + (255,))
            self.img_h = p.ret(w, h, h / 2, AZUL_HOVER + (255,), glow=(0, 112, 209, 150), glow_r=16)
            self.img_d = p.ret(w, h, h / 2, (255, 255, 255, 22))
        else:
            self.img_n = p.ret(w, h, h / 2, (14, 22, 40, 225), outline=(255, 255, 255, 60), largura=1)
            self.img_h = p.ret(w, h, h / 2, (28, 40, 66, 235), outline=(255, 255, 255, 140), largura=1)
            self.img_d = self.img_n
        self.im = c.create_image(p.px(x), p.px(y), image=self.img_n, tags=(tag, self.tag))
        self.tx = c.create_text(p.px(x), p.px(y), text=texto, fill=BRANCO,
                                font=(F_SEMI, -p.px(tamanho_fonte)), tags=(tag, self.tag))
        c.tag_bind(self.tag, "<Enter>", self._entrar)
        c.tag_bind(self.tag, "<Leave>", self._sair)
        c.tag_bind(self.tag, "<Button-1>", self._clicar)

    def _entrar(self, _):
        if self.ativo:
            self.app.c.itemconfig(self.im, image=self.img_h)
            self.app.c.config(cursor="hand2")

    def _sair(self, _):
        self.app.c.itemconfig(self.im, image=self.img_n if self.ativo else self.img_d)
        self.app.c.config(cursor="")

    def _clicar(self, _):
        if self.ativo and self.acao:
            self.app.c.config(cursor="")
            self.acao()

    def set_ativo(self, ativo):
        self.ativo = ativo
        self.app.c.itemconfig(self.im, image=self.img_n if ativo else self.img_d)
        self.app.c.itemconfig(self.tx, fill=BRANCO if ativo else CINZA_ESCURO)

    def set_texto(self, t):
        self.app.c.itemconfig(self.tx, text=t)


class Cartao:
    """Cartão grande clicável com ícone (tela inicial)."""

    def __init__(self, app, x, y, w, h, icone, titulo, sub, acao):
        c, p = app.c, app.p
        self.app, self.acao = app, acao
        self.tag = f"card{id(self)}"
        self.img_n = p.ret(w, h, 22, (255, 255, 255, 12), outline=(255, 255, 255, 34), largura=1, icone=icone)
        self.img_h = p.ret(w, h, 22, (255, 255, 255, 24), outline=(90, 170, 255, 230), largura=2,
                           glow=(0, 112, 209, 120), glow_r=22, icone=icone)
        self.im = c.create_image(p.px(x), p.px(y), image=self.img_n, tags=("view", self.tag))
        c.create_text(p.px(x), p.px(y + h * 0.18), text=titulo, fill=BRANCO,
                      font=(F_SEMI, -p.px(19)), tags=("view", self.tag))
        c.create_text(p.px(x), p.px(y + h * 0.32), text=sub, fill=CINZA,
                      font=(F_REG, -p.px(13)), tags=("view", self.tag))
        c.tag_bind(self.tag, "<Enter>", lambda e: (c.itemconfig(self.im, image=self.img_h), c.config(cursor="hand2")))
        c.tag_bind(self.tag, "<Leave>", lambda e: (c.itemconfig(self.im, image=self.img_n), c.config(cursor="")))
        c.tag_bind(self.tag, "<Button-1>", lambda e: (c.config(cursor=""), acao()))


# =============================================================== FTP: gerenciador de arquivos
PASTAS_SISTEMA = ("/dev_flash", "/dev_flash2", "/dev_flash3", "/dev_blind")
RAIZES = ("/", "/dev_hdd0", "/dev_hdd1", "/dev_usb000", "/dev_usb001", "/dev_bdvd", "/app_home", "/host_root")
EXT_TEXTO = (".txt", ".cfg", ".ini", ".xml", ".json", ".log", ".conf", ".lst", ".md", ".yml", ".yaml", ".csv")
LIMITE_EDICAO = 1024 * 1024


def sem_acento(texto):
    """Minúsculas e sem acentos, para a pesquisa achar "Música" digitando "musica"."""
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFD", texto.casefold()) if unicodedata.category(ch) != "Mn")


def fora_da_busca(caminho):
    """Pastas que a pesquisa nas subpastas pula (sistema e cópias de outras pastas)."""
    return any(caminho == s or caminho.startswith(s + "/")
               for s in PASTAS_SISTEMA + ("/dev_bdvd", "/app_home", "/host_root"))


def juntar(a, b):
    return "/" + b if a in ("", "/") else a.rstrip("/") + "/" + b


def pai(caminho):
    caminho = caminho.rstrip("/")
    return caminho.rsplit("/", 1)[0] or "/"


def protegido(caminho):
    c = caminho.rstrip("/") or "/"
    return c in RAIZES or any(c == s or c.startswith(s + "/") for s in PASTAS_SISTEMA)


def listar_remoto(ftp, caminho):
    itens = []
    try:
        for nome, fatos in ftp.mlsd(caminho, facts=["type", "size"]):
            tipo = fatos.get("type", "file").lower()
            if nome in (".", "..") or tipo in ("cdir", "pdir"):
                continue
            itens.append((nome, tipo == "dir", int(fatos.get("size", 0) or 0)))
    except (ftplib.error_perm, ftplib.error_reply):
        itens = []
        linhas = []
        ftp.cwd(caminho)
        ftp.retrlines("LIST", linhas.append)
        for linha in linhas:
            partes = linha.split(None, 8)
            if len(partes) < 9 or partes[8] in (".", ".."):
                continue
            itens.append((partes[8], linha.startswith("d"), int(partes[4]) if partes[4].isdigit() else 0))
    itens.sort(key=lambda x: (not x[1], x[0].lower()))
    return itens


def apagar_remoto(ftp, caminho, eh_pasta):
    if protegido(caminho):
        raise PermissionError("Pasta do sistema protegida")
    if eh_pasta:
        for nome, d, _ in listar_remoto(ftp, caminho):
            apagar_remoto(ftp, juntar(caminho, nome), d)
        ftp.rmd(caminho)
    else:
        ftp.delete(caminho)


def baixar_remoto(ftp, remoto, eh_pasta, local, progresso):
    if eh_pasta:
        os.makedirs(local, exist_ok=True)
        for nome, d, _ in listar_remoto(ftp, remoto):
            baixar_remoto(ftp, juntar(remoto, nome), d, os.path.join(local, legivel(nome)), progresso)
    else:
        with open(local, "wb") as f:
            def cb(dados):
                f.write(dados)
                progresso(len(dados))
            ftp.retrbinary(f"RETR {remoto}", cb, blocksize=BLOCO)


def ler_texto_remoto(ftp, caminho):
    import io
    buf = io.BytesIO()
    ftp.retrbinary(f"RETR {caminho}", buf.write)
    dados = buf.getvalue()
    for cod in ("utf-8", "latin-1"):
        try:
            return dados.decode(cod), cod
        except UnicodeDecodeError:
            continue
    return dados.decode("latin-1", "replace"), "latin-1"


def gravar_texto_remoto(ftp, caminho, texto, cod):
    import io
    ftp.storbinary(f"STOR {caminho}", io.BytesIO(texto.encode(cod, "replace")))


def mini_icone(tipo, cor=(225, 232, 245, 255)):
    T = 72
    img = Image.new("RGBA", (T, T), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    lw = 6
    if tipo == "pasta":
        d.rounded_rectangle([8, 14, 34, 26], 4, outline=cor, width=lw)
        d.rounded_rectangle([8, 20, 64, 60], 7, fill=(10, 18, 34, 255), outline=cor, width=lw)
    else:
        d.polygon([(16, 8), (46, 8), (58, 20), (58, 64), (16, 64)], outline=cor, width=lw)
        if tipo == "texto":
            for y in (30, 41, 52):
                d.line([26, y, 48, y], fill=cor, width=4)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(18, 18))


# cores dos painéis (iguais às imagens do canvas)
PAINEL = "#0A1222"
PAINEL_RGB = (10, 18, 34)
LINHA_SEL = "#12305C"
BTN = "#16233F"
BTN_HOVER = "#20345C"


class Extras:
    # ================================================= abas
    ABAS = [("enviar", "Enviar jogos", 104), ("arquivos", "Arquivos", 84), ("rap", "Licenças", 84),
            ("console", "Console", 80), ("tela", "Tela", 64)]
    ABAS_X = 461

    def _montar_abas(self):
        p, c = self.p, self.c
        total = sum(w for *_, w in self.ABAS) + 8
        self.abas_x0 = self.ABAS_X - total / 2
        c.create_image(p.px(self.ABAS_X), p.px(56), image=p.ret(total, 44, 22, (14, 24, 46, 220),
                                                        outline=(255, 255, 255, 40), largura=1))
        self.aba_sel_img = {k: p.ret(w - 6, 34, 17, (255, 255, 255, 240)) for k, _, w in self.ABAS}
        self.aba_sel = c.create_image(0, 0)
        self.aba_tx = {}
        x = self.abas_x0 + 4
        self.aba_pos = {}
        for k, nome, w in self.ABAS:
            cx = x + w / 2
            self.aba_pos[k] = cx
            tg = f"aba_{k}"
            self.aba_tx[k] = c.create_text(p.px(cx), p.px(56), text=nome, fill=CINZA,
                                           font=(F_SEMI, -p.px(13)), tags=(tg,))
            # área clicável invisível
            r = c.create_rectangle(p.px(x), p.px(38), p.px(x + w), p.px(74), outline="", fill="", tags=(tg,))
            c.tag_lower(r, self.aba_tx[k])
            c.tag_bind(tg, "<Enter>", lambda e, k=k: self._hover_aba(k, True))
            c.tag_bind(tg, "<Leave>", lambda e, k=k: self._hover_aba(k, False))
            c.tag_bind(tg, "<Button-1>", lambda e, k=k: self.trocar_aba(k))
            x += w
        self.aba_barra = c.create_rectangle(0, 0, 0, 0, fill="#1888F0", outline="", state="hidden")
        self._pintar_abas()

    def _hover_aba(self, k, dentro):
        self.c.config(cursor="hand2" if dentro else "")
        if k != self.aba:
            self.c.itemconfig(self.aba_tx[k], fill=BRANCO if dentro else CINZA)

    def _pintar_abas(self):
        p = self.p
        self.c.itemconfig(self.aba_sel, image=self.aba_sel_img[self.aba])
        self.c.coords(self.aba_sel, p.px(self.aba_pos[self.aba]), p.px(56))
        for k, tx in self.aba_tx.items():
            self.c.itemconfig(tx, fill="#0B1426" if k == self.aba else CINZA)
            self.c.tag_raise(tx)

    def trocar_aba(self, k):
        if self.op_ativa or k == self.aba:
            return
        self.aba = k
        self._pintar_abas()
        self._mostrar_aba(k)

    def _mostrar_aba(self, k):
        {"enviar": self._tela_enviar, "arquivos": self.tela_arquivos, "rap": self.tela_rap,
         "console": self.tela_console, "tela": self.tela_espelho}[k]()

    def _tela_enviar(self):
        """Aba Enviar jogos: progresso se estiver enviando, resultado pendente, ou a tela inicial."""
        if self.enviando:
            self.tela_enviando()
        elif getattr(self, "envio_pendente", None):
            pend, self.envio_pendente = self.envio_pendente, None
            self._atualizar_aba_envio(None)
            self.c.delete("aviso_app")
            self._evento(*pend)
        else:
            self.tela_inicio()

    def _atualizar_aba_envio(self, frac, texto=None):
        """Mostra o andamento do envio no próprio botão da aba (para quando você está em outra aba)."""
        c, p = self.c, self.p
        if not getattr(self, "aba_tx", None):
            return
        nome = texto or ("Enviar jogos" if frac is None else f"Enviando {int(frac * 100)}%")
        c.itemconfig(self.aba_tx["enviar"], text=nome)
        if frac is None:
            c.itemconfig(self.aba_barra, state="hidden")
            return
        x0 = self.aba_pos["enviar"] - 40
        c.coords(self.aba_barra, p.px(x0), p.px(70), p.px(x0 + 80 * max(0.03, frac)), p.px(72))
        c.itemconfig(self.aba_barra, state="normal")
        c.tag_raise(self.aba_barra)

    def _aviso_app(self, texto, cor="#34D399"):
        """Aviso rápido no topo da janela, some sozinho."""
        c, p = self.c, self.p
        c.delete("aviso_app")
        w = 12 + len(texto) * 7.4
        c.create_image(p.px(W / 2), p.px(98), tags="aviso_app",
                       image=p.ret(w + 40, 34, 17, (14, 24, 46, 240), outline=(255, 255, 255, 50), largura=1))
        c.create_oval(p.px(W / 2 - w / 2 - 6), p.px(94), p.px(W / 2 - w / 2 + 2), p.px(102), fill=cor, outline="",
                      tags="aviso_app")
        c.create_text(p.px(W / 2 + 6), p.px(98), text=texto, fill=BRANCO, font=(F_SEMI, -p.px(13)),
                      tags="aviso_app")
        if getattr(self, "_aviso_job", None):
            self.root.after_cancel(self._aviso_job)
        self._aviso_job = self.root.after(5000, lambda: c.delete("aviso_app"))

    # ================================================= utilidades de thread / diálogos
    def em_thread(self, trabalho, ok=None, erro=None, sempre=None):
        def rodar():
            ftp = None
            try:
                ftp = conectar(self.cfg)
                r = trabalho(ftp)
                if ok:
                    self.fila.put(("cb", lambda: ok(r)))
            except Exception as e:
                if erro:
                    self.fila.put(("cb", lambda e=e: erro(e)))
            finally:
                if ftp:
                    try:
                        ftp.quit()
                    except Exception:
                        ftp.close()
                if sempre:
                    self.fila.put(("cb", sempre))
        threading.Thread(target=rodar, daemon=True).start()

    def _janela(self, titulo, largura, altura):
        j = ctk.CTkToplevel(self.root)
        j.title(titulo)
        j.geometry(f"{largura}x{altura}")
        j.resizable(False, False)
        j.configure(fg_color="#0B1324")
        j.transient(self.root)
        j.after(150, lambda: j.winfo_exists() and j.grab_set())
        return j

    def dialogo(self, titulo, texto, botao="OK", acao=None, perigo=False, cancelar=True, campo=None):
        j = self._janela(titulo, 440, 200 if campo is None else 250)
        fonte = ctk.CTkFont(family=F_REG, size=13)
        ctk.CTkLabel(j, text=titulo, font=ctk.CTkFont(family=F_LIGHT, size=22), text_color=BRANCO).pack(
            anchor="w", padx=26, pady=(22, 4))
        ctk.CTkLabel(j, text=texto, font=fonte, text_color=CINZA, wraplength=388, justify="left").pack(
            anchor="w", padx=26)
        entrada = None
        if campo is not None:
            entrada = ctk.CTkEntry(j, height=36, corner_radius=10, fg_color="#111C33", border_color="#26324D",
                                   font=fonte)
            entrada.insert(0, campo)
            entrada.pack(fill="x", padx=26, pady=(12, 0))
            entrada.focus_set()
            entrada.select_range(0, "end")
        fr = ctk.CTkFrame(j, fg_color="transparent")
        fr.pack(side="bottom", fill="x", padx=26, pady=22)

        def confirmar(_=None):
            valor = entrada.get().strip() if entrada else None
            j.destroy()
            if acao:
                acao(valor) if campo is not None else acao()
        cor = ("#B91C1C", "#DC2626") if perigo else ("#0070D1", "#1888F0")
        ctk.CTkButton(fr, text=botao, height=38, width=130, corner_radius=19, fg_color=cor[0], hover_color=cor[1],
                      font=ctk.CTkFont(family=F_SEMI, size=14), command=confirmar).pack(side="right")
        if cancelar:
            ctk.CTkButton(fr, text="Cancelar", height=38, width=110, corner_radius=19, fg_color="transparent",
                          border_width=1, border_color="#3A4660", hover_color="#1A2744", font=fonte,
                          command=j.destroy).pack(side="right", padx=(0, 10))
        if entrada:
            entrada.bind("<Return>", confirmar)
        return j

    # ================================================= aba ARQUIVOS
    def tela_arquivos(self):
        self.limpar()
        p, c = self.p, self.c
        x0, y0, w, h = 48, 116, 864, 466
        c.create_image(p.px(x0 + w / 2), p.px(y0 + h / 2), tags="view",
                       image=p.ret(w, h, 20, PAINEL_RGB + (255,), outline=(255, 255, 255, 30), largura=1))
        fonte = ctk.CTkFont(family=F_REG, size=13)
        fonte_b = ctk.CTkFont(family=F_SEMI, size=13)
        painel = ctk.CTkFrame(self.root, fg_color=PAINEL, corner_radius=0, width=w - 28, height=h - 28)
        painel.pack_propagate(False)
        painel.grid_propagate(False)
        c.create_window(p.px(x0 + 14), p.px(y0 + 14), window=painel, anchor="nw", tags="view")
        self.widgets.append(painel)

        def botao(pai_, texto, cmd, largura=None, perigo=False):
            b = ctk.CTkButton(pai_, text=texto, command=cmd, height=34, corner_radius=17, font=fonte_b,
                              width=largura or 0, fg_color="#3A1620" if perigo else BTN,
                              hover_color="#5A1E2C" if perigo else BTN_HOVER,
                              text_color="#FCA5A5" if perigo else BRANCO, text_color_disabled=CINZA_ESCURO)
            return b

        topo = ctk.CTkFrame(painel, fg_color="transparent")
        topo.pack(fill="x", padx=8, pady=(6, 8))
        self.fm_btn_voltar = botao(topo, "←", self.fm_subir, 40)
        self.fm_btn_voltar.pack(side="left")
        self.fm_lbl_path = ctk.CTkLabel(topo, text=legivel(self.fm_path), font=ctk.CTkFont(family=F_SEMI, size=15),
                                        text_color=BRANCO, anchor="w")
        self.fm_lbl_path.pack(side="left", padx=12, fill="x", expand=True)
        botao(topo, "⟳", self.fm_listar, 40).pack(side="right")
        for nome, cam in reversed([("HD", "/dev_hdd0"), ("Jogos", "/dev_hdd0/GAMES"), ("ISOs", "/dev_hdd0/PS3ISO"),
                                   ("Plugins", "/dev_hdd0/plugins"), ("Pendrive", "/dev_usb000")]):
            botao(topo, nome, lambda c_=cam: self.fm_ir(c_)).pack(side="right", padx=(0, 6))

        # ---- pesquisa: filtra enquanto digita; Enter procura também dentro das subpastas
        busca = ctk.CTkFrame(painel, fg_color="transparent")
        busca.pack(fill="x", padx=8, pady=(0, 6))
        self.fm_busca = ctk.CTkEntry(busca, height=34, corner_radius=17, fg_color="#0A1222", border_color="#26324D",
                                     text_color=BRANCO, font=fonte, placeholder_text_color=CINZA_ESCURO,
                                     placeholder_text="Pesquisar nesta pasta…   (Enter procura também nas subpastas)")
        self.fm_busca.pack(side="left", fill="x", expand=True)
        self.fm_busca.bind("<KeyRelease>", self._fm_digitou)
        self.fm_busca.bind("<Return>", lambda e: self.fm_buscar_fundo())
        self.fm_busca.bind("<Escape>", lambda e: self.fm_limpar_busca())
        self.fm_btn_fundo = botao(busca, "Nas subpastas", self.fm_buscar_fundo)
        self.fm_btn_fundo.pack(side="left", padx=(6, 0))
        botao(busca, "✕", self.fm_limpar_busca, 40).pack(side="left", padx=(6, 0))
        self.fm_modo_fundo = False

        self.fm_lista = ctk.CTkScrollableFrame(painel, fg_color=PAINEL, corner_radius=0, height=256,
                                               scrollbar_button_color="#1E2A44",
                                               scrollbar_button_hover_color="#2A3A5E")
        self.fm_lista.pack(fill="both", expand=True, padx=2)

        self.fm_lbl_status = ctk.CTkLabel(painel, text="", font=fonte, text_color=CINZA, anchor="w", height=22)
        self.fm_lbl_status.pack(fill="x", padx=10, pady=(6, 2))

        acoes = ctk.CTkFrame(painel, fg_color="transparent")
        acoes.pack(fill="x", padx=8, pady=(2, 4))
        botao(acoes, "Enviar arquivos", self.fm_enviar_arquivos).pack(side="left")
        botao(acoes, "Enviar pasta", self.fm_enviar_pasta).pack(side="left", padx=6)
        botao(acoes, "Nova pasta", self.fm_nova_pasta).pack(side="left")
        self.fm_btn_apagar = botao(acoes, "Apagar", self.fm_apagar, perigo=True)
        self.fm_btn_apagar.pack(side="right")
        self.fm_btn_renomear = botao(acoes, "Renomear", self.fm_renomear)
        self.fm_btn_renomear.pack(side="right", padx=6)
        self.fm_btn_baixar = botao(acoes, "Baixar", self.fm_baixar)
        self.fm_btn_baixar.pack(side="right")
        self.fm_btn_editar = botao(acoes, "Editar", self.fm_editar)
        self.fm_btn_editar.pack(side="right", padx=6)
        self.fm_icones = {k: mini_icone(k) for k in ("pasta", "arquivo", "texto")}
        self.fm_listar()

    def _fm_ativo(self):
        return self.aba == "arquivos" and getattr(self, "fm_lista", None) is not None and self.fm_lista.winfo_exists()

    def fm_status(self, texto, cor=CINZA):
        if self._fm_ativo():
            self.fm_lbl_status.configure(text=texto, text_color=cor)

    def _fm_botoes(self):
        sel = self.fm_sel
        tem = sel is not None
        prot = tem and protegido(juntar(self.fm_path, sel[0]))
        texto = tem and not sel[1] and sel[0].lower().endswith(EXT_TEXTO) and sel[2] <= LIMITE_EDICAO
        ocupado = self.op_ativa
        self.fm_btn_editar.configure(state="normal" if texto and not ocupado else "disabled")
        self.fm_btn_baixar.configure(state="normal" if tem and not ocupado else "disabled")
        self.fm_btn_renomear.configure(state="normal" if tem and not prot and not ocupado else "disabled")
        self.fm_btn_apagar.configure(state="normal" if tem and not prot and not ocupado else "disabled")
        self.fm_btn_voltar.configure(state="normal" if self.fm_path != "/" else "disabled")

    def fm_ir(self, caminho):
        if self.op_ativa:
            return
        self.fm_path = caminho
        self._fm_zerar_busca()
        self.fm_listar()

    def fm_subir(self):
        self.fm_ir(pai(self.fm_path))

    def fm_listar(self):
        if not self._fm_ativo():
            return
        if self.fm_modo_fundo:          # recarregar no meio de uma pesquisa: refaz a pesquisa
            return self.fm_buscar_fundo()
        self.fm_busca_id += 1           # cancela uma pesquisa que ainda esteja rodando
        self.fm_sel = None
        self.fm_lbl_path.configure(text=legivel(self.fm_path))
        for w_ in self.fm_lista.winfo_children():
            w_.destroy()
        self._fm_botoes()
        if self.estado_ps3 != "ok":
            self.fm_desconectado = True
            self.fm_status("Conecte o PS3 para ver os arquivos.", "#FBBF24")
            return
        self.fm_desconectado = False
        self.fm_status("Carregando…")
        caminho = self.fm_path

        def ok(itens):
            if not self._fm_ativo() or caminho != self.fm_path or self.fm_modo_fundo:
                return
            self.fm_todos = itens
            self._fm_filtrar()

        def erro(e):
            self.fm_status(f"Não consegui abrir esta pasta ({str(e)[:60]})", "#F87171")
        self.em_thread(lambda ftp: listar_remoto(ftp, caminho), ok, erro)

    # ---- pesquisa
    def _fm_zerar_busca(self):
        self.fm_busca_id += 1
        self.fm_modo_fundo = False
        if self._fm_ativo():
            self.fm_busca.delete(0, "end")
            self.fm_btn_fundo.configure(text="Nas subpastas")

    def fm_limpar_busca(self):
        estava_fundo = self.fm_modo_fundo
        self._fm_zerar_busca()
        if estava_fundo:
            self.fm_listar()
        else:
            self._fm_filtrar()
        self.fm_lista.focus_set()

    def _fm_digitou(self, e=None):
        if e is not None and e.keysym in ("Return", "KP_Enter", "Escape"):
            return
        if self.fm_modo_fundo:          # mudou o texto depois de pesquisar nas subpastas: volta para esta pasta
            self.fm_busca_id += 1
            self.fm_modo_fundo = False
            self.fm_btn_fundo.configure(text="Nas subpastas")
        if getattr(self, "_fm_espera", None):
            self.root.after_cancel(self._fm_espera)
        self._fm_espera = self.root.after(140, self._fm_filtrar)

    def _fm_filtrar(self):
        self._fm_espera = None
        if not self._fm_ativo() or self.fm_modo_fundo:
            return
        bruto = self.fm_busca.get().strip()
        termo = sem_acento(bruto)
        todos = self.fm_todos
        self.fm_itens = [it for it in todos if termo in sem_acento(legivel(it[0]))] if termo else list(todos)
        self.fm_sel = None
        self._fm_botoes()
        for w_ in self.fm_lista.winfo_children():
            w_.destroy()
        self._fm_desenhar()
        n, total = len(self.fm_itens), len(todos)
        if not termo:
            self.fm_status("Pasta vazia" if not n else f"{n} {'item' if n == 1 else 'itens'}")
        elif not n:
            self.fm_status(f"Nada com “{bruto}” nesta pasta. Aperte Enter para procurar também nas subpastas.",
                           "#FBBF24")
        else:
            self.fm_status(f"{n} de {total} itens")

    def fm_buscar_fundo(self):
        if not self._fm_ativo() or self.estado_ps3 != "ok":
            return
        bruto = self.fm_busca.get().strip()
        termo = sem_acento(bruto)
        if not termo:
            self.fm_status("Digite o nome (ou parte do nome) do que você procura.", "#FBBF24")
            return
        self.fm_busca_id += 1
        meu = self.fm_busca_id
        self.fm_modo_fundo = True
        self.fm_btn_fundo.configure(text="Procurando…")
        self.fm_sel = None
        self.fm_itens = []
        self._fm_botoes()
        for w_ in self.fm_lista.winfo_children():
            w_.destroy()
        self.fm_linhas = []
        self.fm_status("Procurando…")
        base = self.fm_path
        limite = 2000
        estado = {"t": 0.0}

        def ativa():
            return self.fm_busca_id == meu

        def trabalho(ftp):
            achados, pastas, fila_ = [], 0, [""]
            while fila_ and ativa() and len(achados) < limite:
                rel = fila_.pop(0)
                try:
                    itens = listar_remoto(ftp, juntar(base, rel) if rel else base)
                except (ftplib.error_perm, ftplib.error_reply):
                    continue            # pasta sem permissão: segue com as outras
                pastas += 1
                for nome, eh_pasta, tam in itens:
                    r = f"{rel}/{nome}" if rel else nome
                    if termo in sem_acento(legivel(nome)):
                        achados.append((r, eh_pasta, tam))
                    # pastas do sistema e espelhos (disco, app_home) só entram se a pesquisa começou nelas
                    if eh_pasta and (fora_da_busca(base) or not fora_da_busca(juntar(base, r))):
                        fila_.append(r)
                agora = time.time()
                if agora - estado["t"] > 0.3:
                    estado["t"] = agora
                    msg = f"Procurando… {pastas} pastas vistas, {len(achados)} encontrados"
                    self.fila.put(("cb", lambda m=msg: ativa() and self.fm_status(m)))
            return achados[:limite], len(achados) >= limite

        def ok(res):
            if not ativa() or not self._fm_ativo():
                return
            achados, cortou = res
            achados.sort(key=lambda x: (x[0].count("/"), not x[1], x[0].lower()))
            self.fm_itens = achados
            self.fm_btn_fundo.configure(text="Nas subpastas")
            self._fm_desenhar()
            n = len(achados)
            if not n:
                self.fm_status(f"Nada com “{bruto}” em {legivel(base)} e nas subpastas.", "#FBBF24")
            else:
                self.fm_status(f"{n}{'+' if cortou else ''} {'encontrado' if n == 1 else 'encontrados'} em "
                               f"{legivel(base)} e nas subpastas" + (" (parei nos primeiros)" if cortou else ""))

        def erro(e):
            if ativa() and self._fm_ativo():
                self.fm_btn_fundo.configure(text="Nas subpastas")
                self.fm_status(f"Não consegui pesquisar ({str(e)[:60]})", "#F87171")
        self.em_thread(trabalho, ok, erro)

    def _fm_desenhar(self):
        fonte = ctk.CTkFont(family=F_REG, size=14)
        fonte_p = ctk.CTkFont(family=F_REG, size=12)
        self.fm_linhas = []
        for i, item in enumerate(self.fm_itens[:600]):
            nome, eh_pasta, tam = item
            tipo = "pasta" if eh_pasta else ("texto" if nome.lower().endswith(EXT_TEXTO) else "arquivo")
            linha = ctk.CTkFrame(self.fm_lista, fg_color=PAINEL, corner_radius=10, height=38)
            linha.pack(fill="x", pady=1, padx=(0, 6))
            linha.pack_propagate(False)
            ic = ctk.CTkLabel(linha, text="", image=self.fm_icones[tipo], width=24)
            ic.pack(side="left", padx=(12, 8))
            pasta_de, _, so_nome = nome.rpartition("/")
            lb = ctk.CTkLabel(linha, text=legivel(so_nome), font=fonte, text_color=BRANCO, anchor="w")
            extra = []
            if pasta_de:                 # resultado de pesquisa nas subpastas: mostra onde está
                lb.pack(side="left")
                lp = ctk.CTkLabel(linha, text="   em " + legivel(pasta_de), font=fonte_p, text_color=CINZA_ESCURO,
                                  anchor="w")
                lp.pack(side="left", fill="x", expand=True)
                extra.append(lp)
            else:
                lb.pack(side="left", fill="x", expand=True)
            tm = ctk.CTkLabel(linha, text="" if eh_pasta else formatar_tamanho(tam), font=fonte_p,
                              text_color=CINZA, width=90, anchor="e")
            tm.pack(side="right", padx=14)
            for w_ in [linha, ic, lb, tm] + extra:
                w_.bind("<Button-1>", lambda e, k=i: self._fm_selecionar(k))
                w_.bind("<Double-Button-1>", lambda e, k=i: self._fm_abrir(k))
            self.fm_linhas.append(linha)
        if len(self.fm_itens) > 600:
            ctk.CTkLabel(self.fm_lista, text=f"+ {len(self.fm_itens) - 600} itens não mostrados",
                         text_color=CINZA, font=fonte_p).pack(pady=6)

    def _fm_selecionar(self, k):
        for i, ln in enumerate(self.fm_linhas):
            ln.configure(fg_color=LINHA_SEL if i == k else PAINEL)
        self.fm_sel = self.fm_itens[k]
        self._fm_botoes()

    def _fm_abrir(self, k):
        nome, eh_pasta, _ = self.fm_itens[k]
        if eh_pasta:
            self.fm_ir(juntar(self.fm_path, nome))
        else:
            self._fm_selecionar(k)
            if self.fm_btn_editar.cget("state") == "normal":
                self.fm_editar()

    # ---- operações
    def _fm_operacao(self, descricao, trabalho, msg_ok, recarregar=True):
        if self.op_ativa:
            return
        self.op_ativa = True
        self._fm_botoes()
        self.fm_status(descricao)

        def ok(_):
            self.fm_status(msg_ok, "#34D399")
            if recarregar:
                self.root.after(600, self.fm_listar)

        def erro(e):
            if isinstance(e, PermissionError):
                self.fm_status("Por segurança, o app não mexe em pastas do sistema.", "#F87171")
            else:
                self.fm_status(f"Não deu certo: {str(e)[:70]}", "#F87171")

        def fim():
            self.op_ativa = False
            if self._fm_ativo():
                self._fm_botoes()
        self.em_thread(trabalho, ok, erro, fim)

    def _progresso_ui(self, prefixo, total=None):
        estado = {"feito": 0, "t": 0}

        def cb(n):
            estado["feito"] += n
            agora = time.time()
            if agora - estado["t"] > 0.2:
                estado["t"] = agora
                f = estado["feito"]
                txt = f"{prefixo} {int(f / total * 100)}%" if total else f"{prefixo} {formatar_tamanho(f)}"
                self.fila.put(("cb", lambda t=txt: self.fm_status(t)))
        return cb

    def _bloquear_sistema(self):
        if any(self.fm_path == s_ or self.fm_path.startswith(s_ + "/") for s_ in PASTAS_SISTEMA):
            self.dialogo("Pasta protegida", "Por segurança, o app não grava arquivos nas pastas do sistema do PS3.",
                         cancelar=False)
            return True
        if self.fm_path == "/":
            self.dialogo("Escolha uma pasta", "Entre no HD (dev_hdd0) ou no pendrive antes de enviar arquivos.",
                         cancelar=False)
            return True
        return False

    def _fm_enviar(self, itens):
        destino = self.fm_path
        lista = [x for it in itens for x in montar_lista(it, destino)]
        total = sum(t for *_, t in lista) or 1
        prog = self._progresso_ui("Enviando…", total)

        def trabalho(ftp):
            cache = set()
            for local, remoto, _ in lista:
                criar_pastas(ftp, remoto, cache)
                with open(local, "rb") as f:
                    ftp.storbinary(f"STOR {remoto}", f, blocksize=BLOCO, callback=lambda d: prog(len(d)))
        self._fm_operacao("Enviando…", trabalho, f"{len(lista)} arquivo(s) enviados.")

    def fm_enviar_arquivos(self):
        if self.estado_ps3 != "ok" or self.op_ativa or self._bloquear_sistema():
            return
        arqs = filedialog.askopenfilenames(title="Arquivos para enviar", parent=self.root)
        if arqs:
            self._fm_enviar(list(arqs))

    def fm_enviar_pasta(self):
        if self.estado_ps3 != "ok" or self.op_ativa or self._bloquear_sistema():
            return
        pasta = filedialog.askdirectory(title="Pasta para enviar", parent=self.root)
        if pasta:
            self._fm_enviar([pasta])

    def fm_nova_pasta(self):
        if self.estado_ps3 != "ok" or self.op_ativa or self._bloquear_sistema():
            return

        def criar(nome):
            if not nome or "/" in nome:
                return
            caminho = juntar(self.fm_path, para_ftp(nome))
            self._fm_operacao("Criando pasta…", lambda ftp: ftp.mkd(caminho), f"Pasta “{nome}” criada.")
        self.dialogo("Nova pasta", f"Vai ser criada em {legivel(self.fm_path)}", "Criar", criar, campo="")

    def fm_renomear(self):
        if not self.fm_sel:
            return
        antigo = self.fm_sel[0]
        so_nome = antigo.rsplit("/", 1)[-1]

        def renomear(novo):
            if not novo or novo == legivel(so_nome) or "/" in novo:
                return
            a = juntar(self.fm_path, antigo)
            b = juntar(pai(a), para_ftp(novo))        # continua na mesma pasta (vale para resultados da pesquisa)
            self._fm_operacao("Renomeando…", lambda ftp: ftp.rename(a, b), f"Renomeado para “{novo}”.")
        self.dialogo("Renomear", f"Novo nome para “{legivel(so_nome)}”:", "Renomear", renomear,
                     campo=legivel(so_nome))

    def fm_apagar(self):
        if not self.fm_sel:
            return
        nome, eh_pasta, _ = self.fm_sel
        caminho = juntar(self.fm_path, nome)
        so_nome = legivel(nome.rsplit("/", 1)[-1])
        aviso = ("A pasta e tudo que está dentro dela serão apagados do PS3. Isso não pode ser desfeito."
                 if eh_pasta else "O arquivo será apagado do PS3. Isso não pode ser desfeito.")
        self.dialogo(f"Apagar “{so_nome}”?", aviso, "Apagar", perigo=True,
                     acao=lambda: self._fm_operacao("Apagando…", lambda ftp: apagar_remoto(ftp, caminho, eh_pasta),
                                                    f"“{so_nome}” foi apagado."))

    def fm_baixar(self):
        if not self.fm_sel or self.op_ativa:
            return
        nome, eh_pasta, tam = self.fm_sel
        destino = filedialog.askdirectory(title="Salvar no PC em…", parent=self.root)
        if not destino:
            return
        remoto = juntar(self.fm_path, nome)
        local = os.path.join(destino, legivel(nome.rsplit("/", 1)[-1]))
        prog = self._progresso_ui("Baixando…", None if eh_pasta else (tam or 1))
        self._fm_operacao("Baixando…", lambda ftp: baixar_remoto(ftp, remoto, eh_pasta, local, prog),
                          f"Salvo em {local}", recarregar=False)

    def fm_editar(self):
        if not self.fm_sel or self.op_ativa:
            return
        nome = self.fm_sel[0]
        caminho = juntar(self.fm_path, nome)
        self.fm_status("Abrindo…")

        def ok(res):
            self.fm_status("")
            self._abrir_editor(caminho, *res)
        self.em_thread(lambda ftp: ler_texto_remoto(ftp, caminho), ok,
                       lambda e: self.fm_status(f"Não consegui abrir o arquivo ({str(e)[:60]})", "#F87171"))

    def _abrir_editor(self, caminho, texto, cod):
        j = self._janela(f"Editando {legivel(os.path.basename(caminho))}", 760, 560)
        fonte = ctk.CTkFont(family=F_REG, size=13)
        ctk.CTkLabel(j, text=legivel(os.path.basename(caminho)), font=ctk.CTkFont(family=F_LIGHT, size=22),
                     text_color=BRANCO).pack(anchor="w", padx=24, pady=(18, 0))
        ctk.CTkLabel(j, text=legivel(caminho), font=fonte, text_color=CINZA).pack(anchor="w", padx=24)
        so_leitura = protegido(caminho)
        if so_leitura:
            ctk.CTkLabel(j, text="Arquivo do sistema: aberto só para leitura.", font=fonte,
                         text_color="#FBBF24").pack(anchor="w", padx=24, pady=(4, 0))
        elif "boot_plugins" in caminho.lower():
            ctk.CTkLabel(j, text="Cuidado: uma linha errada aqui pode travar o HEN ao ligar o PS3.", font=fonte,
                         text_color="#FBBF24").pack(anchor="w", padx=24, pady=(4, 0))
        caixa = ctk.CTkTextbox(j, font=ctk.CTkFont(family="Consolas" if WIN else "DejaVu Sans Mono", size=13),
                               fg_color="#0A1222", border_color="#1E2A44", border_width=1, corner_radius=12,
                               text_color="#E5ECF8", wrap="none", undo=True)
        caixa.pack(fill="both", expand=True, padx=24, pady=12)
        caixa.insert("1.0", texto)
        if so_leitura:
            caixa.configure(state="disabled")
        rod = ctk.CTkFrame(j, fg_color="transparent")
        rod.pack(fill="x", padx=24, pady=(0, 18))
        status = ctk.CTkLabel(rod, text="", font=fonte, text_color=CINZA)
        status.pack(side="left")

        def salvar():
            novo = caixa.get("1.0", "end-1c")
            btn.configure(state="disabled")
            status.configure(text="Salvando no PS3…", text_color=CINZA)

            def ok(_):
                if j.winfo_exists():
                    status.configure(text="Salvo no PS3 ✓", text_color="#34D399")
                    btn.configure(state="normal")

            def erro(e):
                if j.winfo_exists():
                    status.configure(text=f"Erro ao salvar: {str(e)[:60]}", text_color="#F87171")
                    btn.configure(state="normal")
            self.em_thread(lambda ftp: gravar_texto_remoto(ftp, caminho, novo, cod), ok, erro)

        btn = ctk.CTkButton(rod, text="Salvar no PS3", height=38, width=150, corner_radius=19, fg_color="#0070D1",
                            hover_color="#1888F0", font=ctk.CTkFont(family=F_SEMI, size=14), command=salvar,
                            state="disabled" if so_leitura else "normal")
        btn.pack(side="right")
        ctk.CTkButton(rod, text="Fechar", height=38, width=110, corner_radius=19, fg_color="transparent",
                      border_width=1, border_color="#3A4660", hover_color="#1A2744", font=fonte,
                      command=j.destroy).pack(side="right", padx=(0, 10))
        j.bind("<Control-s>", lambda e: salvar() if not so_leitura else None)

    # ================================================= aba LICENÇAS RAP
    def tela_rap(self):
        self.limpar()
        p, c = self.p, self.c
        if not self.raps:
            c.create_text(p.px(W / 2), p.px(160), text="Envie suas licenças para o PS3", fill=BRANCO,
                          font=(F_LIGHT, -p.px(26)), tags="view")
            c.create_text(p.px(W / 2), p.px(194), text="Os arquivos .rap vão direto para a pasta exdata do console.",
                          fill=CINZA, font=(F_REG, -p.px(14)), tags="view")
            Cartao(self, W / 2, 360, 340, 230, "chave", "Escolher arquivos .rap", "Pode escolher vários de uma vez",
                   self.add_raps)
            self.tx_rap_info = c.create_text(p.px(W / 2), p.px(510), text="", fill=CINZA_ESCURO,
                                             font=(F_REG, -p.px(13)), tags="view")
            self._contar_raps()
            return
        validos = [r for r in self.raps if r["ok"]]
        n = len(self.raps)
        c.create_text(p.px(W / 2), p.px(150), text="Licenças prontas para enviar", fill=BRANCO,
                      font=(F_LIGHT, -p.px(26)), tags="view")
        sub = f"{len(validos)} {'licença' if len(validos) == 1 else 'licenças'} → /dev_hdd0/exdata"
        if len(validos) < n:
            sub += f"   •   {n - len(validos)} arquivo(s) inválido(s) serão ignorados"
        c.create_text(p.px(W / 2), p.px(182), text=sub, fill=CINZA, font=(F_REG, -p.px(14)), tags="view")
        lw, lh, y0 = 620, 50, 228
        linha = p.ret(lw, lh, 14, (255, 255, 255, 13), outline=(255, 255, 255, 30), largura=1)
        for i, r in enumerate(self.raps[:5]):
            y = y0 + i * (lh + 8)
            c.create_image(p.px(W / 2), p.px(y), image=linha, tags="view")
            nome = r["nome"] if len(r["nome"]) <= 52 else r["nome"][:50] + "…"
            c.create_text(p.px(W / 2 - lw / 2 + 22), p.px(y), anchor="w", text=nome, fill=BRANCO,
                          font=(F_REG, -p.px(14)), tags="view")
            c.create_text(p.px(W / 2 + lw / 2 - 64), p.px(y), anchor="e", tags="view",
                          text="Licença" if r["ok"] else "Inválido", fill=CINZA if r["ok"] else "#F87171",
                          font=(F_REG, -p.px(12)))
            tg = f"rmr{i}"
            c.create_text(p.px(W / 2 + lw / 2 - 30), p.px(y), text="✕", fill=CINZA,
                          font=(F_SYM, -p.px(14)), tags=("view", tg))
            c.tag_bind(tg, "<Enter>", lambda e, t=tg: (c.itemconfig(t, fill=BRANCO), c.config(cursor="hand2")))
            c.tag_bind(tg, "<Leave>", lambda e, t=tg: (c.itemconfig(t, fill=CINZA), c.config(cursor="")))
            c.tag_bind(tg, "<Button-1>", lambda e, k=i: (c.config(cursor=""), self.remover_rap(k)))
        if n > 5:
            c.create_text(p.px(W / 2), p.px(y0 + 5 * (lh + 8) - 4), text=f"+ {n - 5} outras", fill=CINZA,
                          font=(F_REG, -p.px(13)), tags="view")
        yb = 530
        x_esq = W / 2 - 310
        Botao(self, x_esq + 80, yb, 160, 48, "+ Adicionar", self.add_raps, "secundario")
        Botao(self, x_esq + 80 + 172, yb, 160, 48, "Limpar", self.limpar_raps, "secundario")
        self.btn_enviar = Botao(self, W / 2 + 310 - 120, yb, 240, 54, "Enviar licenças", self.enviar_raps,
                                tamanho_fonte=16)
        self.btn_enviar.set_ativo(self.estado_ps3 == "ok" and bool(validos))

    def _contar_raps(self):
        if self.estado_ps3 != "ok":
            return

        def ok(itens):
            if self.aba == "rap" and not self.raps:
                n = sum(1 for nome, d, _ in itens if not d and nome.lower().endswith(".rap"))
                try:
                    self.c.itemconfig(self.tx_rap_info, text=f"No PS3: {n} {'licença' if n == 1 else 'licenças'} "
                                                             f"na pasta exdata")
                except tk.TclError:
                    pass
        self.em_thread(lambda ftp: listar_remoto(ftp, "/dev_hdd0/exdata"), ok, lambda e: None)

    def add_raps(self):
        arqs = filedialog.askopenfilenames(title="Escolha os arquivos .rap", parent=self.root,
                                           filetypes=[("Licenças RAP", "*.rap *.RAP"), ("Todos", "*.*")])
        for a in arqs:
            if any(os.path.normpath(r["item"]) == os.path.normpath(a) for r in self.raps):
                continue
            ok = a.lower().endswith(".rap") and os.path.getsize(a) == 16
            self.raps.append({"item": a, "nome": os.path.basename(a), "ok": ok})
        if arqs:
            self.tela_rap()

    def remover_rap(self, k):
        if 0 <= k < len(self.raps):
            self.raps.pop(k)
        self.tela_rap()

    def limpar_raps(self):
        self.raps = []
        self.tela_rap()

    def enviar_raps(self):
        validos = [r for r in self.raps if r["ok"]]
        if not validos or self.op_ativa:
            return
        self.op_ativa = True
        if self.btn_enviar:
            self.btn_enviar.set_ativo(False)
            self.btn_enviar.set_texto("Enviando…")

        def trabalho(ftp):
            try:
                ftp.mkd("/dev_hdd0/exdata")
            except ftplib.error_perm:
                pass
            for r in validos:
                with open(r["item"], "rb") as f:
                    ftp.storbinary(f"STOR /dev_hdd0/exdata/{para_ftp(r['nome'])}", f)
            return len(validos)

        def ok(n):
            self.raps = []
            self.tela_final(True, "Licenças enviadas!",
                            f"{n} {'arquivo copiado' if n == 1 else 'arquivos copiados'} para a pasta exdata.",
                            "Reinicie o PS3 e ative o HEN para as licenças serem reconhecidas.",
                            acao_ok=self.tela_rap, texto_ok="Enviar mais licenças")

        def erro(e):
            titulo, sub = mensagem_erro(e)
            self.tela_final(False, titulo, sub, f"Detalhe: {str(e)[:120]}",
                            acao_tentar=self.enviar_raps, acao_voltar=self.tela_rap)

        def fim():
            self.op_ativa = False
        self.em_thread(trabalho, ok, erro, fim)


# =============================================================== Console: energia, plugins, controle
XPAD_DIR = "/dev_hdd0/plugins/ps3xpad"
XPAD_VSH = XPAD_DIR + "/xpad_vsh_autodiscovery.sprx"
XPAD_API = "https://api.github.com/repos/GabaRSk/XPAD-Revolution/releases/latest"
XPAD_ZIP_PADRAO = "https://github.com/GabaRSk/XPAD-Revolution/releases/latest/download/XPAD-Revolution-v1.0.0.zip"
SLOTS_VSH = range(0, 7)


def http_webman(ip, caminho, timeout=6):
    """Chama um comando web do webMAN MOD e devolve o texto da resposta."""
    with urllib.request.urlopen(f"http://{ip}/{caminho}", timeout=timeout) as r:
        return r.read(64 * 1024).decode("latin-1", "ignore")


def comando_energia(ip, acao):
    """restart.ps3 / shutdown.ps3 — o console pode cortar a conexão antes de responder."""
    try:
        http_webman(ip, f"{acao}.ps3")
    except (ConnectionResetError, socket.timeout, TimeoutError):
        pass
    except OSError as e:
        if "reset" not in str(e).lower() and "timed out" not in str(e).lower():
            raise
    return True


def _url_caminho(caminho):
    import urllib.parse
    return urllib.parse.quote(caminho, safe="/")


def plugins_ativos(ip):
    """Pergunta ao webMAN (PS3MAPI) o que está carregado em cada slot.
    Devolve {caminho: slot}, ou None se o console não informar."""
    import re
    ativos, respondeu = {}, False
    for slot in SLOTS_VSH:
        try:
            txt = http_webman(ip, f"ps3mapi.ps3?MODULE%20GETVSHPLUGINFO%20{slot}", timeout=4)
        except OSError:
            continue
        respondeu = True
        m = re.search(r"(/dev_[^\"'<>\s,]+?\.sprx)", txt, re.I)
        if m:
            ativos[m.group(1)] = slot
    return ativos if respondeu else None


def _carregar_no_slot(ip, caminho, slot):
    """Carrega o .sprx num slot. Usa o comando que existe em todas as versões do webMAN MOD
    (/loadprx.ps3) e, se o console recusar, o painel do PS3MAPI."""
    prx = _url_caminho(caminho)
    try:
        http_webman(ip, f"loadprx.ps3?slot={slot}&prx={prx}", timeout=20)
    except (socket.timeout, TimeoutError, urllib.error.URLError) as e:
        if isinstance(e, urllib.error.HTTPError):
            raise
        if isinstance(e, urllib.error.URLError) and not isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise
        # o webMAN só responde depois que o plugin termina de iniciar, e alguns (como o XPAD) demoram:
        # em vez de dar erro, confere se ele já está carregado
        if _esperar_plugin(ip, caminho, 25) is False:
            raise RuntimeError("O PS3 não respondeu a tempo e o plugin não apareceu como ativo. "
                               "Espere uns segundos e clique em ⟳ Atualizar para conferir.") from None
    except urllib.error.HTTPError as e:
        if e.code not in (400, 404, 501):
            raise
        try:
            http_webman(ip, f"vshplugin.ps3mapi?load_slot={slot}&prx={prx}")
        except urllib.error.HTTPError:
            raise RuntimeError("O webMAN MOD do seu PS3 não aceitou o comando para carregar plugins. "
                               "Atualize o webMAN MOD e tente de novo.") from None


def _esperar_plugin(ip, caminho, segundos):
    """Fica perguntando ao PS3 se o plugin já está carregado.
    True = está; False = o PS3 respondeu e ele não está; None = o PS3 não respondeu nada."""
    fim, respondeu = time.time() + segundos, False
    while time.time() < fim:
        ativos = plugins_ativos(ip)      # None enquanto o webMAN ainda está ocupado
        if ativos is not None:
            respondeu = True
            if caminho in ativos:
                return True
        time.sleep(2)
    return False if respondeu else None


def ativar_plugin(ip, caminho, ocupados):
    """Carrega o plugin só nesta sessão (some ao reiniciar). Não mexe no boot_plugins.txt."""
    livres = [s for s in range(6, 0, -1) if s not in set((ocupados or {}).values())]
    if ocupados is not None and not livres:
        raise RuntimeError("Todos os espaços de plugin do PS3 estão ocupados. Desative algum antes.")
    slot = livres[0] if ocupados is not None else 6
    _carregar_no_slot(ip, caminho, slot)
    return slot


def desativar_plugin(ip, caminho, slot):
    try:
        if slot is not None:
            http_webman(ip, f"unloadprx.ps3?slot={slot}")
        else:
            http_webman(ip, f"unloadprx.ps3{_url_caminho(caminho)}")      # /unloadprx.ps3/dev_hdd0/...
    except urllib.error.HTTPError as e:
        if e.code not in (400, 404, 501) or slot is None:
            raise
        http_webman(ip, f"vshplugin.ps3mapi?unload_slot={slot}")


def trava_plugin(caminho):
    c = caminho.lower()
    if "webftp_server" in c or "webman" in c:
        return "Necessário para este app (webMAN)"
    if c.endswith("xpad_game.sprx"):
        return "Carrega dentro do jogo com SELECT + L3 + R3"
    return None


def procurar_sprx(ftp):
    achados = []
    try:
        nivel1 = listar_remoto(ftp, "/dev_hdd0/plugins")
    except ftplib.all_errors:
        return achados
    for nome, d, _ in nivel1:
        caminho = juntar("/dev_hdd0/plugins", nome)
        if d:
            try:
                for n2, d2, _ in listar_remoto(ftp, caminho):
                    if not d2 and n2.lower().endswith(".sprx"):
                        achados.append(juntar(caminho, n2))
            except ftplib.all_errors:
                pass
        elif nome.lower().endswith(".sprx"):
            achados.append(caminho)
    return achados


def existe_remoto(ftp, caminho):
    return tamanho_remoto(ftp, caminho) is not None


def ler_analog(ftp):
    import re
    try:
        texto, _ = ler_texto_remoto(ftp, XPAD_DIR + "/xpad_analog.txt")
    except ftplib.error_perm:
        return None

    def valor(chave, padrao):
        m = re.search(rf"^\s*{chave}\s*=\s*(\d+)", texto, re.M)
        return int(m.group(1)) if m else padrao
    return {"sat": valor("ANALOG_SATURATION", 80), "dz": valor("ANALOG_DEADZONE", 4)}


def gravar_analog(ftp, sat, dz):
    import re
    caminho = XPAD_DIR + "/xpad_analog.txt"
    try:
        texto, cod = ler_texto_remoto(ftp, caminho)
    except ftplib.error_perm:
        texto, cod = "", "utf-8"
    for chave, v in (("ANALOG_SATURATION", sat), ("ANALOG_DEADZONE", dz)):
        if re.search(rf"^\s*{chave}\s*=", texto, re.M):
            texto = re.sub(rf"^(\s*{chave}\s*=\s*).*$", rf"\g<1>{v}", texto, count=1, flags=re.M)
        else:
            texto = texto.rstrip("\n") + f"\n{chave} = {v}\n"
    gravar_texto_remoto(ftp, caminho, texto, cod)


def baixar_xpad_zip():
    """Baixa o ZIP mais recente do XPAD Revolution (GitHub) e devolve os bytes."""
    import urllib.request
    cab = {"User-Agent": "PSTudo"}
    url = XPAD_ZIP_PADRAO
    try:
        with urllib.request.urlopen(urllib.request.Request(XPAD_API, headers=cab), timeout=15) as r:
            dados = json.load(r)
        for a in dados.get("assets", []):
            if a.get("name", "").lower().endswith(".zip"):
                url = a["browser_download_url"]
                break
    except Exception:
        pass
    with urllib.request.urlopen(urllib.request.Request(url, headers=cab), timeout=60) as r:
        return r.read()


def abrir_xpad_zip(dados):
    """Valida o ZIP e devolve ({nome: bytes}, versão)."""
    import hashlib
    import io
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(dados))
    arquivos = {}
    for info in z.infolist():
        partes = info.filename.replace("\\", "/").split("/")
        if len(partes) >= 2 and partes[-2] == "ps3xpad" and partes[-1] and not info.is_dir():
            arquivos[partes[-1]] = z.read(info)
    if "xpad_vsh_autodiscovery.sprx" not in arquivos:
        raise ValueError("Esse ZIP não parece ser do XPAD Revolution.")
    nomes = {i.filename.split("/")[-1].upper(): i for i in z.infolist()}
    if "SHA256SUMS.TXT" in nomes:
        for linha in z.read(nomes["SHA256SUMS.TXT"]).decode("utf-8", "ignore").splitlines():
            partes = linha.split()
            if len(partes) == 2:
                nome = partes[1].split("/")[-1]
                if nome in arquivos and hashlib.sha256(arquivos[nome]).hexdigest().lower() != partes[0].lower():
                    raise ValueError(f"O arquivo {nome} do ZIP está corrompido. Baixe de novo.")
    versao = ""
    if "VERSION.TXT" in nomes:
        versao = z.read(nomes["VERSION.TXT"]).decode("utf-8", "ignore").splitlines()[0].strip()
    return arquivos, versao


def instalar_xpad(ftp, arquivos):
    """Copia os arquivos para o PS3. Não altera o boot_plugins.txt."""
    import io
    for d in ("/dev_hdd0/plugins", XPAD_DIR):
        try:
            ftp.mkd(d)
        except ftplib.error_perm:
            pass
    mantidos = []
    for nome, dados in arquivos.items():
        remoto = f"{XPAD_DIR}/{nome}"
        if nome.lower().endswith(".txt") and existe_remoto(ftp, remoto):
            mantidos.append(nome)  # preserva as configurações do usuário
            continue
        ftp.storbinary(f"STOR {remoto}", io.BytesIO(dados))
    return mantidos


# =============================================================== controles do PC -> xpad_devices.txt
XPAD_DEVICES = XPAD_DIR + "/xpad_devices.txt"
LIMITE_DEVICES = 24
TIPOS_PAD = {"XTYPE_XBOX360": "Xbox 360 / XInput", "PTYPE_PS4": "DualShock 4", "PTYPE_PS5": "DualSense",
             "XTYPE_XBOX360W": "Receptor sem fio Xbox 360"}
SONY_PS4 = {0x05C4, 0x09CC, 0x0BA0}
SONY_PS5 = {0x0CE6, 0x0DF2}
XBOX_ONE = {0x02D1, 0x02DD, 0x02E3, 0x02EA, 0x0B00, 0x0B12, 0x0B13, 0x0B20, 0x0B22}
NOMES_GAME = ("game controller", "gamepad", "controlador de jogo", "controle de jogo", "controlador de juego",
              "joystick", "xbox", "controller")
CABECALHO_DEVICES = ("# Add your custom controller VID/PIDs here, one line per device.\n"
                     "# Format: VID, PID, NAME, XTYPE   ('#' starts a comment anywhere)\n")


def _joysticks_winmm():
    """Joysticks conectados segundo a API do Windows (winmm). Lista de (vid, pid, nome)."""
    import ctypes
    from ctypes import wintypes

    class JOYCAPSW(ctypes.Structure):
        _fields_ = [("wMid", wintypes.WORD), ("wPid", wintypes.WORD), ("szPname", wintypes.WCHAR * 32),
                    ("wXmin", wintypes.UINT), ("wXmax", wintypes.UINT), ("wYmin", wintypes.UINT),
                    ("wYmax", wintypes.UINT), ("wZmin", wintypes.UINT), ("wZmax", wintypes.UINT),
                    ("wNumButtons", wintypes.UINT), ("wPeriodMin", wintypes.UINT), ("wPeriodMax", wintypes.UINT),
                    ("wRmin", wintypes.UINT), ("wRmax", wintypes.UINT), ("wUmin", wintypes.UINT),
                    ("wUmax", wintypes.UINT), ("wVmin", wintypes.UINT), ("wVmax", wintypes.UINT),
                    ("wCaps", wintypes.UINT), ("wMaxAxes", wintypes.UINT), ("wNumAxes", wintypes.UINT),
                    ("wMaxButtons", wintypes.UINT), ("szRegKey", wintypes.WCHAR * 32),
                    ("szOEMVxD", wintypes.WCHAR * 260)]

    class JOYINFOEX(ctypes.Structure):
        _fields_ = [(n, wintypes.DWORD) for n in ("dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos",
                                                   "dwUpos", "dwVpos", "dwButtons", "dwButtonNumber", "dwPOV",
                                                   "dwReserved1", "dwReserved2")]
    winmm = ctypes.WinDLL("winmm")
    achados = []
    for i in range(16):
        info = JOYINFOEX(dwSize=ctypes.sizeof(JOYINFOEX), dwFlags=0xFF)
        if winmm.joyGetPosEx(i, ctypes.byref(info)) != 0:
            continue  # vazio ou desconectado
        caps = JOYCAPSW()
        if winmm.joyGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            achados.append((caps.wMid, caps.wPid, caps.szPname.strip()))
    return achados


def _nome_oem(vid, pid):
    import winreg
    chave = (r"System\CurrentControlSet\Control\MediaProperties\PrivateProperties\Joystick\OEM"
             rf"\VID_{vid:04X}&PID_{pid:04X}")
    for raiz in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(raiz, chave) as k:
                nome = winreg.QueryValueEx(k, "OEMName")[0].strip()
                if nome:
                    return nome
        except OSError:
            continue
    return None


def _dispositivos_pnp():
    """Dispositivos HID/XInput conectados (nome, id, classe) via PowerShell."""
    import subprocess
    cmd = ("Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in 'HIDClass','XnaComposite',"
           "'XboxComposite' -and $_.Status -eq 'OK' } | Select-Object Name,DeviceID,PNPClass | "
           "ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True,
                       timeout=25, creationflags=0x08000000)  # CREATE_NO_WINDOW
    saida = r.stdout.decode("utf-8", "ignore").strip()
    if not saida:
        return []
    dados = json.loads(saida)
    return dados if isinstance(dados, list) else [dados]


def classificar_pad(vid, pid, xinput):
    """Devolve (tipo, aviso). tipo None = não dá para registrar."""
    if vid == 0x054C and pid in SONY_PS4:
        return "PTYPE_PS4", None
    if vid == 0x054C and pid in SONY_PS5:
        return "PTYPE_PS5", None
    if vid == 0x045E and pid in (0x0291, 0x0719):
        return "XTYPE_XBOX360W", None
    if vid == 0x045E and pid in XBOX_ONE:
        return None, "Controle de Xbox One/Series ainda não é suportado pelo XPAD."
    if xinput:
        return "XTYPE_XBOX360", None
    return "XTYPE_XBOX360", "Parece estar no modo DInput. Troque para XInput e procure de novo."


def limpar_nome(nome):
    nome = " ".join(nome.replace(",", " ").replace("#", " ").split())
    return nome[:40] or "Controle"


def detectar_controles():
    """Procura controles conectados ao PC. Lista de dicts: vid, pid, nome, tipo, aviso."""
    import re
    if not WIN:
        return []
    pads = {}
    try:
        for vid, pid, nome in _joysticks_winmm():
            pads[(vid, pid)] = {"nomes": [nome], "xinput": False, "joy": True}
    except Exception:
        pass
    try:
        pnp = _dispositivos_pnp()
    except Exception:
        pnp = []
    for d in pnp:
        dev_id = (d.get("DeviceID") or "").upper()
        m = re.search(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", dev_id)
        if not m:
            continue
        chave = (int(m.group(1), 16), int(m.group(2), 16))
        nome = d.get("Name") or ""
        xin = "&IG_" in dev_id or d.get("PNPClass") in ("XnaComposite", "XboxComposite")
        parece_jogo = any(k in nome.lower() for k in NOMES_GAME)
        if chave in pads:
            pads[chave]["xinput"] |= xin
            pads[chave]["nomes"].append(nome)
        elif xin or parece_jogo:
            pads[chave] = {"nomes": [nome], "xinput": xin, "joy": False}
    resultado = []
    for (vid, pid), info in sorted(pads.items()):
        tipo, aviso = classificar_pad(vid, pid, info["xinput"])
        genericos = ("hid", "compatível", "compliant", "dispositivo", "device")
        candidatos = [_nome_oem(vid, pid)] + info["nomes"]
        bons = [n for n in candidatos if n and not any(g in n.lower() for g in genericos)]
        nome = limpar_nome((bons or [n for n in candidatos if n] or ["Controle"])[0])
        resultado.append({"vid": vid, "pid": pid, "nome": nome, "tipo": tipo, "aviso": aviso})
    return resultado


def ler_devices_txt(texto):
    """VID/PIDs já registrados (linhas não comentadas)."""
    registrados = set()
    for linha in texto.splitlines():
        linha = linha.split("#", 1)[0].strip()
        partes = [p_.strip() for p_ in linha.split(",")]
        if len(partes) >= 4:
            try:
                registrados.add((int(partes[0], 16), int(partes[1], 16)))
            except ValueError:
                pass
    return registrados


def mesclar_devices(texto, novos):
    """Acrescenta controles novos. Devolve (texto_novo, adicionados, ja_existiam, sem_espaco)."""
    registrados = ler_devices_txt(texto)
    adicionados, ja, sem_espaco, linhas = [], [], [], []
    livres = LIMITE_DEVICES - len(registrados)
    for pad in novos:
        chave = (pad["vid"], pad["pid"])
        if chave in registrados:
            ja.append(pad)
            continue
        if livres <= 0:
            sem_espaco.append(pad)
            continue
        linhas.append(f"0x{pad['vid']:04x}, 0x{pad['pid']:04x}, {limpar_nome(pad['nome'])}, {pad['tipo']}")
        registrados.add(chave)
        adicionados.append(pad)
        livres -= 1
    if not texto.strip():
        texto = CABECALHO_DEVICES
    if linhas:
        texto = texto.rstrip("\n") + "\n# Adicionado pelo PSTudo\n" + "\n".join(linhas) + "\n"
    return texto, adicionados, ja, sem_espaco


def registrar_devices(ftp, novos):
    try:
        texto, cod = ler_texto_remoto(ftp, XPAD_DEVICES)
    except ftplib.error_perm:
        texto, cod = "", "utf-8"
    novo, adicionados, ja, sem = mesclar_devices(texto, novos)
    if adicionados:
        gravar_texto_remoto(ftp, XPAD_DEVICES, novo, cod)
    return adicionados, ja, sem


class Controles:
    def abrir_registro_controles(self):
        if self.op_ativa or self.estado_ps3 != "ok":
            return
        j = self._janela("Registrar controles", 600, 500)
        self._rc_janela = j
        f_tit = ctk.CTkFont(family=F_LIGHT, size=22)
        f_txt = ctk.CTkFont(family=F_REG, size=12)
        f_nome = ctk.CTkFont(family=F_SEMI, size=13)
        ctk.CTkLabel(j, text="Registrar controles do PC", font=f_tit, text_color=BRANCO).pack(
            anchor="w", padx=24, pady=(20, 2))
        ctk.CTkLabel(j, text="Ligue os controles neste PC (cabo ou receptor) e clique em Procurar. Os marcados "
                             "serão adicionados ao xpad_devices.txt do PS3.",
                     font=f_txt, text_color=CINZA, wraplength=550, justify="left").pack(anchor="w", padx=24)
        lista = ctk.CTkScrollableFrame(j, fg_color="#0A1222", corner_radius=12, height=250,
                                       scrollbar_button_color="#1E2A44")
        lista.pack(fill="both", expand=True, padx=24, pady=(12, 6))
        status = ctk.CTkLabel(j, text="", font=f_txt, text_color=CINZA, anchor="w", wraplength=550,
                              justify="left")
        status.pack(fill="x", padx=26)
        rod = ctk.CTkFrame(j, fg_color="transparent")
        rod.pack(fill="x", padx=24, pady=(6, 18))
        btn_reg = self._cn_btn(rod, "Registrar no PS3", lambda: registrar(), "azul", 150, 38)
        btn_reg.pack(side="right")
        btn_proc = self._cn_btn(rod, "Procurar", lambda: procurar(), "normal", 110, 38)
        btn_proc.pack(side="right", padx=(0, 10))
        linhas = []

        def mostrar(pads):
            if not j.winfo_exists():
                return
            for w_ in lista.winfo_children():
                w_.destroy()
            linhas.clear()
            btn_proc.configure(state="normal")
            if not pads:
                ctk.CTkLabel(lista, text="Nenhum controle encontrado.\nConecte o controle no PC e clique em Procurar.",
                             font=f_txt, text_color=CINZA).pack(pady=40)
                status.configure(text="")
                btn_reg.configure(state="disabled")
                return
            for pad in pads:
                fr = ctk.CTkFrame(lista, fg_color="#0F1A30", corner_radius=10)
                fr.pack(fill="x", pady=3, padx=(0, 4))
                var = tk.BooleanVar(value=pad["tipo"] is not None and pad["aviso"] is None)
                tipo = None
                if pad["tipo"]:
                    tipo = ctk.CTkOptionMenu(fr, values=list(TIPOS_PAD.values()), width=190, height=30,
                                             corner_radius=8, fg_color="#16233F", button_color="#1A2744",
                                             button_hover_color="#24365C", font=f_txt, dynamic_resizing=False)
                    tipo.set(TIPOS_PAD[pad["tipo"]])
                    tipo.pack(side="right", padx=10)
                esq = ctk.CTkFrame(fr, fg_color="transparent")
                esq.pack(side="left", fill="x", expand=True, padx=10, pady=8)
                cb = ctk.CTkCheckBox(esq, text=pad["nome"], variable=var, font=f_nome, text_color=BRANCO,
                                     fg_color="#0070D1", hover_color="#1888F0", border_color="#3A4660",
                                     checkbox_width=20, checkbox_height=20)
                cb.pack(anchor="w")
                info = f"{pad['vid']:04X}:{pad['pid']:04X}"
                if pad["aviso"]:
                    info += "  •  " + pad["aviso"]
                ctk.CTkLabel(esq, text=info, font=f_txt, text_color="#FBBF24" if pad["aviso"] else CINZA_ESCURO,
                             anchor="w", wraplength=290, justify="left").pack(anchor="w", padx=(28, 0))
                if not pad["tipo"]:
                    cb.configure(state="disabled")
                linhas.append((pad, var, tipo))
            n = len(pads)
            status.configure(text=f"{n} controle(s) encontrado(s).", text_color=CINZA)
            btn_reg.configure(state="normal")

        def procurar():
            btn_proc.configure(state="disabled")
            btn_reg.configure(state="disabled")
            status.configure(text="Procurando controles…", text_color=CINZA)

            def tarefa():
                try:
                    pads = detectar_controles()
                except Exception:
                    pads = []
                self.fila.put(("cb", lambda: mostrar(pads)))
            threading.Thread(target=tarefa, daemon=True).start()

        def registrar():
            escolhidos = []
            inverso = {v: k for k, v in TIPOS_PAD.items()}
            for pad, var, tipo in linhas:
                if var.get() and tipo is not None:
                    escolhidos.append(dict(pad, tipo=inverso[tipo.get()]))
            if not escolhidos:
                status.configure(text="Marque pelo menos um controle.", text_color="#FBBF24")
                return
            btn_reg.configure(state="disabled")
            status.configure(text="Gravando no PS3…", text_color=CINZA)

            def ok(res):
                if not j.winfo_exists():
                    return
                adicionados, ja, sem = res
                partes = []
                if adicionados:
                    partes.append(f"{len(adicionados)} registrado(s)")
                if ja:
                    partes.append(f"{len(ja)} já estava(m) na lista")
                if sem:
                    partes.append(f"{len(sem)} sem espaço (limite de {LIMITE_DEVICES})")
                txt = ", ".join(partes) + "."
                if adicionados:
                    txt += " Reative o XPAD (ou reinicie o PS3) para o controle ser reconhecido."
                status.configure(text=txt, text_color="#34D399" if adicionados else "#FBBF24")
                btn_reg.configure(state="normal")
                if adicionados:
                    self._rc_oferecer_recarga(rod)

            def erro(e):
                if j.winfo_exists():
                    status.configure(text=f"Não consegui gravar ({str(e)[:60]})", text_color="#F87171")
                    btn_reg.configure(state="normal")
            self.em_thread(lambda ftp: registrar_devices(ftp, escolhidos), ok, erro)

        procurar()

    def _rc_oferecer_recarga(self, rod):
        if getattr(self, "_rc_btn_recarga", None) and self._rc_btn_recarga.winfo_exists():
            return
        self._rc_btn_recarga = self._cn_btn(rod, "Reativar XPAD agora", self.recarregar_xpad, "normal", 170, 38)
        self._rc_btn_recarga.pack(side="left")

    def recarregar_xpad(self):
        """Desativa e ativa o XPAD nesta sessão para ele ler a lista nova."""
        ip = self.cfg.get("ip")
        if not hasattr(self, "cn_sessao"):
            self.cn_sessao = {}

        def tarefa():
            try:
                ativos = plugins_ativos(ip)
                slot = (ativos or {}).get(XPAD_VSH, self.cn_sessao.get(XPAD_VSH))
                if (ativos and XPAD_VSH in ativos) or XPAD_VSH in self.cn_sessao:
                    desativar_plugin(ip, XPAD_VSH, slot)
                    time.sleep(1.5)
                    ativos = plugins_ativos(ip)
                self.cn_sessao[XPAD_VSH] = ativar_plugin(ip, XPAD_VSH, ativos)
                msg, cor = "XPAD reativado. Espere a mensagem no PS3 e conecte o controle.", "#34D399"
            except Exception as e:
                msg, cor = f"Não consegui reativar ({str(e)[:50]})", "#F87171"
            self.fila.put(("cb", lambda: self.dialogo("Reativar XPAD", msg, cancelar=False)
                           if cor == "#F87171" else self._rc_status(msg)))
        threading.Thread(target=tarefa, daemon=True).start()

    def _rc_status(self, msg):
        self.dialogo("XPAD reativado", msg, cancelar=False)
        if self._cn_ativo():
            self.carregar_console()


CARD = "#0F1A30"


class Console:
    def _cn_btn(self, pai_, texto, cmd, tipo="normal", largura=0, altura=34):
        """Botão arredondado no estilo do app (usado nas janelas e painéis)."""
        cores = {"normal": (BTN, BTN_HOVER, BRANCO), "azul": ("#0070D1", "#1888F0", BRANCO),
                 "perigo": ("#3A1620", "#5A1E2C", "#FCA5A5")}[tipo]
        return ctk.CTkButton(pai_, text=texto, command=cmd, height=altura, corner_radius=altura // 2,
                             font=ctk.CTkFont(family=F_SEMI, size=13), width=largura, fg_color=cores[0],
                             hover_color=cores[1], text_color=cores[2], text_color_disabled=CINZA_ESCURO)

    def tela_console(self):
        self.limpar()
        p, c = self.p, self.c
        x0, y0, w, h = 48, 116, 864, 466
        c.create_image(p.px(x0 + w / 2), p.px(y0 + h / 2), tags="view",
                       image=p.ret(w, h, 20, PAINEL_RGB + (255,), outline=(255, 255, 255, 30), largura=1))
        painel = ctk.CTkFrame(self.root, fg_color=PAINEL, corner_radius=0, width=w - 28, height=h - 28)
        painel.grid_propagate(False)
        c.create_window(p.px(x0 + 14), p.px(y0 + 14), window=painel, anchor="nw", tags="view")
        self.widgets.append(painel)
        painel.grid_columnconfigure(0, minsize=330)
        painel.grid_columnconfigure(1, weight=1)
        painel.grid_rowconfigure(1, weight=1)

        f_tit = ctk.CTkFont(family=F_SEMI, size=15)
        f_txt = ctk.CTkFont(family=F_REG, size=12)
        f_btn = ctk.CTkFont(family=F_SEMI, size=13)

        def cartao(linha, coluna, rowspan=1, padx=(0, 0), pady=(0, 0)):
            fr = ctk.CTkFrame(painel, fg_color=CARD, corner_radius=14)
            fr.grid(row=linha, column=coluna, rowspan=rowspan, sticky="nsew", padx=padx, pady=pady)
            return fr

        def btn(pai_, texto, cmd, tipo="normal", largura=0, altura=34):
            cores = {"normal": (BTN, BTN_HOVER, BRANCO), "azul": ("#0070D1", "#1888F0", BRANCO),
                     "perigo": ("#3A1620", "#5A1E2C", "#FCA5A5")}[tipo]
            return ctk.CTkButton(pai_, text=texto, command=cmd, height=altura, corner_radius=altura // 2,
                                 font=f_btn, width=largura, fg_color=cores[0], hover_color=cores[1],
                                 text_color=cores[2], text_color_disabled=CINZA_ESCURO)

        # ---- Energia
        en = cartao(0, 0, pady=(0, 10))
        ctk.CTkLabel(en, text="Energia", font=f_tit, text_color=BRANCO).pack(anchor="w", padx=16, pady=(12, 0))
        ctk.CTkLabel(en, text="Controle o PS3 daqui mesmo.", font=f_txt, text_color=CINZA).pack(anchor="w", padx=16)
        lin = ctk.CTkFrame(en, fg_color="transparent")
        lin.pack(fill="x", padx=16, pady=(10, 14))
        self.cn_btn_reiniciar = btn(lin, "↻  Reiniciar", lambda: self.energia("restart"), largura=140)
        self.cn_btn_reiniciar.pack(side="left")
        self.cn_btn_desligar = btn(lin, "⏻  Desligar", lambda: self.energia("shutdown"), "perigo", 140)
        self.cn_btn_desligar.pack(side="left", padx=10)

        # ---- Controle (XPAD Revolution)
        ct = cartao(1, 0)
        ctk.CTkLabel(ct, text="Suporte a controles", font=f_tit, text_color=BRANCO).pack(anchor="w", padx=16,
                                                                                          pady=(12, 0))
        ctk.CTkLabel(ct, text="XPAD Revolution: use controles de Xbox, GameSir,\n8BitDo, DualShock 4 e outros no PS3.",
                     font=f_txt, text_color=CINZA, justify="left").pack(anchor="w", padx=16)
        self.cn_xpad_status = ctk.CTkLabel(ct, text="Verificando…", font=f_txt, text_color=CINZA, anchor="w")
        self.cn_xpad_status.pack(anchor="w", padx=16, pady=(6, 0))
        lin2 = ctk.CTkFrame(ct, fg_color="transparent")
        lin2.pack(fill="x", padx=16, pady=(6, 6))
        self.cn_btn_instalar = btn(lin2, "Instalar", lambda: self.instalar_controle(False), "azul", 150)
        self.cn_btn_instalar.pack(side="left")
        self.cn_btn_zip = btn(lin2, "Usar ZIP do PC", lambda: self.instalar_controle(True), largura=130)
        self.cn_btn_zip.pack(side="left", padx=10)

        def slider(rotulo, de, ate, fmt):
            topo = ctk.CTkFrame(ct, fg_color="transparent")
            topo.pack(fill="x", padx=16, pady=(6, 0))
            ctk.CTkLabel(topo, text=rotulo, font=f_txt, text_color=BRANCO).pack(side="left")
            val = ctk.CTkLabel(topo, text="", font=f_txt, text_color=CINZA)
            val.pack(side="right")
            s_ = ctk.CTkSlider(ct, from_=de, to=ate, number_of_steps=ate - de, height=16, button_color="#E5ECF8",
                               button_hover_color=BRANCO, progress_color="#0070D1", fg_color="#22304D",
                               command=lambda v: val.configure(text=fmt(int(round(v)))))
            s_.pack(fill="x", padx=12, pady=(2, 0))
            s_.mostrar = lambda: val.configure(text=fmt(int(round(s_.get()))))
            return s_, val
        self.cn_sat, self.cn_sat_val = slider("Alcance do analógico", 70, 100,
                                              lambda v: f"{v}" + ("  (parecido com DS3)" if v == 80 else
                                                                  "  (sem correção)" if v == 100 else ""))
        self.cn_dz, self.cn_dz_val = slider("Zona morta", 0, 10, lambda v: f"{v}%")
        lin3 = ctk.CTkFrame(ct, fg_color="transparent")
        lin3.pack(fill="x", padx=16, pady=(10, 12))
        self.cn_btn_analog = btn(lin3, "Salvar analógico", self.salvar_analogico, largura=136)
        self.cn_btn_analog.pack(side="left")
        self.cn_btn_registrar = btn(lin3, "Registrar controles", self.abrir_registro_controles, largura=150)
        self.cn_btn_registrar.pack(side="left", padx=10)

        # ---- Plugins (só nesta sessão)
        pl = cartao(0, 1, rowspan=2, padx=(10, 0))
        ctk.CTkLabel(pl, text="Plugins — só até reiniciar", font=f_tit, text_color=BRANCO).pack(
            anchor="w", padx=16, pady=(12, 0))
        ctk.CTkLabel(pl, text="Ative um plugin agora. Ao reiniciar o PS3 tudo volta ao normal: "
                              "o boot_plugins.txt não é alterado.",
                     font=f_txt, text_color=CINZA, wraplength=440, justify="left").pack(anchor="w", padx=16)
        self.cn_lista = ctk.CTkScrollableFrame(pl, fg_color=CARD, corner_radius=0, scrollbar_button_color="#1E2A44",
                                               scrollbar_button_hover_color="#2A3A5E")
        self.cn_lista.pack(fill="both", expand=True, padx=6, pady=(8, 0))
        rod = ctk.CTkFrame(pl, fg_color="transparent")
        rod.pack(fill="x", padx=16, pady=(8, 12))
        self.cn_status = ctk.CTkLabel(rod, text="", font=f_txt, text_color=CINZA, anchor="w")
        self.cn_status.pack(side="left", fill="x", expand=True)
        self.cn_btn_atualizar = btn(rod, "⟳  Atualizar", self.carregar_console, largura=120)
        self.cn_btn_atualizar.pack(side="right")

        self.cn_dados = None
        self.cn_plugins = []
        self._cn_botoes()
        self.carregar_console()

    def _cn_ativo(self):
        return self.aba == "console" and getattr(self, "cn_lista", None) is not None and self.cn_lista.winfo_exists()

    def _cn_botoes(self):
        if not self._cn_ativo():
            return
        on = self.estado_ps3 == "ok" and not self.op_ativa
        tem_dados = self.cn_dados is not None
        xpad = tem_dados and self.cn_dados["xpad"]
        for b in (self.cn_btn_reiniciar, self.cn_btn_desligar):
            b.configure(state="normal" if on and not self.enviando else "disabled")
        self.cn_btn_atualizar.configure(state="normal" if on else "disabled")
        self.cn_btn_instalar.configure(state="normal" if on and tem_dados else "disabled",
                                       text="Atualizar e ativar" if xpad else "Instalar e ativar")
        self.cn_btn_zip.configure(state="normal" if on and tem_dados else "disabled")
        self.cn_btn_registrar.configure(state="normal" if on and xpad else "disabled")
        tem_analog = tem_dados and self.cn_dados["analog"] is not None
        for w_ in (self.cn_sat, self.cn_dz, self.cn_btn_analog):
            w_.configure(state="normal" if on and tem_analog else "disabled")
        for item in self.cn_plugins:
            b = item.get("botao")
            if b is not None and b.winfo_exists():
                b.configure(state="normal" if on and not trava_plugin(item["caminho"]) else "disabled")

    def cn_msg(self, texto, cor=CINZA):
        if self._cn_ativo():
            self.cn_status.configure(text=texto, text_color=cor)

    def carregar_console(self):
        if not self._cn_ativo():
            return
        if self.estado_ps3 != "ok":
            self.cn_msg("Conecte o PS3 para ver os plugins.", "#FBBF24")
            self.cn_xpad_status.configure(text="PS3 desconectado", text_color="#FBBF24")
            return
        self.cn_msg("Lendo o console…")
        ip = self.cfg.get("ip")
        sessao = getattr(self, "cn_sessao", {})

        def trabalho(ftp):
            sprx = procurar_sprx(ftp)
            dados = {"sprx": sprx, "xpad": existe_remoto(ftp, XPAD_VSH), "analog": ler_analog(ftp)}
            dados["ativos"] = plugins_ativos(ip)
            return dados

        def ok(d):
            if not self._cn_ativo():
                return
            self.cn_dados = d
            ativos = d["ativos"]
            if ativos is None:  # o console não informa: usa o que este app ativou
                ativos = dict(sessao)
            self.cn_ativos = ativos
            todos = list(dict.fromkeys(list(ativos) + d["sprx"]))
            self.cn_plugins = [{"caminho": c_, "ativo": c_ in ativos, "slot": ativos.get(c_)} for c_ in todos]
            self._cn_desenhar_plugins()
            if d["xpad"]:
                ligado = XPAD_VSH in ativos
                self.cn_xpad_status.configure(text="✓ Instalado" + (" e ativo agora" if ligado else ""),
                                              text_color="#34D399")
            else:
                self.cn_xpad_status.configure(text="Não instalado", text_color=CINZA)
            if d["analog"]:
                self.cn_sat.set(max(70, min(100, d["analog"]["sat"])))
                self.cn_dz.set(max(0, min(10, d["analog"]["dz"])))
                self.cn_sat.mostrar()
                self.cn_dz.mostrar()
            n_on = sum(1 for i in self.cn_plugins if i["ativo"])
            aviso = "" if d["ativos"] is not None else "  (o PS3 não informa quais estão ativos)"
            self.cn_msg(f"{len(self.cn_plugins)} plugin(s) • {n_on} ativo(s){aviso}")
            self._cn_botoes()

        def erro(e):
            self.cn_msg(f"Não consegui ler o console ({str(e)[:60]})", "#F87171")
        self.em_thread(trabalho, ok, erro)

    def _cn_desenhar_plugins(self):
        for w_ in self.cn_lista.winfo_children():
            w_.destroy()
        f_nome = ctk.CTkFont(family=F_SEMI, size=13)
        f_cam = ctk.CTkFont(family=F_REG, size=11)
        if not self.cn_plugins:
            ctk.CTkLabel(self.cn_lista, text="Nenhum plugin encontrado em /dev_hdd0/plugins.", font=f_cam,
                         text_color=CINZA).pack(pady=20)
            return
        for item in self.cn_plugins:
            motivo = trava_plugin(item["caminho"])
            linha = ctk.CTkFrame(self.cn_lista, fg_color="#0B1426", corner_radius=10)
            linha.pack(fill="x", pady=3, padx=(0, 6))
            txt = ctk.CTkFrame(linha, fg_color="transparent")
            txt.pack(side="left", fill="x", expand=True, padx=12, pady=7)
            topo = ctk.CTkFrame(txt, fg_color="transparent")
            topo.pack(anchor="w")
            ctk.CTkLabel(topo, text=legivel(item["caminho"].rsplit("/", 1)[-1]), font=f_nome, text_color=BRANCO,
                         anchor="w").pack(side="left")
            if item["ativo"]:
                ctk.CTkLabel(topo, text="  ● ativo", font=f_cam, text_color="#34D399").pack(side="left")
            ctk.CTkLabel(txt, text=motivo or legivel(item["caminho"]), font=f_cam, anchor="w",
                         text_color="#FBBF24" if motivo else CINZA_ESCURO).pack(anchor="w")
            estilo = "normal" if motivo else ("perigo" if item["ativo"] else "azul")
            b = self._cn_btn(linha, "Desativar" if item["ativo"] else "Ativar",
                             lambda it=item: self.alternar_plugin(it), estilo, 104, 32)
            b.pack(side="right", padx=10)
            item["botao"] = b

    def alternar_plugin(self, item):
        if self.op_ativa or trava_plugin(item["caminho"]):
            return
        ip, caminho = self.cfg.get("ip"), item["caminho"]
        nome = legivel(caminho.rsplit("/", 1)[-1])
        ligar = not item["ativo"]
        ocupados = self.cn_dados["ativos"] if self.cn_dados else None
        self.op_ativa = True
        self._cn_botoes()
        self.cn_msg(("Ativando " + nome + "… alguns plugins levam até meio minuto") if ligar
                    else ("Desativando " + nome + "…"))
        if not hasattr(self, "cn_sessao"):
            self.cn_sessao = {}

        def trabalho():
            try:
                if ligar:
                    slot = ativar_plugin(ip, caminho, ocupados)
                    self.cn_sessao[caminho] = slot
                else:
                    desativar_plugin(ip, caminho, item.get("slot"))
                    self.cn_sessao.pop(caminho, None)
                try:
                    http_webman(ip, "popup.ps3/" + _url_caminho(
                        f"PSTudo: {nome} {'ativado' if ligar else 'desativado'}"), timeout=3)
                except OSError:
                    pass
                time.sleep(1.5)
                self.fila.put(("cb", lambda: self._plugin_ok(nome, ligar)))
            except Exception as e:
                self.fila.put(("cb", lambda e=e: self.cn_msg(f"Não deu certo: {str(e)[:70]}", "#F87171")))
            finally:
                self.fila.put(("cb", self._op_fim))
        threading.Thread(target=trabalho, daemon=True).start()

    def _plugin_ok(self, nome, ligar):
        self.carregar_console()
        self.root.after(900, lambda: self.cn_msg(f"{nome} {'ativado até reiniciar' if ligar else 'desativado'}.",
                                                 "#34D399"))

    # ---- controle
    def instalar_controle(self, do_pc):
        if self.op_ativa:
            return
        zip_local = None
        if do_pc:
            zip_local = filedialog.askopenfilename(title="ZIP do XPAD Revolution", parent=self.root,
                                                   filetypes=[("ZIP", "*.zip")])
            if not zip_local:
                return
        self.op_ativa = True
        self._cn_botoes()
        self.cn_xpad_status.configure(text="Baixando o XPAD Revolution…" if not do_pc else "Lendo o ZIP…",
                                      text_color=CINZA)
        ip = self.cfg.get("ip")
        ocupados = self.cn_dados["ativos"] if self.cn_dados else None
        if not hasattr(self, "cn_sessao"):
            self.cn_sessao = {}

        def trabalho():
            try:
                if zip_local:
                    with open(zip_local, "rb") as f:
                        dados = f.read()
                else:
                    dados = baixar_xpad_zip()
                arquivos, versao = abrir_xpad_zip(dados)
                self.fila.put(("cb", lambda: self.cn_xpad_status.configure(text="Enviando para o PS3…")
                               if self._cn_ativo() else None))
                ftp = conectar(self.cfg)
                try:
                    mantidos = instalar_xpad(ftp, arquivos)
                finally:
                    try:
                        ftp.quit()
                    except Exception:
                        ftp.close()
                ativo = False
                if ocupados is None or XPAD_VSH not in ocupados:
                    try:
                        self.cn_sessao[XPAD_VSH] = ativar_plugin(ip, XPAD_VSH, ocupados)
                        ativo = True
                    except Exception:
                        ativo = False
                else:
                    ativo = True
                self.fila.put(("cb", lambda: self._xpad_ok(versao, mantidos, ativo)))
            except Exception as e:
                msg = str(e)
                if "urlopen" in msg or "getaddrinfo" in msg or "HTTP Error" in msg:
                    msg = "Sem acesso ao GitHub. Baixe o ZIP no navegador e use “Usar ZIP do PC”."
                self.fila.put(("cb", lambda m=msg: self._xpad_erro(m)))
            finally:
                self.fila.put(("cb", self._op_fim))
        threading.Thread(target=trabalho, daemon=True).start()

    def _op_fim(self):
        self.op_ativa = False
        self._cn_botoes()

    def _xpad_ok(self, versao, mantidos, ativo):
        extra = " Suas configurações antigas foram mantidas." if mantidos else ""
        if ativo:
            txt = (f"{versao or 'XPAD Revolution'} foi instalado e ativado agora, só até reiniciar.{extra} "
                   "Espere uns 10 segundos pela mensagem “XPAD Rev Loaded!” e conecte o controle. "
                   "Dentro do jogo, segure SELECT + L3 + R3 se o controle precisar.")
        else:
            txt = (f"{versao or 'XPAD Revolution'} foi instalado.{extra} Não consegui ativá-lo agora; "
                   "use o botão Ativar na lista de plugins.")
        self.dialogo("Suporte a controles", txt, cancelar=False)
        self.carregar_console()

    def _xpad_erro(self, msg):
        if self._cn_ativo():
            self.cn_xpad_status.configure(text=msg[:90], text_color="#F87171")

    def salvar_analogico(self):
        if self.op_ativa:
            return
        sat, dz = int(round(self.cn_sat.get())), int(round(self.cn_dz.get()))
        self.op_ativa = True
        self._cn_botoes()
        self.cn_xpad_status.configure(text="Salvando ajustes…", text_color=CINZA)

        def ok(_):
            if self._cn_ativo():
                self.cn_xpad_status.configure(text="✓ Salvo. Desative e ative o XPAD para aplicar.",
                                              text_color="#34D399")

        def erro(e):
            self._xpad_erro(f"Não consegui salvar ({str(e)[:60]})")
        self.em_thread(lambda ftp: gravar_analog(ftp, sat, dz), ok, erro, self._op_fim)

    # ---- energia
    def energia(self, acao):
        if acao == "restart":
            self.dialogo("Reiniciar o PS3?", "O console vai reiniciar. Depois é preciso ativar o HEN de novo.",
                         "Reiniciar", lambda: self._energia_enviar("restart"))
        else:
            self.dialogo("Desligar o PS3?", "O console vai desligar. Para ligar de novo, use o botão do console "
                         "ou do controle.", "Desligar", lambda: self._energia_enviar("shutdown"), perigo=True)

    def _energia_enviar(self, acao):
        ip = self.cfg.get("ip")

        def trabalho():
            try:
                comando_energia(ip, acao)
                self.fila.put(("cb", lambda: self._energia_ok(acao)))
            except Exception as e:
                self.fila.put(("cb", lambda e=e: self.dialogo(
                    "Não deu certo", f"O webMAN não respondeu ao comando ({str(e)[:80]}).", cancelar=False)))
        threading.Thread(target=trabalho, daemon=True).start()

    def _energia_ok(self, acao):
        self.cn_sessao = {}
        self.atualizar_status("erro" if acao == "shutdown" else "busca")
        if self._cn_ativo():
            self.cn_msg("Reiniciando o PS3…" if acao == "restart" else "PS3 desligando…", "#FBBF24")
            self._cn_botoes()
        if acao == "restart":
            self.root.after(45000, self.buscar_ps3)


# =============================================================== Tela: espelhar a placa de captura
# =============================================================== tela cheia na placa de vídeo (OpenGL)
VS_TELA = """
#version 330
in vec2 pos;
out vec2 uv;
uniform vec4 caixa;   // x, y, largura, altura em coordenadas -1..1
uniform float inverter;   // 1 = imagem da placa (linhas de cima para baixo); 0 = textura já desenhada
void main() {
    uv = vec2(pos.x, mix(pos.y, 1.0 - pos.y, inverter));
    gl_Position = vec4(caixa.xy + pos * caixa.zw, 0.0, 1.0);
}
"""

FS_SIMPLES = """
#version 330
in vec2 uv;
out vec4 cor;
uniform sampler2D tex;
void main() { cor = vec4(texture(tex, uv).rgb, 1.0); }
"""

# Aumento de resolução Lanczos-2 com trava anti-halo (mesma ideia do EASU do FSR 1)
FS_LANCZOS = """
#version 330
in vec2 uv;
out vec4 cor;
uniform sampler2D tex;
uniform vec2 tam;      // tamanho da imagem de origem em pixels
float lz(float x) {
    x = abs(x);
    if (x < 1e-4) return 1.0;
    if (x >= 2.0) return 0.0;
    float px = 3.14159265 * x;
    return 2.0 * sin(px) * sin(px * 0.5) / (px * px);
}
void main() {
    vec2 p = uv * tam - 0.5;
    vec2 f = fract(p);
    vec2 base = (floor(p) + 0.5) / tam;
    vec3 soma = vec3(0.0); float pesos = 0.0;
    vec3 mn = vec3(1.0), mx = vec3(0.0);
    for (int j = -1; j <= 2; j++) {
        float wy = lz(float(j) - f.y);
        for (int i = -1; i <= 2; i++) {
            float w = lz(float(i) - f.x) * wy;
            vec3 c = texture(tex, base + vec2(i, j) / tam).rgb;
            soma += c * w; pesos += w;
            if (i >= 0 && i <= 1 && j >= 0 && j <= 1) { mn = min(mn, c); mx = max(mx, c); }
        }
    }
    cor = vec4(clamp(soma / pesos, mn, mx), 1.0);
}
"""

# RCAS adaptado do AMD FidelityFX FSR 1 (licença MIT, ver THIRD_PARTY_NOTICES.md): nitidez sem halos
FS_RCAS = """
#version 330
in vec2 uv;
out vec4 cor;
uniform sampler2D tex;
uniform vec2 texel;
uniform float nitidez;   // exp2(-stops); 1.0 = máximo
void main() {
    vec3 b = texture(tex, uv + vec2(0.0, -texel.y)).rgb;
    vec3 d = texture(tex, uv + vec2(-texel.x, 0.0)).rgb;
    vec3 e = texture(tex, uv).rgb;
    vec3 f = texture(tex, uv + vec2(texel.x, 0.0)).rgb;
    vec3 h = texture(tex, uv + vec2(0.0, texel.y)).rgb;
    vec3 mn4 = min(min(b, d), min(f, h));
    vec3 mx4 = max(max(b, d), max(f, h));
    vec3 hitMin = min(mn4, e) / (4.0 * mx4 + 1e-5);
    vec3 hitMax = (1.0 - max(mx4, e)) / (4.0 * min(mn4, e) - 4.0 - 1e-5);
    vec3 lobeRGB = max(-hitMin, hitMax);
    float lobe = max(-0.1875, min(max(lobeRGB.r, max(lobeRGB.g, lobeRGB.b)), 0.0)) * nitidez;
    cor = vec4((lobe * (b + d + f + h) + e) / (4.0 * lobe + 1.0), 1.0);
}
"""


# Quadro intermediário (fluxo nos dois sentidos, aproximação Super SloMo, checagem ida-e-volta)
FS_INTERP = """
#version 330
in vec2 uv;
out vec4 cor;
uniform sampler2D ta;
uniform sampler2D tb;
uniform sampler2D fab;     // movimento A -> B (unidades de textura)
uniform sampler2D fba;     // movimento B -> A
uniform sampler2D tpar;    // 1 = pixel parado (HUD, placar, textos)
uniform float alfa;        // 0 = A, 1 = B
uniform vec2 res_fluxo;    // resolução em que o movimento foi medido
void main() {
    float t = alfa;
    vec2 f01 = texture(fab, uv).xy;
    vec2 f10 = texture(fba, uv).xy;
    vec2 ft0 = -(1.0 - t) * t * f01 + t * t * f10;
    vec2 ft1 = (1.0 - t) * (1.0 - t) * f01 - t * (1.0 - t) * f10;
    vec2 p0 = uv + ft0, p1 = uv + ft1;
    vec3 c0 = texture(ta, p0).rgb;
    vec3 c1 = texture(tb, p1).rgb;
    // confiança: ir de A para B e voltar deve dar no mesmo lugar
    vec2 g0 = texture(fab, p0).xy; vec2 v0 = texture(fba, p0 + g0).xy;
    vec2 g1 = texture(fba, p1).xy; vec2 v1 = texture(fab, p1 + g1).xy;
    float e0 = length((g0 + v0) * res_fluxo);
    float e1 = length((g1 + v1) * res_fluxo);
    // amostra que caiu em cima do HUD não serve para um pixel que está se mexendo
    float s = texture(tpar, uv).r;
    float s0 = texture(tpar, p0).r, s1 = texture(tpar, p1).r;
    float w0 = (1.0 - t) / (1.0 + e0 * e0) * (1.0 - s0) + 1e-5 * (1.0 - t);
    float w1 = t / (1.0 + e1 * e1) * (1.0 - s1) + 1e-5 * t;
    vec3 c = (c0 * w0 + c1 * w1) / (w0 + w1);
    // quadro real mais próximo no tempo: usado quando inventar daria imagem dupla
    vec3 a0 = texture(ta, uv).rgb, b0 = texture(tb, uv).rgb;
    vec3 perto = t < 0.5 ? a0 : b0;
    // as duas versões discordam (movimento errado ou objeto aparecendo): nada de mistura transparente
    c = mix(c, perto, smoothstep(0.06, 0.18, length(c0 - c1)));
    // as duas amostras caíram no HUD
    c = mix(c, perto, s0 * s1 * (1.0 - s));
    cor = vec4(mix(c, perto, s), 1.0);
}
"""

# Aviso no canto (texto já desenhado numa textura com transparência)
FS_AVISO = """
#version 330
in vec2 uv;
out vec4 cor;
uniform sampler2D tex;
uniform float opacidade;
void main() {
    vec4 c = texture(tex, uv);
    cor = vec4(c.rgb, c.a * opacidade);
}
"""

INTERP_OPCOES = {"Desligada": 0, "60 Hz": 60, "120 Hz": 120, "144 Hz": 144, "210 Hz": 210}


class Movimento:
    """Mede o movimento entre dois quadros em outra thread (OpenCV DIS, nos dois sentidos).
    Começa no modo de qualidade média e passa para o rápido se o PC não acompanhar."""
    LARG, ALT = 640, 360

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.dis_medio = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self.dis_rapido = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
        self.rapido = False
        self.grade = None
        self.tempo_medio = 0.0
        self.pedido = None
        self.resultado = None
        self.cond = threading.Condition()
        self.rodando = True
        threading.Thread(target=self._loop, daemon=True).start()

    def pequeno(self, quadro):
        cv2 = self.cv2
        return cv2.cvtColor(cv2.resize(quadro, (self.LARG, self.ALT), interpolation=cv2.INTER_AREA),
                            cv2.COLOR_BGR2GRAY)

    def pedir(self, a, b):
        with self.cond:
            self.pedido = (a, b)
            self.cond.notify()

    def pegar(self):
        with self.cond:
            r, self.resultado = self.resultado, None
            return r

    def parar(self):
        with self.cond:
            self.rodando = False
            self.cond.notify()

    def _medir(self, pa, pb):
        """Devolve (fab, fba, parado) ou None quando não dá para interpolar com segurança."""
        import numpy as np
        cv2 = self.cv2
        dif = cv2.absdiff(pa, pb)
        if float(dif.mean()) > 60:      # troca de cena: não inventa quadro nenhum
            return None
        dis = self.dis_rapido if self.rapido else self.dis_medio
        fab = cv2.medianBlur(dis.calc(pa, pb, None), 5)
        fba = cv2.medianBlur(dis.calc(pb, pa, None), 5)
        if self.grade is None:
            self.grade = np.meshgrid(np.arange(self.LARG, dtype=np.float32), np.arange(self.ALT, dtype=np.float32))
        gx, gy = self.grade
        puxado = cv2.remap(pb, gx + fab[..., 0], gy + fab[..., 1], cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REPLICATE)
        erro_parado = cv2.blur(dif.astype(np.float32), (3, 3))
        erro_mov = cv2.blur(cv2.absdiff(pa, puxado).astype(np.float32), (3, 3))
        # parado = "não se mexer" explica o pixel melhor que o movimento medido (HUD, placar, textos)
        mexeu = np.hypot(fab[..., 0], fab[..., 1]) > 0.75
        parado = ((erro_parado <= erro_mov * 0.5 + 2.0) & mexeu) | (erro_parado < 2.0)
        parado = cv2.morphologyEx(parado.astype(np.uint8), cv2.MORPH_OPEN, None)
        # se o movimento não explica boa parte da imagem (explosão, efeito na tela toda), não inventa
        if float(((erro_mov > 25) & (parado == 0)).mean()) > 0.2:
            return None
        for f in (fab, fba):
            f[parado > 0] = 0
            f[..., 0] /= self.LARG
            f[..., 1] /= self.ALT
        return np.ascontiguousarray(fab), np.ascontiguousarray(fba), np.ascontiguousarray(parado * 255)

    def _loop(self):
        while True:
            with self.cond:
                while self.rodando and self.pedido is None:
                    self.cond.wait()
                if not self.rodando:
                    return
                (qa, pa, ta), (qb, pb, tb) = self.pedido
                self.pedido = None
            t0 = time.perf_counter()
            fluxo = self._medir(pa, pb)
            gasto = time.perf_counter() - t0
            dur = max(tb - ta, 1 / 240)
            self.tempo_medio = gasto if not self.tempo_medio else self.tempo_medio * 0.8 + gasto * 0.2
            # ajuste automático: se demora mais que 70% do intervalo do jogo, usa o modo rápido
            if not self.rapido and self.tempo_medio > 0.7 * dur:
                self.rapido = True
            elif self.rapido and self.tempo_medio < 0.25 * dur:
                self.rapido = False
            with self.cond:
                self.resultado = (qa, qb, fluxo, tb - ta)


class TelaCheiaGPU:
    """Janela de tela cheia desenhada pela placa de vídeo, em uma thread própria.
    Esc ou clique duplo fecha; os atalhos do FSR e da interpolação vêm das configurações."""

    def __init__(self, captura, fsr, ao_fechar, ao_mudar_fsr=None, interp_hz=0, ao_mudar_interp=None,
                 atalhos=None, compativel=True):
        self.cap, self.fsr, self.ao_fechar, self.ao_mudar_fsr = captura, fsr, ao_fechar, ao_mudar_fsr
        self.interp_hz, self.ao_mudar_interp = interp_hz, ao_mudar_interp
        self.atalhos = atalhos or {"fsr": "f", "interp": "i"}
        # janela 1 pixel maior que o monitor: o Windows não a trata como tela cheia exclusiva,
        # então Discord, OBS e companhia capturam sem travar
        self.compativel = compativel
        self.rodando = True
        self.erro = None
        self.fps = 0.0
        self.hz_monitor = 0
        self.fonte_fps = 0.0
        self.modo_rapido = False
        self.aviso_txt, self.aviso_t = None, 0.0
        self.pronto = threading.Event()
        self.terminou = threading.Event()
        threading.Thread(target=self._rodar, daemon=True).start()

    def fechar(self, esperar=0.0):
        self.rodando = False
        if esperar:
            self.terminou.wait(esperar)

    def avisar(self, texto):
        """Mostra um aviso no canto por 1 segundo (pode ser chamado de qualquer thread)."""
        self.aviso_txt, self.aviso_t = texto, time.perf_counter()

    def definir_fsr(self, ligado):
        self.fsr = bool(ligado)
        self.avisar(f"FSR 1: {'ligado' if self.fsr else 'desligado'}")

    def definir_interp(self, hz):
        self.interp_hz = hz
        self.avisar(f"Interpolação: {hz} Hz" if hz else "Interpolação: desligada")

    def alternar_fsr(self):
        self.definir_fsr(not self.fsr)
        if self.ao_mudar_fsr:
            self.ao_mudar_fsr(self.fsr)

    def proxima_interp(self):
        opcoes = list(INTERP_OPCOES.values())
        novo = opcoes[(opcoes.index(self.interp_hz) + 1) % len(opcoes)] if self.interp_hz in opcoes else 0
        self.definir_interp(novo)
        if self.ao_mudar_interp:
            self.ao_mudar_interp(novo)

    # ---- atalhos que funcionam mesmo com outra janela em foco (Ctrl+Shift+tecla)
    def _atalhos_globais(self):
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._thread_atalhos = kernel32.GetCurrentThreadId()
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)   # cria a fila de mensagens desta thread
        acoes = {1: self.alternar_fsr, 2: self.proxima_interp}
        usados = []
        for id_, nome in ((1, "fsr"), (2, "interp")):
            vk = tecla_para_vk(self.atalhos.get(nome, ""))
            if vk and user32.RegisterHotKey(None, id_, 0x0002 | 0x0004 | 0x4000, vk):  # Ctrl+Shift, sem repetir
                usados.append(id_)
        try:
            while self.rodando and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and msg.wParam in acoes:   # WM_HOTKEY
                    acoes[msg.wParam]()
        finally:
            for id_ in usados:
                user32.UnregisterHotKey(None, id_)

    def _parar_atalhos(self):
        tid, self._thread_atalhos = getattr(self, "_thread_atalhos", None), None
        if WIN and tid:
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(tid, 0x0012, 0, 0)   # WM_QUIT

    def trocar_atalhos(self, atalhos):
        self.atalhos = atalhos
        if WIN and self.rodando:
            self._parar_atalhos()
            time.sleep(0.05)
            threading.Thread(target=self._atalhos_globais, daemon=True).start()

    def _rodar(self):
        relogio = False
        try:
            if WIN:
                import ctypes
                relogio = ctypes.windll.winmm.timeBeginPeriod(1) == 0  # pausas de 1 ms precisas
                threading.Thread(target=self._atalhos_globais, daemon=True).start()
            self._loop()
        except Exception as e:
            self.erro = e
        finally:
            self.rodando = False
            self._parar_atalhos()
            if relogio:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            self.pronto.set()
            try:
                import pygame
                pygame.display.quit()
            except Exception:
                pass
            self.terminou.set()
            self.ao_fechar(self.erro)

    def _loop(self):
        import os as _os
        _os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        _os.environ["SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS"] = "0"
        import numpy as np
        import pygame
        import moderngl
        pygame.display.init()
        pygame.font.init()
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
        larg, alt = pygame.display.get_desktop_sizes()[0]
        oy = 1 if self.compativel else 0     # a linha de baixo fica fora do monitor
        _os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
        pygame.display.set_mode((larg, alt + oy), pygame.OPENGL | pygame.DOUBLEBUF | pygame.NOFRAME, vsync=0)
        try:
            pygame.Window.from_display_module().position = (0, 0)
        except Exception:
            pass
        pygame.display.set_caption("PSTudo — Tela")
        pygame.mouse.set_visible(False)
        try:
            self.hz_monitor = int(pygame.display.get_current_refresh_rate())
        except Exception:
            self.hz_monitor = 0
        ctx = moderngl.create_context()
        try:
            pygame.display.gl_set_swap_interval(0)   # sem esperar o monitor: menos atraso
        except Exception:
            pass
        quad = ctx.buffer(np.array([0, 0, 1, 0, 0, 1, 1, 1], dtype="f4").tobytes())
        progs = {n: ctx.program(vertex_shader=VS_TELA, fragment_shader=fs)
                 for n, fs in (("simples", FS_SIMPLES), ("lanczos", FS_LANCZOS), ("rcas", FS_RCAS),
                               ("interp", FS_INTERP), ("aviso", FS_AVISO))}
        vaos = {n: ctx.vertex_array(p_, [(quad, "2f", "pos")]) for n, p_ in progs.items()}
        cache = {}
        escala_aviso = max(1.0, alt / 1080)
        try:
            fonte = pygame.font.SysFont("Segoe UI Semibold, Segoe UI, Arial", int(26 * escala_aviso))
        except Exception:
            fonte = pygame.font.Font(None, int(34 * escala_aviso))
        aviso_cache = {"txt": None, "tex": None, "tam": (0, 0)}

        def textura(nome, tam, comp=3, dtype="f1", filtro=moderngl.LINEAR, bgr=False):
            t = cache.get(nome)
            if t is None or t.size != tam or t.components != comp:
                t = ctx.texture(tam, comp, dtype=dtype, alignment=1)
                t.filter = (filtro, filtro)
                t.repeat_x = t.repeat_y = False
                if bgr:
                    t.swizzle = "BGR"   # a placa entrega BGR: a troca é feita pela GPU
                cache[nome] = t
                cache.pop(nome + "_fbo", None)
            return t

        def fbo_de(nome, tex):
            f = cache.get(nome + "_fbo")
            if f is None:
                f = ctx.framebuffer(color_attachments=[tex])
                cache[nome + "_fbo"] = f
            return f

        def desenhar(prog, caixa, inverter, viewport, **unis):
            ctx.viewport = viewport
            p_ = progs[prog]
            p_["caixa"] = caixa
            p_["inverter"] = inverter
            for k, v in unis.items():
                p_[k] = v
            vaos[prog].render(moderngl.TRIANGLE_STRIP)

        def desenhar_aviso():
            if not self.aviso_txt:
                return
            idade = time.perf_counter() - self.aviso_t
            if idade > 1.25:
                return
            opac = 1.0 if idade < 1.0 else 1.0 - (idade - 1.0) / 0.25
            if aviso_cache["txt"] != self.aviso_txt:
                txt = fonte.render(self.aviso_txt, True, (255, 255, 255))
                pad_x, pad_y = int(22 * escala_aviso), int(12 * escala_aviso)
                sup = pygame.Surface((txt.get_width() + 2 * pad_x + int(14 * escala_aviso),
                                      txt.get_height() + 2 * pad_y), pygame.SRCALPHA)
                raio = sup.get_height() // 2
                pygame.draw.rect(sup, (10, 18, 34, 225), sup.get_rect(), border_radius=raio)
                pygame.draw.rect(sup, (255, 255, 255, 50), sup.get_rect(), width=1, border_radius=raio)
                cx = pad_x - int(2 * escala_aviso)
                pygame.draw.circle(sup, (0, 112, 209, 255), (cx, sup.get_height() // 2), int(5 * escala_aviso))
                sup.blit(txt, (cx + int(14 * escala_aviso), pad_y))
                dados = pygame.image.tobytes(sup, "RGBA")
                t = ctx.texture(sup.get_size(), 4, dados)
                t.filter = (moderngl.LINEAR, moderngl.LINEAR)
                aviso_cache.update(txt=self.aviso_txt, tex=t, tam=sup.get_size())
            aw, ah = aviso_cache["tam"]
            m = int(32 * escala_aviso)
            caixa = (1 - 2 * (aw + m) / larg, 1 - 2 * (ah + m) / alt, 2 * aw / larg, 2 * ah / alt)
            ctx.enable(moderngl.BLEND)
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            aviso_cache["tex"].use(0)
            desenhar("aviso", caixa, 1.0, (0, oy, larg, alt), tex=0, opacidade=opac)
            ctx.disable(moderngl.BLEND)

        def mostrar(src, inv, w, h):
            """Desenha a textura src (w×h) na tela, com ou sem FSR, mais o aviso."""
            esc = min(larg / w, alt / h)
            vw, vh = max(2, int(w * esc)), max(2, int(h * esc))
            caixa = (-vw / larg, -vh / alt, 2 * vw / larg, 2 * vh / alt)
            ctx.screen.use()
            ctx.viewport = (0, 0, larg, alt + oy)
            ctx.clear(0, 0, 0)
            if self.fsr:
                meio = textura("meio", (vw, vh), filtro=moderngl.NEAREST)
                fbo_de("meio", meio).use()
                src.use(0)
                desenhar("lanczos", (-1.0, -1.0, 2.0, 2.0), inv, (0, 0, vw, vh), tex=0, tam=(float(w), float(h)))
                ctx.screen.use()
                meio.use(0)
                desenhar("rcas", caixa, 0.0, (0, oy, larg, alt), tex=0, texel=(1.0 / vw, 1.0 / vh), nitidez=0.87)
            else:
                src.use(0)
                desenhar("simples", caixa, inv, (0, oy, larg, alt), tex=0)
            desenhar_aviso()
            pygame.display.flip()

        mov = None
        self.pronto.set()
        ultimo, ult_clique, cont, t0 = -1, 0.0, 0, time.time()
        chave_ant = None            # último quadro DIFERENTE (quadro, pequeno, tempo)
        par = None                  # (w, h, duração) do par sendo interpolado
        inicio_par = 0.0
        prox = time.perf_counter()
        distintos, t_dist = 0, time.time()
        while self.rodando and self.cap.rodando:
            for ev in pygame.event.get():
                if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                    self.rodando = False
                elif ev.type == pygame.KEYDOWN:
                    nome = pygame.key.name(ev.key).lower()
                    if ev.mod & pygame.KMOD_CTRL and ev.mod & pygame.KMOD_SHIFT and WIN:
                        pass                    # Ctrl+Shift já chega pelo atalho global
                    elif nome == self.atalhos.get("fsr"):
                        self.alternar_fsr()
                    elif nome == self.atalhos.get("interp"):
                        self.proxima_interp()
                elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    agora = time.time()
                    if agora - ult_clique < 0.35:
                        self.rodando = False
                    ult_clique = agora
            hz = self.interp_hz   # cópia: pode ser trocado pela outra janela a qualquer momento
            aviso_ativo = self.aviso_txt and time.perf_counter() - self.aviso_t < 1.3
            # ---------------- sem interpolação: mostra cada quadro assim que chega
            if not hz:
                if mov:
                    mov.parar()
                    mov, chave_ant, par = None, None, None
                tem_novo = self.cap.novo.wait(0.01)
                if not tem_novo and not aviso_ativo:
                    continue
                self.cap.novo.clear()
                quadro = self.cap.quadro
                if quadro is None or (self.cap.n == ultimo and not aviso_ativo):
                    continue
                ultimo = self.cap.n
                h, w = quadro.shape[:2]
                tex = textura("q", (w, h), bgr=True)
                tex.write(np.ascontiguousarray(quadro))
                mostrar(tex, 1.0, w, h)
            # ---------------- com interpolação: ritmo próprio no Hz escolhido
            else:
                if mov is None:
                    mov = Movimento()
                if self.cap.n != ultimo and self.cap.quadro is not None:
                    ultimo = self.cap.n
                    quadro, t_q = self.cap.quadro, time.perf_counter()
                    peq = mov.pequeno(quadro)
                    # o PS3 manda 60 Hz mesmo com o jogo a 30: quadros repetidos são ignorados
                    if chave_ant is None or float(np.mean(cv2_absdiff(peq, chave_ant[1]))) > 0.6:
                        if chave_ant is not None:
                            mov.pedir(chave_ant, (quadro, peq, t_q))
                        chave_ant = (quadro, peq, t_q)
                        distintos += 1
                res = mov.pegar()
                if res is not None:
                    qa, qb, fluxo, dur = res
                    h, w = qb.shape[:2]
                    textura("a", (w, h), bgr=True).write(np.ascontiguousarray(qa))
                    textura("b", (w, h), bgr=True).write(np.ascontiguousarray(qb))
                    if fluxo is None:          # troca de cena ou movimento confuso: vai direto para o quadro novo
                        par = (w, h, 1e-6, False)
                    else:
                        fab, fba, parado = fluxo
                        textura("fab", (fab.shape[1], fab.shape[0]), comp=2, dtype="f4").write(fab)
                        textura("fba", (fba.shape[1], fba.shape[0]), comp=2, dtype="f4").write(fba)
                        textura("par", (parado.shape[1], parado.shape[0]), comp=1).write(parado)
                        par = (w, h, min(max(dur, 1 / 120), 0.1), True)
                    inicio_par = time.perf_counter()
                    self.modo_rapido = mov.rapido
                if par is not None:
                    w, h, dur, tem_fluxo = par
                    alfa = min(1.0, (time.perf_counter() - inicio_par) / dur)
                    if tem_fluxo and alfa < 1.0:
                        saida = textura("interp", (w, h))
                        fbo_de("interp", saida).use()
                        cache["a"].use(0)
                        cache["b"].use(1)
                        cache["fab"].use(2)
                        cache["fba"].use(3)
                        cache["par"].use(4)
                        desenhar("interp", (-1.0, -1.0, 2.0, 2.0), 1.0, (0, 0, w, h), ta=0, tb=1, fab=2, fba=3,
                                 tpar=4, alfa=alfa, res_fluxo=(float(Movimento.LARG), float(Movimento.ALT)))
                        mostrar(saida, 0.0, w, h)
                    else:
                        mostrar(cache["b"], 1.0, w, h)
                elif chave_ant is not None:
                    qa = chave_ant[0]
                    h, w = qa.shape[:2]
                    tex = textura("q", (w, h), bgr=True)
                    tex.write(np.ascontiguousarray(qa))
                    mostrar(tex, 1.0, w, h)
                # espera até o próximo quadro de saída
                prox += 1.0 / hz
                agora = time.perf_counter()
                if prox < agora - 0.05:
                    prox = agora
                while True:
                    falta = prox - time.perf_counter()
                    if falta <= 0:
                        break
                    time.sleep(falta - 0.0015 if falta > 0.002 else 0)
            cont += 1
            agora = time.time()
            if agora - t0 >= 1:
                self.fps, cont, t0 = cont / (agora - t0), 0, agora
            if agora - t_dist >= 1:
                self.fonte_fps, distintos, t_dist = distintos / (agora - t_dist), 0, agora
        if mov:
            mov.parar()
        ctx.release()


def tecla_para_vk(nome):
    """Nome de tecla (padrão do pygame) -> código virtual do Windows, para os atalhos globais."""
    nome = (nome or "").lower()
    if len(nome) == 1 and (nome.isalpha() or nome.isdigit()):
        return ord(nome.upper())
    if nome.startswith("f") and nome[1:].isdigit() and 1 <= int(nome[1:]) <= 24:
        return 0x70 + int(nome[1:]) - 1
    return {"space": 0x20, "tab": 0x09, "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
            "page up": 0x21, "page down": 0x22, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
            "pause": 0x13, "scroll lock": 0x91, "return": 0x0D, "backspace": 0x08}.get(nome)


def cv2_absdiff(a, b):
    import cv2
    return cv2.absdiff(a, b)


CAPTURA_PALAVRAS = ("capture", "captura", "hdmi", "cam link", "elgato", "avermedia", "usb3", "usb 3", "video",
                    "uvc", "game", "live gamer", "ezcap", "magewell", "razer ripsaw")
MODOS_TELA = {"1080p 60": (1920, 1080, 60), "1080p 30": (1920, 1080, 30), "720p 60": (1280, 720, 60)}
HOSTAPI_ORDEM = ("Windows WASAPI", "Windows DirectSound", "MME")


def listar_placas_video():
    """Nomes das entradas de vídeo, na mesma ordem que o OpenCV usa com DirectShow."""
    if not WIN:
        return []
    try:
        import comtypes
        comtypes.CoInitialize()  # roda em outra thread
        from pygrabber.dshow_graph import FilterGraph
        return list(FilterGraph().get_input_devices())
    except Exception:
        return []


def sondar_placas_video(limite=5):
    """Plano B: testa as entradas de vídeo uma a uma quando os nomes não puderem ser lidos."""
    try:
        import cv2
    except Exception:
        return []
    achadas = []
    for i in range(limite):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW if WIN else cv2.CAP_ANY)
        ok = cap.isOpened()
        cap.release()
        if not ok:
            break
        achadas.append(f"Entrada de vídeo {i + 1}")
    return achadas


def listar_entradas_audio():
    """{nome: [índices em ordem de preferência da API de áudio]} (WASAPI primeiro)."""
    try:
        import sounddevice as sd
    except Exception:
        return {}
    apis = sd.query_hostapis()
    grupos = {}
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] < 1:
            continue
        api = apis[d["hostapi"]]["name"]
        prio = HOSTAPI_ORDEM.index(api) if api in HOSTAPI_ORDEM else 9
        nome_l = d["name"].lower()
        chave = next((k for k in grupos if min(len(k), len(nome_l)) >= 20 and
                      (k.startswith(nome_l) or nome_l.startswith(k))), nome_l)  # o MME corta nomes longos
        grupos.setdefault(chave, []).append((prio, i, d["name"]))
    resultado = {}
    for itens in grupos.values():
        itens.sort()
        nome = max((n for *_, n in itens), key=len)
        resultado[nome] = [i for _, i, _ in itens]
    return resultado


def escolher_padrao(nomes):
    for nome in nomes:
        if any(k in nome.lower() for k in CAPTURA_PALAVRAS):
            return nome
    return nomes[0] if nomes else None


class Audio:
    """Passa o áudio da placa de captura para a saída padrão do PC."""

    def __init__(self, indices, volume):
        import sounddevice as sd
        self.sd = sd
        self.volume = volume  # lista de 1 item, alterada pela interface
        self.stream = None
        erro = None
        for idx in indices:
            try:
                d = sd.query_devices(idx)
                api = sd.query_hostapis(d["hostapi"])
                saida = api["default_output_device"]
                if saida is None or saida < 0:
                    continue
                d_out = sd.query_devices(saida)
                canais = max(1, min(2, d["max_input_channels"], d_out["max_output_channels"]))
                sr = int(d["default_samplerate"] or 48000)

                def cb(indata, outdata, frames, t, status, _c=canais):
                    outdata[:] = indata * self.volume[0]
                self.stream = sd.Stream(device=(idx, saida), samplerate=sr, channels=canais, dtype="float32",
                                        latency="low", callback=cb)
                self.stream.start()
                self.info = f"{api['name']} • {sr // 1000} kHz"
                return
            except Exception as e:
                erro = e
                self.stream = None
        raise RuntimeError(f"não consegui abrir o áudio ({erro})")

    def parar(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


class Captura:
    """Lê quadros da placa em outra thread e guarda sempre o mais recente."""

    def __init__(self, fonte, modo):
        self.fonte, self.modo = fonte, modo
        self.quadro = None
        self.n = 0
        self.erro = None
        self.rodando = True
        self.fps = 0.0
        self.tamanho = None
        self.novo = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        import cv2
        arquivo = isinstance(self.fonte, str)
        if arquivo:
            cap = cv2.VideoCapture(self.fonte)
        else:
            cap = cv2.VideoCapture(self.fonte, cv2.CAP_DSHOW if WIN else cv2.CAP_ANY)
            w, h, fps = self.modo
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            cap.set(cv2.CAP_PROP_FPS, fps)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            self.erro = "abrir"
            self.rodando = False
            return
        t0, cont, falhas = time.time(), 0, 0
        intervalo = 1 / (cap.get(cv2.CAP_PROP_FPS) or 30) if arquivo else 0
        while self.rodando:
            ok, q = cap.read()
            if not ok:
                if arquivo:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                falhas += 1
                if falhas > 60:
                    self.erro = "sinal"
                    break
                time.sleep(0.02)
                continue
            falhas = 0
            self.quadro = q
            self.tamanho = (q.shape[1], q.shape[0])
            self.n += 1
            self.novo.set()
            cont += 1
            agora = time.time()
            if agora - t0 >= 1:
                self.fps, cont, t0 = cont / (agora - t0), 0, agora
            if intervalo:
                time.sleep(intervalo)
        cap.release()
        self.rodando = False

    def parar(self):
        self.rodando = False


class Tela:
    PREV_W, PREV_H, PREV_Y = 752, 423, 326

    def tela_espelho(self):
        self.limpar()
        p, c = self.p, self.c
        pw, ph = self.PREV_W + 16, self.PREV_H + 16
        c.create_image(p.px(W / 2), p.px(self.PREV_Y), tags="view",
                       image=p.ret(pw, ph, 18, (3, 6, 12, 255), outline=(255, 255, 255, 34), largura=1))
        self.tl_item = c.create_image(p.px(W / 2), p.px(self.PREV_Y), tags=("view", "tl_video"))
        self.tl_aviso = c.create_text(p.px(W / 2), p.px(self.PREV_Y - 12), fill=BRANCO, tags="view",
                                      font=(F_LIGHT, -p.px(22)), text="Espelhar a placa de captura")
        self.tl_aviso2 = c.create_text(p.px(W / 2), p.px(self.PREV_Y + 22), fill=CINZA, tags="view",
                                       font=(F_REG, -p.px(13)), width=p.px(560), justify="center",
                                       text="Ligue o PS3 na placa, a placa no PC, escolha abaixo e clique em Iniciar.")
        self.tl_info = c.create_text(p.px(W / 2 + self.PREV_W / 2 - 10), p.px(self.PREV_Y - self.PREV_H / 2 + 14),
                                     anchor="ne", fill="#9AA4B8", font=(F_REG, -p.px(11)), text="", tags="view")
        c.tag_bind("tl_video", "<Double-Button-1>", lambda e: self.tl_tela_cheia())

        barra = ctk.CTkFrame(self.root, fg_color="#050B18", corner_radius=0, height=38, width=680)
        barra.pack_propagate(False)
        c.create_window(p.px(48), p.px(551), window=barra, anchor="nw", tags="view")
        self.widgets.append(barra)
        f_txt = ctk.CTkFont(family=F_REG, size=12)

        def menu(valores, largura):
            m = ctk.CTkOptionMenu(barra, values=valores or ["Nenhum encontrado"], width=largura, height=34,
                                  corner_radius=10, fg_color="#16233F", button_color="#1A2744",
                                  button_hover_color="#24365C", font=f_txt, dynamic_resizing=False)
            m.pack(side="left", padx=(0, 6))
            return m

        self.tl_videos, self.tl_audios = [], {}
        self.tl_m_video = menu(["Procurando placas…"], 128)
        self.tl_m_audio = menu(["Procurando áudio…"], 128)
        self.tl_m_modo = menu(list(MODOS_TELA), 106)
        self.tl_m_modo.set(self.cfg.get("tela_modo") if self.cfg.get("tela_modo") in MODOS_TELA else "1080p 60")
        self.tl_btn = ctk.CTkButton(barra, text="▶  Iniciar", width=96, height=34, corner_radius=17,
                                    fg_color="#0070D1", hover_color="#1888F0",
                                    font=ctk.CTkFont(family=F_SEMI, size=13), command=self.tl_alternar)
        self.tl_btn.pack(side="left", padx=(0, 6))
        self.tl_btn_cheia = ctk.CTkButton(barra, text="⛶", width=40, height=34, corner_radius=17, fg_color=BTN,
                                          hover_color=BTN_HOVER, font=ctk.CTkFont(family=F_SYM, size=15),
                                          command=self.tl_tela_cheia)
        self.tl_btn_cheia.pack(side="left", padx=(0, 6))
        self.tl_fsr = tk.BooleanVar(value=bool(self.cfg.get("tela_fsr", False)))
        self.tl_interp = self.cfg.get("tela_interp", "Desligada")
        if self.tl_interp not in INTERP_OPCOES:
            self.tl_interp = "Desligada"
        ctk.CTkButton(barra, text="Imagem", width=70, height=34, corner_radius=17, fg_color=BTN,
                      hover_color=BTN_HOVER, font=ctk.CTkFont(family=F_SEMI, size=12),
                      command=self.tl_opcoes_imagem).pack(side="left", padx=(0, 6))
        self.tl_vol = getattr(self, "tl_vol", [float(self.cfg.get("tela_volume", 1.0))])
        sl = ctk.CTkSlider(barra, from_=0, to=1.5, width=50, height=16, button_color="#E5ECF8",
                           progress_color="#0070D1", fg_color="#22304D",
                           command=lambda v: self.tl_vol.__setitem__(0, float(v)))
        sl.set(self.tl_vol[0])
        sl.pack(side="left")
        self.tl_btn.configure(state="disabled")
        self.tl_foto = None
        self._tl_alvo = None
        if getattr(self, "tl_cap", None):        # a placa continuou ligada enquanto você estava em outra aba
            self.c.itemconfig(self.tl_aviso, text="Conectando à placa…" if self.tl_cap.quadro is None else "")
            self.c.itemconfig(self.tl_aviso2, text="")
            self.tl_btn.configure(text="■  Parar", fg_color="#3A1620", hover_color="#5A1E2C", text_color="#FCA5A5",
                                  state="normal")
        else:
            self.tl_cap = None
            self.tl_audio = None
            self.tl_cheia = None
        self._tl_listar()

    def _tl_listar(self):
        def tarefa():
            res = {}
            t = threading.Thread(target=lambda: res.update(v=listar_placas_video()), daemon=True)
            t.start()
            t.join(8)
            videos = res.get("v") or sondar_placas_video()
            try:
                audios = listar_entradas_audio()
            except Exception:
                audios = {}
            self.fila.put(("cb", lambda: self._tl_preencher(videos, audios)))
        threading.Thread(target=tarefa, daemon=True).start()

    def _tl_preencher(self, videos, audios):
        if self.aba != "tela" or not self.tl_btn.winfo_exists():
            return
        self.tl_videos, self.tl_audios = videos, audios
        nomes_audio = ["Sem áudio"] + list(audios)
        self.tl_m_video.configure(values=videos or ["Nenhuma placa encontrada"])
        self.tl_m_audio.configure(values=nomes_audio)
        v_salvo, a_salvo = self.cfg.get("tela_video"), self.cfg.get("tela_audio")
        if videos:
            self.tl_m_video.set(v_salvo if v_salvo in videos else escolher_padrao(videos))
            self.tl_btn.configure(state="normal")
        elif getattr(self, "tl_cap", None):
            self.tl_m_video.set(v_salvo or "Placa ligada")
        else:
            self.tl_m_video.set("Nenhuma placa encontrada")
            self.c.itemconfig(self.tl_aviso2, text="Nenhuma placa de captura encontrada. Conecte a placa no PC "
                                                   "e abra esta aba de novo.")
        if a_salvo in nomes_audio:
            self.tl_m_audio.set(a_salvo)
        else:
            parecidos = [n for n in audios if any(k in n.lower() for k in CAPTURA_PALAVRAS)]
            self.tl_m_audio.set(parecidos[0] if parecidos else "Sem áudio")

    # ---- iniciar / parar
    def tl_alternar(self):
        if self.tl_cap:
            self.tl_parar()
        else:
            self.tl_iniciar()

    def tl_iniciar(self, fonte=None):
        if fonte is None:
            nome = self.tl_m_video.get()
            if nome not in self.tl_videos:
                return
            fonte = self.tl_videos.index(nome)
        modo = self.tl_m_modo.get()
        self.cfg.update(tela_video=self.tl_m_video.get(), tela_audio=self.tl_m_audio.get(), tela_modo=modo)
        self.salvar_cfg()
        self.tl_cap = Captura(fonte, MODOS_TELA.get(modo, (1920, 1080, 60)))
        self.tl_ultimo = -1
        self.tl_geracao = getattr(self, "tl_geracao", 0) + 1
        self.c.itemconfig(self.tl_aviso, text="Conectando à placa…")
        self.c.itemconfig(self.tl_aviso2, text="")
        self.tl_btn.configure(text="■  Parar", fg_color="#3A1620", hover_color="#5A1E2C", text_color="#FCA5A5")
        self.tl_audio_msg = ""
        nome_a = self.tl_m_audio.get()
        if nome_a in getattr(self, "tl_audios", {}):
            try:
                self.tl_audio = Audio(self.tl_audios[nome_a], self.tl_vol)
                self.tl_audio_msg = "Áudio: " + self.tl_audio.info
            except Exception as e:
                self.tl_audio = None
                self.tl_audio_msg = f"Sem áudio ({str(e)[:50]})"
        g = self.tl_geracao
        self.root.after(15, lambda: self.tl_desenhar(g))

    def tl_parar(self, msg=None, msg2=""):
        if getattr(self, "tl_cap", None):
            self.tl_cap.parar()
        self.tl_cap = None
        if getattr(self, "tl_audio", None):
            self.tl_audio.parar()
        self.tl_audio = None
        self.cfg["tela_volume"] = round(getattr(self, "tl_vol", [1.0])[0], 2)
        if getattr(self, "tl_cheia", None):
            self._tl_sair_cheia()
        if getattr(self, "tl_gpu", None):
            self.tl_gpu.fechar(esperar=1.5)
            self.tl_gpu = None
        if self.aba == "tela" and getattr(self, "tl_btn", None) and self.tl_btn.winfo_exists():
            self.c.itemconfig(self.tl_item, image="")
            self.tl_foto = None
            self.c.itemconfig(self.tl_aviso, text=msg or "Espelhar a placa de captura")
            self.c.itemconfig(self.tl_aviso2, text=msg2)
            self.c.itemconfig(self.tl_info, text="")
            self.tl_btn.configure(text="▶  Iniciar", fg_color="#0070D1", hover_color="#1888F0", text_color=BRANCO)

    # ---- desenho
    def _tl_converter(self, quadro, larg, alt):
        import cv2
        h, w = quadro.shape[:2]
        esc = min(larg / w, alt / h)
        nw, nh = max(2, int(w * esc)), max(2, int(h * esc))
        rgb = cv2.cvtColor(cv2.resize(quadro, (nw, nh), interpolation=cv2.INTER_LINEAR), cv2.COLOR_BGR2RGB)
        return Image.frombuffer("RGB", (nw, nh), rgb.tobytes(), "raw", "RGB", 0, 1)

    def tl_desenhar(self, geracao=None):
        cap = getattr(self, "tl_cap", None)
        if not cap or (geracao is not None and geracao != getattr(self, "tl_geracao", 0)):
            return
        prox = lambda ms: self.root.after(ms, lambda: self.tl_desenhar(geracao))   # noqa: E731
        if cap.erro:
            erro = cap.erro
            self.tl_parar("Não consegui mostrar a imagem",
                          "Feche o OBS ou outro programa que esteja usando a placa e tente de novo."
                          if erro == "abrir" else "A placa parou de mandar imagem. Confira o cabo HDMI e o PS3.")
            return
        if getattr(self, "tl_gpu", None):
            if cap.n % 30 == 0:
                g = self.tl_gpu
                txt = f"Tela cheia na placa de vídeo • {g.fps:.0f} fps na tela"
                if g.interp_hz:
                    txt += f" (jogo a {g.fonte_fps:.0f})"
                if g.interp_hz and g.modo_rapido:
                    txt += " • movimento: modo rápido"
                if g.fsr:
                    txt += " • FSR"
                if g.interp_hz and g.hz_monitor and g.interp_hz > g.hz_monitor + 1:
                    txt += f" • seu monitor é {g.hz_monitor} Hz"
                if self.aba == "tela":
                    self.c.itemconfig(self.tl_info, text=txt)
            prox(50)
            return
        if self.aba != "tela" and not self.tl_cheia:
            prox(100)        # em outra aba: a placa e o som continuam, só não desenha a prévia
            return
        if cap.n != self.tl_ultimo and cap.quadro is not None:
            self.tl_ultimo = cap.n
            if self.tl_cheia:
                cv_, item, larg, alt = self.tl_cheia["c"], self.tl_cheia["item"], self.tl_cheia["w"], self.tl_cheia["h"]
            else:
                cv_, item = self.c, self.tl_item
                larg, alt = self.p.px(self.PREV_W), self.p.px(self.PREV_H)
            img = self._tl_converter(cap.quadro, larg, alt)
            if self.tl_foto is None or (self.tl_foto.width(), self.tl_foto.height()) != img.size or \
                    getattr(self, "_tl_alvo", None) is not cv_:
                self.tl_foto = ImageTk.PhotoImage(img)
                cv_.itemconfig(item, image=self.tl_foto)
                self._tl_alvo = cv_
            else:
                self.tl_foto.paste(img)
            if not self.tl_cheia and self.c.itemcget(self.tl_aviso, "text"):
                self.c.itemconfig(self.tl_aviso, text="")
                self.c.itemconfig(self.tl_aviso2, text="")
            if cap.n % 15 == 0 and not self.tl_cheia:
                w_, h_ = cap.tamanho or (0, 0)
                txt = f"{w_}×{h_} • {cap.fps:.0f} fps"
                if self.tl_audio_msg:
                    txt += f"   {self.tl_audio_msg}"
                self.c.itemconfig(self.tl_info, text=txt)
        prox(4)

    def _tl_mudou_fsr(self):
        v = bool(self.tl_fsr.get())
        self.cfg["tela_fsr"] = v
        if getattr(self, "tl_gpu", None):
            self.tl_gpu.definir_fsr(v)

    def _tl_mudou_interp(self, nome):
        self.tl_interp = nome
        self.cfg["tela_interp"] = nome
        if getattr(self, "tl_gpu", None):
            self.tl_gpu.definir_interp(INTERP_OPCOES[nome])

    # ---- opções de imagem
    def tl_opcoes_imagem(self):
        j = self._janela("Imagem", 460, 500)
        f_tit = ctk.CTkFont(family=F_LIGHT, size=22)
        f_txt = ctk.CTkFont(family=F_REG, size=12)
        f_rot = ctk.CTkFont(family=F_SEMI, size=13)
        ctk.CTkLabel(j, text="Imagem na tela cheia", font=f_tit, text_color=BRANCO).pack(anchor="w", padx=24,
                                                                                         pady=(20, 10))
        ctk.CTkSwitch(j, text="FSR 1 — mais nitidez ao ampliar", variable=self.tl_fsr, font=f_rot,
                      progress_color="#0070D1", button_color="#E5ECF8", fg_color="#2A3A5E",
                      command=self._tl_mudou_fsr).pack(anchor="w", padx=24)
        ctk.CTkLabel(j, text=f"Não muda a quantidade de quadros. Atalho na tela cheia: {self.nome_tecla('fsr')}.",
                     font=f_txt,
                     text_color=CINZA, wraplength=360, justify="left").pack(anchor="w", padx=(70, 24))
        ctk.CTkLabel(j, text="Interpolação de quadros", font=f_rot, text_color=BRANCO).pack(anchor="w", padx=24,
                                                                                            pady=(18, 4))
        menu = ctk.CTkSegmentedButton(j, values=list(INTERP_OPCOES), font=f_txt, height=34,
                                      selected_color="#0070D1", selected_hover_color="#1888F0",
                                      unselected_color="#16233F", unselected_hover_color="#20345C",
                                      command=self._tl_mudou_interp)
        menu.set(self.tl_interp)
        menu.pack(fill="x", padx=24)
        ctk.CTkLabel(j, text="Cria quadros intermediários a partir do movimento da imagem. Deixa tudo mais fluido, "
                             "mas acrescenta um pouco de atraso (cerca de 1 quadro do jogo) e pode gerar pequenas "
                             "distorções em movimentos rápidos. Escolha um valor até o Hz do seu monitor. "
                             f"Atalho na tela cheia: {self.nome_tecla('interp')}.",
                     font=f_txt, text_color=CINZA, wraplength=410, justify="left").pack(anchor="w", padx=24,
                                                                                      pady=(8, 0))
        self.tl_compat = tk.BooleanVar(value=self.cfg.get("tela_compativel", True))
        ctk.CTkSwitch(j, text="Compatível com Discord e OBS", variable=self.tl_compat, font=f_rot,
                      progress_color="#0070D1", button_color="#E5ECF8", fg_color="#2A3A5E",
                      command=lambda: self.cfg.update(tela_compativel=bool(self.tl_compat.get()))).pack(
            anchor="w", padx=24, pady=(18, 0))
        ctk.CTkLabel(j, text="Evita que a transmissão trave com a tela cheia em foco. Desligue só se não for "
                             "transmitir. Vale na próxima vez que abrir a tela cheia.\n"
                             f"Com outra janela em foco, use Ctrl+Shift+{self.nome_tecla('fsr')} (FSR) e "
                             f"Ctrl+Shift+{self.nome_tecla('interp')} (interpolação).",
                     font=f_txt, text_color=CINZA, wraplength=360, justify="left").pack(anchor="w", padx=(70, 24))
        ctk.CTkButton(j, text="OK", height=38, width=110, corner_radius=19, fg_color="#0070D1",
                      hover_color="#1888F0", font=ctk.CTkFont(family=F_SEMI, size=14),
                      command=lambda: (self.salvar_cfg(), j.destroy())).pack(side="bottom", anchor="e", padx=24,
                                                                           pady=20)

    # ---- tela cheia
    def tl_tela_cheia(self):
        if not getattr(self, "tl_cap", None) or self.tl_cheia or getattr(self, "tl_gpu", None):
            return
        if not getattr(self, "tl_gpu_falhou", False):
            def fechou(erro):
                def na_tela():
                    self.tl_gpu = None
                    if erro is not None:
                        self.tl_gpu_falhou = True
                        self._tl_cheia_tk()
                self.fila.put(("cb", na_tela))

            def mudou_fsr(v):
                self.fila.put(("cb", lambda: (self.tl_fsr.set(v), self.cfg.update(tela_fsr=v))))

            def mudou_interp(hz):
                nome = next((k for k, v in INTERP_OPCOES.items() if v == hz), "Desligada")
                self.fila.put(("cb", lambda: (setattr(self, "tl_interp", nome), self.cfg.update(tela_interp=nome))))
            self.tl_gpu = TelaCheiaGPU(self.tl_cap, bool(self.tl_fsr.get()), fechou, mudou_fsr,
                                       INTERP_OPCOES.get(self.tl_interp, 0), mudou_interp,
                                       {"fsr": self.atalho("fsr"), "interp": self.atalho("interp")},
                                       compativel=self.cfg.get("tela_compativel", True))
            return
        self._tl_cheia_tk()

    def _tl_cheia_tk(self):
        """Plano B sem placa de vídeo (mais lento)."""
        if not getattr(self, "tl_cap", None) or self.tl_cheia:
            return
        j = tk.Toplevel(self.root, bg="black")
        j.attributes("-fullscreen", True)
        j.configure(cursor="none")
        j.update_idletasks()
        w, h = j.winfo_screenwidth(), j.winfo_screenheight()
        cv_ = tk.Canvas(j, width=w, height=h, bg="black", highlightthickness=0, bd=0)
        cv_.pack(fill="both", expand=True)
        item = cv_.create_image(w // 2, h // 2)
        dica = cv_.create_text(w // 2, h - 40, text="Esc ou clique duplo para sair", fill="#9AA4B8",
                               font=(F_REG, 14))
        j.after(2500, lambda: cv_.winfo_exists() and cv_.delete(dica))
        self.tl_cheia = {"j": j, "c": cv_, "item": item, "w": w, "h": h}
        self.tl_foto = None
        for alvo in (j, cv_):
            alvo.bind("<Escape>", lambda e: self._tl_sair_cheia())
            alvo.bind("<Double-Button-1>", lambda e: self._tl_sair_cheia())
        j.protocol("WM_DELETE_WINDOW", self._tl_sair_cheia)
        j.focus_force()

    def _tl_sair_cheia(self):
        cheia, self.tl_cheia = self.tl_cheia, None
        self.tl_foto = None
        if cheia:
            try:
                cheia["j"].destroy()
            except tk.TclError:
                pass


# =============================================================== som
def recurso(nome):
    """Arquivo que vai junto com o app: dentro do .exe, ou nas pastas do projeto ao rodar pelo código."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for sub in ("", "assets", os.path.join("third_party", "ps3iso-utils", "bin")):
        caminho = os.path.join(base, sub, nome)
        if os.path.exists(caminho):
            return caminho
    return os.path.join(base, nome)


def tocar_som(nome="som_envio.wav"):
    caminho = recurso(nome)
    if not os.path.exists(caminho):
        return False
    try:
        if WIN:
            import winsound
            winsound.PlaySound(caminho, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        else:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.Sound(caminho).play()
        return True
    except Exception:
        return False


# =============================================================== conversão para ISO (pasta e PKG)
PKG_CHAVES = {0: bytes.fromhex("2e7b71d7c9c9a14ea3221f188828b8f8"),   # PS3
              1: bytes.fromhex("07f2c68290b50d2c33818d709b60e62b")}   # PSP/PSX dentro de PKG de PS3


class Cancelado2(Exception):
    pass


def ler_sfo(caminho):
    """PARAM.SFO -> {chave: valor}."""
    try:
        with open(caminho, "rb") as f:
            d = f.read(64 * 1024)
        if d[:4] != b"\0PSF":
            return {}
        k_ini, d_ini, n = struct.unpack_from("<III", d, 8)
        res = {}
        for i in range(n):
            k_off, fmt, d_len, _max, d_off = struct.unpack_from("<HHIII", d, 20 + i * 16)
            fim = d.index(b"\0", k_ini + k_off)
            chave = d[k_ini + k_off:fim].decode("latin-1")
            bruto = d[d_ini + d_off:d_ini + d_off + d_len]
            if fmt == 0x0404:
                res[chave] = struct.unpack("<I", bruto[:4])[0]
            else:
                res[chave] = bruto.split(b"\0")[0].decode("utf-8", "ignore")
        return res
    except Exception:
        return {}


def trocar_sfo(caminho, chave, novo):
    """Troca um texto curto do PARAM.SFO no lugar (ex.: CATEGORY HG -> DG)."""
    with open(caminho, "r+b") as f:
        d = bytearray(f.read())
        k_ini, d_ini, n = struct.unpack_from("<III", d, 8)
        for i in range(n):
            k_off, fmt, d_len, d_max, d_off = struct.unpack_from("<HHIII", d, 20 + i * 16)
            fim = d.index(b"\0", k_ini + k_off)
            if d[k_ini + k_off:fim].decode("latin-1") == chave:
                valor = novo.encode() + b"\0"
                if len(valor) > d_max:
                    return False
                d[d_ini + d_off:d_ini + d_off + d_max] = valor.ljust(d_max, b"\0")
                struct.pack_into("<I", d, 20 + i * 16 + 4, len(valor))
                f.seek(0)
                f.write(d)
                return True
    return False


def criar_sfb(caminho, title_id):
    """PS3_DISC.SFB mínimo (disco de jogo)."""
    d = bytearray(0x10000)
    d[0:8] = b".SFB\x00\x01\x00\x00"
    d[0x20:0x20 + 11] = b"HYBRID_FLAG"
    struct.pack_into(">II", d, 0x30, 0x200, 0x20)
    d[0x40:0x40 + 8] = b"TITLE_ID"
    struct.pack_into(">II", d, 0x50, 0x220, 0x10)
    d[0x200] = ord("g")
    tid = title_id[:4] + "-" + title_id[4:9]
    d[0x220:0x220 + len(tid)] = tid.encode()
    with open(caminho, "wb") as f:
        f.write(d)


class PKG:
    """Leitor de PKG de PS3 (formato público: cabeçalho big-endian, conteúdo em AES-128-CTR)."""

    def __init__(self, caminho):
        self.caminho = caminho
        with open(caminho, "rb") as f:
            cab = f.read(0x100)
        if cab[:4] != b"\x7fPKG":
            raise ValueError("Esse arquivo não é um PKG de PS3.")
        (self.rev, self.tipo, _mdofs, _mdcnt, _hdr, self.n_itens, _total, self.dataofs,
         self.datasize) = struct.unpack_from(">HHIIIIQQQ", cab, 4)
        self.content_id = cab[0x30:0x60].split(b"\0")[0].decode("latin-1")
        self.digest = cab[0x60:0x70]
        self.riv = int.from_bytes(cab[0x70:0x80], "big")
        self.debug = (self.rev & 0x8000) == 0
        if self.tipo != 1:
            raise ValueError("Esse PKG não é de PS3 (é de PSP/PS Vita).")
        self.title_id = self.content_id[7:16] if len(self.content_id) >= 16 else ""
        tabela = self._ler(0, self.n_itens * 32, 0)
        self.itens = []
        for i in range(self.n_itens):
            n_ofs, n_tam, d_ofs, d_tam, flags, _pad = struct.unpack_from(">IIQQII", tabela, i * 32)
            nome = bytes(self._ler(n_ofs, n_tam, 0)).split(b"\0")[0].decode("utf-8", "replace")
            pasta = (flags & 0xFF) in (0x04, 0x12)
            self.itens.append({"nome": nome, "ofs": d_ofs, "tam": d_tam, "pasta": pasta,
                               "chave": (flags >> 28) & 0x7})

    def _fluxo(self, ofs, tam, chave):
        """Bytes de chave (keystream) do CTR para [ofs, ofs+tam), com ofs alinhado em 16."""
        if self.debug:
            import hashlib
            base = bytearray(0x40)
            base[0x00:0x08] = self.digest[0:8]
            base[0x08:0x10] = self.digest[0:8]
            base[0x10:0x18] = self.digest[8:16]
            base[0x18:0x20] = self.digest[8:16]
            cont = int.from_bytes(base, "big") + ofs // 16
            out = bytearray()
            for i in range((tam + 15) // 16):
                out += hashlib.sha1((cont + i).to_bytes(0x40, "big")).digest()[:16]
            return bytes(out[:tam])
        from Crypto.Cipher import AES
        aes = AES.new(PKG_CHAVES.get(chave, PKG_CHAVES[0]), AES.MODE_CTR, nonce=b"",
                      initial_value=(self.riv + ofs // 16) & ((1 << 128) - 1))
        return aes.encrypt(bytes(tam))

    def _ler(self, ofs, tam, chave):
        inicio = ofs - (ofs % 16)
        extra = ofs - inicio
        with open(self.caminho, "rb") as f:
            f.seek(self.dataofs + inicio)
            bruto = f.read(tam + extra)
        fluxo = self._fluxo(inicio, len(bruto), chave)
        return bytes(a ^ b for a, b in zip(bruto, fluxo))[extra:] if len(bruto) < 4096 else \
            (int.from_bytes(bruto, "big") ^ int.from_bytes(fluxo, "big")).to_bytes(len(bruto), "big")[extra:]

    def extrair(self, destino, progresso=None, cancelar=None, bloco=4 * 1024 * 1024):
        from Crypto.Cipher import AES
        total = sum(i["tam"] for i in self.itens if not i["pasta"]) or 1
        feito = 0
        with open(self.caminho, "rb") as f:
            for it in self.itens:
                rel = it["nome"].replace("\\", "/").lstrip("/")
                if ".." in rel.split("/"):
                    continue  # nome perigoso: ignora
                alvo = os.path.join(destino, *rel.split("/"))
                if it["pasta"]:
                    os.makedirs(alvo, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(alvo), exist_ok=True)
                sobra = it["ofs"] % 16          # o CTR anda em blocos de 16: começa do bloco inteiro
                f.seek(self.dataofs + it["ofs"] - sobra)
                restante, ofs = it["tam"] + sobra, it["ofs"] - sobra
                if self.debug:
                    decifra = None
                else:
                    decifra = AES.new(PKG_CHAVES.get(it["chave"], PKG_CHAVES[0]), AES.MODE_CTR, nonce=b"",
                                      initial_value=(self.riv + ofs // 16) & ((1 << 128) - 1))
                with open(alvo, "wb") as out:
                    while restante > 0:
                        if cancelar is not None and cancelar.is_set():
                            raise Cancelado2()
                        n = min(bloco, restante)
                        dados = f.read(n)
                        if decifra is not None:
                            claro = decifra.decrypt(dados)
                        else:
                            fl = self._fluxo(ofs, len(dados), 0)
                            claro = (int.from_bytes(dados, "big") ^ int.from_bytes(fl, "big")).to_bytes(len(dados), "big")
                        out.write(claro[sobra:])
                        feito += n - sobra
                        sobra = 0
                        restante -= n
                        ofs += n
                        if progresso:
                            progresso(feito / total)


def ferramenta(nome):
    return recurso(nome + (".exe" if WIN else ""))


def criar_iso(pasta_jogo, iso_saida, progresso=None, cancelar=None):
    """Roda o makeps3iso (Estwald, GPLv3) e acompanha a porcentagem."""
    import re
    import subprocess
    exe = ferramenta("makeps3iso")
    if not os.path.exists(exe):
        raise RuntimeError("Ferramenta makeps3iso não encontrada.")
    proc = subprocess.Popen([exe, "-p0", pasta_jogo, iso_saida], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, creationflags=0x08000000 if WIN else 0)
    texto = b""
    while True:
        if cancelar is not None and cancelar.is_set():
            proc.kill()
            proc.wait()
            raise Cancelado2()
        pedaco = proc.stdout.read1(256) if hasattr(proc.stdout, "read1") else proc.stdout.read(256)
        if not pedaco:
            break
        texto += pedaco
        m = re.findall(rb"Percent done:\s*(\d+)%", texto[-200:])
        if m and progresso:
            progresso(min(1.0, int(m[-1]) / 100))
    proc.wait()
    if proc.returncode != 0 or not os.path.exists(iso_saida):
        msg = texto.decode("latin-1", "ignore").strip().splitlines()
        raise RuntimeError(next((l for l in msg if "rror" in l), "a ferramenta não conseguiu criar a ISO"))
    return iso_saida


def nome_iso(titulo, title_id):
    limpo = "".join(c for c in titulo if c not in '<>:"/\\|?*').strip() or "Jogo"
    return f"{limpo} [{title_id}].iso" if title_id else f"{limpo}.iso"


def analisar_fonte(caminho):
    """Descobre o que é a fonte e se dá para converter. Devolve dict com tipo, título, id, aviso, ok."""
    if os.path.isdir(caminho):
        if os.path.basename(os.path.normpath(caminho)).upper() == "PS3_GAME":
            caminho = os.path.dirname(os.path.normpath(caminho))
        sfo = ler_sfo(os.path.join(caminho, "PS3_GAME", "PARAM.SFO"))
        if not sfo:
            return {"ok": False, "aviso": "Essa pasta não tem PS3_GAME/PARAM.SFO. Escolha a pasta do jogo "
                                          "(a que tem PS3_GAME dentro)."}
        return {"ok": True, "tipo": "pasta", "caminho": caminho, "titulo": sfo.get("TITLE", "Jogo"),
                "id": sfo.get("TITLE_ID", ""), "tam": tamanho_item(caminho), "aviso": None}
    try:
        pkg = PKG(caminho)
    except ValueError as e:
        return {"ok": False, "aviso": str(e)}
    except Exception as e:
        return {"ok": False, "aviso": f"Não consegui ler o PKG ({str(e)[:60]})"}
    tid = pkg.title_id
    sfo_item = next((i for i in pkg.itens if i["nome"].upper() in ("PARAM.SFO", "PS3_GAME/PARAM.SFO")), None)
    titulo, categoria = tid or "Jogo", ""
    if sfo_item and sfo_item["tam"] < 64 * 1024:
        import tempfile
        bruto = pkg._ler(sfo_item["ofs"], sfo_item["tam"], sfo_item["chave"])
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sfo") as t:
            t.write(bruto)
        sfo = ler_sfo(t.name)
        os.unlink(t.name)
        titulo, categoria = sfo.get("TITLE", titulo), sfo.get("CATEGORY", "")
        tid = sfo.get("TITLE_ID", tid)
    info = {"tipo": "pkg", "caminho": caminho, "titulo": titulo, "id": tid, "tam": os.path.getsize(caminho),
            "categoria": categoria, "pkg": pkg, "ok": True, "aviso": None}
    if tid.startswith("NP"):
        info.update(ok=False, aviso="Jogo da PSN (NP…): não existe versão em disco, então não dá para virar ISO. "
                                     "Envie o PKG para o PS3 e instale normalmente.")
    elif categoria == "GD":
        info.update(ok=False, aviso="Esse PKG é uma atualização (patch), não o jogo completo. Instale pelo PS3.")
    elif not sfo_item:
        info.update(ok=False, aviso="Esse PKG não tem PARAM.SFO de jogo, então não dá para virar ISO.")
    else:
        info["aviso"] = "Experimental: funciona com jogos de disco que foram empacotados em PKG."
    return info


def converter_para_iso(info, pasta_destino, progresso, cancelar):
    """Faz a conversão e devolve o caminho da ISO criada."""
    import shutil
    import tempfile
    iso = os.path.join(pasta_destino, nome_iso(info["titulo"], info["id"]))
    if info["tipo"] == "pasta":
        progresso(0.0, "Criando a ISO…")
        return criar_iso(info["caminho"], iso, lambda f: progresso(f, "Criando a ISO…"), cancelar)
    tmp = tempfile.mkdtemp(prefix="PSTudo_", dir=pasta_destino)
    try:
        jogo = os.path.join(tmp, info["id"] or "JOGO")
        base = os.path.join(jogo, "PS3_GAME")
        pkg = info["pkg"]
        com_ps3_game = any(i["nome"].upper().startswith("PS3_GAME/") for i in pkg.itens)
        pkg.extrair(jogo if com_ps3_game else base, lambda f: progresso(f * 0.5, "Abrindo o PKG…"), cancelar)
        sfo = os.path.join(base, "PARAM.SFO")
        if ler_sfo(sfo).get("CATEGORY") == "HG":
            trocar_sfo(sfo, "CATEGORY", "DG")    # jogo de HD -> jogo de disco
        if not os.path.exists(os.path.join(jogo, "PS3_DISC.SFB")):
            criar_sfb(os.path.join(jogo, "PS3_DISC.SFB"), info["id"])
        return criar_iso(jogo, iso, lambda f: progresso(0.5 + f * 0.5, "Criando a ISO…"), cancelar)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


class Conversor:
    def abrir_conversor(self):
        if getattr(self, "_cv_janela", None) and self._cv_janela.winfo_exists():
            self._cv_janela.focus()
            return
        j = self._janela("Converter para ISO", 520, 470)
        self._cv_janela = j
        f_tit = ctk.CTkFont(family=F_LIGHT, size=22)
        f_txt = ctk.CTkFont(family=F_REG, size=12)
        f_nome = ctk.CTkFont(family=F_SEMI, size=15)
        ctk.CTkLabel(j, text="Converter para ISO", font=f_tit, text_color=BRANCO).pack(anchor="w", padx=24,
                                                                                       pady=(20, 2))
        ctk.CTkLabel(j, text="Transforme um jogo em pasta (BLUS, BLES…) ou um PKG em ISO, o formato mais prático "
                             "para o webMAN.", font=f_txt, text_color=CINZA, wraplength=470,
                     justify="left").pack(anchor="w", padx=24)
        lin = ctk.CTkFrame(j, fg_color="transparent")
        lin.pack(fill="x", padx=24, pady=(14, 8))
        b_pasta = self._cn_btn(lin, "Escolher pasta do jogo", lambda: escolher("pasta"), largura=200, altura=38)
        b_pasta.pack(side="left")
        b_pkg = self._cn_btn(lin, "Escolher PKG", lambda: escolher("pkg"), largura=150, altura=38)
        b_pkg.pack(side="left", padx=10)
        cartao = ctk.CTkFrame(j, fg_color="#0F1A30", corner_radius=12)
        cartao.pack(fill="x", padx=24, pady=(4, 8))
        lb_nome = ctk.CTkLabel(cartao, text="Nenhum jogo escolhido", font=f_nome, text_color=BRANCO, anchor="w")
        lb_nome.pack(anchor="w", padx=14, pady=(10, 0))
        lb_info = ctk.CTkLabel(cartao, text="", font=f_txt, text_color=CINZA, anchor="w", wraplength=440,
                               justify="left")
        lb_info.pack(anchor="w", padx=14, pady=(0, 10))
        lin2 = ctk.CTkFrame(j, fg_color="transparent")
        lin2.pack(fill="x", padx=24)
        destino = {"pasta": self.cfg.get("iso_destino", "")}
        lb_dest = ctk.CTkLabel(lin2, text="", font=f_txt, text_color=CINZA, anchor="w")
        lb_dest.pack(side="left", fill="x", expand=True)

        def mostrar_destino():
            d = destino["pasta"]
            curto = d if len(d) <= 52 else "…" + d[-50:]
            lb_dest.configure(text=f"Salvar em: {curto}" if d else "Salvar em: mesma pasta do jogo")
        mostrar_destino()

        def mudar_destino():
            d = filedialog.askdirectory(title="Onde salvar a ISO", parent=j)
            if d:
                destino["pasta"] = d
                self.cfg["iso_destino"] = d
                mostrar_destino()
        self._cn_btn(lin2, "Mudar", mudar_destino, largura=80, altura=30).pack(side="right")
        sw_fila = ctk.CTkSwitch(j, text="Colocar na lista para enviar ao PS3 quando terminar", font=f_txt,
                                progress_color="#0070D1")
        if self.cfg.get("iso_para_fila", True):
            sw_fila.select()
        sw_fila.pack(anchor="w", padx=24, pady=(12, 6))
        barra = ctk.CTkProgressBar(j, height=10, corner_radius=5, progress_color="#1888F0", fg_color="#22304D")
        barra.set(0)
        barra.pack(fill="x", padx=24, pady=(8, 2))
        lb_status = ctk.CTkLabel(j, text="", font=f_txt, text_color=CINZA, anchor="w")
        lb_status.pack(fill="x", padx=24)
        rod = ctk.CTkFrame(j, fg_color="transparent")
        rod.pack(side="bottom", fill="x", padx=24, pady=18)
        b_conv = self._cn_btn(rod, "Converter", lambda: converter(), "azul", 140, 40)
        b_conv.pack(side="right")
        b_canc = self._cn_btn(rod, "Fechar", lambda: cancelar_ou_fechar(), "normal", 110, 40)
        b_canc.pack(side="right", padx=(0, 10))
        b_conv.configure(state="disabled")
        estado = {"info": None, "rodando": False, "cancelar": threading.Event()}

        def escolher(tipo):
            if estado["rodando"]:
                return
            if tipo == "pasta":
                c = filedialog.askdirectory(title="Pasta do jogo (a que tem PS3_GAME dentro)", parent=j)
            else:
                c = filedialog.askopenfilename(title="PKG do jogo", parent=j, filetypes=[("PKG de PS3", "*.pkg")])
            if not c:
                return
            lb_nome.configure(text="Analisando…")
            lb_info.configure(text="", text_color=CINZA)

            def tarefa():
                info = analisar_fonte(c)
                self.fila.put(("cb", lambda: mostrar(info)))
            threading.Thread(target=tarefa, daemon=True).start()

        def mostrar(info):
            if not j.winfo_exists():
                return
            estado["info"] = info
            if not info.get("titulo"):
                lb_nome.configure(text="Não dá para converter")
            else:
                lb_nome.configure(text=info["titulo"][:48])
            detalhes = []
            if info.get("id"):
                detalhes.append(info["id"])
            if info.get("tam"):
                detalhes.append(formatar_tamanho(info["tam"]))
            if info.get("tipo"):
                detalhes.append("Pasta de jogo" if info["tipo"] == "pasta" else "PKG")
            txt = "  •  ".join(detalhes)
            if info.get("aviso"):
                txt += ("\n" if txt else "") + info["aviso"]
            lb_info.configure(text=txt, text_color=CINZA if info["ok"] and not info.get("aviso") else
                              ("#FBBF24" if info["ok"] else "#F87171"))
            b_conv.configure(state="normal" if info["ok"] else "disabled")
            barra.set(0)
            lb_status.configure(text="")

        def cancelar_ou_fechar():
            if estado["rodando"]:
                estado["cancelar"].set()
                lb_status.configure(text="Cancelando…")
            else:
                j.destroy()

        def converter():
            info = estado["info"]
            if not info or not info["ok"] or estado["rodando"]:
                return
            pasta = destino["pasta"] or os.path.dirname(os.path.normpath(info["caminho"]))
            import shutil
            precisa = info["tam"] * (2 if info["tipo"] == "pkg" else 1) + 64 * 1024 * 1024
            try:
                livre = shutil.disk_usage(pasta).free
            except OSError:
                livre = precisa
            if livre < precisa:
                lb_status.configure(text=f"Pouco espaço: precisa de uns {formatar_tamanho(precisa)} livres em "
                                         f"{pasta}.", text_color="#F87171")
                return
            self.cfg["iso_para_fila"] = bool(sw_fila.get())
            self.salvar_cfg()
            estado.update(rodando=True)
            estado["cancelar"].clear()
            b_conv.configure(state="disabled")
            b_pasta.configure(state="disabled")
            b_pkg.configure(state="disabled")
            b_canc.configure(text="Cancelar")
            lb_status.configure(text="Começando…", text_color=CINZA)

            def prog(f, txt):
                self.fila.put(("cb", lambda: (barra.set(f), lb_status.configure(text=f"{txt} {int(f * 100)}%"))
                               if j.winfo_exists() else None))

            def tarefa():
                try:
                    iso = converter_para_iso(info, pasta, prog, estado["cancelar"])
                    self.fila.put(("cb", lambda: fim(iso, None)))
                except Cancelado2:
                    self.fila.put(("cb", lambda: fim(None, "cancelado")))
                except Exception as e:
                    self.fila.put(("cb", lambda e=e: fim(None, str(e))))
            threading.Thread(target=tarefa, daemon=True).start()

        def fim(iso, erro):
            estado["rodando"] = False
            if j.winfo_exists():
                b_pasta.configure(state="normal")
                b_pkg.configure(state="normal")
                b_canc.configure(text="Fechar")
                b_conv.configure(state="normal")
            if iso:
                if j.winfo_exists():
                    barra.set(1)
                    lb_status.configure(text=f"Pronto! {os.path.basename(iso)}", text_color="#34D399")
                self._som_fim()
                if self.cfg.get("iso_para_fila", True):
                    self._adicionar(iso)
                    if self.aba == "enviar" and not self.enviando:
                        self.tela_inicio()
                    self._aviso_app("ISO criada e colocada na lista de envio!")
                else:
                    self._aviso_app("ISO criada!")
            elif erro == "cancelado":
                if j.winfo_exists():
                    barra.set(0)
                    lb_status.configure(text="Conversão cancelada.", text_color=CINZA)
            else:
                if j.winfo_exists():
                    lb_status.configure(text=f"Não deu certo: {erro[:80]}", text_color="#F87171")


# =============================================================== atalhos
ATALHOS_PADRAO = {"fsr": "f", "interp": "i"}
ATALHOS_NOMES = {"fsr": "Ligar/desligar FSR (tela cheia)", "interp": "Trocar interpolação (tela cheia)"}
_TK_PARA_PYGAME = {"return": "return", "space": "space", "tab": "tab", "backspace": "backspace",
                   "insert": "insert", "delete": "delete", "home": "home", "end": "end", "prior": "page up",
                   "next": "page down", "up": "up", "down": "down", "left": "left", "right": "right",
                   "pause": "pause", "scroll_lock": "scroll lock"}


def tecla_tk_para_nome(keysym):
    """Converte a tecla do Tk para o nome usado pelo pygame. None = tecla não permitida."""
    k = keysym.lower()
    if k in ("escape",) or k.startswith(("shift", "control", "alt", "super", "win", "caps", "num_lock", "kp_")):
        return None
    if len(k) == 1 and (k.isalnum() or k in "-=[];',./\\`"):
        return k
    if k.startswith("f") and k[1:].isdigit() and 1 <= int(k[1:]) <= 24:
        return k
    return _TK_PARA_PYGAME.get(k)


def nome_bonito(tecla):
    if not tecla:
        return "—"
    return tecla.upper() if len(tecla) <= 3 else tecla.title()


# =============================================================== app
class App(Extras, Console, Controles, Tela, Conversor):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk()
        self.root.title(APP_NOME)
        try:
            escala = ctk.ScalingTracker.get_window_dpi_scaling(self.root)
        except Exception:
            escala = 1.0
        self.escala_base = escala
        self.p = Pintor(escala)
        p = self.p
        self.root.configure(fg_color="#050B18")
        self.c = tk.Canvas(self.root, width=p.px(W), height=p.px(H), highlightthickness=0, bd=0, bg="#050b18")
        self.c.pack(expand=True)
        self._icone = ImageTk.PhotoImage(icone_app(64))
        self.root.iconphoto(True, self._icone)

        self.cfg = self.carregar_cfg()
        self.jogos = []
        self.estado_ps3 = "busca"
        self.fila = queue.Queue()
        self.cancelar = threading.Event()
        self.enviando = False
        self.aba = "enviar"
        self.widgets = []
        self.raps = []
        self.fm_path = "/dev_hdd0"
        self.fm_sel = None
        self.fm_itens = []
        self.fm_todos = []
        self.fm_busca_id = 0
        self.fm_modo_fundo = False
        self.op_ativa = False

        self._montar_base()
        self.root.bind_all("<KeyPress>", self._tecla_app, add="+")
        # o botão de maximizar fica ativo; a interface cresce junto com a janela
        # tamanho fixo pedido pelo app (sem a escala automática do CTk): assim, ao sair do "maximizado",
        # a janela volta ao tamanho normal em vez de ficar do tamanho da interface ampliada
        tk.Wm.wm_geometry(self.root, f"{p.px(W)}x{p.px(H)}")
        tk.Wm.wm_minsize(self.root, int(p.px(W) * 0.6), int(p.px(H) * 0.6))
        self.root.bind("<Configure>", self._janela_mudou, add="+")

        self.tela_inicio()
        self.root.after(50, self.ler_fila)
        self.root.after(300, self.buscar_ps3)
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)

    def _montar_base(self):
        """Fundo, título, crédito, status do PS3 e abas (refeito ao mudar o tamanho)."""
        p, estado = self.p, self.estado_ps3
        self.bg = p.fundo(W, H)
        self.c.create_image(0, 0, image=self.bg, anchor="nw")
        self.c.create_text(p.px(48), p.px(54), text=APP_NOME, anchor="w", fill=BRANCO,
                           font=(F_LIGHT, -p.px(30)))
        self.c.create_text(p.px(W - 24), p.px(H - 9), text="Feito por MrKitanoX usando o Claude", anchor="e",
                           fill=CINZA_ESCURO, font=(F_REG, -p.px(11)))
        self._montar_status()
        self._montar_abas()
        self.atualizar_status(estado)

    # ---------------- config
    def carregar_cfg(self):
        padrao = {"ip": "", "porta": 21, "usuario": "anonymous", "senha": "", "destino": "Automático", "pular": True}
        for arq in (CONFIG, CONFIG_ANTIGA):   # aproveita as configurações da versão antiga
            try:
                with open(arq, encoding="utf-8") as f:
                    padrao.update(json.load(f))
                break
            except (OSError, ValueError):
                continue
        return padrao

    def salvar_cfg(self):
        dados = {k: v for k, v in self.cfg.items() if k != "senha"}
        try:
            with open(CONFIG, "w", encoding="utf-8") as f:
                json.dump(dados, f)
        except OSError:
            pass

    # ---------------- status do PS3 (canto superior direito)
    def _montar_status(self):
        p, c = self.p, self.c
        self.pill_w = 168
        x = W - 48 - 44 - 12 - self.pill_w / 2
        self.pill_imgs = {k: p.ret(self.pill_w, 40, 20, (14, 24, 46, 220), outline=(255, 255, 255, 40), largura=1)
                          for k in ("ok", "busca", "erro")}
        self.pill = c.create_image(p.px(x), p.px(56), image=self.pill_imgs["busca"], tags=("pill",))
        self.pill_ponto = c.create_oval(0, 0, 0, 0, outline="", tags=("pill",))
        self.pill_tx = c.create_text(p.px(x - self.pill_w / 2 + 34), p.px(56), anchor="w", fill=BRANCO,
                                     font=(F_REG, -p.px(13)), tags=("pill",))
        self._pill_x = x
        c.tag_bind("pill", "<Enter>", lambda e: c.config(cursor="hand2"))
        c.tag_bind("pill", "<Leave>", lambda e: c.config(cursor=""))
        c.tag_bind("pill", "<Button-1>", lambda e: self.abrir_config())
        # botão engrenagem
        gx = W - 48 - 22
        self.eng_n = p.ret(44, 44, 22, (14, 24, 46, 220), outline=(255, 255, 255, 40), largura=1)
        self.eng_h = p.ret(44, 44, 22, (30, 44, 74, 235), outline=(255, 255, 255, 120), largura=1)
        self.eng = c.create_image(p.px(gx), p.px(56), image=self.eng_n, tags=("eng",))
        c.create_text(p.px(gx), p.px(56), text="⚙", fill=BRANCO, font=(F_SYM, -p.px(19)), tags=("eng",))
        c.tag_bind("eng", "<Enter>", lambda e: (c.itemconfig(self.eng, image=self.eng_h), c.config(cursor="hand2")))
        c.tag_bind("eng", "<Leave>", lambda e: (c.itemconfig(self.eng, image=self.eng_n), c.config(cursor="")))
        c.tag_bind("eng", "<Button-1>", lambda e: self.abrir_config())
        self.atualizar_status("busca")

    def atualizar_status(self, estado):
        self.estado_ps3 = estado
        textos = {"ok": "PS3 conectado", "busca": "Procurando o PS3…", "erro": "PS3 não encontrado"}
        cores = {"ok": "#34D399", "busca": "#FBBF24", "erro": "#F87171"}
        p = self.p
        cx, cy, r = self._pill_x - self.pill_w / 2 + 20, 56, 4.5
        self.c.coords(self.pill_ponto, p.px(cx - r), p.px(cy - r), p.px(cx + r), p.px(cy + r))
        self.c.itemconfig(self.pill_ponto, fill=cores[estado])
        self.c.itemconfig(self.pill_tx, text=textos[estado])
        if getattr(self, "btn_enviar", None) and not self.enviando:
            pronto = bool(self.raps) if self.aba == "rap" else bool(self.jogos)
            self.btn_enviar.set_ativo(estado == "ok" and pronto)
        if estado == "ok" and getattr(self, "aba", "") == "arquivos" and getattr(self, "fm_desconectado", False):
            self.fm_listar()
        if getattr(self, "aba", "") == "console" and self._cn_ativo():
            self._cn_botoes()
            if estado == "ok" and self.cn_dados is None:
                self.carregar_console()

    def buscar_ps3(self):
        self.atualizar_status("busca")

        def tarefa():
            ip = procurar_ps3(self.cfg.get("porta", 21), self.cfg.get("ip"))
            self.fila.put(("ps3", ip))
        threading.Thread(target=tarefa, daemon=True).start()

    def _tentar_de_novo(self):
        if self.estado_ps3 == "erro" and not self.enviando:
            self.buscar_ps3()

    def checar_periodico(self):
        if self.enviando or self.estado_ps3 != "ok":
            return

        def tarefa():
            ok = testar_ftp(self.cfg["ip"], self.cfg.get("porta", 21), 2)
            self.fila.put(("check", bool(ok)))
        threading.Thread(target=tarefa, daemon=True).start()

    # ---------------- telas
    def limpar(self):
        self.c.delete("view")
        self.btn_enviar = None
        self.vendo_envio = False
        for w_ in self.widgets:
            try:
                w_.destroy()
            except Exception:
                pass
        self.widgets = []

    def tela_inicio(self):
        self.limpar()
        p, c = self.p, self.c
        if not self.jogos:
            c.create_text(p.px(W / 2), p.px(168), text="O que você quer enviar?", fill=BRANCO,
                          font=(F_LIGHT, -p.px(26)), tags="view")
            Cartao(self, W / 2 - 284, 340, 268, 230, "pasta", "Pasta do jogo", "Jogos em pasta (BLUS, BLES…)",
                   self.add_pasta)
            Cartao(self, W / 2, 340, 268, 230, "disco", "ISO ou PKG", "Imagens de disco e pacotes", self.add_arquivo)
            Cartao(self, W / 2 + 284, 340, 268, 230, "iso", "Converter para ISO", "Pasta ou PKG → ISO",
                   self.abrir_conversor)
            self.btn_enviar = None
            return

        n = len(self.jogos)
        c.create_text(p.px(W / 2), p.px(150), text="Pronto para enviar" if n else "", fill=BRANCO,
                      font=(F_LIGHT, -p.px(26)), tags="view")
        total = sum(j["tamanho"] for j in self.jogos)
        c.create_text(p.px(W / 2), p.px(182), fill=CINZA, font=(F_REG, -p.px(14)), tags="view",
                      text=f"{n} {'jogo' if n == 1 else 'jogos'} • {formatar_tamanho(total)}")
        lw, lh, y0 = 620, 58, 232
        linha = p.ret(lw, lh, 16, (255, 255, 255, 13), outline=(255, 255, 255, 30), largura=1)
        for i, j in enumerate(self.jogos[:4]):
            y = y0 + i * (lh + 10)
            c.create_image(p.px(W / 2), p.px(y), image=linha, tags="view")
            nome = j["nome"] if len(j["nome"]) <= 48 else j["nome"][:46] + "…"
            c.create_text(p.px(W / 2 - lw / 2 + 24), p.px(y), anchor="w", text=nome, fill=BRANCO,
                          font=(F_REG, -p.px(16)), tags="view")
            c.create_text(p.px(W / 2 + lw / 2 - 64), p.px(y), anchor="e", text=formatar_tamanho(j["tamanho"]),
                          fill=CINZA, font=(F_REG, -p.px(13)), tags="view")
            tg = f"rm{i}"
            c.create_text(p.px(W / 2 + lw / 2 - 30), p.px(y), text="✕", fill=CINZA,
                          font=(F_SYM, -p.px(15)), tags=("view", tg))
            c.tag_bind(tg, "<Enter>", lambda e, t=tg: (c.itemconfig(t, fill=BRANCO), c.config(cursor="hand2")))
            c.tag_bind(tg, "<Leave>", lambda e, t=tg: (c.itemconfig(t, fill=CINZA), c.config(cursor="")))
            c.tag_bind(tg, "<Button-1>", lambda e, k=i: (c.config(cursor=""), self.remover(k)))
        if n > 4:
            c.create_text(p.px(W / 2), p.px(y0 + 4 * (lh + 10) - 8), text=f"+ {n - 4} outros", fill=CINZA,
                          font=(F_REG, -p.px(13)), tags="view")
        yb = 530
        x_esq = W / 2 - 310
        Botao(self, x_esq + 62, yb, 124, 48, "+ Pasta", self.add_pasta, "secundario")
        Botao(self, x_esq + 62 + 132, yb, 124, 48, "+ ISO ou PKG", self.add_arquivo, "secundario")
        Botao(self, x_esq + 62 + 264, yb, 124, 48, "→ ISO", self.abrir_conversor, "secundario")
        self.btn_enviar = Botao(self, W / 2 + 310 - 110, yb, 220, 54, "Enviar para o PS3", self.iniciar_envio,
                                tamanho_fonte=16)
        self.btn_enviar.set_ativo(self.estado_ps3 == "ok")

    def tela_enviando(self):
        self.limpar()
        p, c = self.p, self.c
        self.tx_jogo = c.create_text(p.px(W / 2), p.px(196), text="Preparando…", fill=BRANCO,
                                     font=(F_LIGHT, -p.px(28)), tags="view")
        self.tx_sub = c.create_text(p.px(W / 2), p.px(232), text="", fill=CINZA, font=(F_REG, -p.px(14)), tags="view")
        self.tx_pct = c.create_text(p.px(W / 2), p.px(318), text="0%", fill=BRANCO,
                                    font=(F_LIGHT, -p.px(64)), tags="view")
        self.bar_w, self.bar_h, self.bar_y = 560, 10, 392
        c.create_image(p.px(W / 2), p.px(self.bar_y), tags="view",
                       image=p.ret(self.bar_w, self.bar_h, 5, (255, 255, 255, 28)))
        self.bar_fill = c.create_image(p.px(W / 2 - self.bar_w / 2), p.px(self.bar_y), anchor="w", tags="view")
        self._bar_img = None
        self._ult_bar = -1
        self.tx_rest = c.create_text(p.px(W / 2), p.px(430), text="Calculando o tempo…", fill=CINZA,
                                     font=(F_REG, -p.px(14)), tags="view")
        Botao(self, W / 2, 520, 180, 48, "Cancelar", self.cancelar.set, "secundario")
        self.vendo_envio = True
        if getattr(self, "ultimo_prog", None):
            self._progresso(self.ultimo_prog)

    def _atualizar_barra(self, frac):
        p = self.p
        w = max(self.bar_h, round(self.bar_w * frac))
        if w == self._ult_bar:
            return
        self._ult_bar = w
        k = 4
        g = p.px(14)
        img = Image.new("RGBA", (p.px(w) + 2 * g, p.px(self.bar_h) + 2 * g), (0, 0, 0, 0))
        gl = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(gl).rounded_rectangle([g, g, g + p.px(w), g + p.px(self.bar_h)], p.px(5), fill=(0, 130, 255, 150))
        img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(g / 2.5)))
        big = Image.new("RGBA", (img.size[0] * k, img.size[1] * k), (0, 0, 0, 0))
        grad = Image.new("RGBA", (256, 1))
        for x in range(256):
            t = x / 255
            grad.putpixel((x, 0), (int(0 + 70 * t), int(100 + 90 * t), int(220 + 35 * t), 255))
        grad = grad.resize((p.px(w) * k, p.px(self.bar_h) * k))
        mask = Image.new("L", grad.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, grad.size[0] - 1, grad.size[1] - 1], p.px(5) * k, fill=255)
        big.paste(grad, (g * k, g * k), mask)
        img = Image.alpha_composite(img, big.resize(img.size, Image.LANCZOS))
        self._bar_img = ImageTk.PhotoImage(img)
        self.c.itemconfig(self.bar_fill, image=self._bar_img)
        self.c.coords(self.bar_fill, p.px(W / 2 - self.bar_w / 2) - g, p.px(self.bar_y))

    def tela_final(self, sucesso, titulo, sub, extra=None, acao_ok=None, texto_ok="Enviar mais jogos",
                   acao_tentar=None, acao_voltar=None):
        self.limpar()
        p, c = self.p, self.c
        c.create_image(p.px(W / 2), p.px(250), tags="view",
                       image=p.ret(120, 120, 60, (0, 0, 0, 0), icone="check" if sucesso else "alerta", icone_y=0.5))
        c.create_text(p.px(W / 2), p.px(336), text=titulo, fill=BRANCO, font=(F_LIGHT, -p.px(30)), tags="view")
        c.create_text(p.px(W / 2), p.px(378), text=sub, fill=CINZA, font=(F_REG, -p.px(15)), tags="view", width=p.px(620),
                      justify="center")
        if extra:
            c.create_text(p.px(W / 2), p.px(412), text=extra, fill=CINZA_ESCURO, font=(F_REG, -p.px(12)), tags="view",
                          width=p.px(620), justify="center")
        if sucesso:
            Botao(self, W / 2, 500, 220, 52, texto_ok, acao_ok or self.recomecar)
        else:
            Botao(self, W / 2 - 115, 500, 210, 52, "Tentar de novo", acao_tentar or self.iniciar_envio)
            Botao(self, W / 2 + 115, 500, 210, 52, "Voltar", acao_voltar or self.tela_inicio, "secundario")

    # ---------------- ações
    def _adicionar(self, item):
        if any(os.path.normpath(j["item"]) == os.path.normpath(item) for j in self.jogos):
            return
        self.jogos.append({"item": item, "nome": nome_amigavel(item), "tamanho": tamanho_item(item)})

    def add_pasta(self):
        pasta = filedialog.askdirectory(title="Escolha a pasta do jogo", parent=self.root)
        if pasta:
            self._adicionar(pasta)
            self.tela_inicio()

    def add_arquivo(self):
        arqs = filedialog.askopenfilenames(title="Escolha os arquivos", parent=self.root,
                                           filetypes=[("Jogos e pacotes", "*.iso *.pkg *.bin *.cue"), ("Todos", "*.*")])
        for a in arqs:
            self._adicionar(a)
        if arqs:
            self.tela_inicio()

    def remover(self, k):
        if 0 <= k < len(self.jogos):
            self.jogos.pop(k)
        self.tela_inicio()

    def recomecar(self):
        self.jogos = []
        self.tela_inicio()

    def iniciar_envio(self):
        if self.enviando or not self.jogos:
            return
        self.enviando = True
        self.ultimo_prog = None
        self.envio_pendente = None
        self.cancelar.clear()
        self.salvar_cfg()
        self.tela_enviando()
        self._atualizar_aba_envio(0.0)
        threading.Thread(target=trabalho_envio, args=(list(self.jogos), dict(self.cfg), self.cancelar,
                                                      lambda t, d: self.fila.put((t, d))), daemon=True).start()

    # ---------------- fila de eventos
    def ler_fila(self):
        ultimo_prog = None
        try:
            while True:
                tipo, dados = self.fila.get_nowait()
                if tipo == "progresso":
                    ultimo_prog = dados
                    continue
                self._evento(tipo, dados)
        except queue.Empty:
            pass
        if ultimo_prog and self.enviando:
            self._progresso(ultimo_prog)
        self.root.after(80, self.ler_fila)

    def _progresso(self, d):
        self.ultimo_prog = d
        enviado, total, idx, n, nome, inicio = d
        frac = min(1.0, enviado / total)
        self._atualizar_aba_envio(frac)
        if not getattr(self, "vendo_envio", False):
            return
        c = self.c
        c.itemconfig(self.tx_jogo, text=nome if len(nome) <= 44 else nome[:42] + "…")
        c.itemconfig(self.tx_sub, text=f"Enviando {idx} de {n}" if n > 1 else "Enviando para o PS3")
        c.itemconfig(self.tx_pct, text=f"{int(frac * 100)}%")
        self._atualizar_barra(frac)
        dt = time.time() - inicio
        if dt > 3 and enviado:
            vel = enviado / dt
            rest = (total - enviado) / vel if vel else 0
            c.itemconfig(self.tx_rest, text=f"{formatar_restante(rest)}   ·   {formatar_tamanho(vel)}/s")

    def _evento(self, tipo, dados):
        if tipo == "cb":
            dados()
            return
        if tipo == "ps3":
            if dados:
                self.cfg["ip"] = dados
                self.salvar_cfg()
                self.atualizar_status("ok")
                self.root.after(15000, self._loop_check)
            else:
                self.atualizar_status("erro")
                self.root.after(15000, self._tentar_de_novo)   # o PS3 pode ser ligado depois do app
        elif tipo == "check":
            if not dados:
                self.atualizar_status("erro")
                self.root.after(5000, self.buscar_ps3)
            else:
                self.root.after(15000, self._loop_check)
        elif tipo in ("fim", "erro", "cancelado") and self.aba != "enviar":
            self.enviando = False
            self.ultimo_prog = None
            if tipo == "cancelado":
                self._atualizar_aba_envio(None)
                return
            self.envio_pendente = (tipo, dados)
            if tipo == "fim":
                self._som_fim()
                self._atualizar_aba_envio(None, "Enviado ✓")
                self._aviso_app(f"{dados[0]} {'jogo enviado' if dados[0] == 1 else 'jogos enviados'} para o PS3!")
            else:
                self._atualizar_aba_envio(None, "Erro no envio")
                self._aviso_app("O envio parou. Abra a aba Enviar jogos para ver.", "#F87171")
        elif tipo == "fim":
            if self.enviando:      # não toca de novo ao abrir um resultado que ficou pendente
                self._som_fim()
            self.enviando = False
            self.ultimo_prog = None
            self._atualizar_aba_envio(None)
            n, enviado, tempo = dados
            minutos = max(1, round(tempo / 60))
            self.tela_final(True, "Tudo pronto!",
                            f"{n} {'jogo enviado' if n == 1 else 'jogos enviados'} para o PS3 em {minutos} min.",
                            "Reinicie o webMAN (ou o XMB) se o jogo não aparecer na lista.")
        elif tipo == "cancelado":
            self.enviando = False
            self.ultimo_prog = None
            self._atualizar_aba_envio(None)
            self.tela_inicio()
        elif tipo == "erro":
            self.enviando = False
            self.ultimo_prog = None
            self._atualizar_aba_envio(None)
            titulo, sub = mensagem_erro(dados)
            self.tela_final(False, titulo, sub, f"Detalhe: {str(dados)[:120]}")

    def _loop_check(self):
        self.checar_periodico()

    # ---------------- configurações
    def abrir_config(self):
        if self.enviando:
            return
        if getattr(self, "_janela_cfg", None) and self._janela_cfg.winfo_exists():
            self._janela_cfg.focus()
            return
        j = ctk.CTkToplevel(self.root)
        self._janela_cfg = j
        j.title("Configurações")
        j.geometry("420x670")
        j.resizable(False, False)
        j.configure(fg_color="#0B1324")
        j.transient(self.root)
        j.after(150, j.grab_set)

        fonte_t = ctk.CTkFont(family=F_LIGHT, size=24)
        fonte = ctk.CTkFont(family=F_REG, size=13)
        ctk.CTkLabel(j, text="Configurações", font=fonte_t, text_color=BRANCO).pack(anchor="w", padx=28, pady=(24, 2))
        ctk.CTkLabel(j, text="Só mexa aqui se o PS3 não for encontrado sozinho. O IP aparece no PS3 em "
                             "Configurações › Configurações de Rede › Lista de Configurações e Status da Conexão.",
                     font=fonte, text_color=CINZA, wraplength=364, justify="left").pack(anchor="w", padx=28,
                                                                                       pady=(0, 14))

        def campo(rotulo, valor, mostrar=None):
            ctk.CTkLabel(j, text=rotulo, font=fonte, text_color=CINZA).pack(anchor="w", padx=28)
            e = ctk.CTkEntry(j, height=36, corner_radius=10, fg_color="#111C33", border_color="#26324D",
                             text_color=BRANCO, font=fonte, show=mostrar)
            e.insert(0, str(valor))
            e.pack(fill="x", padx=28, pady=(2, 10))
            return e

        e_ip = campo("IP do PS3", self.cfg.get("ip", ""))
        linha = ctk.CTkFrame(j, fg_color="transparent")
        linha.pack(fill="x", padx=28)
        ctk.CTkLabel(linha, text="Usuário", font=fonte, text_color=CINZA).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(linha, text="Senha", font=fonte, text_color=CINZA).grid(row=0, column=1, sticky="w", padx=(12, 0))
        e_usr = ctk.CTkEntry(linha, height=36, corner_radius=10, fg_color="#111C33", border_color="#26324D", font=fonte)
        e_usr.insert(0, self.cfg.get("usuario", "anonymous"))
        e_usr.grid(row=1, column=0, sticky="ew")
        e_pwd = ctk.CTkEntry(linha, height=36, corner_radius=10, fg_color="#111C33", border_color="#26324D",
                             font=fonte, show="•")
        e_pwd.insert(0, self.cfg.get("senha", ""))
        e_pwd.grid(row=1, column=1, sticky="ew", padx=(12, 0))
        linha.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(j, text="Onde salvar no PS3", font=fonte, text_color=CINZA).pack(anchor="w", padx=28, pady=(12, 0))
        op = ctk.CTkOptionMenu(j, values=DESTINOS, height=36, corner_radius=10, fg_color="#111C33",
                               button_color="#1A2744", button_hover_color="#24365C", font=fonte)
        op.set(self.cfg.get("destino", "Automático"))
        op.pack(fill="x", padx=28, pady=(2, 12))
        sw = ctk.CTkSwitch(j, text="Não reenviar o que já está no PS3", font=fonte, progress_color="#0070D1")
        if self.cfg.get("pular", True):
            sw.select()
        sw.pack(anchor="w", padx=28, pady=(2, 8))
        sw_som = ctk.CTkSwitch(j, text="Tocar um som quando o envio terminar", font=fonte,
                               progress_color="#0070D1", command=lambda: tocar_som() if sw_som.get() else None)
        if self.cfg.get("som_fim", True):
            sw_som.select()
        sw_som.pack(anchor="w", padx=28, pady=(2, 14))

        # ---- atalhos
        ctk.CTkLabel(j, text="Atalhos", font=ctk.CTkFont(family=F_SEMI, size=15), text_color=BRANCO).pack(
            anchor="w", padx=28)
        ctk.CTkLabel(j, text="Clique no botão e aperte a tecla nova. Esc cancela.", font=fonte,
                     text_color=CINZA).pack(anchor="w", padx=28, pady=(0, 6))
        novos = {k: self.atalho(k) for k in ATALHOS_PADRAO}
        botoes_tecla = {}

        def capturar(nome):
            b = botoes_tecla[nome]
            b.configure(text="Aperte…", fg_color="#0070D1")

            def pegou(e):
                j.unbind("<KeyPress>")
                if e.keysym != "Escape":
                    t = tecla_tk_para_nome(e.keysym)
                    if t and t not in [v for k, v in novos.items() if k != nome]:
                        novos[nome] = t
                b.configure(text=nome_bonito(novos[nome]), fg_color="#16233F")
                return "break"
            j.bind("<KeyPress>", pegou)
            b.focus_set()

        for nome, rotulo in ATALHOS_NOMES.items():
            ln = ctk.CTkFrame(j, fg_color="transparent")
            ln.pack(fill="x", padx=28, pady=2)
            ctk.CTkLabel(ln, text=rotulo, font=fonte, text_color=BRANCO).pack(side="left")
            b = ctk.CTkButton(ln, text=nome_bonito(novos[nome]), width=96, height=32, corner_radius=10,
                              fg_color="#16233F", hover_color="#20345C", font=ctk.CTkFont(family=F_SEMI, size=13),
                              command=lambda n=nome: capturar(n))
            b.pack(side="right")
            botoes_tecla[nome] = b

        def salvar():
            self.cfg.update(ip=e_ip.get().strip(), usuario=e_usr.get().strip() or "anonymous",
                            senha=e_pwd.get(), destino=op.get(), pular=bool(sw.get()), som_fim=bool(sw_som.get()))
            for k, v in novos.items():
                self.cfg[f"atalho_{k}"] = v
            if getattr(self, "tl_gpu", None):
                self.tl_gpu.trocar_atalhos({"fsr": self.atalho("fsr"), "interp": self.atalho("interp")})
            self.salvar_cfg()
            j.destroy()
            self.buscar_ps3()

        def procurar():
            self.cfg["ip"] = ""
            j.destroy()
            self.buscar_ps3()

        botoes = ctk.CTkFrame(j, fg_color="transparent")
        botoes.pack(fill="x", padx=28)
        ctk.CTkButton(botoes, text="Procurar de novo", height=40, corner_radius=20, fg_color="transparent",
                      border_width=1, border_color="#3A4660", hover_color="#1A2744", font=fonte,
                      command=procurar).pack(side="left")
        ctk.CTkButton(botoes, text="Salvar", height=40, width=130, corner_radius=20, fg_color="#0070D1",
                      hover_color="#1888F0", font=ctk.CTkFont(family=F_SEMI, size=14),
                      command=salvar).pack(side="right")

    def _som_fim(self):
        if self.cfg.get("som_fim", True):
            tocar_som()

    # ---------------- atalhos
    def atalho(self, nome):
        return self.cfg.get(f"atalho_{nome}", ATALHOS_PADRAO[nome])

    def nome_tecla(self, nome):
        return nome_bonito(self.atalho(nome))

    def _tecla_app(self, e):
        foco = self.root.focus_get()
        if foco is not None and foco.winfo_class() in ("Entry", "Text"):
            return  # digitando em um campo
        nome = tecla_tk_para_nome(e.keysym)
        gpu = getattr(self, "tl_gpu", None)
        if gpu and nome and not (e.state & 0x4 and e.state & 0x1):   # tela cheia aberta e o app em foco
            if nome == self.atalho("fsr"):
                return gpu.alternar_fsr()
            if nome == self.atalho("interp"):
                return gpu.proxima_interp()

    # ---------------- janela maximizada / redimensionada: a interface acompanha o tamanho
    def _janela_mudou(self, e):
        if e.widget is not self.root:
            return
        if getattr(self, "_espera_tam", None):
            self.root.after_cancel(self._espera_tam)
        self._espera_tam = self.root.after(220, self._ajustar_escala)

    def _ajustar_escala(self):
        self._espera_tam = None
        larg, alt = self.root.winfo_width(), self.root.winfo_height()
        if larg < 50 or alt < 50:
            return
        escala = min(larg / W, alt / H)
        if abs(escala - self.p.s) < 0.02:
            return
        if self.op_ativa:               # no meio de uma operação: refaz depois que terminar
            self._espera_tam = self.root.after(500, self._ajustar_escala)
            return
        self._reconstruir(escala)

    def _reconstruir(self, escala):
        self.limpar()
        self.p = Pintor(escala)
        try:
            ctk.set_widget_scaling(escala / self.escala_base)
        except Exception:
            pass
        self.c.delete("all")
        self.c.config(width=self.p.px(W), height=self.p.px(H))
        self.c.pack_configure(expand=True)
        self._montar_base()
        self._mostrar_aba(self.aba)
        if self.enviando and getattr(self, "ultimo_prog", None):
            self._atualizar_aba_envio(min(1.0, self.ultimo_prog[0] / self.ultimo_prog[1]))

    def fechar(self):
        self.tl_parar()
        self.cancelar.set()
        self.salvar_cfg()
        self.root.destroy()

    def rodar(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().rodar()
