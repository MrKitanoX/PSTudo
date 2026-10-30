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
import collections
import json
import math
import os
import queue
import random
import re
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



# =============================================================== idiomas
# As frases do app estão escritas em português no código. A tradução acontece na hora de mostrar:
# rótulos, botões, menus, textos do canvas, títulos de janela e avisos passam por traduzir().
# Frases montadas com números/nomes usam modelos com {0}, {1}… (assets/idiomas/<idioma>.json).
IDIOMAS = {"pt": "Português", "en": "English", "es": "Español"}
IDIOMA = {"atual": "pt"}
_TRAD, _MODELOS, _CACHE_T, _MODELOS_CRUS = {}, [], {}, {}
_ESPACO_MODELO = re.compile(r"\{(\d+)(?::[^}]*)?\}")


def carregar_idioma(cod):
    """Troca o idioma da interface (pt = sem tradução)."""
    _TRAD.clear()
    _MODELOS.clear()
    _CACHE_T.clear()
    _MODELOS_CRUS.clear()
    IDIOMA["atual"] = cod if cod in IDIOMAS else "pt"
    if IDIOMA["atual"] == "pt":
        return
    try:
        with open(recurso(os.path.join("idiomas", IDIOMA["atual"] + ".json")), encoding="utf-8") as f:
            dados = json.load(f)
    except Exception:
        IDIOMA["atual"] = "pt"
        return
    for pt, tr in dados.items():
        if _ESPACO_MODELO.search(pt):
            partes, pos = [], 0
            for m in _ESPACO_MODELO.finditer(pt):
                partes.append(re.escape(pt[pos:m.start()].replace("{{", "{").replace("}}", "}")))
                partes.append("(.+?)")
                pos = m.end()
            partes.append(re.escape(pt[pos:].replace("{{", "{").replace("}}", "}")))
            _MODELOS_CRUS[pt] = tr
            literal = len(_ESPACO_MODELO.sub("", pt))
            if len(re.findall(r"[^\W\d_]", _ESPACO_MODELO.sub("", pt))) >= 3:   # "{0} de {1}" só por chamada
                _MODELOS.append((literal, re.compile("^" + "".join(partes) + "$", re.S), tr))
        else:
            _TRAD[pt] = tr
    _MODELOS.sort(key=lambda x: -x[0])


def _preencher(alvo, grupos):
    r = _ESPACO_MODELO.sub(lambda m: grupos[int(m.group(1))] if int(m.group(1)) < len(grupos) else "", alvo)
    return r.replace("{{", "{").replace("}}", "}")


def traduzir(texto):
    """Traduz uma frase da interface para o idioma escolhido (devolve igual se não souber)."""
    if IDIOMA["atual"] == "pt" or not isinstance(texto, str) or not texto or texto.isspace():
        return texto
    r = _CACHE_T.get(texto)
    if r is not None:
        return r
    r = _TRAD.get(texto)
    if r is None:
        nu = texto.strip()
        if nu != texto and nu in _TRAD:
            r = texto.replace(nu, _TRAD[nu], 1)
        else:
            for _n, rx, alvo in _MODELOS:
                m = rx.match(texto)
                if m:
                    r = _preencher(alvo, [traduzir(g) for g in m.groups()])
                    break
        if r is None and "\n" in texto:
            linhas = texto.split("\n")
            novas = [traduzir(x) for x in linhas]
            if novas != linhas:
                r = "\n".join(novas)
        if r is None:
            r = texto
    if len(_CACHE_T) > 5000:
        _CACHE_T.clear()
    _CACHE_T[texto] = r
    return r


def traduzir_modelo(modelo, *valores):
    """Monta a frase a partir de um modelo com {0}, {1}… já no idioma escolhido."""
    alvo = _MODELOS_CRUS.get(modelo) if IDIOMA["atual"] != "pt" else None
    if alvo is None:
        return modelo.format(*valores)
    feitos = [format(valores[int(m.group(1))], (m.group(0)[len(m.group(1)) + 2:-1]) if ":" in m.group(0) else "")
              for m in _ESPACO_MODELO.finditer(modelo)]
    ordem = {int(m.group(1)): v for m, v in zip(_ESPACO_MODELO.finditer(modelo), feitos)}
    return _preencher(alvo, [ordem.get(i, "") for i in range(max(ordem) + 1)] if ordem else [])


def texto_cru(canvas, *a, **k):
    """Texto no canvas sem tradução (nomes de arquivos, jogos…)."""
    return _CRIAR_TEXTO_CRU(canvas, *a, **k)


_CRIAR_TEXTO_CRU = tk.Canvas.create_text


def _instalar_traducao():
    """Faz os componentes da interface traduzirem o que mostram (uma vez, ao abrir o app)."""
    def com_texto(cls, chaves=("text",)):
        ini, conf, cget = cls.__init__, cls.configure, cls.cget

        def __init__(self, *a, **k):
            for c in chaves:
                if isinstance(k.get(c), str):
                    setattr(self, "_pst_" + c, k[c])
                    k[c] = traduzir(k[c])
            ini(self, *a, **k)

        def configure(self, *a, **k):
            for c in chaves:
                if isinstance(k.get(c), str):
                    setattr(self, "_pst_" + c, k[c])
                    k[c] = traduzir(k[c])
            return conf(self, *a, **k)

        def cget_(self, nome):
            if nome in chaves and hasattr(self, "_pst_" + nome):   # o código compara com o texto original
                return getattr(self, "_pst_" + nome)
            return cget(self, nome)
        cls.__init__, cls.configure, cls.config, cls.cget = __init__, configure, configure, cget_

    for cls in (ctk.CTkLabel, ctk.CTkButton, ctk.CTkSwitch, ctk.CTkCheckBox, ctk.CTkRadioButton):
        com_texto(cls)
    com_texto(ctk.CTkEntry, ("placeholder_text",))

    def com_valores(cls):
        """Menus: mostram traduzido, mas o código continua recebendo o valor original."""
        ini, conf, set_, get_ = cls.__init__, cls.configure, cls.set, cls.get

        def _vals(self, vals):
            mapa = self.__dict__.setdefault("_pst_mapa", {})
            out = []
            for v in vals:
                tv = traduzir(v)
                mapa[tv] = v
                out.append(tv)
            return out

        def _cmd(self, cmd):
            return (lambda v: cmd(self.__dict__.get("_pst_mapa", {}).get(v, v))) if cmd else cmd

        def __init__(self, *a, **k):
            if k.get("values") is not None:
                k["values"] = _vals(self, k["values"])
            if k.get("command"):
                k["command"] = _cmd(self, k["command"])
            ini(self, *a, **k)

        def configure(self, *a, **k):
            if k.get("values") is not None:
                k["values"] = _vals(self, k["values"])
            if k.get("command"):
                k["command"] = _cmd(self, k["command"])
            return conf(self, *a, **k)

        def set(self, valor, *a, **k):
            if isinstance(valor, str) and valor not in self.__dict__.get("_pst_mapa", {}):
                valor = traduzir(valor)
            return set_(self, valor, *a, **k)

        def get(self):
            v = get_(self)
            return self.__dict__.get("_pst_mapa", {}).get(v, v)
        cls.__init__, cls.configure, cls.config, cls.set, cls.get = __init__, configure, configure, set, get

    com_valores(ctk.CTkOptionMenu)
    com_valores(ctk.CTkSegmentedButton)

    criar_texto, item_conf = tk.Canvas.create_text, tk.Canvas.itemconfigure

    def create_text(self, *a, **k):
        if isinstance(k.get("text"), str):
            k["text"] = traduzir(k["text"])
        return criar_texto(self, *a, **k)

    def itemconfigure(self, tag, cnf=None, **k):
        if isinstance(k.get("text"), str):
            k["text"] = traduzir(k["text"])
        return item_conf(self, tag, cnf, **k)
    tk.Canvas.create_text = create_text
    tk.Canvas.itemconfigure = tk.Canvas.itemconfig = itemconfigure

    titulo = tk.Wm.wm_title

    def wm_title(self, string=None):
        return titulo(self, traduzir(string) if isinstance(string, str) else string)
    tk.Wm.wm_title = tk.Wm.title = wm_title

    for nome in ("askopenfilename", "askopenfilenames", "askdirectory", "asksaveasfilename"):
        orig = getattr(filedialog, nome)

        def dialogo(*a, _orig=orig, **k):
            if isinstance(k.get("title"), str):
                k["title"] = traduzir(k["title"])
            if k.get("filetypes"):
                k["filetypes"] = [(traduzir(d), p) for d, p in k["filetypes"]]
            return _orig(*a, **k)
        setattr(filedialog, nome, dialogo)


_instalar_traducao()

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


def instalar_pkg_ps3(cfg, ftp, caminho, cancelar, nome="o pacote", pronto=None):
    """Pede ao webMAN para instalar um .pkg que já está no PS3 e espera terminar
    (o webMAN apaga o arquivo depois de instalar). O PS3 mostra o andamento na tela.
    False = este webMAN não instala .pkg sozinho (aí é pelo Package Manager do PS3)."""
    try:
        http_webman(cfg.get("ip"), "install.ps3" + _url_caminho(caminho), timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            raise RuntimeError(f"O PS3 recusou instalar {nome}. Saia do jogo (fique no XMB) "
                               f"e confira o espaço livre.") from None
        return False
    except (socket.timeout, TimeoutError, ConnectionError):
        pass                                    # o pedido chegou; o PS3 só demorou para responder
    except urllib.error.URLError as e:
        if not isinstance(e.reason, (socket.timeout, TimeoutError, ConnectionError)):
            raise
    fim = time.time() + 30 * 60
    while time.time() < fim:
        if cancelar is not None and cancelar.is_set():
            raise Cancelado()
        time.sleep(3)
        try:
            ftp.voidcmd("TYPE I")
            try:
                ftp.size(caminho)
                sumiu = False
            except ftplib.error_perm:          # 550 = o arquivo não existe mais
                sumiu = True
            if sumiu or (pronto is not None and pronto(ftp)):
                time.sleep(2)
                return True
        except ftplib.all_errors:              # o PS3 fica ocupado instalando: conecta de novo
            try:
                ftp.close()
                ftp.connect(cfg["ip"], int(cfg.get("porta", 21)), timeout=30)
                ftp.login(cfg.get("usuario") or "anonymous", cfg.get("senha") or "")
            except ftplib.all_errors:
                pass
    raise RuntimeError(f"A instalação de {nome} não terminou em 30 minutos. Confira no PS3 em Package Manager.")


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
        # .pkg mandado para /dev_hdd0/packages: o webMAN instala na hora, um de cada vez
        pkgs = [(nome, remoto) for nome, lista in planos for _l, remoto, _t in lista
                if remoto.lower().endswith(".pkg") and remoto.startswith("/dev_hdd0/packages/")]
        instalados, manual = 0, False
        if cfg.get("instalar_pkg", True):
            for i, (nome, remoto) in enumerate(pkgs, 1):
                if cancelar.is_set():
                    raise Cancelado()
                avisar("instalando", (i, len(pkgs), nome))
                if not instalar_pkg_ps3(cfg, ftp, remoto, cancelar, nome):
                    manual = True
                    break
                instalados += 1
        else:
            manual = bool(pkgs)
        avisar("fim", (len(planos), enviado, time.time() - inicio, instalados, manual))
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
FUNDO_GRANDE = {}     # (w, h) -> fundo PIL no tamanho da tela inteira, feito em segundo plano


def preparar_fundo_grande(w, h, escala):
    try:
        FUNDO_GRANDE[(w, h)] = Pintor(escala).fundo_pil(w, h)
    except Exception:
        pass


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
        g = self.px(glow_r) if glow else 0
        W_, H_ = self.px(w) + 2 * g, self.px(h) + 2 * g
        k = 4 if max(W_, H_) <= 320 else 2      # painéis grandes: 2x já deixa os cantos lisos
        img = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
        if glow:
            d4 = 4                               # o brilho é desfocado: dá para calcular em 1/4
            gl = Image.new("RGBA", (max(2, W_ // d4), max(2, H_ // d4)), (0, 0, 0, 0))
            ImageDraw.Draw(gl).rounded_rectangle([g / d4, g / d4, (W_ - g) / d4, (H_ - g) / d4],
                                                 self.px(r) / d4, fill=glow)
            gl = gl.filter(ImageFilter.GaussianBlur(g / 2.2 / d4)).resize((W_, H_), Image.BILINEAR)
            img = Image.alpha_composite(img, gl)
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

    def fundo_pil(self, w, h):
        """Fundo da janela como imagem PIL (pode rodar em outra thread)."""
        W_, H_ = self.px(w), self.px(h)
        rnd = random.Random(7)
        # gradiente base
        grad = Image.new("RGB", (1, 256))
        for y in range(256):
            t = y / 255
            grad.putpixel((0, y), (int(9 - 6 * t), int(24 - 18 * t), int(58 - 46 * t)))
        img = grad.resize((W_, H_), Image.BILINEAR).convert("RGBA")
        # brilho azul no canto (feito em 1/8 do tamanho e ampliado: é todo desfocado, fica igual)
        d8 = 8
        w8, h8 = max(2, W_ // d8), max(2, H_ // d8)
        gl = Image.new("RGBA", (w8, h8), (0, 0, 0, 0))
        dg = ImageDraw.Draw(gl)
        dg.ellipse([w8 * 0.45, -h8 * 0.55, w8 * 1.35, h8 * 0.55], fill=(0, 112, 209, 110))
        dg.ellipse([-w8 * 0.3, h8 * 0.65, w8 * 0.35, h8 * 1.4], fill=(40, 70, 160, 55))
        gl = gl.filter(ImageFilter.GaussianBlur(self.px(120) / d8)).resize((W_, H_), Image.BILINEAR)
        img = Image.alpha_composite(img, gl)
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
        return img

    def fundo(self, w, h):
        """Usa o fundo grande já pronto (feito em segundo plano) e só reduz: maximizar fica rápido."""
        W_, H_ = self.px(w), self.px(h)
        base = FUNDO_GRANDE.get((w, h))
        if base is not None and base.width >= W_:
            img = base if base.width == W_ else base.resize((W_, H_), Image.BILINEAR, reducing_gap=2.0)
        else:
            img = self.fundo_pil(w, h)
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
    itens.sort(key=lambda x: (not x[1], ordem_natural(x[0])))
    return itens


def ordem_natural(nome):
    """Jogo_2 antes de Jogo_10."""
    import re
    return [int(p_) if p_.isdigit() else p_.casefold() for p_ in re.split(r"(\d+)", nome)]


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


def caixa_marcar(marcada, tam):
    """Caixinha de marcar (para selecionar vários arquivos)."""
    k = 4
    img = Image.new("RGBA", (tam * k, tam * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m, r = 2 * k, 5 * k
    if marcada:
        d.rounded_rectangle([m, m, tam * k - m, tam * k - m], r, fill=(0, 112, 209, 255))
        d.line([(tam * k * 0.28, tam * k * 0.52), (tam * k * 0.44, tam * k * 0.68), (tam * k * 0.73, tam * k * 0.34)],
               fill=(255, 255, 255, 255), width=int(2.2 * k), joint="curve")
    else:
        d.rounded_rectangle([m, m, tam * k - m, tam * k - m], r, outline=(90, 104, 132, 255), width=int(1.6 * k))
    return img.resize((tam, tam), Image.LANCZOS)


def mini_icone(tipo, cor=(225, 232, 245, 255), pil=False):
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
    if pil:
        return img
    return ctk.CTkImage(light_image=img, dark_image=img, size=(18, 18))


# cores dos painéis (iguais às imagens do canvas)
PAINEL = "#0A1222"
PAINEL_RGB = (10, 18, 34)
LINHA_SEL = "#12305C"
BTN = "#16233F"
BTN_HOVER = "#20345C"


class Extras:
    # ================================================= abas
    ABAS = [("enviar", "Enviar", 64), ("arquivos", "Arquivos", 70), ("rap", "Licenças", 70),
            ("updates", "Updates", 70), ("trofeus", "Troféus", 70), ("console", "Console", 68), ("tela", "Tela", 50)]
    ABAS_X = 405

    def _abas(self):
        """Abas com a largura ajustada ao texto do idioma escolhido (a barra não cresce: a letra diminui)."""
        self._abas_fonte = 13
        if IDIOMA["atual"] == "pt":
            return list(self.ABAS)
        import tkinter.font as tkfont
        try:
            f = tkfont.Font(family=F_SEMI, size=-self.p.px(13))
            larg = [f.measure(traduzir(n)) / self.p.s for _k, n, _w in self.ABAS]
        except Exception:
            return list(self.ABAS)
        cabe = sum(w for *_, w in self.ABAS)
        fator = min(1.0, (cabe - 18 * len(larg)) / sum(larg))
        self._abas_fonte = max(10.5, 13 * fator)
        sobra = (cabe - sum(x * fator for x in larg)) / len(larg)
        return [(k, n, x * fator + sobra) for (k, n, _w), x in zip(self.ABAS, larg)]

    def _montar_abas(self):
        p, c = self.p, self.c
        abas = self._abas()
        total = int(sum(w for *_, w in abas) + 8)
        self.abas_x0 = self.ABAS_X - total / 2
        c.create_image(p.px(self.ABAS_X), p.px(56), image=p.ret(total, 44, 22, (14, 24, 46, 220),
                                                        outline=(255, 255, 255, 40), largura=1))
        self.aba_sel_img = {k: p.ret(int(w - 6), 34, 17, (255, 255, 255, 240)) for k, _, w in abas}
        self.aba_sel = c.create_image(0, 0)
        self.aba_tx = {}
        x = self.abas_x0 + 4
        self.aba_pos = {}
        for k, nome, w in abas:
            cx = x + w / 2
            self.aba_pos[k] = cx
            tg = f"aba_{k}"
            self.aba_tx[k] = c.create_text(p.px(cx), p.px(56), text=nome, fill=CINZA,
                                           font=(F_SEMI, -p.px(self._abas_fonte)), tags=(tg,))
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
         "console": self.tela_console, "tela": self.tela_espelho,
         "updates": self.tela_updates, "trofeus": self.tela_trofeus}[k]()

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
        nome = texto or ("Enviar" if frac is None else f"↑ {int(frac * 100)}%")
        c.itemconfig(self.aba_tx["enviar"], text=nome)
        if frac is None:
            c.itemconfig(self.aba_barra, state="hidden")
            return
        x0 = self.aba_pos["enviar"] - 26
        c.coords(self.aba_barra, p.px(x0), p.px(70), p.px(x0 + 52 * max(0.03, frac)), p.px(72))
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
        f_ = self.p.s / self.escala_base         # janela maximizada: as letras crescem, a janela também
        j.geometry(f"{int(largura * f_)}x{int(altura * f_)}")
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
        painel.grid_propagate(False)
        painel.pack_propagate(False)
        c.create_window(p.px(x0 + 14), p.px(y0 + 14), window=painel, anchor="nw", tags="view")
        self.widgets.append(painel)
        # grade: a lista fica com o espaço que sobrar, então os botões de baixo nunca são empurrados para fora
        painel.grid_columnconfigure(0, weight=1)
        painel.grid_rowconfigure(2, weight=1)

        def botao(pai_, texto, cmd, largura=None, perigo=False):
            return ctk.CTkButton(pai_, text=texto, command=cmd, height=34, corner_radius=17, font=fonte_b,
                                 width=largura or 0, fg_color="#3A1620" if perigo else BTN,
                                 hover_color="#5A1E2C" if perigo else BTN_HOVER,
                                 text_color="#FCA5A5" if perigo else BRANCO, text_color_disabled="#6B7488")

        topo = ctk.CTkFrame(painel, fg_color="transparent")
        topo.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 8))
        self.fm_btn_voltar = botao(topo, "←", self.fm_subir, 40)
        self.fm_btn_voltar.pack(side="left")
        self.fm_lbl_path = ctk.CTkLabel(topo, text=legivel(self.fm_path), font=ctk.CTkFont(family=F_SEMI, size=15),
                                        text_color=BRANCO, anchor="w")
        self.fm_lbl_path.pack(side="left", padx=12, fill="x", expand=True)
        botao(topo, "↻", self.fm_listar, 40).pack(side="right")
        for nome, cam in reversed([("HD", "/dev_hdd0"), ("Jogos", "/dev_hdd0/GAMES"), ("ISOs", "/dev_hdd0/PS3ISO"),
                                   ("Plugins", "/dev_hdd0/plugins"), ("Pendrive", "/dev_usb000")]):
            botao(topo, nome, lambda c_=cam: self.fm_ir(c_)).pack(side="right", padx=(0, 6))

        # ---- pesquisa: filtra enquanto digita; Enter procura também dentro das subpastas
        busca = ctk.CTkFrame(painel, fg_color="transparent")
        busca.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))
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

        # ---- lista desenhada num canvas: rolagem presa ao conteúdo e seleção de vários itens
        caixa = tk.Frame(painel, bg=PAINEL, bd=0, highlightthickness=0)
        caixa.grid(row=2, column=0, sticky="nsew", padx=(2, 2))
        caixa.grid_columnconfigure(0, weight=1)
        caixa.grid_rowconfigure(0, weight=1)
        self.fm_cv = tk.Canvas(caixa, bg=PAINEL, highlightthickness=0, bd=0, height=10, width=10,
                               takefocus=1)
        self.fm_cv.grid(row=0, column=0, sticky="nsew")
        self.fm_barra = ctk.CTkScrollbar(caixa, command=self._fm_barra_cmd, fg_color=PAINEL,
                                         button_color="#1E2A44", button_hover_color="#2A3A5E")
        self.fm_barra.grid(row=0, column=1, sticky="ns")
        self.fm_lista = self.fm_cv          # nome antigo usado em outros lugares
        self._fm_barra_pos = None
        self.fm_off = 0
        self.fm_hover = None
        cv = self.fm_cv
        cv.bind("<Configure>", lambda e: self._fm_redesenhar())
        cv.bind("<Button-1>", self._fm_clique)
        cv.bind("<Double-Button-1>", self._fm_duplo)
        cv.bind("<Motion>", self._fm_mover)
        cv.bind("<Leave>", lambda e: self._fm_set_hover(None))
        cv.bind("<MouseWheel>", lambda e: self._fm_rolar(-e.delta / 120 * 3))
        cv.bind("<Button-4>", lambda e: self._fm_rolar(-3))
        cv.bind("<Button-5>", lambda e: self._fm_rolar(3))
        cv.bind("<Control-a>", lambda e: (self.fm_marcar_tudo(True), "break")[1])
        cv.bind("<Control-A>", lambda e: (self.fm_marcar_tudo(True), "break")[1])
        cv.bind("<Delete>", lambda e: self.fm_apagar())
        cv.bind("<Return>", lambda e: self._fm_abrir_marcado())
        cv.bind("<Up>", lambda e: self._fm_teclas(-1, e))
        cv.bind("<Down>", lambda e: self._fm_teclas(1, e))
        cv.bind("<Prior>", lambda e: self._fm_rolar(-8))
        cv.bind("<Next>", lambda e: self._fm_rolar(8))

        rod = ctk.CTkFrame(painel, fg_color="transparent")
        rod.grid(row=3, column=0, sticky="ew", padx=10, pady=(6, 2))
        self.fm_lbl_status = ctk.CTkLabel(rod, text="", font=fonte, text_color=CINZA, anchor="w", height=22)
        self.fm_lbl_status.pack(side="left", fill="x", expand=True)
        self.fm_btn_tudo = ctk.CTkButton(rod, text="Marcar tudo", command=self.fm_marcar_tudo, height=22, width=0,
                                         fg_color="transparent", hover_color=BTN, text_color="#7FB2F0",
                                         font=ctk.CTkFont(family=F_SEMI, size=12), corner_radius=11)
        self.fm_btn_tudo.pack(side="right")
        self.fm_lbl_sel = ctk.CTkLabel(rod, text="", font=fonte, text_color=BRANCO, height=22)
        self.fm_lbl_sel.pack(side="right", padx=(0, 8))

        acoes = ctk.CTkFrame(painel, fg_color="transparent")
        acoes.grid(row=4, column=0, sticky="ew", padx=8, pady=(2, 6))
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
        self._fm_preparar_desenho()
        self.fm_listar()

    def _fm_ativo(self):
        return self.aba == "arquivos" and getattr(self, "fm_cv", None) is not None and self.fm_cv.winfo_exists()

    def fm_status(self, texto, cor=CINZA):
        if self._fm_ativo():
            self.fm_lbl_status.configure(text=texto, text_color=cor)

    # ---- seleção (vários itens)
    @property
    def fm_sel(self):
        """O item marcado quando há exatamente um (para editar e renomear)."""
        m = self.fm_marcados_itens()
        return m[0] if len(m) == 1 else None

    @fm_sel.setter
    def fm_sel(self, valor):
        self.fm_marcados = set() if valor is None else {valor[0]}

    def fm_marcados_itens(self):
        marc = getattr(self, "fm_marcados", set())
        return [it for it in self.fm_itens if it[0] in marc]

    def _fm_botoes(self):
        if not self._fm_ativo():
            return
        itens = self.fm_marcados_itens()
        n = len(itens)
        um = itens[0] if n == 1 else None
        algum_prot = any(protegido(juntar(self.fm_path, it[0])) for it in itens)
        texto = um is not None and not um[1] and um[0].lower().endswith(EXT_TEXTO) and um[2] <= LIMITE_EDICAO
        livre = not self.op_ativa
        self.fm_btn_editar.configure(state="normal" if texto and livre else "disabled")
        self.fm_btn_baixar.configure(state="normal" if n and livre else "disabled")
        self.fm_btn_renomear.configure(state="normal" if um and not algum_prot and livre else "disabled")
        self.fm_btn_apagar.configure(state="normal" if n and not algum_prot and livre else "disabled",
                                     text=f"Apagar ({n})" if n > 1 else "Apagar")
        self.fm_btn_baixar.configure(text=f"Baixar ({n})" if n > 1 else "Baixar")
        self.fm_btn_voltar.configure(state="normal" if self.fm_path != "/" else "disabled")
        self.fm_lbl_sel.configure(text=f"{n} marcados" if n > 1 else "")
        todos = bool(self.fm_itens) and n == len(self.fm_itens)
        self.fm_btn_tudo.configure(text="Desmarcar" if todos else "Marcar tudo",
                                   state="normal" if self.fm_itens else "disabled")

    def fm_marcar_tudo(self, so_marcar=False):
        if not self._fm_ativo() or not self.fm_itens:
            return
        if not so_marcar and len(self.fm_marcados_itens()) == len(self.fm_itens):
            self.fm_marcados = set()
        else:
            self.fm_marcados = {it[0] for it in self.fm_itens}
        self._fm_redesenhar()
        self._fm_botoes()

    def fm_ir(self, caminho):
        if self.op_ativa:
            return
        self.fm_path = caminho
        self.fm_off = 0
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
        self.fm_lbl_path.configure(text=legivel(self.fm_path))
        if self.estado_ps3 != "ok":
            self.fm_desconectado = True
            self.fm_itens, self.fm_todos = [], []
            self.fm_sel = None
            self._fm_redesenhar()
            self._fm_botoes()
            self.fm_status("Conecte o PS3 para ver os arquivos.", "#FBBF24")
            return
        self.fm_desconectado = False
        self.fm_status("Carregando…")
        caminho = self.fm_path

        def ok(itens):
            if not self._fm_ativo() or caminho != self.fm_path or self.fm_modo_fundo:
                return
            self.fm_todos = itens
            mesma = getattr(self, "fm_path_listado", None) == caminho     # recarregou a mesma pasta
            self.fm_path_listado = caminho
            self._fm_filtrar(manter=mesma)

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
        self.fm_off = 0
        if estava_fundo:
            self.fm_listar()
        else:
            self._fm_filtrar()
        self.fm_cv.focus_set()

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

    def _fm_filtrar(self, manter=False):
        """Monta a lista visível. manter=True (recarregar a mesma pasta) guarda marcações e a posição."""
        self._fm_espera = None
        if not self._fm_ativo() or self.fm_modo_fundo:
            return
        bruto = self.fm_busca.get().strip()
        termo = sem_acento(bruto)
        todos = self.fm_todos
        self.fm_itens = [it for it in todos if termo in sem_acento(legivel(it[0]))] if termo else list(todos)
        if manter:
            nomes = {it[0] for it in self.fm_itens}
            self.fm_marcados = {n for n in getattr(self, "fm_marcados", set()) if n in nomes}
        else:
            self.fm_marcados = set()
            self.fm_off = 0
        self._fm_redesenhar()
        self._fm_botoes()
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
        self.fm_marcados = set()
        self.fm_itens = []
        self.fm_off = 0
        self._fm_redesenhar()
        self._fm_botoes()
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
            self._fm_redesenhar()
            self._fm_botoes()
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

    # ---- desenho da lista (só as linhas que aparecem)
    def _fm_preparar_desenho(self):
        import tkinter.font as tkfont
        p = self.p
        self.fm_alt = p.px(40)
        self.fm_fonte = tkfont.Font(family=F_REG, size=-p.px(14))
        self.fm_fonte_p = tkfont.Font(family=F_REG, size=-p.px(12))
        t = p.px(18)
        self.fm_fotos = {k: ImageTk.PhotoImage(mini_icone(k, pil=True).resize((t, t), Image.LANCZOS))
                         for k in ("pasta", "arquivo", "texto")}
        self.fm_caixas = {v: ImageTk.PhotoImage(caixa_marcar(v, p.px(18))) for v in (False, True)}

    def _fm_corta(self, texto, fonte, largura):
        if largura <= 0:
            return ""
        if fonte.measure(texto) <= largura:
            return texto
        a, b = 0, len(texto)
        while a < b:
            m = (a + b + 1) // 2
            if fonte.measure(texto[:m] + "…") <= largura:
                a = m
            else:
                b = m - 1
        return texto[:a] + "…"

    def _fm_total(self):
        return len(self.fm_itens) * self.fm_alt

    def _fm_prender(self):
        """A rolagem nunca passa do começo nem do fim (nem rola quando tudo cabe)."""
        vis = max(1, self.fm_cv.winfo_height())
        self.fm_off = int(max(0, min(self.fm_off, self._fm_total() - vis)))

    def _fm_redesenhar(self):
        # a barra de rolagem do CTk processa eventos ao se redesenhar: sem esta trava a lista era
        # desenhada por cima dela mesma
        if getattr(self, "_fm_desenhando", False):
            self._fm_de_novo = True
            return
        self._fm_desenhando = True
        try:
            self._fm_redesenhar_agora()
        finally:
            self._fm_desenhando = False
        if getattr(self, "_fm_de_novo", False):
            self._fm_de_novo = False
            self.root.after_idle(self._fm_redesenhar)

    def _fm_redesenhar_agora(self):
        if not self._fm_ativo():
            return
        cv, p = self.fm_cv, self.p
        cv.delete("all")
        larg, vis = cv.winfo_width(), cv.winfo_height()
        if larg < 20 or vis < 20:
            return
        self._fm_prender()
        total, rh = self._fm_total(), self.fm_alt
        if not self.fm_itens:
            msg = "" if self.fm_lbl_status.cget("text") in ("Carregando…", "Procurando…") else "Nada para mostrar"
            cv.create_text(larg / 2, min(vis / 2, p.px(60)), text=msg, fill=CINZA_ESCURO, font=self.fm_fonte_p)
            self._fm_atualizar_barra(0.0, 1.0)
            return
        marc = getattr(self, "fm_marcados", set())
        lw = max(40, (larg - p.px(8)) / p.s)
        fundo_sel = p.ret(lw, (rh - p.px(3)) / p.s, 10, (18, 48, 92, 255))
        # destaque do mouse: um item só, que é movido de linha em linha (sem redesenhar a lista)
        cv.create_image(p.px(4), -1000, image=p.ret(lw, (rh - p.px(3)) / p.s, 10, (17, 28, 50, 255)),
                        anchor="nw", tags="hover", state="hidden")
        primeiro = self.fm_off // rh
        ultimo = min(len(self.fm_itens), (self.fm_off + vis) // rh + 1)
        x_tam = larg - p.px(16)
        for i in range(primeiro, ultimo):
            nome, eh_pasta, tam = self.fm_itens[i]
            y = i * rh - self.fm_off
            meio = y + rh / 2
            if nome in marc:
                cv.create_image(p.px(4), y + p.px(1), image=fundo_sel, anchor="nw")
            cv.create_image(p.px(22), meio, image=self.fm_caixas[nome in marc])
            tipo = "pasta" if eh_pasta else ("texto" if nome.lower().endswith(EXT_TEXTO) else "arquivo")
            cv.create_image(p.px(52), meio, image=self.fm_fotos[tipo])
            tam_txt = "" if eh_pasta else formatar_tamanho(tam)
            if tam_txt:
                cv.create_text(x_tam, meio, text=tam_txt, anchor="e", fill=CINZA, font=self.fm_fonte_p)
            limite = x_tam - p.px(100 if tam_txt else 10)
            pasta_de, _, so_nome = nome.rpartition("/")
            x = p.px(72)
            t = self._fm_corta(legivel(so_nome), self.fm_fonte, limite - x)
            texto_cru(cv, x, meio, text=t, anchor="w", fill=BRANCO, font=self.fm_fonte)     # nome: sem traduzir
            if pasta_de:                 # resultado da pesquisa nas subpastas: mostra onde está
                x += self.fm_fonte.measure(t) + p.px(10)
                onde = self._fm_corta(traduzir_modelo("em {0}", legivel(pasta_de)), self.fm_fonte_p, limite - x)
                texto_cru(cv, x, meio, text=onde, anchor="w", fill=CINZA_ESCURO, font=self.fm_fonte_p)
        self._fm_mostrar_hover()
        # a barra vem por último e só quando muda (ela força a tela a se redesenhar)
        self._fm_atualizar_barra(self.fm_off / total, min(1.0, (self.fm_off + vis) / total))

    def _fm_atualizar_barra(self, a, b):
        pos = (round(a, 4), round(b, 4))
        if pos != getattr(self, "_fm_barra_pos", None):
            self._fm_barra_pos = pos
            self.fm_barra.set(*pos)

    def _fm_mostrar_hover(self):
        cv, i = self.fm_cv, self.fm_hover
        if i is None or i >= len(self.fm_itens) or self.fm_itens[i][0] in getattr(self, "fm_marcados", set()):
            cv.itemconfigure("hover", state="hidden")
            return
        cv.coords("hover", self.p.px(4), i * self.fm_alt - self.fm_off + self.p.px(1))
        cv.itemconfigure("hover", state="normal")
        cv.tag_lower("hover")

    def _fm_rolar(self, linhas):
        self.fm_off += int(linhas * self.fm_alt / 1.5)
        self._fm_redesenhar()

    def _fm_barra_cmd(self, *args):
        vis, total = max(1, self.fm_cv.winfo_height()), self._fm_total()
        if args[0] == "moveto":
            self.fm_off = int(float(args[1]) * total)
        elif args[0] == "scroll":
            passo = vis if args[2] == "pages" else self.fm_alt
            self.fm_off += int(args[1]) * passo
        self._fm_redesenhar()

    def _fm_indice(self, y):
        i = int((y + self.fm_off) // self.fm_alt)
        return i if 0 <= i < len(self.fm_itens) else None

    def _fm_set_hover(self, i):
        if i != self.fm_hover:
            self.fm_hover = i
            if self._fm_ativo():
                self._fm_mostrar_hover()

    def _fm_mover(self, e):
        self._fm_set_hover(self._fm_indice(e.y))

    def _fm_clique(self, e):
        self.fm_cv.focus_set()
        i = self._fm_indice(e.y)
        if i is None:
            self.fm_marcados = set()
        else:
            na_caixa = e.x < self.p.px(38)
            ctrl, shift = bool(e.state & 0x4), bool(e.state & 0x1)
            self._fm_selecionar(i, alternar=ctrl or na_caixa, faixa=shift)
            return
        self._fm_redesenhar()
        self._fm_botoes()

    def _fm_selecionar(self, k, alternar=False, faixa=False):
        """Clique: marca só este. Ctrl ou caixinha: marca/desmarca. Shift: marca do último até este."""
        nome = self.fm_itens[k][0]
        self.fm_cursor = k
        marc = set(getattr(self, "fm_marcados", set()))
        ancora = getattr(self, "fm_ancora", None)
        if faixa and ancora is not None and ancora < len(self.fm_itens):
            a, b = sorted((ancora, k))
            if not alternar:
                marc = set()
            marc |= {self.fm_itens[j][0] for j in range(a, b + 1)}
        elif alternar:
            marc ^= {nome}
            self.fm_ancora = k
        else:
            marc = {nome}
            self.fm_ancora = k
        self.fm_marcados = marc
        self._fm_redesenhar()
        self._fm_botoes()

    def _fm_teclas(self, passo, e):
        if not self.fm_itens:
            return "break"
        atual = getattr(self, "fm_cursor", None)
        k = 0 if atual is None else max(0, min(len(self.fm_itens) - 1, atual + passo))
        self._fm_selecionar(k, faixa=bool(e.state & 0x1))
        y = k * self.fm_alt
        vis = self.fm_cv.winfo_height()
        if y < self.fm_off:
            self.fm_off = y
        elif y + self.fm_alt > self.fm_off + vis:
            self.fm_off = y + self.fm_alt - vis
        self._fm_redesenhar()
        return "break"

    def _fm_duplo(self, e):
        i = self._fm_indice(e.y)
        if i is not None:
            self._fm_abrir(i)

    def _fm_abrir_marcado(self):
        um = self.fm_sel
        if um is not None:
            self._fm_abrir(self.fm_itens.index(um))

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
            self.fm_status("Por segurança, o app não grava arquivos nas pastas do sistema do PS3.", "#F87171")
            return True
        if self.fm_path == "/":
            self.fm_status("Entre no HD (dev_hdd0) ou no pendrive antes de enviar arquivos.", "#FBBF24")
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
        if not self.fm_sel or self.op_ativa:
            return
        antigo = self.fm_sel[0]
        so_nome = antigo.rsplit("/", 1)[-1]

        def renomear(novo):
            if not novo or novo == legivel(so_nome) or "/" in novo:
                return
            a = juntar(self.fm_path, antigo)
            b = juntar(pai(a), para_ftp(novo))        # continua na mesma pasta (vale para resultados da pesquisa)
            rel_pai = antigo.rpartition("/")[0]
            self.fm_marcados = {f"{rel_pai}/{para_ftp(novo)}" if rel_pai else para_ftp(novo)}   # continua marcado
            self._fm_operacao("Renomeando…", lambda ftp: ftp.rename(a, b), f"Renomeado para “{novo}”.")
        self.dialogo("Renomear", f"Novo nome para “{legivel(so_nome)}”:", "Renomear", renomear,
                     campo=legivel(so_nome))

    def fm_apagar(self):
        itens = self.fm_marcados_itens()
        if not itens or self.op_ativa:
            return
        if any(protegido(juntar(self.fm_path, it[0])) for it in itens):
            self.fm_status("Por segurança, o app não mexe em pastas do sistema.", "#F87171")
            return
        alvos = [(juntar(self.fm_path, n), d) for n, d, _ in itens]
        nomes = [legivel(n.rsplit("/", 1)[-1]) for n, _, _ in itens]
        msg_ok = f"“{nomes[0]}” foi apagado." if len(itens) == 1 else f"{len(itens)} itens apagados."

        def trabalho(ftp):
            for k, (caminho, eh_pasta) in enumerate(alvos, 1):
                if len(alvos) > 1:
                    self.fila.put(("cb", lambda k=k: self.fm_status(f"Apagando… {k} de {len(alvos)}")))
                apagar_remoto(ftp, caminho, eh_pasta)
        self._fm_operacao("Apagando…", trabalho, msg_ok)      # direto, sem caixa de confirmação

    def fm_baixar(self):
        itens = self.fm_marcados_itens()
        if not itens or self.op_ativa:
            return
        destino = filedialog.askdirectory(title="Salvar no PC em…", parent=self.root)
        if not destino:
            return
        lista = [(juntar(self.fm_path, n), d, os.path.join(destino, legivel(n.rsplit("/", 1)[-1])), t)
                 for n, d, t in itens]
        so_arquivos = all(not d for _, d, _, _ in lista)
        total = sum(t for *_, t in lista) if so_arquivos else None
        prog = self._progresso_ui("Baixando…", total or None)

        def trabalho(ftp):
            for remoto, eh_pasta, local, _ in lista:
                baixar_remoto(ftp, remoto, eh_pasta, local, prog)
        msg = f"Salvo em {lista[0][2]}" if len(lista) == 1 else f"{len(lista)} itens salvos em {destino}"
        self._fm_operacao("Baixando…", trabalho, msg, recarregar=False)

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
            sub = traduzir(sub) + traduzir(f"   •   {n - len(validos)} arquivo(s) inválido(s) serão ignorados")
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


def atualizar_xmb(ip):
    """Atualiza a lista de jogos do webMAN e recarrega o XMB (os jogos novos aparecem).
    O XMB recarregando pode derrubar a conexão: isso conta como sucesso. Devolve False se o XMB não recarregou."""
    def pedir(cmd, espera):
        try:
            http_webman(ip, cmd, timeout=espera)
        except (ConnectionResetError, socket.timeout, TimeoutError):
            pass
        except urllib.error.URLError as e:
            if isinstance(e, urllib.error.HTTPError) or not isinstance(e.reason, (socket.timeout, TimeoutError,
                                                                                  ConnectionResetError)):
                raise
    pedir("refresh.ps3", 120)                      # refaz a lista de jogos (mygames.xml)
    try:
        pedir("reloadxmb.ps3", 20)                 # recarrega o XMB para mostrar a lista nova
    except urllib.error.HTTPError as e:
        if e.code in (400, 404, 501):
            return False                           # webMAN sem esse comando: a lista foi atualizada mesmo assim
        raise
    return True


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
                               "Espere uns segundos e clique em Atualizar para conferir.") from None
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
    """Tira o plugin da memória. Alguns (como o XPAD) demoram para sair e o webMAN só responde
    depois, ou nem responde: o pedido conta como enviado e o app confere se ele saiu mesmo."""
    def pedir(cmd):
        try:
            http_webman(ip, cmd, timeout=10)
        except urllib.error.HTTPError:
            raise
        except (socket.timeout, TimeoutError, ConnectionError):
            pass
        except urllib.error.URLError as e:
            if not isinstance(e.reason, (socket.timeout, TimeoutError, ConnectionError)):
                raise
        except Exception:        # resposta cortada no meio (http.client)
            pass

    try:
        if slot is not None:
            pedir(f"unloadprx.ps3?slot={slot}")
        else:
            pedir(f"unloadprx.ps3{_url_caminho(caminho)}")      # /unloadprx.ps3/dev_hdd0/...
    except urllib.error.HTTPError as e:
        if e.code not in (400, 404, 501) or slot is None:
            raise
        pedir(f"vshplugin.ps3mapi?unload_slot={slot}")
    fim, ativos = time.time() + 15, None
    while time.time() < fim:
        ativos = plugins_ativos(ip)
        if ativos is not None and caminho not in ativos:
            return
        time.sleep(1.5)
    if ativos is not None and caminho in ativos:
        raise RuntimeError("O PS3 não tirou o plugin da memória. Reinicie o PS3 para desligá-lo de vez.")


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
    """Copia os arquivos para o PS3. (O início automático é ligado à parte, pelo autoexec.bat.)"""
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


LISTAS_BOOT = ("/dev_hdd0/boot_plugins.txt", "/dev_hdd0/boot_plugins_nocobra.txt", "/dev_hdd0/boot_plugins_dex.txt",
               "/dev_hdd0/boot_plugins_nocobra_dex.txt", "/dev_hdd0/mamba_plugins.txt", "/dev_hdd0/prx_plugins.txt",
               "/dev_hdd0/game/PRXLOADER/USRDIR/plugins.txt")


def _eh_xpad(texto):
    t = texto.lower()
    return "ps3xpad" in t or "xpad_vsh" in t or "xpad_game" in t or "/xpad.sprx" in t


AUTOEXEC = "/dev_hdd0/autoexec.bat"       # script que o webMAN MOD roda sozinho quando liga
BLOCO_INI = "# >>> PSTudo: XPAD Revolution"
BLOCO_FIM = "# <<< PSTudo: XPAD Revolution"
ATRASO_XPAD = 15


def bloco_inicio_xpad(segundos=ATRASO_XPAD):
    """Trecho do autoexec.bat: espera o XMB, espera mais N segundos e carrega o XPAD."""
    esperas = []
    while segundos > 0:                   # o webMAN aceita esperas curtas: divide em pedaços de até 9 s
        esperas.append(f"wait {min(9, segundos)}")
        segundos -= min(9, segundos)
    return "\n".join([BLOCO_INI + f" (carrega {ATRASO_XPAD} s depois do HEN; criado pelo PSTudo)",
                      "wait xmb", *esperas,
                      f"/loadprx.ps3?slot=0&prx={XPAD_VSH}",     # slot 0 = primeiro espaço livre
                      BLOCO_FIM]) + "\n"


def _tirar_bloco(texto):
    if BLOCO_INI not in texto:
        return texto
    antes, _, resto = texto.partition(BLOCO_INI)
    _, achou, depois = resto.partition(BLOCO_FIM)
    if not achou:
        return antes
    return antes + depois.lstrip("\r\n")


def ler_autoexec(ftp):
    try:
        return ler_texto_remoto(ftp, AUTOEXEC)
    except ftplib.error_perm:
        return "", "utf-8"


def inicio_atrasado_ligado(ftp):
    return BLOCO_INI in ler_autoexec(ftp)[0]


def _tirar_xpad_das_listas(ftp, pasta_backup):
    """Tira as linhas do XPAD das listas de plugins do boot (guardando no PC uma cópia antes de mexer)."""
    mudou = []
    for lista in LISTAS_BOOT:
        if not existe_remoto(ftp, lista):
            continue
        texto, cod = ler_texto_remoto(ftp, lista)
        linhas = texto.splitlines(keepends=True)
        sobra = [ln for ln in linhas if not _eh_xpad(ln)]
        if len(sobra) != len(linhas):
            os.makedirs(pasta_backup, exist_ok=True)
            with open(os.path.join(pasta_backup, lista.strip("/").replace("/", "_")), "w", encoding="utf-8") as fl:
                fl.write(texto)
            gravar_texto_remoto(ftp, lista, "".join(sobra), cod)
            mudou.append((lista.rsplit("/", 1)[-1], len(linhas) - len(sobra)))
    return mudou


def ligar_inicio_atrasado(ftp, pasta_backup):
    """Coloca o XPAD para ligar sozinho 15 s depois do HEN, pelo autoexec.bat do webMAN.
    Tira o XPAD das listas do boot: carregado duas vezes, o webMAN acabaria desligando ele."""
    texto, cod = ler_autoexec(ftp)
    texto = _tirar_bloco(texto)
    if texto and not texto.endswith("\n"):
        texto += "\n"
    gravar_texto_remoto(ftp, AUTOEXEC, texto + bloco_inicio_xpad(), cod)
    return _tirar_xpad_das_listas(ftp, pasta_backup)


def desligar_inicio_atrasado(ftp):
    texto, cod = ler_autoexec(ftp)
    if BLOCO_INI not in texto:
        return False
    sobra = _tirar_bloco(texto)
    if sobra.strip():
        gravar_texto_remoto(ftp, AUTOEXEC, sobra, cod)
    else:
        ftp.delete(AUTOEXEC)              # o arquivo só tinha o trecho do PSTudo
    return True


def desinstalar_xpad(ftp, pasta_backup):
    """Remove o XPAD Revolution do PS3: a pasta dele, .sprx soltos do XPAD em /dev_hdd0/plugins e as linhas
    dele nas listas de plugins do boot. Antes, guarda no PC uma cópia das configurações e das listas."""
    os.makedirs(pasta_backup, exist_ok=True)
    rel = {"arquivos": 0, "listas": []}
    try:
        itens = listar_remoto(ftp, XPAD_DIR)
    except ftplib.all_errors:
        itens = None
    if itens is not None:
        # cópia das configurações (controles registrados, analógico…) antes de apagar
        for nome, d, _ in itens:
            if not d and nome.lower().endswith((".txt", ".ini", ".cfg")):
                with open(os.path.join(pasta_backup, legivel(nome)), "wb") as fl:
                    ftp.retrbinary(f"RETR {juntar(XPAD_DIR, nome)}", fl.write)
        rel["arquivos"] += sum(1 for _, d, _ in itens if not d)
        apagar_remoto(ftp, XPAD_DIR, True)
    # .sprx do XPAD soltos na pasta de plugins (versões antigas ou cópias manuais)
    try:
        for nome, d, _ in listar_remoto(ftp, "/dev_hdd0/plugins"):
            n = nome.lower()
            if not d and n.endswith(".sprx") and (n.startswith("xpad") or _eh_xpad("/" + n)):
                ftp.delete(juntar("/dev_hdd0/plugins", nome))
                rel["arquivos"] += 1
    except ftplib.all_errors:
        pass
    # linhas do XPAD nas listas de plugins que carregam no boot e o início atrasado no autoexec.bat
    rel["listas"] = _tirar_xpad_das_listas(ftp, pasta_backup)
    rel["autoexec"] = desligar_inicio_atrasado(ftp)
    return rel


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


def devices_detalhes(texto):
    """Controles do xpad_devices.txt com nome e tipo (linhas não comentadas)."""
    lista, vistos = [], set()
    for linha in texto.splitlines():
        util = linha.split("#", 1)[0].strip()
        partes = [p_.strip() for p_ in util.split(",")]
        if len(partes) >= 4:
            try:
                vid, pid = int(partes[0], 16), int(partes[1], 16)
            except ValueError:
                continue
            if (vid, pid) not in vistos:
                vistos.add((vid, pid))
                lista.append({"vid": vid, "pid": pid, "nome": partes[2] or "Controle", "tipo": partes[3]})
    return lista


XPAD_LOG = XPAD_DIR + "/xpad.log"


def estado_log_xpad(texto):
    """Do xpad.log do último boot: ({(vid, pid)} registrados no PS3, houve falta de espaço?)."""
    import re
    reg = {(int(a, 16), int(b, 16)) for a, b in re.findall(r"\]\s*registered ([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})", texto)}
    cheio = "LDD table full" in texto
    return reg, cheio


def ler_devices_remoto(ftp):
    try:
        texto, _ = ler_texto_remoto(ftp, XPAD_DEVICES)
    except ftplib.error_perm:
        return []
    lista = devices_detalhes(texto)
    try:
        log, _ = ler_texto_remoto(ftp, XPAD_LOG)
        reg, cheio = estado_log_xpad(log)
        for d in lista:            # None = sem informação; True = carregou no último boot; False = ficou de fora
            d["carregado"] = True if (d["vid"], d["pid"]) in reg else (False if cheio else None)
    except ftplib.all_errors:
        pass
    return lista


def remover_devices(ftp, chaves):
    """Tira do xpad_devices.txt as linhas dos controles (vid, pid) indicados."""
    texto, cod = ler_texto_remoto(ftp, XPAD_DEVICES)
    novas, tirou = [], 0
    for linha in texto.splitlines(keepends=True):
        partes = [p_.strip() for p_ in linha.split("#", 1)[0].split(",")]
        if len(partes) >= 4:
            try:
                if (int(partes[0], 16), int(partes[1], 16)) in chaves:
                    tirou += 1
                    continue
            except ValueError:
                pass
        novas.append(linha)
    if tirou:
        gravar_texto_remoto(ftp, XPAD_DEVICES, "".join(novas), cod)
    return tirou


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
        j = self._janela("Registrar controles", 900, 540)
        self._rc_janela = j
        f_tit = ctk.CTkFont(family=F_LIGHT, size=22)
        f_sub = ctk.CTkFont(family=F_SEMI, size=14)
        f_txt = ctk.CTkFont(family=F_REG, size=12)
        f_nome = ctk.CTkFont(family=F_SEMI, size=13)
        ctk.CTkLabel(j, text="Controles do XPAD", font=f_tit, text_color=BRANCO).pack(anchor="w", padx=24,
                                                                                       pady=(20, 2))
        ctk.CTkLabel(j, text="À esquerda, o que já está no xpad_devices.txt do PS3. À direita, os controles ligados "
                             "neste PC (cabo ou receptor) que ainda não foram registrados.",
                     font=f_txt, text_color=CINZA, wraplength=850, justify="left").pack(anchor="w", padx=24)
        corpo = ctk.CTkFrame(j, fg_color="transparent")
        corpo.pack(fill="both", expand=True, padx=24, pady=(12, 6))
        corpo.grid_columnconfigure((0, 1), weight=1, uniform="col")
        corpo.grid_rowconfigure(1, weight=1)

        def cabecalho(col, texto):
            fr = ctk.CTkFrame(corpo, fg_color="transparent")
            fr.grid(row=0, column=col, sticky="ew", padx=(0, 8) if col == 0 else (8, 0), pady=(0, 6))
            ctk.CTkLabel(fr, text=texto, font=f_sub, text_color=BRANCO).pack(side="left")
            cont = ctk.CTkLabel(fr, text="", font=f_txt, text_color=CINZA_ESCURO)
            cont.pack(side="right")
            return cont

        cont_reg = cabecalho(0, "Já registrados no PS3")
        cont_disp = cabecalho(1, "Disponíveis neste PC")
        lista_reg = ctk.CTkScrollableFrame(corpo, fg_color="#0A1222", corner_radius=12,
                                           scrollbar_button_color="#1E2A44")
        lista_reg.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        lista_disp = ctk.CTkScrollableFrame(corpo, fg_color="#0A1222", corner_radius=12,
                                            scrollbar_button_color="#1E2A44")
        lista_disp.grid(row=1, column=1, sticky="nsew", padx=(8, 0))

        status = ctk.CTkLabel(j, text="", font=f_txt, text_color=CINZA, anchor="w", wraplength=850,
                              justify="left")
        status.pack(fill="x", padx=26)
        self._rc_lbl = status
        rod = ctk.CTkFrame(j, fg_color="transparent")
        rod.pack(fill="x", padx=24, pady=(6, 18))
        btn_reg = self._cn_btn(rod, "Registrar no PS3  →", lambda: registrar(), "azul", 170, 38)
        btn_reg.pack(side="right")
        btn_proc = self._cn_btn(rod, "Procurar de novo", lambda: atualizar(), "normal", 140, 38)
        btn_proc.pack(side="right", padx=(0, 10))
        estado = {"registrados": None, "pads": None}
        linhas = []

        def vazio(lista, texto):
            ctk.CTkLabel(lista, text=texto, font=f_txt, text_color=CINZA, justify="center").pack(pady=40)

        def mostrar_registrados():
            for w_ in lista_reg.winfo_children():
                w_.destroy()
            regs = estado["registrados"]
            if regs is None:
                vazio(lista_reg, "Lendo o PS3…")
                return
            cont_reg.configure(text=traduzir_modelo("{0} de {1}", len(regs), LIMITE_DEVICES))
            if not regs:
                vazio(lista_reg, "Nenhum controle registrado ainda.")
                return
            for d in regs:
                fr = ctk.CTkFrame(lista_reg, fg_color="#0F1A30", corner_radius=10)
                fr.pack(fill="x", pady=3, padx=(0, 4))
                self._cn_btn(fr, "Remover", lambda d=d: remover(d), "perigo", 84, 28).pack(side="right", padx=10)
                esq = ctk.CTkFrame(fr, fg_color="transparent")
                esq.pack(side="left", fill="x", expand=True, padx=12, pady=8)
                ctk.CTkLabel(esq, text=d["nome"], font=f_nome, text_color=BRANCO, anchor="w").pack(anchor="w")
                ctk.CTkLabel(esq, text=f"{d['vid']:04X}:{d['pid']:04X}  •  {TIPOS_PAD.get(d['tipo'], d['tipo'])}",
                             font=f_txt, text_color=CINZA_ESCURO, anchor="w").pack(anchor="w")
                if d.get("carregado") is not None:
                    ctk.CTkLabel(esq, text="✓ carregado no último boot" if d["carregado"] else
                                 "✗ não carregou: o PS3 ficou sem espaço (limite do XPAD)", font=f_txt,
                                 text_color="#34D399" if d["carregado"] else "#FBBF24", anchor="w").pack(anchor="w")
            if any(d.get("carregado") is False for d in regs):
                ctk.CTkLabel(lista_reg, text="O XPAD carrega a lista dele primeiro e o PS3 só tem uns 22 espaços, "
                                             "então controles registrados aqui podem ficar de fora. Use um modo do "
                                             "controle que o XPAD já conhece (ex.: DualShock 4, luz azul nos GameSir).",
                             font=f_txt, text_color=CINZA, wraplength=360, justify="left").pack(anchor="w", padx=8,
                                                                                               pady=(8, 4))

        def mostrar_disponiveis():
            for w_ in lista_disp.winfo_children():
                w_.destroy()
            linhas.clear()
            pads = estado["pads"]
            if pads is None:
                vazio(lista_disp, "Procurando controles…")
                btn_reg.configure(state="disabled")
                return
            ja = {(d["vid"], d["pid"]) for d in (estado["registrados"] or [])}
            novos = [pd for pd in pads if (pd["vid"], pd["pid"]) not in ja]
            cont_disp.configure(text=f"{len(novos)}" if novos else "")
            if not novos:
                vazio(lista_disp, "Nenhum controle novo.\nConecte o controle no PC e clique em Procurar de novo."
                      if not pads else "Todos os controles ligados neste PC\njá estão registrados.")
                btn_reg.configure(state="disabled")
                return
            for pad in novos:
                fr = ctk.CTkFrame(lista_disp, fg_color="#0F1A30", corner_radius=10)
                fr.pack(fill="x", pady=3, padx=(0, 4))
                var = tk.BooleanVar(value=pad["tipo"] is not None and pad["aviso"] is None)
                tipo = None
                if pad["tipo"]:
                    tipo = ctk.CTkOptionMenu(fr, values=list(TIPOS_PAD.values()), width=150, height=28,
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
                    info += "  •  " + traduzir(pad["aviso"])
                ctk.CTkLabel(esq, text=info, font=f_txt, text_color="#FBBF24" if pad["aviso"] else CINZA_ESCURO,
                             anchor="w", wraplength=200, justify="left").pack(anchor="w", padx=(28, 0))
                if not pad["tipo"]:
                    cb.configure(state="disabled")
                linhas.append((pad, var, tipo))
            btn_reg.configure(state="normal")

        def ler_registrados():
            def ok(res):
                if j.winfo_exists():
                    estado["registrados"] = res
                    mostrar_registrados()
                    mostrar_disponiveis()

            def erro(e):
                if j.winfo_exists():
                    estado["registrados"] = []
                    mostrar_registrados()
                    status.configure(text=f"Não consegui ler o xpad_devices.txt ({str(e)[:50]})", text_color="#F87171")
            self.em_thread(ler_devices_remoto, ok, erro)

        def atualizar():
            btn_proc.configure(state="disabled")
            estado["pads"] = None
            mostrar_disponiveis()
            status.configure(text="", text_color=CINZA)

            def tarefa():
                try:
                    pads = detectar_controles()
                except Exception:
                    pads = []

                def pronto():
                    if j.winfo_exists():
                        estado["pads"] = pads
                        btn_proc.configure(state="normal")
                        mostrar_disponiveis()
                self.fila.put(("cb", pronto))
            threading.Thread(target=tarefa, daemon=True).start()
            ler_registrados()

        def registrar():
            escolhidos = []
            inverso = {v: k for k, v in TIPOS_PAD.items()}
            for pad, var, tipo in linhas:
                if var.get() and tipo is not None:
                    escolhidos.append(dict(pad, tipo=inverso[tipo.get()]))
            if not escolhidos:
                status.configure(text="Marque pelo menos um controle à direita.", text_color="#FBBF24")
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
                    partes.append(traduzir(f"{len(ja)} já estava(m) na lista"))
                if sem:
                    partes.append(traduzir(f"{len(sem)} sem espaço (limite de {LIMITE_DEVICES})"))
                txt = ", ".join(partes) + "."
                if adicionados:
                    txt += traduzir(" Reative o XPAD (ou reinicie o PS3) para o controle ser reconhecido.")
                status.configure(text=txt, text_color="#34D399" if adicionados else "#FBBF24")
                if adicionados:
                    self._rc_oferecer_recarga(rod)
                ler_registrados()           # o registrado passa para a esquerda

            def erro(e):
                if j.winfo_exists():
                    status.configure(text=f"Não consegui gravar ({str(e)[:60]})", text_color="#F87171")
                    btn_reg.configure(state="normal")
            self.em_thread(lambda ftp: registrar_devices(ftp, escolhidos), ok, erro)

        def remover(d):
            status.configure(text=f"Removendo {d['nome']}…", text_color=CINZA)

            def ok(n):
                if j.winfo_exists():
                    status.configure(text=f"{d['nome']} removido. Reative o XPAD (ou reinicie o PS3) para valer.",
                                     text_color="#34D399")
                    self._rc_oferecer_recarga(rod)
                    ler_registrados()

            def erro(e):
                if j.winfo_exists():
                    status.configure(text=f"Não consegui remover ({str(e)[:60]})", text_color="#F87171")
            self.em_thread(lambda ftp: remover_devices(ftp, {(d["vid"], d["pid"])}), ok, erro)

        mostrar_registrados()
        atualizar()

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
            self.fila.put(("cb", lambda: self._rc_status(msg, cor)))
        threading.Thread(target=tarefa, daemon=True).start()

    def _rc_status(self, msg, cor="#34D399"):
        lbl = getattr(self, "_rc_lbl", None)
        if lbl is not None and lbl.winfo_exists():
            lbl.configure(text=msg, text_color=cor)
        self.cn_msg(msg, cor)
        if self._cn_ativo() and cor != "#F87171":
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
        lin = ctk.CTkFrame(en, fg_color="transparent")
        lin.pack(fill="x", padx=16, pady=(8, 12))
        self.cn_btn_reiniciar = btn(lin, "↻  Reiniciar", lambda: self.energia("restart"), largura=140)
        self.cn_btn_reiniciar.pack(side="left")
        self.cn_btn_desligar = btn(lin, "⏻  Desligar", lambda: self.energia("shutdown"), "perigo", 140)
        self.cn_btn_desligar.pack(side="left", padx=10)

        # ---- Controle (XPAD Revolution)
        ct = cartao(1, 0)
        ctk.CTkLabel(ct, text="Suporte a controles", font=f_tit, text_color=BRANCO).pack(anchor="w", padx=16,
                                                                                          pady=(12, 0))
        ctk.CTkLabel(ct, text="XPAD Revolution: Xbox, GameSir, 8BitDo, DS4 e outros.",
                     font=f_txt, text_color=CINZA, justify="left").pack(anchor="w", padx=16)
        lin_st = ctk.CTkFrame(ct, fg_color="transparent")
        lin_st.pack(fill="x", padx=16, pady=(6, 0))
        self.cn_xpad_status = ctk.CTkLabel(lin_st, text="Verificando…", font=f_txt, text_color=CINZA, anchor="w")
        self.cn_xpad_status.pack(side="left")
        self.cn_btn_desinstalar = ctk.CTkButton(lin_st, text="Desinstalar", command=self.desinstalar_controle,
                                                height=22, width=0, corner_radius=11, fg_color="transparent",
                                                hover_color="#3A1620", text_color="#F87171",
                                                text_color_disabled=CINZA_ESCURO,
                                                font=ctk.CTkFont(family=F_SEMI, size=12))
        self.cn_btn_desinstalar.pack(side="right")
        lin2 = ctk.CTkFrame(ct, fg_color="transparent")
        lin2.pack(fill="x", padx=16, pady=(6, 6))
        self.cn_btn_instalar = btn(lin2, "Instalar", lambda: self.instalar_controle(False), "azul", 150)
        self.cn_btn_instalar.pack(side="left")
        self.cn_btn_zip = btn(lin2, "Usar ZIP do PC", lambda: self.instalar_controle(True), largura=130)
        self.cn_btn_zip.pack(side="left", padx=10)
        self.cn_auto = tk.BooleanVar(value=self.cfg.get("xpad_auto", True))
        self.cn_sw_auto = ctk.CTkSwitch(ct, text=f"Ligar sozinho {ATRASO_XPAD} s depois do HEN", variable=self.cn_auto,
                                        font=f_txt, text_color=BRANCO, progress_color="#0070D1",
                                        button_color="#E5ECF8", fg_color="#2A3A5E", switch_width=36,
                                        switch_height=18, command=self.alternar_inicio_xpad)
        self.cn_sw_auto.pack(anchor="w", padx=16, pady=(0, 2))

        def slider(rotulo, de, ate, fmt):
            topo = ctk.CTkFrame(ct, fg_color="transparent")
            topo.pack(fill="x", padx=16, pady=(4, 0))
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
        lin3.pack(fill="x", padx=16, pady=(8, 10))
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
        self.cn_btn_atualizar = btn(rod, "Atualizar", self.carregar_console, largura=120)
        self.cn_btn_atualizar.pack(side="right")          # primeiro: o texto longo não empurra o botão
        self.cn_status = ctk.CTkLabel(rod, text="", font=f_txt, text_color=CINZA, anchor="w", justify="left",
                                      wraplength=320)
        self.cn_status.pack(side="left", fill="x", expand=True, padx=(0, 10))

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
        self.cn_btn_desinstalar.configure(state="normal" if on and xpad else "disabled")
        self.cn_sw_auto.configure(state="normal" if on and xpad else "disabled")
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
            dados = {"sprx": sprx, "xpad": existe_remoto(ftp, XPAD_VSH), "analog": ler_analog(ftp),
                     "auto": inicio_atrasado_ligado(ftp)}
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
                self.cn_auto.set(bool(d.get("auto")))
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
            pendente, self._cn_msg_pendente = getattr(self, "_cn_msg_pendente", None), None
            if pendente:
                self.cn_msg(*pendente)
            else:
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
                auto = False
                try:
                    mantidos = instalar_xpad(ftp, arquivos)
                    if self.cfg.get("xpad_auto", True):    # liga sozinho 15 s depois do HEN, a cada boot
                        pasta = os.path.join(os.path.expanduser("~"), "PSTudo", "backup_xpad",
                                             time.strftime("%Y-%m-%d_%H-%M-%S"))
                        ligar_inicio_atrasado(ftp, pasta)
                        auto = True
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
                self.fila.put(("cb", lambda: self._xpad_ok(versao, mantidos, ativo, auto)))
            except Exception as e:
                msg = str(e)
                if "urlopen" in msg or "getaddrinfo" in msg or "HTTP Error" in msg:
                    msg = "Sem acesso ao GitHub. Baixe o ZIP no navegador e use “Usar ZIP do PC”."
                self.fila.put(("cb", lambda m=msg: self._xpad_erro(m)))
            finally:
                self.fila.put(("cb", self._op_fim))
        threading.Thread(target=trabalho, daemon=True).start()

    def alternar_inicio_xpad(self):
        """Liga/desliga o início automático do XPAD (autoexec.bat do webMAN), na hora."""
        ligar = bool(self.cn_auto.get())
        self.cfg["xpad_auto"] = ligar
        self.salvar_cfg()
        if self.op_ativa or self.estado_ps3 != "ok":
            return
        pasta = os.path.join(os.path.expanduser("~"), "PSTudo", "backup_xpad", time.strftime("%Y-%m-%d_%H-%M-%S"))

        def trabalho(ftp):
            return ligar_inicio_atrasado(ftp, pasta) if ligar else desligar_inicio_atrasado(ftp)

        def ok(res):
            if ligar:
                txt = traduzir(f"Pronto: nos próximos boots o XPAD liga sozinho {ATRASO_XPAD} s depois do HEN.")
                if res:
                    txt += traduzir(" Ele saiu do boot_plugins.txt para não carregar duas vezes.")
            else:
                txt = "Pronto: o XPAD não liga mais sozinho. Use Ativar quando quiser."
            self.cn_msg(txt, "#34D399")

        def erro(e):
            self.cn_msg(f"Não consegui mudar o início automático ({str(e)[:50]})", "#F87171")
            self.cn_auto.set(not ligar)
        self._op_simples("Salvando…", trabalho, ok, erro)

    def _op_simples(self, texto, trabalho, ok, erro):
        self.op_ativa = True
        self._cn_botoes()
        self.cn_msg(texto)
        self.em_thread(trabalho, ok, erro, self._op_fim)

    def desinstalar_controle(self):
        """Tira o XPAD da memória e apaga tudo dele do PS3 (sem perguntar; as configurações ficam salvas no PC)."""
        if self.op_ativa or self.estado_ps3 != "ok":
            return
        self.op_ativa = True
        self._cn_botoes()
        self.cn_xpad_status.configure(text="Desinstalando…", text_color=CINZA)
        ip = self.cfg.get("ip")
        pasta = os.path.join(os.path.expanduser("~"), "PSTudo", "backup_xpad", time.strftime("%Y-%m-%d_%H-%M-%S"))

        def trabalho():
            try:
                # 1) tira da memória o que estiver carregado (vale até reiniciar)
                tirou = False
                try:
                    ativos = plugins_ativos(ip) or {}
                    for caminho, slot in list(ativos.items()):
                        if _eh_xpad(caminho):
                            desativar_plugin(ip, caminho, slot)
                            tirou = True
                    for caminho, slot in list(getattr(self, "cn_sessao", {}).items()):
                        if _eh_xpad(caminho) and caminho not in ativos:
                            desativar_plugin(ip, caminho, slot)
                            tirou = True
                except Exception:
                    pass
                self.cn_sessao = {c: s for c, s in getattr(self, "cn_sessao", {}).items() if not _eh_xpad(c)}
                if tirou:
                    time.sleep(1.5)
                # 2) apaga os arquivos e as linhas do boot
                ftp = conectar(self.cfg)
                try:
                    rel = desinstalar_xpad(ftp, pasta)
                finally:
                    try:
                        ftp.quit()
                    except Exception:
                        ftp.close()
                self.fila.put(("cb", lambda: self._desinstalou(rel, pasta)))
            except Exception as e:
                self.fila.put(("cb", lambda e=e: self._xpad_erro(f"Não consegui desinstalar ({str(e)[:60]})")))
            finally:
                self.fila.put(("cb", self._op_fim))
        threading.Thread(target=trabalho, daemon=True).start()

    def _desinstalou(self, rel, pasta):
        try:
            vazia = not os.listdir(pasta)
            if vazia:
                os.rmdir(pasta)
        except OSError:
            vazia = True
        linhas = sum(n for _, n in rel["listas"])
        txt = traduzir(f"XPAD desinstalado: {rel['arquivos']} arquivo(s)")
        if linhas:
            txt += traduzir(f" e {linhas} linha(s) do boot")
        if rel.get("autoexec"):
            txt += traduzir(", início automático desligado")
        if not vazia:
            txt += traduzir(". Configurações salvas em PSTudo\\backup_xpad")
        msg = (txt + ".", "#34D399")
        self.cn_msg(*msg)
        self._cn_msg_pendente = msg          # continua aparecendo depois de recarregar a lista
        self.cn_xpad_status.configure(text="Não instalado", text_color=CINZA)
        self.carregar_console()

    def _op_fim(self):
        self.op_ativa = False
        self._cn_botoes()

    def _xpad_ok(self, versao, mantidos, ativo, auto=False):
        nome = versao or "XPAD Revolution"
        if ativo:
            txt = traduzir(f"{nome} instalado e ativo. Conecte o controle quando aparecer “XPAD Rev Loaded!”.")
        else:
            txt = traduzir(f"{nome} instalado. Não consegui ativar agora: use Ativar na lista de plugins.")
        if auto:
            txt += traduzir(f" Nos próximos boots ele liga sozinho {ATRASO_XPAD} s depois do HEN.")
        if mantidos:
            txt += traduzir(" Configurações antigas mantidas.")
        self._cn_msg_pendente = (txt, "#34D399" if ativo else "#FBBF24")
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
        """Reinicia ou desliga na hora, sem perguntar."""
        self._energia_enviar(acao)

    def _energia_enviar(self, acao):
        ip = self.cfg.get("ip")
        self.cn_msg("Reiniciando o PS3…" if acao == "restart" else "Desligando o PS3…", "#FBBF24")

        def trabalho():
            try:
                comando_energia(ip, acao)
                self.fila.put(("cb", lambda: self._energia_ok(acao)))
            except Exception as e:
                self.fila.put(("cb", lambda e=e: self.cn_msg(
                    f"O webMAN não respondeu ao comando ({str(e)[:60]}).", "#F87171")))
        threading.Thread(target=trabalho, daemon=True).start()

    def _energia_ok(self, acao):
        self.cn_sessao = {}
        self.atualizar_status("erro" if acao == "shutdown" else "busca")
        if self._cn_ativo():
            self.cn_msg("Reiniciando o PS3… depois é só ativar o HEN de novo." if acao == "restart"
                        else "PS3 desligando…", "#FBBF24")
            self._cn_botoes()
        if acao == "restart":
            self.root.after(45000, self.buscar_ps3)


# =============================================================== Tela: espelhar a placa de captura
# =============================================================== tela cheia na placa de vídeo (OpenGL)
VS_TELA = """
#version 330
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

# Todas as texturas guardam a imagem com a linha 0 no topo. "virar" = desenhando direto na tela (y para cima).
# Passo 1: leva a imagem do tamanho da placa para o tamanho da tela, corrigindo a faixa de cor.
# modo 0 = bilinear (com média de 4 pontos ao reduzir), modo 1 = FSR 1 EASU (AMD, licença MIT).
FS_ESCALA = """
#version 330
uniform sampler2D src;
uniform vec2 tam_in;
uniform vec2 tam_out;
uniform vec2 origem;
uniform float virar;
uniform int modo;
uniform int faixa;        // 1 = sinal "limitado" (16-235) mostrado como completo: estica para 0-255
out vec4 cor;

vec3 corrige(vec3 c) {
    if (faixa == 1) c = clamp((c - 16.0 / 255.0) * (255.0 / 219.0), 0.0, 1.0);
    return c;
}
vec3 px(ivec2 p) { return corrige(texelFetch(src, clamp(p, ivec2(0), ivec2(tam_in) - 1), 0).rgb); }
float rcpLo(float a) { return uintBitsToFloat(0x7ef07ebbu - floatBitsToUint(a)); }
float rsqLo(float a) { return uintBitsToFloat(0x5f347d74u - (floatBitsToUint(a) >> 1u)); }
float lum(vec3 c) { return c.b * 0.5 + (c.r * 0.5 + c.g); }

void tap(inout vec3 aC, inout float aW, vec2 off, vec2 dir, vec2 len, float lob, float clp, vec3 c) {
    vec2 v = vec2(off.x * dir.x + off.y * dir.y, off.x * (-dir.y) + off.y * dir.x) * len;
    float d2 = min(v.x * v.x + v.y * v.y, clp);
    float wB = 2.0 / 5.0 * d2 - 1.0;
    float wA = lob * d2 - 1.0;
    wB *= wB; wA *= wA;
    wB = 25.0 / 16.0 * wB - (25.0 / 16.0 - 1.0);
    float w = wB * wA;
    aC += c * w; aW += w;
}
void setF(inout vec2 dir, inout float len, float w, float lA, float lB, float lC, float lD, float lE) {
    float dc = lD - lC, cb = lC - lB;
    float lenX = rcpLo(max(abs(dc), abs(cb)));
    float dirX = lD - lB;
    dir.x += dirX * w;
    lenX = clamp(abs(dirX) * lenX, 0.0, 1.0);
    len += lenX * lenX * w;
    float ec = lE - lC, ca = lC - lA;
    float lenY = rcpLo(max(abs(ec), abs(ca)));
    float dirY = lE - lA;
    dir.y += dirY * w;
    lenY = clamp(abs(dirY) * lenY, 0.0, 1.0);
    len += lenY * lenY * w;
}
vec3 easu(vec2 ip) {
    vec2 esc = tam_in / tam_out;
    vec2 pp = ip * esc + (0.5 * esc - 0.5);
    vec2 fp = floor(pp);
    pp -= fp;
    ivec2 f = ivec2(fp);
    vec3 b = px(f + ivec2(0, -1)), c = px(f + ivec2(1, -1));
    vec3 e = px(f + ivec2(-1, 0)), F = px(f), g = px(f + ivec2(1, 0)), h = px(f + ivec2(2, 0));
    vec3 i = px(f + ivec2(-1, 1)), j = px(f + ivec2(0, 1)), k = px(f + ivec2(1, 1)), l = px(f + ivec2(2, 1));
    vec3 n = px(f + ivec2(0, 2)), o = px(f + ivec2(1, 2));
    float bL = lum(b), cL = lum(c), eL = lum(e), fL = lum(F), gL = lum(g), hL = lum(h);
    float iL = lum(i), jL = lum(j), kL = lum(k), lL = lum(l), nL = lum(n), oL = lum(o);
    vec2 dir = vec2(0.0);
    float len = 0.0;
    setF(dir, len, (1.0 - pp.x) * (1.0 - pp.y), bL, eL, fL, gL, jL);
    setF(dir, len, pp.x * (1.0 - pp.y), cL, fL, gL, hL, kL);
    setF(dir, len, (1.0 - pp.x) * pp.y, fL, iL, jL, kL, nL);
    setF(dir, len, pp.x * pp.y, gL, jL, kL, lL, oL);
    vec2 dir2 = dir * dir;
    float dirR = dir2.x + dir2.y;
    bool zro = dirR < 1.0 / 32768.0;
    dirR = zro ? 1.0 : rsqLo(dirR);
    dir.x = zro ? 1.0 : dir.x;
    dir *= dirR;
    len = len * 0.5;
    len *= len;
    float stretch = (dir.x * dir.x + dir.y * dir.y) * rcpLo(max(abs(dir.x), abs(dir.y)));
    vec2 len2 = vec2(1.0 + (stretch - 1.0) * len, 1.0 - 0.5 * len);
    float lob = 0.5 + ((1.0 / 4.0 - 0.04) - 0.5) * len;
    float clp = rcpLo(lob);
    vec3 mn4 = min(min(F, g), min(j, k));
    vec3 mx4 = max(max(F, g), max(j, k));
    vec3 aC = vec3(0.0);
    float aW = 0.0;
    tap(aC, aW, vec2(0.0, -1.0) - pp, dir, len2, lob, clp, b);
    tap(aC, aW, vec2(1.0, -1.0) - pp, dir, len2, lob, clp, c);
    tap(aC, aW, vec2(-1.0, 1.0) - pp, dir, len2, lob, clp, i);
    tap(aC, aW, vec2(0.0, 1.0) - pp, dir, len2, lob, clp, j);
    tap(aC, aW, vec2(0.0, 0.0) - pp, dir, len2, lob, clp, F);
    tap(aC, aW, vec2(-1.0, 0.0) - pp, dir, len2, lob, clp, e);
    tap(aC, aW, vec2(1.0, 1.0) - pp, dir, len2, lob, clp, k);
    tap(aC, aW, vec2(2.0, 1.0) - pp, dir, len2, lob, clp, l);
    tap(aC, aW, vec2(2.0, 0.0) - pp, dir, len2, lob, clp, h);
    tap(aC, aW, vec2(1.0, 0.0) - pp, dir, len2, lob, clp, g);
    tap(aC, aW, vec2(1.0, 2.0) - pp, dir, len2, lob, clp, o);
    tap(aC, aW, vec2(0.0, 2.0) - pp, dir, len2, lob, clp, n);
    return min(mx4, max(mn4, aC / aW));
}
void main() {
    vec2 ip = floor(gl_FragCoord.xy - origem);
    if (virar > 0.5) ip.y = tam_out.y - 1.0 - ip.y;
    vec3 c;
    if (modo == 1) {
        c = easu(ip);
    } else {
        vec2 uv = (ip + 0.5) / tam_out;
        vec2 esc = tam_in / tam_out;
        if (esc.x > 1.5) {          // reduzindo bastante: média de 4 pontos evita serrilhado
            vec2 d = 0.25 / tam_out;
            c = (texture(src, uv + vec2(-d.x, -d.y)).rgb + texture(src, uv + vec2(d.x, -d.y)).rgb +
                 texture(src, uv + vec2(-d.x, d.y)).rgb + texture(src, uv + d).rgb) * 0.25;
        } else {
            c = texture(src, uv).rgb;
        }
        c = corrige(c);
    }
    cor = vec4(c, 1.0);
}
"""

# Passo 2: RCAS do FSR 1 (AMD, licença MIT, ver THIRD_PARTY_NOTICES.md): nitidez sem halos, já na tela
FS_RCAS = """
#version 330
uniform sampler2D src;
uniform vec2 tam;
uniform vec2 origem;
uniform float virar;
uniform float nitidez;   // 0 = desligada, 1 = máximo
out vec4 cor;
vec3 px(ivec2 p) { return texelFetch(src, clamp(p, ivec2(0), ivec2(tam) - 1), 0).rgb; }
void main() {
    vec2 ip = floor(gl_FragCoord.xy - origem);
    if (virar > 0.5) ip.y = tam.y - 1.0 - ip.y;
    ivec2 p = ivec2(ip);
    vec3 e = px(p);
    if (nitidez <= 0.0) { cor = vec4(e, 1.0); return; }
    vec3 b = px(p + ivec2(0, -1)), d = px(p + ivec2(-1, 0)), f = px(p + ivec2(1, 0)), h = px(p + ivec2(0, 1));
    vec3 mn4 = min(min(b, d), min(f, h));
    vec3 mx4 = max(max(b, d), max(f, h));
    vec3 hitMin = mn4 / (4.0 * mx4 + 1e-5);
    vec3 hitMax = (1.0 - mx4) / (4.0 * mn4 - 4.0 - 1e-5);
    vec3 lobeRGB = max(-hitMin, hitMax);
    float lobe = max(-0.1875, min(max(lobeRGB.r, max(lobeRGB.g, lobeRGB.b)), 0.0)) * nitidez;
    cor = vec4(clamp((lobe * (b + d + f + h) + e) / (4.0 * lobe + 1.0), 0.0, 1.0), 1.0);
}
"""

# Aviso no canto (texto já desenhado numa textura com transparência, linha 0 no topo)
FS_AVISO = """
#version 330
uniform sampler2D tex;
uniform vec2 tam;
uniform vec2 origem;
uniform float opacidade;
out vec4 cor;
void main() {
    vec2 uv = (gl_FragCoord.xy - origem) / tam;
    vec4 c = texture(tex, vec2(uv.x, 1.0 - uv.y));
    cor = vec4(c.rgb, c.a * opacidade);
}
"""

# 0 = desligada; 2…6 = multiplica os quadros do jogo; INTERP_NATIVO = acompanha o Hz do monitor
INTERP_NATIVO = -1
INTERP_OPCOES = {"Desligada": 0, "x2": 2, "x3": 3, "x4": 4, "x5": 5, "x6": 6, "Nativo": INTERP_NATIVO}
FAIXAS_COR = ("Automática", "Limitada", "Completa")
FORMATOS_CAPTURA = ("Automático", "Sem compressão", "MJPEG")
NIVEIS_IA = {"Automática": None, "Leve": 640, "Equilibrada": 960, "Alta": 1280}
LARGURAS_IA = (1280, 960, 640)


class TelaCheiaGPU:
    """Janela de tela cheia desenhada pela placa de vídeo, em uma thread própria.
    Esc ou clique duplo fecha; os atalhos do FSR e da interpolação vêm das configurações.

    Ritmo: com a sincronização vertical ligada, cada troca de imagem espera o monitor (sem rasgos).
    Fluidez: o RIFE (rede neural de interpolação) roda na própria placa de vídeo e cria os quadros
    que faltam entre dois quadros diferentes do jogo, numa linha do tempo com atraso constante."""

    def __init__(self, captura, fsr, ao_fechar, ao_mudar_fsr=None, interp_modo=0, ao_mudar_interp=None,
                 atalhos=None, compativel=True, opcoes=None):
        self.cap, self.fsr, self.ao_fechar, self.ao_mudar_fsr = captura, fsr, ao_fechar, ao_mudar_fsr
        self.interp_modo, self.ao_mudar_interp = interp_modo, ao_mudar_interp
        self.atalhos = atalhos or {"fsr": "f", "interp": "i"}
        self.opcoes = dict(nitidez=0.5, faixa="Automática", vsync=True, ia="Automática")
        self.opcoes.update(opcoes or {})
        # janela 1 pixel maior que o monitor: o Windows não a trata como tela cheia exclusiva,
        # então Discord, OBS e companhia capturam sem travar
        self.compativel = compativel
        self.rodando = True
        self.erro = None
        self.fps = 0.0
        self.hz_monitor = 0
        self.fonte_fps = 0.0
        self.atraso_ms = 0.0
        self.ia_info = ""
        self.ia_falhou = ""
        self.faixa_atual = ""
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
        self.aviso_txt, self.aviso_t = traduzir(texto), time.perf_counter()

    def definir_fsr(self, ligado):
        self.fsr = bool(ligado)
        self.avisar(f"FSR 1: {'ligado' if self.fsr else 'desligado'}")

    def definir_interp(self, modo):
        self.interp_modo = modo
        txt = texto_interp(modo, self.fonte_fps, self.hz_monitor)
        if modo and self.ia_falhou:
            txt = "indisponível nesta placa de vídeo"
        self.avisar("Fluidez: " + txt)

    def definir_opcoes(self, **op):
        self.opcoes.update(op)

    def alternar_fsr(self):
        self.definir_fsr(not self.fsr)
        if self.ao_mudar_fsr:
            self.ao_mudar_fsr(self.fsr)

    def proxima_interp(self):
        opcoes = list(INTERP_OPCOES.values())
        novo = opcoes[(opcoes.index(self.interp_modo) + 1) % len(opcoes)] if self.interp_modo in opcoes else 0
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

    # ---- janela e contexto OpenGL (4.3 para a IA rodar mais rápido; 3.3 se a placa não tiver)
    def _abrir_janela(self, pygame, moderngl, larg, alt):
        ultimo = None
        for maior, menor in ((4, 3), (3, 3)):
            try:
                pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, maior)
                pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, menor)
                pygame.display.gl_set_attribute(pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE)
                pygame.display.set_mode((larg, alt), pygame.OPENGL | pygame.DOUBLEBUF | pygame.NOFRAME, vsync=0)
                return moderngl.create_context()
            except Exception as e:
                ultimo = e
        raise ultimo

    def _loop(self):
        import os as _os
        _os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        _os.environ["SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS"] = "0"
        _os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
        import numpy as np
        import pygame
        import moderngl
        pygame.display.init()
        pygame.font.init()
        larg, alt = pygame.display.get_desktop_sizes()[0]
        oy = 1 if self.compativel else 0     # a linha de baixo fica fora do monitor
        ctx = self._abrir_janela(pygame, moderngl, larg, alt + oy)
        try:
            pygame.Window.from_display_module().position = (0, 0)
        except Exception:
            pass
        pygame.display.set_caption("PSTudo — Tela")
        pygame.mouse.set_visible(False)
        try:
            self.hz_monitor = int(round(pygame.display.get_current_refresh_rate())) or 60
        except Exception:
            self.hz_monitor = 60
        progs = {n: ctx.program(vertex_shader=VS_TELA, fragment_shader=fs)
                 for n, fs in (("escala", FS_ESCALA), ("rcas", FS_RCAS), ("aviso", FS_AVISO))}
        vaos = {n: ctx.vertex_array(p_, []) for n, p_ in progs.items()}
        cache = {}
        escala_aviso = max(1.0, alt / 1080)
        try:
            fonte = pygame.font.SysFont("Segoe UI Semibold, Segoe UI, Arial", int(26 * escala_aviso))
        except Exception:
            fonte = pygame.font.Font(None, int(34 * escala_aviso))
        aviso_cache = {"txt": None, "tex": None, "tam": (0, 0)}

        def textura(nome, tam, comp=3, dtype="f1", bgr=False):
            t = cache.get(nome)
            if t is None or t.size != tuple(tam) or t.components != comp or t.dtype != dtype:
                if t is not None:
                    t.release()
                    f_ = cache.pop(nome + "_fbo", None)
                    if f_ is not None:
                        f_.release()
                t = ctx.texture(tuple(tam), comp, dtype=dtype, alignment=1)
                t.filter = (moderngl.LINEAR, moderngl.LINEAR)
                t.repeat_x = t.repeat_y = False
                if bgr:
                    t.swizzle = "BGR"   # a placa entrega BGR: a troca é feita pela GPU
                cache[nome] = t
            return t

        def fbo_de(nome):
            f_ = cache.get(nome + "_fbo")
            if f_ is None:
                f_ = ctx.framebuffer(color_attachments=[cache[nome]])
                cache[nome + "_fbo"] = f_
            return f_

        def passo(prog, viewport, texs, **unis):
            """Roda um programa (nome, ou "monta" da IA) cobrindo o viewport."""
            ctx.viewport = viewport
            p_, vao = (cache["prog_monta"], cache["vao_monta"]) if prog == "monta" else (progs[prog], vaos[prog])
            for k, v in unis.items():
                try:
                    p_[k] = v
                except KeyError:       # o compilador tirou a variável que não é usada
                    pass
            for unidade, t in texs:
                t.use(unidade)
            vao.render(moderngl.TRIANGLES, vertices=3)

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
                if aviso_cache["tex"] is not None:
                    aviso_cache["tex"].release()
                t = ctx.texture(sup.get_size(), 4, pygame.image.tobytes(sup, "RGBA"))
                t.filter = (moderngl.LINEAR, moderngl.LINEAR)
                aviso_cache.update(txt=self.aviso_txt, tex=t, tam=sup.get_size())
            aw, ah = aviso_cache["tam"]
            m = int(32 * escala_aviso)
            x0, y0 = larg - aw - m, oy + alt - ah - m
            ctx.enable(moderngl.BLEND)
            ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
            passo("aviso", (x0, y0, aw, ah), [(0, aviso_cache["tex"])], tex=0, tam=(float(aw), float(ah)),
                  origem=(float(x0), float(y0)), opacidade=opac)
            ctx.disable(moderngl.BLEND)

        def esperar_ate(alvo):
            while True:
                falta = alvo - time.perf_counter()
                if falta <= 0:
                    return
                time.sleep(falta - 0.0015 if falta > 0.002 else 0)

        def faixa_agora():
            f = self.opcoes.get("faixa", "Automática")
            if f == "Automática":
                f = "Limitada" if getattr(self.cap, "faixa_detectada", "") == "limitada" else "Completa"
            self.faixa_atual = f
            return 1 if f == "Limitada" else 0

        def mostrar(src, w, h):
            """Desenha a textura src (w×h, linha 0 no topo) na tela: escala/FSR, faixa de cor, nitidez, aviso."""
            esc = min(larg / w, alt / h)
            vw, vh = max(2, int(round(w * esc))), max(2, int(round(h * esc)))
            x0, y0 = (larg - vw) // 2, oy + (alt - vh) // 2
            meio = textura("meio", (vw, vh), comp=4, dtype="f2")
            usar_easu = self.fsr and esc > 1.01
            fbo_de("meio").use()
            passo("escala", (0, 0, vw, vh), [(0, src)], src=0, tam_in=(float(w), float(h)),
                  tam_out=(float(vw), float(vh)), origem=(0.0, 0.0), virar=0.0, modo=int(usar_easu),
                  faixa=faixa_agora())
            ctx.screen.use()
            ctx.viewport = (0, 0, larg, alt + oy)
            ctx.clear(0, 0, 0)
            nit = float(self.opcoes.get("nitidez", 0.5)) if self.fsr else 0.0
            passo("rcas", (x0, y0, vw, vh), [(0, meio)], src=0, tam=(float(vw), float(vh)),
                  origem=(float(x0), float(y0)), virar=1.0, nitidez=nit)
            desenhar_aviso()
            pygame.display.flip()
            if vsync:
                ctx.finish()           # não deixa o driver acumular imagens: menos atraso, ritmo certo

        # ---- fluidez com IA
        ia = {"rede": None, "nivel": None, "medidas": [], "n": 0, "query": None, "t_nivel": 0.0, "carga": 0.0}

        def preparar_ia(w, h):
            if self.ia_falhou:
                return None
            try:
                if ia["rede"] is None:
                    from pstudo_ia import RifeGL, VS as VS_IA, FS_MONTA
                    ia["rede"] = RifeGL(ctx, vagas=5)
                    cache["prog_monta"] = ctx.program(vertex_shader=VS_IA.replace("{ver}", "330"),
                                                      fragment_shader=FS_MONTA)
                    cache["vao_monta"] = ctx.vertex_array(cache["prog_monta"], [])
                    ia["query"] = ctx.query(time=True)
                escolha = NIVEIS_IA.get(self.opcoes.get("ia", "Automática"))
                if ia["nivel"] is None or (escolha and ia["nivel"] != escolha):
                    ia["nivel"] = min(escolha or 960, w)
                lw = min(ia["nivel"], w)
                lh = max(32, int(round(lw * h / w / 2)) * 2)
                rede = ia["rede"]
                if rede.tam is None or rede.conteudo != (lw, lh):
                    rede.preparar(lw, lh)
                    for q in quadros:          # os quadros guardados precisam ir de novo para a rede
                        rede.carregar_quadro(q["vaga"], q["tex"])
                    ia["chave"] = None
                return rede
            except Exception as e:
                self.ia_falhou = str(e)[:120] or type(e).__name__
                self.avisar("Fluidez com IA indisponível nesta placa de vídeo")
                return None

        def interpolar(qa, qb, alfa):
            rede = ia["rede"]
            medir = ia["n"] % 12 == 0
            if medir:
                with ia["query"]:
                    rede.inferir(qa["vaga"], qb["vaga"], alfa)
            else:
                rede.inferir(qa["vaga"], qb["vaga"], alfa)
            ia["n"] += 1
            w, h = qa["w"], qa["h"]
            saida = textura("interp", (w, h), comp=4, dtype="f2")
            fbo_de("interp").use()
            passo("monta", (0, 0, w, h), [(0, qa["tex"]), (1, qb["tex"]), (2, rede.estado)], A=0, B=1, S=2,
                  rede=tuple(float(v) for v in rede.tam), conteudo=tuple(float(v) for v in rede.conteudo),
                  tam_fonte=(float(w), float(h)))
            if medir:
                try:
                    gasto = ia["query"].elapsed / 1e9
                    ia["medidas"].append(gasto)
                    del ia["medidas"][:-5]
                except Exception:
                    pass
            return saida

        def ajustar_nivel(w):
            """Automática: diminui a rede se a placa de vídeo estiver apertada, aumenta se sobrar folga."""
            if not ia["medidas"] or NIVEIS_IA.get(self.opcoes.get("ia", "Automática")):
                return
            agora_ = time.perf_counter()
            tempo = sorted(ia["medidas"])[len(ia["medidas"]) // 2]
            carga = tempo * ia_por_seg[0]
            ia["carga"] = carga
            if agora_ - ia["t_nivel"] < 3.0:
                return
            niveis = [n for n in LARGURAS_IA if n <= max(w, 640)]
            i = niveis.index(ia["nivel"]) if ia["nivel"] in niveis else len(niveis) - 1
            if carga > 0.55 and i < len(niveis) - 1:
                ia["nivel"] = niveis[i + 1]
            elif carga < 0.18 and i > 0:
                ia["nivel"] = niveis[i - 1]
            else:
                return
            ia["t_nivel"] = agora_
            ia["medidas"].clear()

        # ---- estado da linha do tempo
        self.pronto.set()
        quadros = []                   # quadros DIFERENTES recentes: dict(tex, ts, corte, vaga, w, h, id)
        pool = []                      # texturas livres do tamanho da placa
        prox_vaga, prox_id = 0, 0
        atraso = 0.05                  # quanto a imagem mostrada fica atrás do jogo (segundos)
        conteudo_ant = 0.0
        deltas = []                    # intervalos entre quadros diferentes do jogo
        ultimo_n, ult_clique, t0 = -1, 0.0, time.time()
        mostradas, chave_mostrada = 0, None
        distintos, t_dist = 0, time.time()
        vsync = None
        trocas = []                    # intervalos medidos entre trocas de imagem (Hz real do monitor)
        t_troca = time.perf_counter()
        prox_relogio = time.perf_counter()
        ia_cont, ia_por_seg, t_ia = 0, [0.0], time.time()

        def guardar_quadro(item):
            nonlocal prox_vaga, prox_id
            q, ts, corte = item
            h, w = q.shape[:2]
            tex = None
            while pool:
                t_ = pool.pop()
                if t_.size == (w, h):
                    tex = t_
                    break
                t_.release()
            if tex is None:
                tex = ctx.texture((w, h), 3, dtype="f1", alignment=1)
                tex.filter = (moderngl.LINEAR, moderngl.LINEAR)
                tex.repeat_x = tex.repeat_y = False
                tex.swizzle = "BGR"
            tex.write(np.ascontiguousarray(q))
            novo = {"tex": tex, "ts": ts, "corte": corte, "vaga": prox_vaga, "w": w, "h": h, "id": prox_id}
            prox_id += 1
            # a vaga da rede é reaproveitada: o quadro que a usava sai da lista
            for velho in [v for v in quadros if v["vaga"] == prox_vaga]:
                quadros.remove(velho)
                pool.append(velho["tex"])
            prox_vaga = (prox_vaga + 1) % 5
            if quadros and 0 < ts - quadros[-1]["ts"] < 0.25:
                deltas.append(ts - quadros[-1]["ts"])
                del deltas[:-60]
            quadros.append(novo)
            if ia["rede"] is not None and ia["rede"].tam is not None:
                try:
                    ia["rede"].carregar_quadro(novo["vaga"], tex)
                except Exception:
                    pass

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
            modo = self.interp_modo if not self.ia_falhou else 0
            aviso_ativo = bool(self.aviso_txt) and time.perf_counter() - self.aviso_t < 1.3
            quer_vsync = bool(self.opcoes.get("vsync", True))
            if quer_vsync != vsync:
                try:
                    pygame.display.gl_set_swap_interval(1 if quer_vsync else 0)
                except Exception:
                    quer_vsync = False
                vsync = quer_vsync
            hz = self.hz_monitor or 60
            if len(trocas) >= 30:
                medio = sorted(trocas)[len(trocas) // 2]
                if 1 / 400 < medio < 1 / 20 and vsync:
                    hz = 1 / medio
            periodo = 1.0 / hz

            # ---------------- sem fluidez: cada quadro novo da placa vai para a tela na próxima troca
            if not modo:
                if quadros:
                    pool.extend(q["tex"] for q in quadros)
                    quadros.clear()
                self.cap.distintos.clear()
                if self.cap.n == ultimo_n and not aviso_ativo:
                    self.cap.novo.wait(0.02)
                    self.cap.novo.clear()
                    if self.cap.n == ultimo_n and not aviso_ativo:
                        continue
                quadro = self.cap.quadro
                if quadro is None:
                    continue
                if self.cap.n != ultimo_n:
                    ultimo_n = self.cap.n
                    h, w = quadro.shape[:2]
                    textura("q", (w, h), bgr=True).write(np.ascontiguousarray(quadro))
                    mostradas += 1
                h, w = quadro.shape[:2]
                mostrar(cache["q"], w, h)
            # ---------------- com fluidez
            else:
                while self.cap.distintos:
                    try:
                        guardar_quadro(self.cap.distintos.popleft())
                    except IndexError:
                        break
                    distintos += 1
                if not quadros:
                    self.cap.novo.wait(0.02)
                    self.cap.novo.clear()
                    continue
                w, h = quadros[-1]["w"], quadros[-1]["h"]
                rede = preparar_ia(w, h)
                agora = time.perf_counter()
                # atraso alvo: o maior intervalo recente do jogo + uma troca de tela + margem do cálculo
                recentes = deltas[-int(max(4, min(60, 1.2 / (sum(deltas[-10:]) / len(deltas[-10:]))))):] \
                    if deltas else [1 / 30]
                gasto_ia = (sorted(ia["medidas"])[len(ia["medidas"]) // 2] if ia["medidas"] else 0.004)
                alvo = min(0.2, max(recentes) + (periodo if vsync else 0.0) + gasto_ia + 0.003)
                atraso = alvo if alvo > atraso else max(alvo, atraso - 0.00025)
                conteudo = agora + (periodo if vsync else 0.0) - atraso
                if conteudo < conteudo_ant:
                    conteudo = conteudo_ant          # o tempo da imagem nunca volta
                conteudo_ant = conteudo
                if conteudo > quadros[-1]["ts"]:     # o próximo quadro atrasou: segura o último e aumenta a folga
                    atraso += min(conteudo - quadros[-1]["ts"], 0.01)
                self.atraso_ms = atraso * 1000
                # par de quadros em volta do instante que vai para a tela
                qa = qb = None
                for i in range(len(quadros) - 1, -1, -1):
                    if quadros[i]["ts"] <= conteudo:
                        qa = quadros[i]
                        qb = quadros[i + 1] if i + 1 < len(quadros) else None
                        break
                if qa is None:
                    qa = quadros[0]
                saida, chave = qa["tex"], ("q", qa["id"])
                if qb is not None and rede is not None and not qb["corte"] and qb["ts"] - qa["ts"] < 0.12 \
                        and (qa["w"], qa["h"]) == (qb["w"], qb["h"]):
                    alfa = (conteudo - qa["ts"]) / (qb["ts"] - qa["ts"])
                    passos = modo if modo != INTERP_NATIVO else 16
                    alfa_q = (int(alfa * passos) if modo != INTERP_NATIVO else round(alfa * passos)) / passos
                    if alfa_q >= 1.0:
                        saida, chave = qb["tex"], ("q", qb["id"])
                    elif alfa_q > 0.0:
                        chave = ("i", qa["id"], qb["id"], alfa_q)
                        if chave == ia.get("chave"):
                            saida = cache["interp"]
                        else:
                            try:
                                saida = interpolar(qa, qb, alfa_q)
                                ia["chave"] = chave
                                ia_cont += 1
                            except Exception as e:
                                self.ia_falhou = str(e)[:120] or type(e).__name__
                                self.avisar("Fluidez com IA indisponível nesta placa de vídeo")
                                saida, chave = qa["tex"], ("q", qa["id"])
                # sobra de quadros velhos (fora da linha do tempo)
                while len(quadros) > 2 and quadros[1]["ts"] < conteudo - 0.3:
                    pool.append(quadros.pop(0)["tex"])
                if chave != chave_mostrada:
                    mostradas += 1
                    chave_mostrada = chave
                if rede is not None:
                    ajustar_nivel(w)
                    self.ia_info = f"IA {rede.conteudo[0]}×{rede.conteudo[1]}"
                mostrar(saida, qa["w"], qa["h"])
                if not vsync:                         # sem sincronização: relógio próprio no Hz do monitor
                    prox_relogio += periodo
                    if prox_relogio < time.perf_counter() - 0.05:
                        prox_relogio = time.perf_counter()
                    esperar_ate(prox_relogio)
            agora_p = time.perf_counter()
            if modo and vsync:
                trocas.append(agora_p - t_troca)
                del trocas[:-90]
            t_troca = agora_p
            agora = time.time()
            if agora - t0 >= 1:
                self.fps, mostradas, t0 = mostradas / (agora - t0), 0, agora
            if agora - t_dist >= 1:
                if modo:
                    self.fonte_fps = distintos / (agora - t_dist)
                else:
                    self.fonte_fps = getattr(self.cap, "fps_distintos", 0.0)
                distintos, t_dist = 0, agora
            if agora - t_ia >= 1:
                ia_por_seg[0], ia_cont, t_ia = ia_cont / (agora - t_ia), 0, agora
        if ia["rede"] is not None:
            try:
                ia["rede"].liberar()
            except Exception:
                pass
        ctx.release()


def texto_interp(modo, fonte_fps=0.0, hz_monitor=0):
    """Texto curto do modo de interpolação, com os quadros por segundo esperados."""
    if not modo:
        return "desligada"
    if modo == INTERP_NATIVO:
        return f"nativa ({hz_monitor} Hz)" if hz_monitor else "nativa (Hz do monitor)"
    if fonte_fps >= 10:
        return f"x{modo} ({round(fonte_fps) * modo} fps)"
    return f"x{modo}"


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


def _fourcc_txt(v):
    v = int(v or 0)
    return "".join(chr((v >> (8 * i)) & 0xFF) for i in range(4)).strip("\x00 ")


class Captura:
    """Lê quadros da placa em outra thread.

    - Formato: "Sem compressão" (YUY2/NV12) não tem os quadradinhos do MJPEG; "Automático" tenta primeiro
      sem compressão e só usa MJPEG se a placa não aguentar o modo escolhido.
    - Cada quadro ganha um horário "alisado" (o USB entrega com tremidas de alguns milissegundos).
    - Quadros repetidos (jogo a 30 numa saída de 60 Hz) são marcados: a fluidez só usa os diferentes.
    - A faixa de cor (limitada 16-235 ou completa) é detectada olhando o preto e o branco mais fortes."""

    def __init__(self, fonte, modo, formato="Automático", preferido=None, ao_escolher=None):
        self.fonte, self.modo = fonte, modo
        self.formato, self.preferido, self.ao_escolher = formato, preferido, ao_escolher
        self.quadro = None
        self.t = 0.0
        self.n = 0
        self.erro = None
        self.rodando = True
        self.fps = 0.0
        self.fps_distintos = 0.0
        self.tamanho = None
        self.formato_usado = ""
        self.faixa_detectada = ""
        self.novo = threading.Event()
        self.distintos = collections.deque(maxlen=8)    # (quadro, horário, troca de cena)
        self.previa_tam = None                           # (larg, alt) pedido pela aba; None = sem prévia
        self.previa = None                               # imagem PIL pronta para a aba
        self.previa_n = 0
        threading.Thread(target=self._loop, daemon=True).start()

    # ---- abrir a placa no formato certo
    def _abrir(self, cv2, fourcc):
        cap = cv2.VideoCapture(self.fonte, cv2.CAP_DSHOW if WIN else cv2.CAP_ANY)
        if not cap.isOpened():
            cap.release()
            return None
        w, h, fps = self.modo
        if fourcc:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
        cap.set(cv2.CAP_PROP_FPS, fps)
        if fourcc:   # alguns drivers só aceitam o formato depois do tamanho
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _aguenta(self, cap, cv2, fourcc, segundos=1.3):
        """Confere se a placa está mesmo entregando o formato, o tamanho e os quadros por segundo pedidos."""
        w, h, fps = self.modo
        if fourcc and _fourcc_txt(cap.get(cv2.CAP_PROP_FOURCC)).upper() not in (fourcc, ""):
            return False
        t0, n, ok_tam = time.perf_counter(), 0, False
        while time.perf_counter() - t0 < segundos and self.rodando:
            ok, q = cap.read()
            if not ok or q is None:
                continue
            n += 1
            ok_tam = q.shape[1] == w and q.shape[0] == h
            self.quadro, self.t = q, time.perf_counter()
            self.tamanho = (q.shape[1], q.shape[0])
            self.n += 1
            self.novo.set()
        ritmo = n / max(1e-3, time.perf_counter() - t0)
        return ok_tam and ritmo >= fps * 0.8

    def _abrir_melhor(self, cv2):
        if isinstance(self.fonte, str):
            cap = cv2.VideoCapture(self.fonte)
            return (cap, "arquivo") if cap.isOpened() else (None, "")
        if self.formato == "MJPEG":
            candidatos = ["MJPG"]
        elif self.formato == "Sem compressão":
            candidatos = ["YUY2", "NV12"]
        else:
            candidatos = ["YUY2", "NV12", "MJPG"]
            if self.preferido in candidatos:
                candidatos.remove(self.preferido)
                candidatos.insert(0, self.preferido)
        for i, fcc in enumerate(candidatos):
            cap = self._abrir(cv2, fcc)
            if cap is None:
                return None, ""
            # último candidato: fica com ele mesmo que não esteja perfeito
            if i == len(candidatos) - 1 or self._aguenta(cap, cv2, fcc):
                return cap, fcc
            cap.release()
        return None, ""

    def _loop(self):
        import cv2
        import numpy as np
        cap, fcc = self._abrir_melhor(cv2)
        if cap is None:
            self.erro = "abrir"
            self.rodando = False
            return
        arquivo = fcc == "arquivo"
        self.formato_usado = {"YUY2": "sem compressão (YUY2)", "NV12": "sem compressão (NV12)", "MJPG": "MJPEG",
                              "arquivo": "arquivo"}.get(fcc, fcc)
        if self.ao_escolher and fcc and not arquivo:
            try:
                self.ao_escolher(fcc)
            except Exception:
                pass
        t0, cont, falhas, dist = time.time(), 0, 0, 0
        intervalo = 1 / (cap.get(cv2.CAP_PROP_FPS) or 30) if arquivo else 0
        periodo = 1.0 / (self.modo[2] if not arquivo else (cap.get(cv2.CAP_PROP_FPS) or 30))
        estimado = None
        anterior = None
        faixas = collections.deque(maxlen=600)
        while self.rodando:
            ok, q = cap.read()
            if not ok or q is None:
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
            chegou = time.perf_counter()
            # horário alisado: a placa manda num ritmo fixo; o atraso do USB varia um pouco a cada quadro
            if estimado is None:
                estimado = chegou
            else:
                previsto = estimado + periodo
                erro = chegou - previsto
                pulados = round(erro / periodo) if erro > 0.6 * periodo else 0
                if pulados:
                    previsto += pulados * periodo
                    erro = chegou - previsto
                if abs(erro) > 0.025:
                    estimado = chegou
                else:
                    estimado = previsto + 0.08 * erro
                    periodo = min(1 / 20, max(1 / 125, periodo + 0.002 * erro))
            # repetido ou novo? (amostra pequena: 1 pixel a cada 8)
            amostra = np.ascontiguousarray(q[::8, ::8])
            if anterior is None or amostra.shape != anterior.shape:
                dif = 255.0
            else:
                m = cv2.mean(cv2.absdiff(amostra, anterior))
                dif = (m[0] + m[1] + m[2]) / 3
            anterior = amostra
            if dif > 0.35:
                self.distintos.append((q, estimado, dif > 45))
                dist += 1
            # faixa de cor: preto mais escuro e branco mais claro dos últimos ~10 s
            if self.n % 6 == 0:
                a16 = amostra.astype(np.uint16)
                plano = ((a16[..., 0] + 2 * a16[..., 1] + a16[..., 2]) >> 2).reshape(-1)   # brilho
                k = max(1, len(plano) // 400)      # ignora 0,25% de cada ponta (ruído e bordas do MJPEG)
                part = np.partition(plano, (k, len(plano) - 1 - k))
                faixas.append((int(part[k]), int(part[len(plano) - 1 - k])))
                if self.n % 60 == 0 and len(faixas) >= 20:
                    lo = min(f[0] for f in faixas)
                    hi = max(f[1] for f in faixas)
                    if lo >= 12 and hi <= 240 and hi - lo > 120:
                        self.faixa_detectada = "limitada"
                    elif lo < 9 or hi > 246:
                        self.faixa_detectada = "completa"
            self.t = estimado
            self.quadro = q
            self.tamanho = (q.shape[1], q.shape[0])
            self.n += 1
            self.novo.set()
            # prévia da aba já pronta aqui, fora da interface (deixa o app leve)
            alvo = self.previa_tam
            if alvo and (dif > 0.35 or self.previa is None or getattr(self, "_previa_alvo", None) != alvo):
                try:
                    pw, ph = alvo
                    esc = min(pw / q.shape[1], ph / q.shape[0])
                    nw, nh = max(2, int(q.shape[1] * esc)), max(2, int(q.shape[0] * esc))
                    pq = cv2.resize(q, (nw, nh), interpolation=cv2.INTER_AREA if esc < 1 else cv2.INTER_LINEAR)
                    self.previa = Image.frombuffer("RGB", (nw, nh), pq.tobytes(), "raw", "BGR", 0, 1)
                    self._previa_alvo = alvo
                    self.previa_n += 1
                except Exception:
                    pass
            cont += 1
            agora = time.time()
            if agora - t0 >= 1:
                self.fps, self.fps_distintos = cont / (agora - t0), dist / (agora - t0)
                cont, dist, t0 = 0, 0, agora
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
        if self.tl_interp not in INTERP_OPCOES:      # versões antigas guardavam "120 Hz" etc.
            self.tl_interp = "Nativo" if str(self.tl_interp).endswith("Hz") else "Desligada"
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
        nome_v = self.tl_m_video.get()
        chave_fmt = f"{nome_v}|{modo}"
        salvos = self.cfg.setdefault("tela_formatos_ok", {})

        def escolheu(fcc, _k=chave_fmt):
            salvos[_k] = fcc
        self.tl_cap = Captura(fonte, MODOS_TELA.get(modo, (1920, 1080, 60)),
                              formato=self.cfg.get("tela_formato", "Automático"), preferido=salvos.get(chave_fmt),
                              ao_escolher=escolheu)
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
    def _tl_texto_gpu(self, g, cap):
        txt = traduzir(f"Tela cheia na placa de vídeo • {g.fps:.0f} fps na tela")
        m = g.interp_modo
        if m and not g.ia_falhou:
            txt += traduzir(f" (jogo a {g.fonte_fps:.0f}) • fluidez {texto_interp(m)}")
            if g.ia_info:
                txt += traduzir(f" • {g.ia_info} • atraso {g.atraso_ms:.0f} ms")
            if m != INTERP_NATIVO and g.hz_monitor and g.fonte_fps * m > g.hz_monitor * 1.05:
                txt += traduzir(f" • passa dos {g.hz_monitor} Hz do monitor: use um x menor ou Nativo")
        elif m and g.ia_falhou:
            txt += traduzir(" • fluidez indisponível nesta placa de vídeo")
        if g.fsr:
            txt += traduzir(" • FSR")
        if g.faixa_atual == "Limitada":
            txt += traduzir(" • cor 16-235 corrigida")
        if cap.formato_usado:
            txt += " • " + traduzir(cap.formato_usado)
        return txt

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
            cap.previa_tam = None          # a tela cheia está na frente: a prévia não gasta nada
            if self.aba == "tela" and (cap.n // 30) != getattr(self, "_tl_ult_info", -1):
                self._tl_ult_info = cap.n // 30
                self.c.itemconfig(self.tl_info, text=self._tl_texto_gpu(self.tl_gpu, cap))
            prox(100)
            return
        if self.aba != "tela" and not self.tl_cheia:
            cap.previa_tam = None          # em outra aba: a placa e o som continuam, sem gastar com a prévia
            prox(150)
            return
        if self.tl_cheia:
            cv_, item, larg, alt = self.tl_cheia["c"], self.tl_cheia["item"], self.tl_cheia["w"], self.tl_cheia["h"]
        else:
            cv_, item = self.c, self.tl_item
            larg, alt = self.p.px(self.PREV_W), self.p.px(self.PREV_H)
        cap.previa_tam = (larg, alt)
        img = cap.previa
        if img is not None and cap.previa_n != getattr(self, "_tl_previa_n", -1):
            self._tl_previa_n = cap.previa_n
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
        if not self.tl_cheia and (cap.n // 15) != getattr(self, "_tl_ult_info", -1) and cap.quadro is not None:
            self._tl_ult_info = cap.n // 15
            w_, h_ = cap.tamanho or (0, 0)
            txt = f"{w_}×{h_} • {cap.fps:.0f} fps"
            if cap.fps_distintos and cap.fps_distintos < cap.fps * 0.9:
                txt += traduzir(f" (jogo a {cap.fps_distintos:.0f})")
            if cap.formato_usado:
                txt += " • " + traduzir(cap.formato_usado)
            if self.tl_audio_msg:
                txt += "   " + traduzir(self.tl_audio_msg)
            self.c.itemconfig(self.tl_info, text=txt)
        prox(8)

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
    def _tl_opcoes(self):
        return dict(nitidez=float(self.cfg.get("tela_nitidez", 0.5)), faixa=self.cfg.get("tela_faixa", "Automática"),
                    vsync=bool(self.cfg.get("tela_vsync", True)), ia=self.cfg.get("tela_ia", "Automática"))

    def _tl_aplicar_opcoes(self):
        if getattr(self, "tl_gpu", None):
            self.tl_gpu.definir_opcoes(**self._tl_opcoes())

    def tl_opcoes_imagem(self):
        j = self._janela("Imagem", 500, 640)
        f_tit = ctk.CTkFont(family=F_LIGHT, size=22)
        f_txt = ctk.CTkFont(family=F_REG, size=12)
        f_rot = ctk.CTkFont(family=F_SEMI, size=13)
        ctk.CTkLabel(j, text="Imagem na tela cheia", font=f_tit, text_color=BRANCO).pack(anchor="w", padx=24,
                                                                                         pady=(20, 6))
        corpo = ctk.CTkScrollableFrame(j, fg_color="transparent", scrollbar_button_color="#26324D")
        corpo.pack(fill="both", expand=True, padx=(10, 6))
        ctk.CTkButton(j, text="OK", height=38, width=110, corner_radius=19, fg_color="#0070D1",
                      hover_color="#1888F0", font=ctk.CTkFont(family=F_SEMI, size=14),
                      command=lambda: (self.salvar_cfg(), j.destroy())).pack(side="bottom", anchor="e", padx=24,
                                                                           pady=(8, 16))

        def titulo(txt, topo=18):
            ctk.CTkLabel(corpo, text=txt, font=f_rot, text_color=BRANCO).pack(anchor="w", padx=14, pady=(topo, 4))

        def explica(txt, recuo=14):
            ctk.CTkLabel(corpo, text=txt, font=f_txt, text_color=CINZA, wraplength=420 - recuo,
                         justify="left").pack(anchor="w", padx=(recuo, 14), pady=(4, 0))

        def segmentado(valores, atual, ao_mudar):
            m = ctk.CTkSegmentedButton(corpo, values=list(valores), font=f_txt, height=32,
                                       selected_color="#0070D1", selected_hover_color="#1888F0",
                                       unselected_color="#16233F", unselected_hover_color="#20345C",
                                       command=ao_mudar)
            m.set(atual)
            m.pack(fill="x", padx=14)
            return m

        def chave(texto, var, ao_mudar):
            ctk.CTkSwitch(corpo, text=texto, variable=var, font=f_rot, progress_color="#0070D1",
                          button_color="#E5ECF8", fg_color="#2A3A5E", command=ao_mudar).pack(anchor="w", padx=14,
                                                                                           pady=(18, 0))

        # ---- nitidez e ampliação
        chave("FSR 1 — ampliação e nitidez da AMD", self.tl_fsr, self._tl_mudou_fsr)
        explica("Amplia a imagem para o tamanho do seu monitor sem borrar (EASU) e realça os detalhes sem "
                f"criar contornos (RCAS). Atalho na tela cheia: {self.nome_tecla('fsr')}.", 60)
        linha = ctk.CTkFrame(corpo, fg_color="transparent")
        linha.pack(fill="x", padx=(60, 14), pady=(8, 0))
        ctk.CTkLabel(linha, text="Nitidez", font=f_txt, text_color=BRANCO).pack(side="left")
        rot_nit = ctk.CTkLabel(linha, text="", font=f_txt, text_color=CINZA, width=40)
        rot_nit.pack(side="right")

        def mudou_nit(v):
            self.cfg["tela_nitidez"] = round(float(v), 2)
            rot_nit.configure(text=f"{round(float(v) * 100)}%")
            self._tl_aplicar_opcoes()
        sl = ctk.CTkSlider(linha, from_=0, to=1, number_of_steps=20, height=16, button_color="#E5ECF8",
                           progress_color="#0070D1", fg_color="#22304D", command=mudou_nit)
        sl.set(float(self.cfg.get("tela_nitidez", 0.5)))
        sl.pack(side="left", fill="x", expand=True, padx=10)
        mudou_nit(sl.get())

        # ---- fluidez
        titulo("Fluidez com IA (interpolação de quadros)")
        segmentado(INTERP_OPCOES, self.tl_interp, self._tl_mudou_interp)
        explica("Uma rede neural (RIFE) roda na sua placa de vídeo e cria os quadros que faltam entre dois quadros "
                "do jogo. x2 dobra (30 → 60), x4 quadruplica e Nativo acompanha o Hz do seu monitor: é o mais "
                "suave. Acrescenta cerca de 1 quadro do jogo de atraso. "
                f"Atalho na tela cheia: {self.nome_tecla('interp')}.")
        titulo("Precisão da IA", 12)

        def mudou_ia(v):
            self.cfg["tela_ia"] = v
            self._tl_aplicar_opcoes()
        segmentado(NIVEIS_IA, self.cfg.get("tela_ia", "Automática"), mudou_ia)
        explica("Automática escolhe sozinha conforme a folga da placa de vídeo. Alta acerta melhor objetos "
                "pequenos e rápidos; Leve serve para placas de vídeo mais simples.")

        # ---- cor e sinal
        titulo("Faixa de cor")

        def mudou_faixa(v):
            self.cfg["tela_faixa"] = v
            self._tl_aplicar_opcoes()
        segmentado(FAIXAS_COR, self.cfg.get("tela_faixa", "Automática"), mudou_faixa)
        explica("Corrige preto acinzentado e cores lavadas quando o PS3 manda RGB Limitado (o padrão dele) e a "
                "placa mostra como Completo. Automática descobre sozinha em alguns segundos.")
        titulo("Formato da placa de captura")

        def mudou_formato(v):
            self.cfg["tela_formato"] = v
        segmentado(FORMATOS_CAPTURA, self.cfg.get("tela_formato", "Automático"), mudou_formato)
        explica("Sem compressão não tem os quadradinhos do MJPEG e gasta menos processador, mas precisa de uma "
                "placa USB 3.0. Automático testa e escolhe. Vale na próxima vez que clicar em Iniciar.")

        # ---- ritmo e transmissão
        self.tl_vsync = tk.BooleanVar(value=self.cfg.get("tela_vsync", True))

        def mudou_vsync():
            self.cfg["tela_vsync"] = bool(self.tl_vsync.get())
            self._tl_aplicar_opcoes()
        chave("Sincronizar com o monitor (sem rasgos)", self.tl_vsync, mudou_vsync)
        explica("Troca a imagem no ritmo do monitor: acaba com as linhas cortando a tela e deixa o movimento "
                "regular. Desligado tem um pouco menos de atraso.", 60)
        self.tl_compat = tk.BooleanVar(value=self.cfg.get("tela_compativel", True))
        chave("Compatível com Discord e OBS", self.tl_compat,
              lambda: self.cfg.update(tela_compativel=bool(self.tl_compat.get())))
        explica("Evita que a transmissão trave com a tela cheia em foco. Desligue só se não for "
                "transmitir. Vale na próxima vez que abrir a tela cheia.\n"
                f"Com outra janela em foco, use Ctrl+Shift+{self.nome_tecla('fsr')} (FSR) e "
                f"Ctrl+Shift+{self.nome_tecla('interp')} (fluidez).", 60)
        ctk.CTkFrame(corpo, fg_color="transparent", height=10).pack()

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
                                       compativel=self.cfg.get("tela_compativel", True), opcoes=self._tl_opcoes())
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
                detalhes.append(traduzir("Pasta de jogo") if info["tipo"] == "pasta" else "PKG")
            txt = "  •  ".join(detalhes)
            if info.get("aviso"):
                txt += ("\n" if txt else "") + traduzir(info["aviso"])
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


# =============================================================== Updates de jogos (servidor da Sony)
# O PS3 pergunta em https://a0.ww.np.dl.playstation.net/tpl/np/<ID>/<ID>-ver.xml quais updates existem.
# Esse XML traz o link de cada .pkg (que fica na CDN da Sony) com tamanho e SHA-1.
SONY_UPD_URL = "https://a0.ww.np.dl.playstation.net/tpl/np/{0}/{0}-ver.xml"
# certificado raiz público da Sony usado por esse servidor (não vem nos navegadores nem no Windows)
SONY_CA = """-----BEGIN CERTIFICATE-----
MIID0jCCArqgAwIBAgIBADANBgkqhkiG9w0BAQUFADBUMQswCQYDVQQGEwJKUDEp
MCcGA1UEChMgU29ueSBDb21wdXRlciBFbnRlcnRhaW5tZW50IEluYy4xGjAYBgNV
BAMTEVNDRUkgRE5BUyBSb290IDA1MB4XDTA0MDcxMjA5MDExOVoXDTM3MTIwNjA5
MDExOVowVDELMAkGA1UEBhMCSlAxKTAnBgNVBAoTIFNvbnkgQ29tcHV0ZXIgRW50
ZXJ0YWlubWVudCBJbmMuMRowGAYDVQQDExFTQ0VJIEROQVMgUm9vdCAwNTCCASIw
DQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANmPeza8PwCqlI7esOGIkoSESnIN
g72ZD3Ut63jy7SdothPIvGBqVZWYkIpqJYJd1I4Nh//IpXQCQL0PnJLrh9BBeowq
Muf5NNq3Us80Ihiu9CvNEAEO18g3OFV1TYdSwQ5zUsk33OUeI7h4aBPDVcZXYeHt
dbPLqe4K8igian5prrAD5S6h28t8aAm+qMWRo+bW25B/841XwDGBP7/IxZv8Yoio
rCo80CVYe6lGoU08eeqQiaHI5zAF281DWZSoVfLjJUEWmEnxqr8aOhszRGePi+Ei
7UQjHDuZX9rLhDI1zAND+BA259tn/iwOqVXe20OccJllHJcG4Ecmd98f5qMCAwEA
AaOBrjCBqzAdBgNVHQ4EFgQUxlahM1tPzoN3YgVEhm0gV7Wv2twwfAYDVR0jBHUw
c4AUxlahM1tPzoN3YgVEhm0gV7Wv2tyhWKRWMFQxCzAJBgNVBAYTAkpQMSkwJwYD
VQQKEyBTb255IENvbXB1dGVyIEVudGVydGFpbm1lbnQgSW5jLjEaMBgGA1UEAxMR
U0NFSSBETkFTIFJvb3QgMDWCAQAwDAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQUF
AAOCAQEACZPihjwXA27wJ03tEKcHAeFLi8aBw2ysH4GwuH1dWb3UpuznWOB0iQT1
wQocnEFYCJx5XFEnj4aLWpSHLEq/sSO+my+aPoTEsy20ajF+YLYZm0bZxH50CJYh
rkET4C2aC0XvhGp9k1JQ1o0W6+cFT5LTlXapsq8Btt31t+XDPX7RqGV4WGekt3hM
T7xRc7JWXdAQijIrbYi8mtbM07KEGnPU6IT8C47+0mSurpwLOoWL1tPgo6ePpLNi
c4quUMgh9RXVjeTyXOMmyYdeUm2gt7qErvQONli+6Epmhm0A2khpIMHSpQjTE8gV
rZp42a6+zg1iYy2vFBOmiQ17GRUl0A==
-----END CERTIFICATE-----
"""
PASTA_PKGS = "/dev_hdd0/packages"
DISPOSITIVOS_JOGOS = ("/dev_hdd0", "/dev_usb000", "/dev_usb001")


def normalizar_id(texto):
    """'BLUS-30443', 'blus30443', 'Jogo [BLUS30443].iso' -> 'BLUS30443' (ou None)."""
    import re
    m = re.search(r"([A-Z]{4})[-_ ]?(\d{5})", (texto or "").upper())
    return (m.group(1) + m.group(2)) if m else None


def versao_num(v):
    try:
        return tuple(int(x) for x in str(v).strip().split(".") if x != "")
    except ValueError:
        return (0,)


def fw_bonito(v):
    """'03.5500' -> '3.55'."""
    try:
        a, b = str(v).split(".")
        return f"{int(a)}.{b[:2]}"
    except ValueError:
        return str(v)


def _contextos_sony():
    """Primeiro tenta conferir o servidor com o certificado da Sony (ele é antigo, assinado com SHA-1).
    Se o Python do PC recusar, cai para sem conferir: o .pkg é checado pelo SHA-1 de qualquer jeito."""
    import ssl
    ctx = ssl.create_default_context(cadata=SONY_CA)
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
    except ssl.SSLError:
        pass
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    solto = ssl.create_default_context()
    solto.check_hostname = False
    solto.verify_mode = ssl.CERT_NONE
    try:
        solto.set_ciphers("DEFAULT:@SECLEVEL=0")
    except ssl.SSLError:
        pass
    return ctx, solto


def _abrir_sony(url, timeout=30):
    import ssl
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    if not url.lower().startswith("https:"):
        return urllib.request.urlopen(req, timeout=timeout)
    ultimo = None
    for ctx in _contextos_sony():
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except urllib.error.HTTPError:
            raise
        except urllib.error.URLError as e:
            if not isinstance(e.reason, ssl.SSLError):
                raise
            ultimo = e
    raise ultimo


def _url_da_sony(url):
    import urllib.parse
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return host == "playstation.net" or host.endswith(".playstation.net")


def buscar_updates(title_id):
    """{'titulo': nome do jogo, 'pacotes': [{versao, tamanho, sha1, url, fw}, ...]} em ordem de versão."""
    import xml.etree.ElementTree as ET
    try:
        with _abrir_sony(SONY_UPD_URL.format(title_id), 20) as r:
            dados = r.read()
    except urllib.error.HTTPError as e:
        if e.code in (403, 404):
            return {"titulo": "", "pacotes": []}
        raise
    if not dados.strip():
        return {"titulo": "", "pacotes": []}
    raiz = ET.fromstring(dados)
    pacotes, vistos = [], set()
    for pk in raiz.iter("package"):
        a = pk.attrib
        url = a.get("url", "")
        if not url or not _url_da_sony(url) or url in vistos:
            continue
        vistos.add(url)
        pacotes.append({"versao": a.get("version", ""), "tamanho": int(a.get("size", "0") or 0),
                        "sha1": a.get("sha1sum", "").lower(), "url": url, "fw": a.get("ps3_system_ver", "")})
    titulo = ""
    for t in raiz.iter("TITLE"):
        if t.text and t.text.strip():
            titulo = t.text.strip()
    pacotes.sort(key=lambda p_: versao_num(p_["versao"]))
    return {"titulo": titulo, "pacotes": pacotes}


def nome_pkg(url):
    import urllib.parse
    return urllib.parse.unquote(urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]) or "update.pkg"


class LeitorPkg:
    """Lê o .pkg da Sony aos pedaços (serve de arquivo para o FTP), conta o progresso e confere o SHA-1.
    O .pkg termina com 32 bytes que guardam o SHA-1 de todo o resto; o XML da Sony traz o mesmo valor."""

    def __init__(self, resp, progresso, cancelar):
        import hashlib
        self.r, self.prog, self.cancelar = resp, progresso, cancelar
        self.h = hashlib.sha1()
        self.cauda = b""
        self.n = 0

    def read(self, n=BLOCO):
        if self.cancelar.is_set():
            raise Cancelado()
        d = self.r.read(n)
        if d:
            junto = self.cauda + d
            self.h.update(junto[:-32])
            self.cauda = junto[-32:]
            self.n += len(d)
            self.prog(len(d))
        return d

    def conferir(self, sha1_xml, tamanho):
        calc = self.h.hexdigest()
        if tamanho and self.n != tamanho:
            raise RuntimeError(f"O download veio incompleto ({formatar_tamanho(self.n)} de "
                               f"{formatar_tamanho(tamanho)}).")
        if calc != (sha1_xml or "") and calc != self.cauda[:20].hex():
            raise RuntimeError("O arquivo baixado veio corrompido (o SHA-1 não confere). Tente de novo.")


def sfo_de_bytes(d):
    """PARAM.SFO (bytes) -> {chave: valor}."""
    try:
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


def ler_bytes_remoto(ftp, caminho, limite=None, inicio=0):
    """Lê um arquivo do PS3 (ou só um pedaço dele, a partir de 'inicio')."""
    import io
    buf = io.BytesIO()
    ftp.voidcmd("TYPE I")
    conn = ftp.transfercmd(f"RETR {caminho}", rest=inicio or None)
    try:
        while limite is None or buf.tell() < limite:
            d = conn.recv(65536 if limite is None else min(65536, limite - buf.tell()))
            if not d:
                break
            buf.write(d)
    finally:
        conn.close()
    try:
        ftp.voidresp()
    except ftplib.all_errors:          # cortar a transferência no meio faz o servidor responder 426
        pass
    return buf.getvalue()


def _sfo_remoto(ftp, caminho):
    try:
        return sfo_de_bytes(ler_bytes_remoto(ftp, caminho, 64 * 1024))
    except ftplib.all_errors:
        return {}


def listar_jogos_ps3(ftp, avisar=None):
    """Junta os jogos do PS3 (pastas GAMES, ISOs e o que estiver instalado em /dev_hdd0/game).
    Devolve [{id, titulo, instalado, origens}] — 'instalado' é a maior versão vista (base ou update)."""
    import re
    jogos = {}

    def add(tid, titulo, versao, origem):
        if not tid:
            return
        j = jogos.setdefault(tid, {"id": tid, "titulo": "", "instalado": "", "origens": []})
        if titulo and (not j["titulo"] or origem != "HDD"):
            j["titulo"] = titulo
        if versao and versao_num(versao) > versao_num(j["instalado"] or "0"):
            j["instalado"] = versao
        if origem not in j["origens"]:
            j["origens"].append(origem)

    for dev in DISPOSITIVOS_JOGOS:
        try:
            pastas = listar_remoto(ftp, f"{dev}/GAMES")
        except ftplib.all_errors:
            pastas = []
        for nome, eh_pasta, _ in pastas:
            if not eh_pasta:
                continue
            if avisar:
                avisar(f"Lendo {legivel(nome)}…")
            sfo = _sfo_remoto(ftp, f"{dev}/GAMES/{nome}/PS3_GAME/PARAM.SFO")
            tid = normalizar_id(sfo.get("TITLE_ID", "")) or normalizar_id(nome)
            add(tid, sfo.get("TITLE") or legivel(nome), sfo.get("APP_VER", ""), "Pasta")
        try:
            isos = listar_remoto(ftp, f"{dev}/PS3ISO")
        except ftplib.all_errors:
            isos = []
        for nome, eh_pasta, _ in isos:
            baixo = nome.lower()
            if eh_pasta or not (baixo.endswith(".iso") or baixo.endswith(".iso.0")):
                continue
            if avisar:
                avisar(f"Lendo {legivel(nome)}…")
            tid = None
            try:      # a ISO do PS3 guarda o código do jogo no setor 1 (posição 0x810)
                tid = normalizar_id(ler_bytes_remoto(ftp, f"{dev}/PS3ISO/{nome}", 10, 0x810).decode("latin-1"))
            except ftplib.all_errors:
                pass
            tid = tid or normalizar_id(nome)
            titulo = re.sub(r"\s*[\[(][A-Z]{4}-?\d{5}[\])]\s*", " ", legivel(nome))
            titulo = re.sub(r"\.iso(\.0)?$", "", titulo, flags=re.I).strip()
            add(tid, titulo, "", "ISO")
    # updates já instalados (e jogos da PSN) ficam em /dev_hdd0/game/<código>
    try:
        instalados = listar_remoto(ftp, "/dev_hdd0/game")
    except ftplib.all_errors:
        instalados = []
    for nome, eh_pasta, _ in instalados:
        if not eh_pasta or normalizar_id(nome) != nome.upper():
            continue
        if avisar:
            avisar(f"Lendo {nome}…")
        sfo = _sfo_remoto(ftp, f"/dev_hdd0/game/{nome}/PARAM.SFO")
        cat = str(sfo.get("CATEGORY", "")).upper()
        if cat not in ("GD", "HG", "DG"):      # GD = update de jogo; HG = jogo da PSN/HDD
            continue
        add(nome.upper(), sfo.get("TITLE", ""), sfo.get("APP_VER", ""), "HDD")
    return sorted(jogos.values(), key=lambda j_: (sem_acento(j_["titulo"] or j_["id"]).lower(), j_["id"]))


def versao_instalada(ftp, tid):
    sfo = _sfo_remoto(ftp, f"/dev_hdd0/game/{tid}/PARAM.SFO")
    return sfo.get("APP_VER", "") if str(sfo.get("CATEGORY", "")).upper() in ("GD", "HG", "DG") else ""


class Updates:
    # ================================================= aba UPDATES
    def _up(self):
        if not hasattr(self, "up_estado"):
            self.up_estado = {"jogos": None, "lendo": False, "sel": None, "info": {}, "buscando": set(),
                              "baixando": False, "msg": ("", CINZA), "frac": None, "cancelar": threading.Event()}
        return self.up_estado

    def _up_ativo(self):
        return self.aba == "updates" and getattr(self, "up_lbl", None) is not None and self.up_lbl.winfo_exists()

    def tela_updates(self):
        self.limpar()
        st = self._up()
        p, c = self.p, self.c
        x0, y0, w, h = 48, 116, 864, 466
        c.create_image(p.px(x0 + w / 2), p.px(y0 + h / 2), tags="view",
                       image=p.ret(w, h, 20, PAINEL_RGB + (255,), outline=(255, 255, 255, 30), largura=1))
        fonte = ctk.CTkFont(family=F_REG, size=13)
        fonte_b = ctk.CTkFont(family=F_SEMI, size=13)
        painel = ctk.CTkFrame(self.root, fg_color=PAINEL, corner_radius=0, width=w - 28, height=h - 28)
        painel.grid_propagate(False)
        painel.pack_propagate(False)
        c.create_window(p.px(x0 + 14), p.px(y0 + 14), window=painel, anchor="nw", tags="view")
        self.widgets.append(painel)
        painel.grid_columnconfigure(0, weight=0)
        painel.grid_columnconfigure(1, weight=1)
        painel.grid_rowconfigure(1, weight=1)

        def botao(pai_, texto, cmd, largura=None, tipo="normal"):
            cores = {"normal": (BTN, BTN_HOVER, BRANCO), "azul": ("#0070D1", "#1888F0", BRANCO),
                     "perigo": ("#3A1620", "#5A1E2C", "#FCA5A5")}[tipo]
            return ctk.CTkButton(pai_, text=texto, command=cmd, height=34, corner_radius=17, font=fonte_b,
                                 width=largura or 0, fg_color=cores[0], hover_color=cores[1], text_color=cores[2],
                                 text_color_disabled="#6B7488")
        self._up_botao = botao

        topo = ctk.CTkFrame(painel, fg_color="transparent")
        topo.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 8))
        self.up_campo = ctk.CTkEntry(topo, height=34, corner_radius=17, fg_color="#0A1222", border_color="#26324D",
                                     text_color=BRANCO, font=fonte, placeholder_text_color=CINZA_ESCURO, width=300,
                                     placeholder_text="Código do jogo (ex.: BLUS30443)")
        self.up_campo.pack(side="left")
        self.up_campo.bind("<Return>", lambda e: self.up_buscar_codigo())
        botao(topo, "Buscar updates", self.up_buscar_codigo).pack(side="left", padx=(6, 0))
        self.up_btn_ler = botao(topo, "Ler jogos do PS3", self.up_ler_jogos)
        self.up_btn_ler.pack(side="right")

        # ---- esquerda: jogos do PS3
        esq = ctk.CTkFrame(painel, fg_color="transparent", width=300)
        esq.grid(row=1, column=0, sticky="nsew", padx=(8, 4))
        esq.grid_propagate(False)
        esq.grid_rowconfigure(1, weight=1)
        esq.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(esq, text="Jogos no PS3", font=ctk.CTkFont(family=F_SEMI, size=14), text_color=BRANCO,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 4))
        self.up_lista_jogos = ctk.CTkScrollableFrame(esq, fg_color="#0B1426", corner_radius=12,
                                                     scrollbar_button_color="#1E2A44",
                                                     scrollbar_button_hover_color="#2A3A5E")
        self.up_lista_jogos.grid(row=1, column=0, sticky="nsew")

        # ---- direita: updates do jogo escolhido
        dir_ = ctk.CTkFrame(painel, fg_color="transparent")
        dir_.grid(row=1, column=1, sticky="nsew", padx=(4, 8))
        dir_.grid_rowconfigure(1, weight=1)
        dir_.grid_columnconfigure(0, weight=1)
        self.up_cab = ctk.CTkLabel(dir_, text="", font=ctk.CTkFont(family=F_SEMI, size=14), text_color=BRANCO,
                                   anchor="w", justify="left", wraplength=480)
        self.up_cab.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 4))
        self.up_lista_pkgs = ctk.CTkScrollableFrame(dir_, fg_color="#0B1426", corner_radius=12,
                                                    scrollbar_button_color="#1E2A44",
                                                    scrollbar_button_hover_color="#2A3A5E")
        self.up_lista_pkgs.grid(row=1, column=0, sticky="nsew")

        # ---- rodapé: andamento e ações
        rod = ctk.CTkFrame(painel, fg_color="transparent")
        rod.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 2))
        rod.grid_columnconfigure(0, weight=1)
        self.up_barra = ctk.CTkProgressBar(rod, height=6, corner_radius=3, fg_color="#1A2744",
                                           progress_color="#1888F0")
        self.up_barra.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.up_lbl = ctk.CTkLabel(rod, text="", font=fonte, text_color=CINZA, anchor="w", justify="left",
                                   wraplength=520)
        self.up_lbl.grid(row=1, column=0, sticky="ew")
        acoes = ctk.CTkFrame(rod, fg_color="transparent")
        acoes.grid(row=1, column=1, sticky="e")
        self.up_btn_cancelar = botao(acoes, "Cancelar", self.up_cancelar, tipo="perigo")
        self.up_btn_pc = botao(acoes, "Baixar no PC", lambda: self.up_baixar(no_ps3=False))
        self.up_btn_pc.pack(side="left", padx=(0, 6))
        self.up_btn_ps3 = botao(acoes, "Instalar no PS3", lambda: self.up_baixar(no_ps3=True), tipo="azul")
        self.up_btn_ps3.pack(side="left")

        self._up_desenhar_jogos()
        self._up_desenhar_pkgs()
        self._up_msg(*st["msg"])
        self._up_progresso(st["frac"])
        self._up_botoes()
        if st["jogos"] is None and not st["lendo"] and self.estado_ps3 == "ok":
            self.up_ler_jogos()

    # ---------------- pedaços da tela
    def _up_msg(self, texto, cor=CINZA):
        self._up()["msg"] = (texto, cor)
        if self._up_ativo():
            self.up_lbl.configure(text=texto, text_color=cor)

    def _up_progresso(self, frac):
        self._up()["frac"] = frac
        if not self._up_ativo():
            return
        if frac is None:
            self.up_barra.grid_remove()
        else:
            self.up_barra.grid()
            self.up_barra.set(max(0.0, min(1.0, frac)))

    def _up_faltando(self, tid):
        info = self._up()["info"].get(tid)
        if not isinstance(info, dict):
            return []
        inst = versao_num(self._up_instalado(tid) or "0")
        return [pk for pk in info["pacotes"] if versao_num(pk["versao"]) > inst]

    def _up_instalado(self, tid):
        for j in self._up()["jogos"] or []:
            if j["id"] == tid:
                return j["instalado"]
        return ""

    def _up_botoes(self):
        if not self._up_ativo():
            return
        st = self._up()
        tid = st["sel"]
        info = st["info"].get(tid)
        tem = isinstance(info, dict) and bool(info["pacotes"])
        falta = self._up_faltando(tid) if tem else []
        livre = not st["baixando"]
        self.up_btn_pc.configure(state="normal" if livre and tem else "disabled")
        self.up_btn_ps3.configure(state="normal" if livre and falta and self.estado_ps3 == "ok" else "disabled",
                                  text="Instalar no PS3" if (falta or not tem) else "Já está atualizado")
        self.up_btn_ler.configure(state="normal" if livre and not st["lendo"] and self.estado_ps3 == "ok"
                                  else "disabled")
        if st["baixando"]:
            self.up_btn_cancelar.pack(side="left", padx=(0, 6), before=self.up_btn_pc)
        else:
            self.up_btn_cancelar.pack_forget()

    def _up_desenhar_jogos(self):
        if not self._up_ativo():
            return
        st = self._up()
        for w_ in self.up_lista_jogos.winfo_children():
            w_.destroy()
        f_nome = ctk.CTkFont(family=F_SEMI, size=13)
        f_sub = ctk.CTkFont(family=F_REG, size=11)
        if st["jogos"] is None:
            txt = "Lendo os jogos do PS3…" if st["lendo"] else (
                "Conecte o PS3 para ver os jogos." if self.estado_ps3 != "ok" else "")
            ctk.CTkLabel(self.up_lista_jogos, text=txt, font=f_sub, text_color=CINZA, wraplength=240).pack(pady=20)
            return
        jogos = list(st["jogos"])
        # códigos digitados à mão que não estão no PS3 também aparecem
        for tid in st["info"]:
            if not any(j["id"] == tid for j in jogos):
                jogos.insert(0, {"id": tid, "titulo": "", "instalado": "", "origens": ["Digitado"]})
        if not jogos:
            ctk.CTkLabel(self.up_lista_jogos, text="Nenhum jogo encontrado.\nDigite o código do jogo acima.",
                         font=f_sub, text_color=CINZA, justify="center").pack(pady=20)
            return
        for j in jogos:
            info = st["info"].get(j["id"])
            titulo = j["titulo"] or (info.get("titulo") if isinstance(info, dict) else "") or j["id"]
            sel = j["id"] == st["sel"]
            linha = ctk.CTkFrame(self.up_lista_jogos, fg_color="#1A3358" if sel else "#0F1B33", corner_radius=10,
                                 cursor="hand2")
            linha.pack(fill="x", pady=2, padx=(0, 4))
            n = ctk.CTkLabel(linha, text=titulo if len(titulo) <= 34 else titulo[:33] + "…", font=f_nome,
                             text_color=BRANCO, anchor="w")
            n.pack(fill="x", padx=10, pady=(6, 0))
            sub = j["id"] + (f"  •  v{j['instalado']}" if j["instalado"] else "")
            if isinstance(info, dict):
                falta = len(self._up_faltando(j["id"]))
                sub += traduzir(f"  •  {falta} update(s) novo(s)" if falta else ("  •  atualizado" if info["pacotes"]
                                                                                 else "  •  sem updates"))
            s = ctk.CTkLabel(linha, text=sub, font=f_sub, text_color="#7FB2F0" if sel else CINZA_ESCURO, anchor="w")
            s.pack(fill="x", padx=10, pady=(0, 6))
            for w_ in (linha, n, s):
                w_.bind("<Button-1>", lambda e, t=j["id"]: self.up_escolher(t))

    def _up_desenhar_pkgs(self):
        if not self._up_ativo():
            return
        st = self._up()
        for w_ in self.up_lista_pkgs.winfo_children():
            w_.destroy()
        f_v = ctk.CTkFont(family=F_SEMI, size=13)
        f_sub = ctk.CTkFont(family=F_REG, size=11)
        tid = st["sel"]
        if not tid:
            self.up_cab.configure(text="Escolha um jogo")
            ctk.CTkLabel(self.up_lista_pkgs, text="Escolha um jogo à esquerda ou digite o código dele.\n"
                                                  "Os updates vêm direto do servidor da Sony.",
                         font=f_sub, text_color=CINZA, justify="center").pack(pady=30)
            return
        info = st["info"].get(tid)
        jogo = next((j for j in st["jogos"] or [] if j["id"] == tid), None)
        nome = (jogo and jogo["titulo"]) or (info.get("titulo") if isinstance(info, dict) else "") or tid
        inst = self._up_instalado(tid)
        self.up_cab.configure(text=f"{nome}   ({tid})" + (f"   •   no PS3: v{inst}" if inst else ""))
        if tid in st["buscando"]:
            ctk.CTkLabel(self.up_lista_pkgs, text="Perguntando ao servidor da Sony…", font=f_sub,
                         text_color=CINZA).pack(pady=30)
            return
        if isinstance(info, Exception):
            ctk.CTkLabel(self.up_lista_pkgs, text=f"Não consegui falar com o servidor da Sony.\n({str(info)[:90]})",
                         font=f_sub, text_color="#F87171", justify="center").pack(pady=24)
            self._up_botao(self.up_lista_pkgs, "Tentar de novo", lambda: self.up_escolher(tid, True)).pack()
            return
        if not info:
            return
        if not info["pacotes"]:
            ctk.CTkLabel(self.up_lista_pkgs, text="A Sony não tem updates para este jogo.", font=f_sub,
                         text_color=CINZA).pack(pady=30)
            return
        inst_n = versao_num(inst or "0")
        total = 0
        for pk in info["pacotes"]:
            novo = versao_num(pk["versao"]) > inst_n
            if novo:
                total += pk["tamanho"]
            linha = ctk.CTkFrame(self.up_lista_pkgs, fg_color="#0F1B33", corner_radius=10)
            linha.pack(fill="x", pady=2, padx=(0, 4))
            ctk.CTkLabel(linha, text=f"Versão {pk['versao']}", font=f_v, text_color=BRANCO).pack(
                side="left", padx=(12, 10), pady=8)
            sub = formatar_tamanho(pk["tamanho"]) + (f"  •  precisa do sistema {fw_bonito(pk['fw'])}" if pk["fw"]
                                                    else "")
            ctk.CTkLabel(linha, text=sub, font=f_sub, text_color=CINZA).pack(side="left")
            ctk.CTkLabel(linha, text="novo" if novo else "✓ instalado", font=f_sub,
                         text_color="#7FB2F0" if novo else "#34D399").pack(side="right", padx=12)
        falta = self._up_faltando(tid)
        if not st["baixando"] and not self.up_lbl.cget("text"):
            if falta:
                self._up_msg(f"{len(falta)} update(s) para instalar • {formatar_tamanho(total)}")
            else:
                self._up_msg("Este jogo já está com o último update.", "#34D399")

    # ---------------- ações
    def up_ler_jogos(self):
        st = self._up()
        if st["lendo"] or self.estado_ps3 != "ok":
            return
        st["lendo"] = True
        st["jogos"] = None
        self._up_desenhar_jogos()
        self._up_botoes()
        self._up_msg("Lendo os jogos do PS3…")

        def avisar(t):
            self.fila.put(("cb", lambda t=t: self._up_msg(t)))

        def ok(jogos):
            st["jogos"] = jogos
            self._up_msg(f"{len(jogos)} jogo(s) encontrado(s). Escolha um para ver os updates." if jogos else
                         "Não achei jogos no PS3. Digite o código do jogo acima.")
            self._up_desenhar_jogos()
            self._up_desenhar_pkgs()

        def erro(e):
            st["jogos"] = []
            self._up_msg(f"Não consegui ler os jogos ({str(e)[:60]})", "#F87171")
            self._up_desenhar_jogos()

        def fim():
            st["lendo"] = False
            self._up_botoes()
        self.em_thread(lambda ftp: listar_jogos_ps3(ftp, avisar), ok, erro, fim)

    def up_buscar_codigo(self):
        tid = normalizar_id(self.up_campo.get())
        if not tid:
            self._up_msg("Digite o código do jogo, como BLUS30443 (fica na capa ou no nome da ISO).", "#FBBF24")
            return
        self.up_campo.delete(0, "end")
        self.up_escolher(tid, True)

    def up_escolher(self, tid, buscar_de_novo=False):
        st = self._up()
        st["sel"] = tid
        if not st["baixando"]:
            self._up_msg("")
        if buscar_de_novo or tid not in st["info"] or isinstance(st["info"].get(tid), Exception):
            st["info"].pop(tid, None)
            st["buscando"].add(tid)

            def tarefa():
                try:
                    r = buscar_updates(tid)
                except Exception as e:
                    r = e
                self.fila.put(("cb", lambda: pronto(r)))

            def pronto(r):
                st["buscando"].discard(tid)
                st["info"][tid] = r
                if st["sel"] == tid:
                    self._up_desenhar_pkgs()
                    self._up_botoes()
                self._up_desenhar_jogos()
            threading.Thread(target=tarefa, daemon=True).start()
        self._up_desenhar_jogos()
        self._up_desenhar_pkgs()
        self._up_botoes()

    def up_cancelar(self):
        self._up()["cancelar"].set()
        self._up_msg("Cancelando…", "#FBBF24")

    def up_baixar(self, no_ps3):
        st = self._up()
        tid = st["sel"]
        info = st["info"].get(tid)
        if st["baixando"] or not isinstance(info, dict) or not info["pacotes"]:
            return
        lista = self._up_faltando(tid) if no_ps3 else (self._up_faltando(tid) or list(info["pacotes"]))
        if not lista:
            return
        pasta = None
        if not no_ps3:
            pasta = filedialog.askdirectory(title="Onde salvar os updates?", parent=self.root)
            if not pasta:
                return
            pasta = os.path.join(pasta, tid)
            os.makedirs(pasta, exist_ok=True)
        st["baixando"] = True
        st["cancelar"] = threading.Event()
        cancelar = st["cancelar"]
        self._up_botoes()
        self._up_progresso(0)
        total = sum(pk["tamanho"] for pk in lista) or 1
        andamento = {"feito": 0, "t0": time.time(), "ultimo": 0.0, "texto": ""}
        ip = self.cfg.get("ip")

        def avisar(t, cor=CINZA):
            self.fila.put(("cb", lambda: self._up_msg(t, cor)))

        def contar(n):
            andamento["feito"] += n
            agora = time.time()
            if agora - andamento["ultimo"] < 0.25:
                return
            andamento["ultimo"] = agora
            feito = andamento["feito"]
            vel = feito / max(0.5, agora - andamento["t0"])
            txt = (f"{andamento['texto']}  •  {formatar_tamanho(feito)} de {formatar_tamanho(total)}"
                   f"  •  {formatar_tamanho(vel)}/s")
            self.fila.put(("cb", lambda f=feito / total, t=txt: (self._up_progresso(f), self._up_msg(t))))

        def trabalho():
            ftp = None
            try:
                if no_ps3:
                    ftp = conectar(self.cfg)
                    try:
                        ftp.mkd(PASTA_PKGS)
                    except ftplib.error_perm:
                        pass
                enviados = []
                for i, pk in enumerate(lista, 1):
                    nome = nome_pkg(pk["url"])
                    andamento["texto"] = f"Baixando a versão {pk['versao']} ({i} de {len(lista)})"
                    avisar(andamento["texto"] + "…")
                    destino = f"{PASTA_PKGS}/{para_ftp(nome)}"
                    if no_ps3 and tamanho_remoto(ftp, destino) == pk["tamanho"]:
                        contar(pk["tamanho"])          # já estava no PS3 de uma vez anterior
                        enviados.append((pk, destino))
                        continue
                    with _abrir_sony(pk["url"], 60) as resp:
                        leitor = LeitorPkg(resp, contar, cancelar)
                        if no_ps3:
                            try:
                                ftp.storbinary(f"STOR {destino}", leitor, blocksize=BLOCO)
                                leitor.conferir(pk["sha1"], pk["tamanho"])
                            except BaseException:
                                try:
                                    ftp.delete(destino)
                                except ftplib.all_errors:
                                    pass
                                raise
                            enviados.append((pk, destino))
                        else:
                            local = os.path.join(pasta, nome)
                            try:
                                with open(local, "wb") as f:
                                    while True:
                                        d = leitor.read(BLOCO)
                                        if not d:
                                            break
                                        f.write(d)
                                leitor.conferir(pk["sha1"], pk["tamanho"])
                            except BaseException:
                                try:
                                    os.remove(local)
                                except OSError:
                                    pass
                                raise
                if not no_ps3:
                    return ("pc", len(lista), pasta)
                # instala um de cada vez, da versão mais antiga para a mais nova
                self.fila.put(("cb", lambda: self._up_progresso(None)))
                for i, (pk, destino) in enumerate(enviados, 1):
                    if cancelar.is_set():
                        raise Cancelado()
                    avisar(f"Instalando a versão {pk['versao']} no PS3 ({i} de {len(enviados)})… "
                           f"fique no XMB, sem abrir jogos.")
                    if not self._up_instalar(ftp, ip, tid, pk, destino, cancelar):
                        return ("manual", len(enviados), None)
                return ("ps3", len(enviados), None)
            finally:
                if ftp:
                    try:
                        ftp.quit()
                    except Exception:
                        ftp.close()

        def rodar():
            try:
                r = trabalho()
                self.fila.put(("cb", lambda: fim_ok(r)))
            except Cancelado:
                self.fila.put(("cb", lambda: fim_erro("Cancelado.", "#FBBF24")))
            except Exception as e:
                self.fila.put(("cb", lambda e=e: fim_erro(f"Não deu certo: {str(e)[:110]}", "#F87171")))

        def terminar():
            st["baixando"] = False
            self._up_progresso(None)
            self._up_botoes()

        def fim_ok(r):
            terminar()
            tipo, n, onde = r
            if tipo == "pc":
                self._up_msg(f"✓ {n} update(s) salvo(s) em {onde}", "#34D399")
                if self.aba != "updates":
                    self._aviso_app("Updates baixados no PC")
                return
            if tipo == "manual":
                self._up_msg(f"✓ {n} update(s) enviado(s) para /dev_hdd0/packages. Para instalar, no PS3 abra "
                             "Package Manager › Install Package Files › Standard e instale do mais antigo "
                             "para o mais novo.", "#34D399")
            else:
                self._up_msg(f"✓ {n} update(s) instalado(s) no PS3.", "#34D399")
                if self.aba != "updates":
                    self._aviso_app("Updates instalados no PS3")
            self._up_atualizar_versao(tid)

        def fim_erro(t, cor):
            terminar()
            self._up_msg(t, cor)
        threading.Thread(target=rodar, daemon=True).start()

    def _up_instalar(self, ftp, ip, tid, pk, destino, cancelar):
        alvo = versao_num(pk["versao"])
        return instalar_pkg_ps3(self.cfg, ftp, destino, cancelar, f"a versão {pk['versao']}",
                                pronto=lambda f: versao_num(versao_instalada(f, tid) or "0") >= alvo)

    def _up_atualizar_versao(self, tid):
        def ok(v):
            for j in self._up()["jogos"] or []:
                if j["id"] == tid and v and versao_num(v) > versao_num(j["instalado"] or "0"):
                    j["instalado"] = v
            self._up_desenhar_jogos()
            self._up_desenhar_pkgs()
            self._up_botoes()
        self.em_thread(lambda ftp: versao_instalada(ftp, tid), ok, lambda e: None)


# =============================================================== Controle remoto (controle do PC -> PS3 pelo webMAN)
# O webMAN MOD cria um controle virtual no PS3 e aceita o estado dele por /pad.ps3?hold<botões>.
# Limites do próprio webMAN: o analógico só vai "inclinado até o fim" (8 direções) e um analógico por vez.
BOTOES_PS3 = ("cross", "circle", "square", "triangle", "L1", "R1", "L2", "R2", "L3", "R3", "select", "start", "psbtn")


def _direcoes(x, y, limite=0.5):
    d = []
    if y < -limite:
        d.append("up")
    elif y > limite:
        d.append("down")
    if x < -limite:
        d.append("left")
    elif x > limite:
        d.append("right")
    return d


def comando_pad(botoes, dpad, esq=(0.0, 0.0), dir_=(0.0, 0.0)):
    """Estado do controle -> texto do /pad.ps3. Eixos de -1 a 1 (y positivo = para baixo).
    O direcional tem prioridade sobre o analógico, e o esquerdo sobre o direito (o webMAN só aceita um)."""
    partes = ["hold"] + [b for b in BOTOES_PS3 if b in botoes]
    if dpad:
        partes += [d for d in ("up", "down", "left", "right") if d in dpad]
    else:
        for nome, (x, y) in (("analogL", esq), ("analogR", dir_)):
            d = _direcoes(x, y)
            if d:
                partes.append(nome + "_" + "".join(d))
                break
    return "_".join(partes)


class EnviadorPad:
    """Manda o estado mais recente do controle para o webMAN, sem acumular fila (só o último vale)."""

    def __init__(self, ip, ao_erro=None):
        self.ip, self.ao_erro = ip, ao_erro
        self.cond = threading.Condition()
        self.pendente = None
        self.desejado = None
        self.vivo = True
        self.con = None
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def enviar(self, comando):
        with self.cond:
            if comando == self.desejado:
                return
            self.desejado = self.pendente = comando
            self.cond.notify()

    def parar(self, esperar=0.0):
        """Solta tudo e desliga o controle virtual do PS3."""
        with self.cond:
            self.vivo = False
            self.cond.notify()
        if esperar:
            self.thread.join(esperar)

    def _pedir(self, caminho):
        import http.client
        for tentativa in range(2):
            try:
                if self.con is None:
                    self.con = http.client.HTTPConnection(self.ip, 80, timeout=4)
                self.con.request("GET", "/" + caminho, headers={"Connection": "keep-alive"})
                r = self.con.getresponse()
                r.read()
                if r.getheader("connection", "").lower() == "close":
                    self.con.close()
                    self.con = None
                return r.status
            except (OSError, http.client.HTTPException):
                try:
                    if self.con:
                        self.con.close()
                except Exception:
                    pass
                self.con = None
                if tentativa:
                    raise

    def _loop(self):
        # começa do zero: o controle virtual é criado de novo no primeiro botão e pega o primeiro
        # espaço livre (jogador 1 se não houver outro controle ligado no PS3)
        try:
            self._pedir("pad.ps3?off")
        except Exception:
            pass
        while True:
            with self.cond:
                while self.vivo and self.pendente is None:
                    self.cond.wait()
                if not self.vivo:
                    break
                cmd, self.pendente = self.pendente, None
            try:
                st = self._pedir("pad.ps3?" + cmd)
                if st in (400, 404, 501):
                    if self.ao_erro:
                        self.ao_erro("O webMAN do seu PS3 não tem o controle virtual. Use a versão completa "
                                     "do webMAN MOD (não a Lite).")
                    break
            except Exception:
                with self.cond:                 # tenta de novo com o estado mais recente
                    if self.pendente is None:
                        self.pendente = self.desejado
                time.sleep(0.5)
        for c in ("pad.ps3?hold", "pad.ps3?off"):
            try:
                self._pedir(c)
            except Exception:
                pass
        try:
            if self.con:
                self.con.close()
        except Exception:
            pass


class ControlePC:
    """Lê o controle ligado no PC. XInput primeiro (Xbox, GameSir, 8BitDo...); senão, joystick do Windows
    (DualShock 4/DualSense e outros) com o layout de controle de PlayStation."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes

        class GAMEPAD(ctypes.Structure):
            _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", ctypes.c_ubyte),
                        ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                        ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short), ("sThumbRY", ctypes.c_short)]

        class STATE(ctypes.Structure):
            _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", GAMEPAD)]

        class JOYINFOEX(ctypes.Structure):
            _fields_ = [(n, wintypes.DWORD) for n in ("dwSize", "dwFlags", "dwXpos", "dwYpos", "dwZpos", "dwRpos",
                                                       "dwUpos", "dwVpos", "dwButtons", "dwButtonNumber", "dwPOV",
                                                       "dwReserved1", "dwReserved2")]
        self.STATE, self.JOYINFOEX = STATE, JOYINFOEX
        self.xget = None
        for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                lib = ctypes.WinDLL(dll)
            except OSError:
                continue
            try:
                self.xget = lib[100]          # XInputGetStateEx: inclui o botão Guia (vira o PS)
            except (AttributeError, OSError):
                self.xget = lib.XInputGetState
            break
        try:
            self.winmm = ctypes.WinDLL("winmm")
        except OSError:
            self.winmm = None
        self.nome = ""

    def ler(self):
        """(nome, botões, direcional, esquerdo, direito) ou None se não houver controle."""
        r = self._xinput()
        return r if r else self._winmm()

    def _xinput(self):
        if not self.xget:
            return None
        ctypes = self.ctypes
        for i in range(4):
            st = self.STATE()
            if self.xget(i, ctypes.byref(st)) != 0:
                continue
            g = st.Gamepad
            b = g.wButtons
            mapa = {0x1000: "cross", 0x2000: "circle", 0x4000: "square", 0x8000: "triangle", 0x100: "L1",
                    0x200: "R1", 0x40: "L3", 0x80: "R3", 0x20: "select", 0x10: "start", 0x400: "psbtn"}
            botoes = {n for m, n in mapa.items() if b & m}
            if g.bLeftTrigger > 100:
                botoes.add("L2")
            if g.bRightTrigger > 100:
                botoes.add("R2")
            dpad = {n for m, n in ((1, "up"), (2, "down"), (4, "left"), (8, "right")) if b & m}
            esq = (g.sThumbLX / 32768, -g.sThumbLY / 32768)
            dir_ = (g.sThumbRX / 32768, -g.sThumbRY / 32768)
            return (f"controle XInput {i + 1}", botoes, dpad, esq, dir_)
        return None

    def _winmm(self):
        if not self.winmm:
            return None
        ctypes = self.ctypes
        for i in range(16):
            info = self.JOYINFOEX(dwSize=ctypes.sizeof(self.JOYINFOEX), dwFlags=0xFF)
            if self.winmm.joyGetPosEx(i, ctypes.byref(info)) != 0:
                continue
            ordem = ("square", "cross", "circle", "triangle", "L1", "R1", "L2", "R2", "select", "start", "L3", "R3",
                     "psbtn")
            botoes = {n for k, n in enumerate(ordem) if info.dwButtons & (1 << k)}
            dpad = set()
            pov = info.dwPOV
            if pov != 0xFFFF and pov <= 36000:
                ang = pov / 100.0
                if ang >= 292.5 or ang <= 67.5:
                    dpad.add("up")
                if 22.5 <= ang <= 157.5:
                    dpad.add("right")
                if 112.5 <= ang <= 247.5:
                    dpad.add("down")
                if 202.5 <= ang <= 337.5:
                    dpad.add("left")

            def eixo(v):
                return (v - 32767.5) / 32767.5
            esq = (eixo(info.dwXpos), eixo(info.dwYpos))
            dir_ = (eixo(info.dwZpos), eixo(info.dwRpos))
            return (f"controle {i + 1} do Windows", botoes, dpad, esq, dir_)
        return None


class ControleRemoto:
    """Liga e desliga o uso do controle do PC no PS3 (botão 🎮 no topo do app)."""

    def remoto_ativo(self):
        return getattr(self, "_remoto", None) is not None

    def alternar_remoto(self):
        if self.remoto_ativo():
            self.desligar_remoto()
        else:
            self.ligar_remoto()

    def ligar_remoto(self, leitor=None):
        if self.remoto_ativo():
            return
        if self.estado_ps3 != "ok":
            self._aviso_app("Conecte o PS3 antes de ligar o controle remoto.", "#FBBF24")
            return
        try:
            leitor = leitor or ControlePC()
        except Exception as e:
            self._aviso_app(f"Não consegui ler os controles do PC ({str(e)[:40]})", "#F87171")
            return
        estado = {"vivo": True, "nome": None, "avisou_sem": False}

        def erro(t):
            self.fila.put(("cb", lambda: (self._aviso_app(t, "#F87171"), self.desligar_remoto())))
        env = EnviadorPad(self.cfg.get("ip"), erro)
        self._remoto = (estado, env)

        def loop():
            while estado["vivo"]:
                try:
                    r = leitor.ler()
                except Exception:
                    r = None
                if r is None:
                    if estado["nome"] is not None or not estado["avisou_sem"]:
                        estado["avisou_sem"] = True
                        estado["nome"] = None
                        env.enviar("hold")
                        self.fila.put(("cb", lambda: self._aviso_app(
                            "Controle remoto ligado, mas não achei controle no PC. Conecte um.", "#FBBF24")))
                    time.sleep(0.5)
                    continue
                nome, botoes, dpad, esq, dir_ = r
                if nome != estado["nome"]:
                    estado["nome"] = nome
                    self.fila.put(("cb", lambda n=nome: self._aviso_app(f"Controle remoto ligado ({n}) 🎮")))
                env.enviar(comando_pad(botoes, dpad, esq, dir_))
                time.sleep(0.008)
        threading.Thread(target=loop, daemon=True).start()
        self._pintar_remoto()

    def desligar_remoto(self, esperar=0.0):
        r = getattr(self, "_remoto", None)
        if r is None:
            return
        estado, env = r
        estado["vivo"] = False
        env.parar(esperar)
        self._remoto = None
        self._pintar_remoto()
        self._aviso_app("Controle remoto desligado.", CINZA)

    def _pintar_remoto(self):
        if getattr(self, "pad_btn", None) is None:
            return
        on = self.remoto_ativo()
        self.c.itemconfig(self.pad_btn, image=self.pad_on if on else self.pad_n)
        self.c.itemconfig(self.pad_tx, fill=BRANCO)


# =============================================================== Troféus (destravar localmente, PS3 HEN)
# Formato dos arquivos: TROPUSR.DAT / TROPTRNS.DAT (engenharia reversa do PS3TrophyIsGood/TROPHYParser
# de darkautism) e PARAM.PFD (pfdtool de flatz; mesma lógica usada pelo Apollo Save Tool de bucanero).
# Só TROPUSR.DAT e TROPTRNS.DAT mudam; as chaves deles são iguais em todo PS3, então não é preciso a
# ID do console nem da conta. Antes de gravar, a assinatura atual é recalculada e precisa bater com a
# do PS3; se não bater, nada é alterado.
import hashlib as _hashlib
import hmac as _hmac

TROFEU_CHAVES = {
    "syscon": bytes.fromhex("D413B89663E1FE9F75143D3BB4565274"),
    "keygen": bytes.fromhex("6B1ACEA246B745FD8F93763B920594CD53483B82"),
    "PARAM.SFO": bytes.fromhex("5D5B647917024E9BB8D330486B996E795D7F4392"),
    "TROPSYS.DAT": bytes.fromhex("B080C40FF358643689281736A6BF15892CFEA436"),
    "TROPUSR.DAT": bytes.fromhex("8711EFF406913F0937F115FAB23DE1A9897A789A"),
    "TROPTRNS.DAT": bytes.fromhex("91EE81555ACC1C4FB5AAE5462CFE1C62A4AF36A5"),
    "TROPCONF.SFM": bytes.fromhex("E2ED33C71C444EEBC1E23D635AD8E82F4ECA4E94"),
}
TROP_MAGIC = 0x818F54AD00010000
TROP_SYNC = 0x00010000          # já foi para a PSN
TROP_NAO_SYNC = 0x00001000      # destravado só no console
TIPOS_TROFEU = {1: "Platina", 2: "Ouro", 3: "Prata", 4: "Bronze"}


class ErroTrofeu(Exception):
    pass


def _aes():
    from Crypto.Cipher import AES
    return AES


def tempo_ps3(segundos_unix):
    """Tempo do PS3: microssegundos desde o ano 1 (UTC)."""
    return int(segundos_unix * 1_000_000) + 62135596800000000


def tempo_unix(t):
    return (t - 62135596800000000) / 1_000_000 if t else 0


# ---------------------------------------------------------------- PARAM.PFD
class Pfd:
    ENTRADA = 272

    def __init__(self, dados):
        self.dados = bytearray(dados)
        d = self.dados
        if d[:8] != b"\0\0\0\0PFDB":
            raise ErroTrofeu("PARAM.PFD inválido")
        self.versao = struct.unpack_from(">Q", d, 8)[0]
        if self.versao not in (3, 4):
            raise ErroTrofeu(f"PARAM.PFD de versão desconhecida ({self.versao})")
        self.iv = bytes(d[16:32])
        AES = _aes()
        sig = AES.new(TROFEU_CHAVES["syscon"], AES.MODE_CBC, self.iv).decrypt(bytes(d[32:96]))
        self.sig = bytearray(sig)
        chave = bytes(sig[40:60])
        self.chave_real = (_hmac.new(TROFEU_CHAVES["keygen"], chave, _hashlib.sha1).digest()
                           if self.versao == 4 else chave)
        self.capacidade, self.reservadas, self.usadas = struct.unpack_from(">QQQ", d, 96)
        if not (0 < self.capacidade < 1000 and self.usadas <= self.reservadas < 1000):
            raise ErroTrofeu("PARAM.PFD com tabela estranha")
        self.ini_entradas = 96 + 24 + self.capacidade * 8
        self.ini_assinaturas = self.ini_entradas + self.reservadas * self.ENTRADA
        if self.ini_assinaturas + self.capacidade * 20 > len(d):
            raise ErroTrofeu("PARAM.PFD cortado")

    def _indice(self, i):
        return struct.unpack_from(">Q", self.dados, 120 + i * 8)[0]

    def _entrada(self, n):
        o = self.ini_entradas + n * self.ENTRADA
        return o, bytes(self.dados[o:o + self.ENTRADA])

    @staticmethod
    def _nome(e):
        return e[8:8 + 65].split(b"\0")[0].decode("latin-1")

    def arquivos(self):
        """{nome: índice da entrada}"""
        r = {}
        for n in range(self.usadas):
            r[self._nome(self._entrada(n)[1]).upper()] = n
        return r

    def tamanho(self, nome):
        o, e = self._entrada(self.arquivos()[nome.upper()])
        return struct.unpack_from(">Q", e, 264)[0]

    def _balde(self, nome):
        h = 0
        for ch in nome.encode("latin-1"):
            h = ((h << 5) - h + ch) & 0xFFFFFFFFFFFFFFFF
        return h % self.capacidade

    def _hash_balde(self, i):
        atual = self._indice(i)
        if atual >= self.reservadas:
            return _hmac.new(self.chave_real, b"", _hashlib.sha1).digest()
        m = _hmac.new(self.chave_real, digestmod=_hashlib.sha1)
        vistos = 0
        while atual < self.reservadas and vistos <= self.reservadas:
            _, e = self._entrada(atual)
            m.update(e[8:8 + 65])
            m.update(e[80:80 + 192])
            atual = struct.unpack_from(">Q", e, 0)[0]
            vistos += 1
        return m.digest()

    @staticmethod
    def hash_arquivo(nome, conteudo):
        chave = TROFEU_CHAVES.get(nome.upper())
        if chave is None:
            return None
        return _hmac.new(chave, conteudo, _hashlib.sha1).digest()

    def conferir(self, arquivos):
        """Recalcula tudo e diz o que não bate (lista vazia = assinatura igual à do PS3).
        arquivos = {nome: bytes como estão no PS3}"""
        erros = []
        d = self.dados
        top = _hmac.new(self.chave_real, bytes(d[96:96 + 24 + self.capacidade * 8]), _hashlib.sha1).digest()
        if top != bytes(self.sig[20:40]):
            erros.append("topo")
        fim = self.ini_assinaturas + self.capacidade * 20
        baixo = _hmac.new(self.chave_real, bytes(d[self.ini_assinaturas:fim]), _hashlib.sha1).digest()
        if baixo != bytes(self.sig[0:20]):
            erros.append("base")
        for i in range(self.capacidade):
            o = self.ini_assinaturas + i * 20
            if self._hash_balde(i) != bytes(d[o:o + 20]):
                erros.append(f"entrada {i}")
        for nome, n in self.arquivos().items():
            o, e = self._entrada(n)
            if nome not in arquivos:
                continue
            h = self.hash_arquivo(nome, arquivos[nome])
            if h is not None and h != e[144:164]:
                erros.append(nome)
        return erros

    def atualizar(self, arquivos):
        """Grava o hash novo dos arquivos alterados e refaz as assinaturas."""
        d = self.dados
        nomes = self.arquivos()
        for nome, conteudo in arquivos.items():
            n = nomes.get(nome.upper())
            if n is None:
                raise ErroTrofeu(f"{nome} não está no PARAM.PFD")
            o, _ = self._entrada(n)
            d[o + 144:o + 164] = self.hash_arquivo(nome, conteudo)
        for i in range(self.capacidade):
            o = self.ini_assinaturas + i * 20
            d[o:o + 20] = self._hash_balde(i)
        fim = self.ini_assinaturas + self.capacidade * 20
        self.sig[0:20] = _hmac.new(self.chave_real, bytes(d[self.ini_assinaturas:fim]), _hashlib.sha1).digest()
        self.sig[20:40] = _hmac.new(self.chave_real, bytes(d[96:96 + 24 + self.capacidade * 8]),
                                    _hashlib.sha1).digest()
        AES = _aes()
        d[32:96] = AES.new(TROFEU_CHAVES["syscon"], AES.MODE_CBC, self.iv).encrypt(bytes(self.sig))
        return bytes(d)

    def _chave_dados(self, nome):
        AES = _aes()
        _, e = self._entrada(self.arquivos()[nome.upper()])
        k = TROFEU_CHAVES[nome.upper()]
        return AES.new(TROFEU_CHAVES["syscon"], AES.MODE_CBC, k[:16]).decrypt(e[80:144])[:16]

    def _xor_contador(self, chave, n_blocos):
        AES = _aes()
        ecb = AES.new(chave, AES.MODE_ECB)
        return ecb.encrypt(b"".join(struct.pack(">QQ", i, 0) for i in range(n_blocos)))

    def decifrar(self, nome, dados):
        AES = _aes()
        tam = self.tamanho(nome)
        alinhado = (tam + 15) // 16 * 16
        bruto = dados[:alinhado].ljust(alinhado, b"\0")
        k = self._chave_dados(nome)
        dec = AES.new(k, AES.MODE_ECB).decrypt(bruto)
        ctr = self._xor_contador(k, alinhado // 16)
        return bytes(a ^ b for a, b in zip(dec, ctr))[:tam]

    def cifrar(self, nome, dados):
        AES = _aes()
        alinhado = (len(dados) + 15) // 16 * 16
        k = self._chave_dados(nome)
        ctr = self._xor_contador(k, alinhado // 16)
        mist = bytes(a ^ b for a, b in zip(dados.ljust(alinhado, b"\0"), ctr))
        return AES.new(k, AES.MODE_ECB).encrypt(mist)


# ---------------------------------------------------------------- TROPUSR.DAT / TROPTRNS.DAT
def _registros(d, nome):
    if len(d) < 48 or struct.unpack_from(">Q", d, 0)[0] != TROP_MAGIC:
        raise ErroTrofeu(f"{nome} inválido")
    n = struct.unpack_from(">I", d, 8)[0]
    if not 0 < n < 64:
        raise ErroTrofeu(f"{nome} com tabela estranha")
    regs = {}
    for i in range(n):
        rid, tam, _u, usos, ofs = struct.unpack_from(">IIIIQ", d, 48 + i * 32)
        regs[rid] = (ofs, tam, usos)
    return regs


def _blocos(d, ofs, qtd):
    """Lista de posições dos dados de 'qtd' blocos seguidos (cada um: cabeçalho de 16 bytes + dados)."""
    r = []
    for _ in range(qtd):
        if ofs + 16 > len(d):
            raise ErroTrofeu("bloco fora do arquivo")
        _tipo, tam = struct.unpack_from(">II", d, ofs)
        if tam == 0 or ofs + 16 + tam > len(d):
            raise ErroTrofeu("bloco com tamanho estranho")
        r.append(ofs + 16)
        ofs += 16 + tam
    return r


class TropUsr:
    def __init__(self, dados):
        self.d = bytearray(dados)
        d = self.d
        regs = _registros(d, "TROPUSR.DAT")
        for k in (3, 4, 5, 6, 7):
            if k not in regs:
                raise ErroTrofeu("TROPUSR.DAT sem a parte %d" % k)
        b3 = regs[3][0] + 16
        self.npcomm = bytes(d[b3:b3 + 16]).split(b"\0")[0].decode("latin-1")
        self.total = struct.unpack_from(">I", d, b3 + 24)[0]
        if not 0 < self.total <= 128:
            raise ErroTrofeu("número de troféus estranho")
        self.tipos = _blocos(d, regs[4][0], self.total)
        self.lista = regs[5][0] + 16
        self.tempos = _blocos(d, regs[6][0], self.total)
        self.r7 = regs[7][0] + 16

    def tipo(self, i):
        return struct.unpack_from(">I", self.d, self.tipos[i] + 4)[0]

    def info(self, i):
        o = self.tempos[i]
        _seq, dest, sync, _u, t1 = struct.unpack_from(">IIIIQ", self.d, o)
        return {"id": i, "tipo": self.tipo(i), "destravado": dest != 0, "sync": bool(sync & TROP_SYNC), "tempo": t1}

    def maior_tempo(self):
        ts = [struct.unpack_from(">Q", self.d, o + 16)[0] for o in self.tempos]
        ts += [struct.unpack_from(">Q", self.d, self.lista + k)[0] for k in (16, 32, 64)]
        return max(ts + [0])

    def destravar(self, i, t):
        d, o = self.d, self.tempos[i]
        if struct.unpack_from(">I", d, o + 4)[0] != 0:
            return False
        struct.pack_into(">II", d, o + 4, 1, TROP_NAO_SYNC)
        struct.pack_into(">QQ", d, o + 16, t, t)
        n = struct.unpack_from(">I", d, self.lista + 112)[0]
        struct.pack_into(">I", d, self.lista + 112, n + 1)
        n7 = struct.unpack_from(">I", d, self.r7)[0]
        struct.pack_into(">I", d, self.r7, n7 + 1)
        oa = self.lista + 128 + (i // 32) * 4
        struct.pack_into(">I", d, oa, struct.unpack_from(">I", d, oa)[0] | (1 << (i % 32)))
        if struct.unpack_from(">Q", d, self.lista + 64)[0] < t:          # último troféu ganho
            struct.pack_into(">QQ", d, self.lista + 64, t, t)
        struct.pack_into(">QQ", d, self.lista + 32, t, t)                  # última atualização
        return True


def _tropusr_mudar_tempo(self, i, t):
    """Troca o horário de um troféu já ganho (só no console)."""
    struct.pack_into(">QQ", self.d, self.tempos[i] + 16, t, t)


def _tropusr_fechar_tempos(self, agora):
    """Depois de mudar horários: "último troféu" = o mais novo dos ganhos; "última atualização" = agora."""
    ts = [struct.unpack_from(">Q", self.d, self.tempos[i] + 16)[0] for i in range(self.total) if self.info(i)["destravado"]]
    if ts:
        struct.pack_into(">QQ", self.d, self.lista + 64, max(ts), max(ts))
    struct.pack_into(">QQ", self.d, self.lista + 32, agora, agora)


TropUsr.mudar_tempo = _tropusr_mudar_tempo
TropUsr.fechar_tempos = _tropusr_fechar_tempos


class TropTrns:
    def __init__(self, dados):
        self.d = bytearray(dados)
        d = self.d
        regs = _registros(d, "TROPTRNS.DAT")
        if 3 not in regs or 4 not in regs:
            raise ErroTrofeu("TROPTRNS.DAT incompleto")
        self.b3 = regs[3][0] + 16
        self.npcomm = bytes(d[self.b3:self.b3 + 16]).split(b"\0")[0].decode("latin-1")
        ofs4 = regs[4][0]
        tam_bloco = struct.unpack_from(">I", d, ofs4 + 4)[0]
        if tam_bloco < 64:
            raise ErroTrofeu("TROPTRNS.DAT com bloco estranho")
        self.passo = 16 + tam_bloco
        self.ini = ofs4                       # bloco 0 = hora de início; 1.. = troféus ganhos
        depois = [o for o, _t, _u in regs.values() if o > ofs4]
        fim = min(depois) if depois else len(d)       # não invade a parte seguinte do arquivo
        self.capacidade = (fim - ofs4) // self.passo - 1
        self.tipo_bloco = struct.unpack_from(">I", d, ofs4)[0]
        self.contagem = struct.unpack_from(">I", d, self.b3 + 20)[0]     # ganhos + 1
        if not 1 <= self.contagem <= self.capacidade + 1:
            raise ErroTrofeu("contagem estranha no TROPTRNS.DAT")

    def ganhos(self):
        r = []
        for k in range(1, self.contagem):
            o = self.ini + k * self.passo + 16
            tid, tp = struct.unpack_from(">II", self.d, o + 32)
            sync = struct.unpack_from(">I", self.d, o + 8)[0]
            t = struct.unpack_from(">Q", self.d, o + 48)[0]
            r.append({"id": tid, "tipo": tp, "sync": sync != 0, "tempo": t})
        return r

    def maior_tempo(self):
        return max([g["tempo"] for g in self.ganhos()] + [0])

    def conferir_formato(self, total):
        """Confere se o arquivo está no formato esperado (ganhos + 1 na contagem, próximo espaço vazio).
        Se não estiver, é melhor não mexer: um formato diferente faria a gravação apagar um troféu."""
        for k in range(1, self.contagem):
            cab = self.ini + k * self.passo
            o = cab + 16
            tipo_b, tam = struct.unpack_from(">II", self.d, cab)
            exist = struct.unpack_from(">I", self.d, o + 4)[0]
            tid = struct.unpack_from(">I", self.d, o + 32)[0]
            if tipo_b != self.tipo_bloco or tam != self.passo - 16 or exist == 0 or tid >= total:
                raise ErroTrofeu("o TROPTRNS.DAT está num formato que o PSTudo não reconhece. Nada foi alterado.")
        self._conferir_vazio(self.contagem)

    def _conferir_vazio(self, k):
        if k > self.capacidade:
            raise ErroTrofeu("não há espaço no TROPTRNS.DAT")
        cab = self.ini + k * self.passo
        tipo_b, tam = struct.unpack_from(">II", self.d, cab)
        o = cab + 16
        exist, sync = struct.unpack_from(">II", self.d, o + 4)
        tid, t1, t2 = struct.unpack_from(">I", self.d, o + 32)[0], *struct.unpack_from(">QQ", self.d, o + 48)
        if tipo_b != self.tipo_bloco or tam != self.passo - 16 or exist or sync or tid or t1 or t2:
            raise ErroTrofeu("o espaço livre do TROPTRNS.DAT não está vazio. Nada foi alterado.")

    def mudar_tempo(self, i, t):
        for k in range(1, self.contagem):
            o = self.ini + k * self.passo + 16
            if struct.unpack_from(">I", self.d, o + 32)[0] == i:
                struct.pack_into(">QQ", self.d, o + 48, t, t)
                return True
        return False

    def destravar(self, i, tipo, t):
        if any(g["id"] == i for g in self.ganhos()):
            raise ErroTrofeu("TROPUSR.DAT e TROPTRNS.DAT não concordam sobre este troféu. Nada foi alterado.")
        k = self.contagem
        self._conferir_vazio(k)
        o = self.ini + k * self.passo + 16
        struct.pack_into(">IIII", self.d, o, k, 2, 0, 0)
        self.d[o + 16:o + self.passo - 16] = b"\0" * (self.passo - 32)
        struct.pack_into(">IIIIQQ", self.d, o + 32, i, tipo, 0x1000, 0, t, t)
        self.contagem += 1
        struct.pack_into(">I", self.d, self.b3 + 20, self.contagem)
        return True


# ---------------------------------------------------------------- nomes (TROP.SFM)
def ler_sfm(dados):
    """{id: {"nome", "detalhe", "tipo", "oculto"}} e o nome do jogo."""
    import re
    import xml.etree.ElementTree as ET
    i = dados.find(b"<?xml")
    if i < 0:
        i = dados.find(b"<trophyconf")
    if i < 0:
        return {}, ""
    texto = dados[i:].split(b"\0")[0]
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError:
        texto = re.sub(rb"&(?!amp;|lt;|gt;|quot;|apos;|#)", b"&amp;", texto)
        try:
            raiz = ET.fromstring(texto)
        except ET.ParseError:
            return {}, ""
    jogo = (raiz.findtext("title-name") or "").strip()
    r = {}
    for t in raiz.iter("trophy"):
        try:
            tid = int(t.get("id", ""))
        except ValueError:
            continue
        r[tid] = {"nome": (t.findtext("name") or "").strip(), "detalhe": (t.findtext("detail") or "").strip(),
                  "ttype": t.get("ttype", ""), "oculto": t.get("hidden", "no") == "yes",
                  "grupo": (t.get("gid") or "").strip()}
    return r, jogo


def destravar_trofeus(arquivos, ids, agora=None):
    """arquivos = {nome: bytes} da pasta do troféu, como estão no PS3.
    Devolve {nome: bytes novos} só dos arquivos que mudam (TROPUSR.DAT, TROPTRNS.DAT, PARAM.PFD)."""
    agora = agora or time.time()
    pfd = Pfd(arquivos["PARAM.PFD"])
    erros = pfd.conferir(arquivos)
    if erros:
        raise ErroTrofeu("A assinatura atual destes troféus não bateu com o cálculo do PSTudo "
                         f"({', '.join(erros[:4])}). Por segurança, nada foi alterado.")
    usr = TropUsr(arquivos["TROPUSR.DAT"])
    trns_plano = pfd.decifrar("TROPTRNS.DAT", arquivos["TROPTRNS.DAT"])
    trns = TropTrns(trns_plano)
    if usr.npcomm and trns.npcomm and usr.npcomm != trns.npcomm:
        raise ErroTrofeu("TROPUSR.DAT e TROPTRNS.DAT são de jogos diferentes.")
    trns.conferir_formato(usr.total)
    ganhos = {g["id"] for g in trns.ganhos()}
    if ganhos != {i for i in range(usr.total) if usr.info(i)["destravado"]}:
        raise ErroTrofeu("TROPUSR.DAT e TROPTRNS.DAT não concordam sobre os troféus ganhos. Nada foi alterado.")
    t = tempo_ps3(agora)
    ultimo = max(trns.maior_tempo(), usr.maior_tempo())
    if t <= ultimo:
        t = ultimo + 1_000_000
    # platina (tipo 1) só por último, e só se todos os troféus do jogo base ficarem ganhos
    grupos = {}
    if "TROPCONF.SFM" in arquivos:
        grupos = {k: v.get("grupo", "") for k, v in ler_sfm(arquivos["TROPCONF.SFM"])[0].items()}
    pedidos = [i for i in sorted(set(ids)) if 0 <= i < usr.total and not usr.info(i)["destravado"]]
    platinas = [i for i in pedidos if usr.tipo(i) == 1]
    outros = [i for i in pedidos if usr.tipo(i) != 1]
    base = [i for i in range(usr.total) if usr.tipo(i) != 1 and grupos.get(i, "") in ("", "0", "000")]
    vao_ficar = set(outros) | {i for i in range(usr.total) if usr.info(i)["destravado"]}
    pulou_platina = bool(platinas) and not all(i in vao_ficar for i in base)
    ordem = outros + ([] if pulou_platina else platinas)
    feitos = 0
    for i in ordem:
        usr.destravar(i, t)
        trns.destravar(i, usr.tipo(i), t)
        t += 1_000_000                       # um segundo entre cada um, na ordem
        feitos += 1
    if not feitos:
        if pulou_platina:
            raise ErroTrofeu("A platina só pode ser destravada junto com (ou depois de) todos os troféus do jogo.")
        return {}, 0, False
    novo_usr = bytes(usr.d)
    novo_trns = pfd.cifrar("TROPTRNS.DAT", bytes(trns.d))
    novo_trns = novo_trns + arquivos["TROPTRNS.DAT"][len(novo_trns):]   # mantém o tamanho do arquivo
    novos = {"TROPUSR.DAT": novo_usr, "TROPTRNS.DAT": novo_trns}
    novo_pfd = pfd.atualizar(novos)
    # confere o resultado antes de devolver
    final = dict(arquivos)
    final.update(novos)
    final["PARAM.PFD"] = novo_pfd
    p2 = Pfd(novo_pfd)
    if p2.conferir(final):
        raise ErroTrofeu("A assinatura nova não conferiu. Nada foi alterado.")
    if TropTrns(p2.decifrar("TROPTRNS.DAT", novo_trns)).contagem != trns.contagem:
        raise ErroTrofeu("O TROPTRNS.DAT novo não conferiu. Nada foi alterado.")
    novos["PARAM.PFD"] = novo_pfd
    return novos, feitos, pulou_platina


DATA_MINIMA_TROFEU = 1163203200      # 11/11/2006, lançamento do PS3


def formato_data():
    """dd/mm/aaaa em português e espanhol; mm/dd/yyyy em inglês."""
    return "%m/%d/%Y" if IDIOMA.get("atual") == "en" else "%d/%m/%Y"


def _abrir_trofeus(arquivos):
    """Confere assinatura e coerência; devolve (pfd, usr, trns)."""
    pfd = Pfd(arquivos["PARAM.PFD"])
    erros = pfd.conferir(arquivos)
    if erros:
        raise ErroTrofeu("A assinatura atual destes troféus não bateu com o cálculo do PSTudo "
                         f"({', '.join(erros[:4])}). Por segurança, nada foi alterado.")
    usr = TropUsr(arquivos["TROPUSR.DAT"])
    trns = TropTrns(pfd.decifrar("TROPTRNS.DAT", arquivos["TROPTRNS.DAT"]))
    if usr.npcomm and trns.npcomm and usr.npcomm != trns.npcomm:
        raise ErroTrofeu("TROPUSR.DAT e TROPTRNS.DAT são de jogos diferentes.")
    trns.conferir_formato(usr.total)
    ganhos = {g["id"] for g in trns.ganhos()}
    if ganhos != {i for i in range(usr.total) if usr.info(i)["destravado"]}:
        raise ErroTrofeu("TROPUSR.DAT e TROPTRNS.DAT não concordam sobre os troféus ganhos. Nada foi alterado.")
    return pfd, usr, trns


def _fechar_trofeus(arquivos, pfd, usr, trns):
    """Cifra, assina de novo e confere o resultado. Devolve {nome: bytes novos}."""
    novo_usr = bytes(usr.d)
    novo_trns = pfd.cifrar("TROPTRNS.DAT", bytes(trns.d))
    novo_trns = novo_trns + arquivos["TROPTRNS.DAT"][len(novo_trns):]   # mantém o tamanho do arquivo
    novos = {"TROPUSR.DAT": novo_usr, "TROPTRNS.DAT": novo_trns}
    novo_pfd = pfd.atualizar(novos)
    final = dict(arquivos)
    final.update(novos)
    final["PARAM.PFD"] = novo_pfd
    p2 = Pfd(novo_pfd)
    if p2.conferir(final):
        raise ErroTrofeu("A assinatura nova não conferiu. Nada foi alterado.")
    if TropTrns(p2.decifrar("TROPTRNS.DAT", novo_trns)).contagem != trns.contagem:
        raise ErroTrofeu("O TROPTRNS.DAT novo não conferiu. Nada foi alterado.")
    novos["PARAM.PFD"] = novo_pfd
    return novos


def mudar_datas_trofeus(arquivos, novas, agora=None):
    """novas = {id: segundos unix}. Muda a data e a hora de troféus já ganhos que nunca foram para a PSN.
    Devolve ({nome: bytes novos}, quantos mudaram)."""
    agora = agora or time.time()
    pfd, usr, trns = _abrir_trofeus(arquivos)
    feitos = 0
    for i, quando in sorted(novas.items()):
        if not 0 <= i < usr.total:
            continue
        info = usr.info(i)
        if not info["destravado"]:
            raise ErroTrofeu(f"o troféu {i} não está ganho. Nada foi alterado.")
        g = next((g for g in trns.ganhos() if g["id"] == i), None)
        if info["sync"] or (g and g["sync"]):
            raise ErroTrofeu("um dos troféus já foi para a PSN; a data dele não pode mudar. Nada foi alterado.")
        if not DATA_MINIMA_TROFEU <= quando <= agora + 60:
            raise ErroTrofeu("a data precisa ficar entre 11/11/2006 e agora. Nada foi alterado.")
        t = tempo_ps3(int(quando))
        if t == info["tempo"]:
            continue
        usr.mudar_tempo(i, t)
        if not trns.mudar_tempo(i, t):
            raise ErroTrofeu("o troféu não está no TROPTRNS.DAT. Nada foi alterado.")
        feitos += 1
    if not feitos:
        return {}, 0
    usr.fechar_tempos(max(tempo_ps3(agora), usr.maior_tempo()))
    return _fechar_trofeus(arquivos, pfd, usr, trns), feitos


def resumo_trofeus(arquivos):
    """Lista dos troféus de uma pasta: [{id, tipo, destravado, sync, tempo, nome, detalhe, oculto}], jogo."""
    usr = TropUsr(arquivos["TROPUSR.DAT"])
    nomes, jogo = {}, ""
    for chave in ("TROP_17.SFM", "TROP_07.SFM", "TROP.SFM", "TROPCONF.SFM"):
        if chave in arquivos:
            n, j = ler_sfm(arquivos[chave])
            if n and not nomes:
                nomes = n
            jogo = jogo or j
            if nomes and jogo:
                break
    lista = []
    for i in range(usr.total):
        x = usr.info(i)
        x.update(nomes.get(i, {"nome": f"Troféu {i}", "detalhe": "", "ttype": "", "oculto": False}))
        lista.append(x)
    return lista, jogo or usr.npcomm


HOME_PS3 = "/dev_hdd0/home"
ARQS_TROFEU_MUDAM = ("TROPUSR.DAT", "TROPTRNS.DAT", "PARAM.PFD")


def listar_usuarios_ps3(ftp):
    """[(id, nome)] dos usuários do PS3."""
    r = []
    try:
        itens = listar_remoto(ftp, HOME_PS3)
    except ftplib.all_errors:
        return r
    for nome, eh_pasta, _ in itens:
        if not eh_pasta or not nome.isdigit():
            continue
        try:
            apelido = ler_bytes_remoto(ftp, f"{HOME_PS3}/{nome}/localusername", 64).split(b"\0")[0]
            apelido = apelido.decode("utf-8", "ignore").strip()
        except ftplib.all_errors:
            apelido = ""
        r.append((nome, apelido or f"Usuário {int(nome)}"))
    return r


def listar_trofeus_ps3(ftp, usuario, avisar=None):
    """Jogos com troféus do usuário: [{pasta, codigo, jogo, total, ganhos, erro}].
    Uma pasta que não dá para ler entra na lista com o motivo (em vez de sumir)."""
    import html
    import re
    base = f"{HOME_PS3}/{usuario}/trophy"
    r = []
    try:
        pastas = listar_remoto(ftp, base)
    except ftplib.all_errors:
        return r
    for nome, eh_pasta, _ in pastas:
        if not eh_pasta:
            continue
        pasta = f"{base}/{nome}"
        if avisar:
            avisar(f"Lendo {nome}…")
        jogo = ""
        for sfm in ("TROPCONF.SFM", "TROP.SFM"):
            try:
                topo = ler_bytes_remoto(ftp, f"{pasta}/{sfm}", 8192)
            except ftplib.all_errors:
                continue
            m = re.search(rb"<title-name>(.*?)</title-name>", topo, re.S)
            if m:
                jogo = m.group(1).decode("utf-8", "ignore").strip()
                break
        item = {"pasta": pasta, "codigo": nome, "jogo": html.unescape(jogo) or nome, "total": 0, "ganhos": 0,
                "erro": ""}
        try:
            usr = TropUsr(ler_bytes_remoto(ftp, f"{pasta}/TROPUSR.DAT"))
            item["total"] = usr.total
            item["ganhos"] = sum(1 for i in range(usr.total) if usr.info(i)["destravado"])
        except ftplib.all_errors as e:
            item["erro"] = f"sem TROPUSR.DAT ({str(e)[:40]})"
        except (ErroTrofeu, struct.error, IndexError, ValueError) as e:
            item["erro"] = str(e)[:80] or type(e).__name__
        r.append(item)
    return sorted(r, key=lambda x: sem_acento(x["jogo"]).lower())


def baixar_pasta_trofeu(ftp, pasta):
    """{nome: bytes} de todos os arquivos da pasta do troféu (menos as imagens)."""
    arqs = {}
    for nome, eh_pasta, _ in listar_remoto(ftp, pasta):
        if eh_pasta or nome.upper().endswith(".PNG"):
            continue
        arqs[nome.upper()] = ler_bytes_remoto(ftp, f"{pasta}/{nome}")
    return arqs


def pasta_backup_trofeus(usuario, codigo):
    return os.path.join(os.path.expanduser("~"), "PSTudo", "backup_trofeus", usuario, codigo)


def gravar_trofeus_ps3(ftp, pasta, novos, originais):
    """Grava os arquivos novos com segurança: primeiro com outro nome, depois troca; no fim confere.
    Se algo falhar no meio, volta os originais."""
    import io
    temporarios = {}
    try:
        for nome, dados in novos.items():
            tmp = f"{pasta}/{nome}.pstudo"
            ftp.storbinary(f"STOR {tmp}", io.BytesIO(dados))
            if tamanho_remoto(ftp, tmp) != len(dados):
                raise ErroTrofeu(f"o PS3 não gravou {nome} inteiro")
            temporarios[nome] = tmp
        for nome in novos:
            try:
                ftp.delete(f"{pasta}/{nome}")
            except ftplib.error_perm:
                pass
            ftp.rename(temporarios[nome], f"{pasta}/{nome}")
        for nome, dados in novos.items():
            if ler_bytes_remoto(ftp, f"{pasta}/{nome}") != dados:
                raise ErroTrofeu(f"{nome} no PS3 ficou diferente do esperado")
    except Exception:
        for nome in novos:                       # volta como estava
            try:
                ftp.storbinary(f"STOR {pasta}/{nome}", io.BytesIO(originais[nome]))
            except ftplib.all_errors:
                pass
        raise
    finally:
        for tmp in temporarios.values():
            try:
                ftp.delete(tmp)
            except ftplib.all_errors:
                pass


class Trofeus:
    # ================================================= aba TROFÉUS
    def _tr(self):
        if not hasattr(self, "tr_estado"):
            self.tr_estado = {"usuarios": None, "usuario": None, "jogos": None, "lendo": False, "sel": None,
                              "lista": {}, "marcados": set(), "ocupado": False, "msg": ("", CINZA)}
        return self.tr_estado

    def _tr_ativo(self):
        return self.aba == "trofeus" and getattr(self, "tr_lbl", None) is not None and self.tr_lbl.winfo_exists()

    def tela_trofeus(self):
        self.limpar()
        st = self._tr()
        p, c = self.p, self.c
        x0, y0, w, h = 48, 116, 864, 466
        c.create_image(p.px(x0 + w / 2), p.px(y0 + h / 2), tags="view",
                       image=p.ret(w, h, 20, PAINEL_RGB + (255,), outline=(255, 255, 255, 30), largura=1))
        fonte = ctk.CTkFont(family=F_REG, size=13)
        fonte_b = ctk.CTkFont(family=F_SEMI, size=13)
        painel = ctk.CTkFrame(self.root, fg_color=PAINEL, corner_radius=0, width=w - 28, height=h - 28)
        painel.grid_propagate(False)
        painel.pack_propagate(False)
        c.create_window(p.px(x0 + 14), p.px(y0 + 14), window=painel, anchor="nw", tags="view")
        self.widgets.append(painel)
        painel.grid_columnconfigure(1, weight=1)
        painel.grid_rowconfigure(1, weight=1)

        def botao(pai_, texto, cmd, tipo="normal"):
            cores = {"normal": (BTN, BTN_HOVER, BRANCO), "azul": ("#0070D1", "#1888F0", BRANCO),
                     "perigo": ("#3A1620", "#5A1E2C", "#FCA5A5")}[tipo]
            return ctk.CTkButton(pai_, text=texto, command=cmd, height=34, corner_radius=17, font=fonte_b, width=0,
                                 fg_color=cores[0], hover_color=cores[1], text_color=cores[2],
                                 text_color_disabled="#6B7488")
        self._tr_botao = botao

        topo = ctk.CTkFrame(painel, fg_color="transparent")
        topo.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(6, 8))
        ctk.CTkLabel(topo, text="Troféus do PS3", font=ctk.CTkFont(family=F_SEMI, size=15), text_color=BRANCO).pack(
            side="left")
        self.tr_usuario = None
        if st["usuarios"] and len(st["usuarios"]) > 1:
            nomes = [f"{n} ({u})" for u, n in st["usuarios"]]
            atual = next((f"{n} ({u})" for u, n in st["usuarios"] if u == st["usuario"]), nomes[0])
            self.tr_usuario = ctk.CTkOptionMenu(topo, values=nomes, command=self._tr_trocar_usuario, height=32,
                                                fg_color=BTN, button_color=BTN_HOVER, font=fonte)
            self.tr_usuario.set(atual)
            self.tr_usuario.pack(side="left", padx=12)
        self.tr_btn_ler = botao(topo, "Ler de novo", self.tr_ler)
        self.tr_btn_ler.pack(side="right")
        botao(topo, "Backups", self.tr_abrir_backups).pack(side="right", padx=6)

        esq = ctk.CTkFrame(painel, fg_color="transparent", width=290)
        esq.grid(row=1, column=0, sticky="nsew", padx=(8, 4))
        esq.grid_propagate(False)
        esq.grid_rowconfigure(0, weight=1)
        esq.grid_columnconfigure(0, weight=1)
        self.tr_lista_jogos = ctk.CTkScrollableFrame(esq, fg_color="#0B1426", corner_radius=12,
                                                     scrollbar_button_color="#1E2A44",
                                                     scrollbar_button_hover_color="#2A3A5E")
        self.tr_lista_jogos.grid(row=0, column=0, sticky="nsew")

        dir_ = ctk.CTkFrame(painel, fg_color="transparent")
        dir_.grid(row=1, column=1, sticky="nsew", padx=(4, 8))
        dir_.grid_rowconfigure(1, weight=1)
        dir_.grid_columnconfigure(0, weight=1)
        self.tr_cab = ctk.CTkLabel(dir_, text="", font=ctk.CTkFont(family=F_SEMI, size=14), text_color=BRANCO,
                                   anchor="w", justify="left", wraplength=480)
        self.tr_cab.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 4))
        self.tr_lista = ctk.CTkScrollableFrame(dir_, fg_color="#0B1426", corner_radius=12,
                                               scrollbar_button_color="#1E2A44",
                                               scrollbar_button_hover_color="#2A3A5E")
        self.tr_lista.grid(row=1, column=0, sticky="nsew")

        rod = ctk.CTkFrame(painel, fg_color="transparent")
        rod.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(8, 2))
        rod.grid_columnconfigure(0, weight=1)
        self.tr_lbl = ctk.CTkLabel(rod, text="", font=fonte, text_color=CINZA, anchor="w", justify="left",
                                   wraplength=430)
        self.tr_lbl.grid(row=0, column=0, sticky="ew")
        acoes = ctk.CTkFrame(rod, fg_color="transparent")
        acoes.grid(row=0, column=1, sticky="e")
        self.tr_btn_restaurar = botao(acoes, "Desfazer", self.tr_restaurar)
        self.tr_btn_restaurar.pack(side="left", padx=(0, 6))
        self.tr_btn_datas = botao(acoes, "Data e hora", self.tr_datas)
        self.tr_btn_datas.pack(side="left", padx=(0, 6))
        self.tr_btn_todos = botao(acoes, "Marcar os que faltam", self.tr_marcar_todos)
        self.tr_btn_todos.pack(side="left", padx=(0, 6))
        self.tr_btn_destravar = botao(acoes, "Destravar", self.tr_destravar, "azul")
        self.tr_btn_destravar.pack(side="left")

        self._tr_desenhar_jogos()
        self._tr_desenhar_trofeus()
        self._tr_msg(*st["msg"])
        self._tr_botoes()
        if st["jogos"] is None and not st["lendo"] and self.estado_ps3 == "ok":
            self.tr_ler()

    def _tr_msg(self, texto, cor=CINZA):
        self._tr()["msg"] = (texto, cor)
        if self._tr_ativo():
            self.tr_lbl.configure(text=texto, text_color=cor)

    def _tr_botoes(self):
        if not self._tr_ativo():
            return
        st = self._tr()
        livre = not st["ocupado"] and not st["lendo"] and self.estado_ps3 == "ok"
        info = st["lista"].get(st["sel"])
        faltam = [t for t in info["trofeus"] if not t["destravado"]] if isinstance(info, dict) else []
        self.tr_btn_ler.configure(state="normal" if livre else "disabled")
        self.tr_btn_todos.configure(state="normal" if livre and faltam else "disabled")
        editaveis = [t for t in info["trofeus"] if t["destravado"] and not t["sync"]] if isinstance(info, dict) else []
        self.tr_btn_datas.configure(state="normal" if livre and editaveis else "disabled")
        n = len(st["marcados"])
        self.tr_btn_destravar.configure(state="normal" if livre and n else "disabled",
                                        text=f"Destravar {n}" if n else "Destravar")
        tem_backup = False
        if st["sel"] and st["usuario"]:
            b = pasta_backup_trofeus(st["usuario"], st["sel"])
            tem_backup = os.path.isdir(b) and any(d.is_dir() and not d.name.endswith("_desfeito")
                                                  and os.path.isdir(os.path.join(d.path, "depois"))
                                                  for d in os.scandir(b))
        self.tr_btn_restaurar.configure(state="normal" if livre and tem_backup else "disabled")

    def _tr_desenhar_jogos(self):
        if not self._tr_ativo():
            return
        st = self._tr()
        for w_ in self.tr_lista_jogos.winfo_children():
            w_.destroy()
        f_nome = ctk.CTkFont(family=F_SEMI, size=13)
        f_sub = ctk.CTkFont(family=F_REG, size=11)
        if st["jogos"] is None:
            txt = "Lendo os troféus do PS3…" if st["lendo"] else (
                "Conecte o PS3 para ver os troféus." if self.estado_ps3 != "ok" else "")
            ctk.CTkLabel(self.tr_lista_jogos, text=txt, font=f_sub, text_color=CINZA, wraplength=240).pack(pady=20)
            return
        if not st["jogos"]:
            ctk.CTkLabel(self.tr_lista_jogos, text="Nenhum jogo com troféus neste usuário.", font=f_sub,
                         text_color=CINZA, wraplength=240).pack(pady=20)
            return
        for j in st["jogos"]:
            sel = j["codigo"] == st["sel"]
            linha = ctk.CTkFrame(self.tr_lista_jogos, fg_color="#1A3358" if sel else "#0F1B33", corner_radius=10,
                                 cursor="hand2")
            linha.pack(fill="x", pady=2, padx=(0, 4))
            t = j["jogo"]
            n = ctk.CTkLabel(linha, text=t if len(t) <= 32 else t[:31] + "…", font=f_nome, text_color=BRANCO,
                             anchor="w")
            n.pack(fill="x", padx=10, pady=(6, 0))
            pct = int(j["ganhos"] * 100 / j["total"]) if j["total"] else 0
            txt_sub = (f"Não consegui ler: {j['erro'][:34]}" if j.get("erro")
                       else f"{j['ganhos']} de {j['total']} troféus  •  {pct}%")
            s = ctk.CTkLabel(linha, text=txt_sub, font=f_sub, anchor="w",
                             text_color="#F87171" if j.get("erro") else ("#7FB2F0" if sel else CINZA_ESCURO))
            s.pack(fill="x", padx=10, pady=(0, 6))
            for w_ in (linha, n, s):
                w_.bind("<Button-1>", lambda e, cod=j["codigo"]: self.tr_escolher(cod))

    def _tr_desenhar_trofeus(self):
        if not self._tr_ativo():
            return
        st = self._tr()
        for w_ in self.tr_lista.winfo_children():
            w_.destroy()
        f_n = ctk.CTkFont(family=F_SEMI, size=13)
        f_sub = ctk.CTkFont(family=F_REG, size=11)
        cod = st["sel"]
        if not cod:
            self.tr_cab.configure(text="Escolha um jogo")
            ctk.CTkLabel(self.tr_lista, text="Escolha um jogo à esquerda para ver e destravar os troféus.\n"
                                             "Antes de mexer, o PSTudo guarda um backup no PC.",
                         font=f_sub, text_color=CINZA, justify="center").pack(pady=30)
            return
        info = st["lista"].get(cod)
        jogo = next((j for j in st["jogos"] or [] if j["codigo"] == cod), None)
        self.tr_cab.configure(text=(jogo["jogo"] if jogo else cod) + f"   ({cod})")
        if info is None:
            ctk.CTkLabel(self.tr_lista, text="Lendo os troféus…", font=f_sub, text_color=CINZA).pack(pady=30)
            return
        if isinstance(info, Exception):
            ctk.CTkLabel(self.tr_lista, text=f"Não consegui ler estes troféus.\n({str(info)[:100]})", font=f_sub,
                         text_color="#F87171", justify="center").pack(pady=24)
            return
        cores = {1: "#7FD3F7", 2: "#F5C542", 3: "#C9D1DC", 4: "#D08A55"}
        for t in info["trofeus"]:
            linha = ctk.CTkFrame(self.tr_lista, fg_color="#0F1B33", corner_radius=10)
            linha.pack(fill="x", pady=2, padx=(0, 4))
            if t["destravado"]:
                ctk.CTkLabel(linha, text="✓", width=24, font=f_n, text_color="#34D399").pack(side="left", padx=(10, 4))
            else:
                v = tk.BooleanVar(value=t["id"] in st["marcados"])
                cb = ctk.CTkCheckBox(linha, text="", width=24, checkbox_width=18, checkbox_height=18, variable=v,
                                     command=lambda i=t["id"], v=v: self._tr_marcar(i, v.get()))
                cb.pack(side="left", padx=(10, 4))
            col = ctk.CTkFrame(linha, fg_color="transparent")
            col.pack(side="left", fill="x", expand=True, pady=6)
            tipo = TIPOS_TROFEU.get(t["tipo"], "")
            nome = t["nome"] + ("  (oculto)" if t["oculto"] else "")
            topo = ctk.CTkFrame(col, fg_color="transparent")
            topo.pack(fill="x")
            ctk.CTkLabel(topo, text="● ", font=f_n, text_color=cores.get(t["tipo"], CINZA)).pack(side="left")
            ctk.CTkLabel(topo, text=nome if len(nome) <= 48 else nome[:47] + "…", font=f_n, text_color=BRANCO,
                         anchor="w").pack(side="left")
            det = t["detalhe"]
            sub = f"{tipo}  •  {det}" if det else tipo
            ctk.CTkLabel(col, text=sub if len(sub) <= 80 else sub[:79] + "…", font=f_sub, text_color=CINZA,
                         anchor="w", justify="left").pack(fill="x")
            if t["destravado"]:
                quando = time.strftime(formato_data() + "  %H:%M", time.localtime(tempo_unix(t["tempo"]))) \
                    if t["tempo"] else ""
                ctk.CTkLabel(linha, text=("na PSN" if t["sync"] else "ganho") + (f"\n{quando}" if quando else ""),
                             font=f_sub, text_color="#34D399" if t["sync"] else "#7FB2F0").pack(side="right", padx=12)

    def _tr_marcar(self, i, on):
        st = self._tr()
        (st["marcados"].add if on else st["marcados"].discard)(i)
        self._tr_botoes()

    # ---------------- ações
    def _tr_trocar_usuario(self, valor):
        st = self._tr()
        for u, n in st["usuarios"] or []:
            if valor == f"{n} ({u})":
                st["usuario"] = u
        st["jogos"], st["sel"], st["lista"], st["marcados"] = None, None, {}, set()
        self.tr_ler(manter_usuarios=True)

    def tr_ler(self, manter_usuarios=False):
        st = self._tr()
        if st["lendo"] or self.estado_ps3 != "ok":
            return
        st["lendo"] = True
        st["jogos"] = None
        if not manter_usuarios:
            st["lista"], st["marcados"] = {}, set()
        self._tr_desenhar_jogos()
        self._tr_botoes()
        self._tr_msg("Lendo os troféus do PS3…")

        def avisar(t):
            self.fila.put(("cb", lambda t=t: self._tr_msg(t)))

        def trabalho(ftp):
            usuarios = st["usuarios"] if manter_usuarios and st["usuarios"] else listar_usuarios_ps3(ftp)
            u = st["usuario"] if st["usuario"] in [x for x, _ in usuarios] else (usuarios[0][0] if usuarios else None)
            jogos = listar_trofeus_ps3(ftp, u, avisar) if u else []
            return usuarios, u, jogos

        def ok(r):
            usuarios, u, jogos = r
            mudou = st["usuarios"] != usuarios
            st["usuarios"], st["usuario"], st["jogos"] = usuarios, u, jogos
            if not usuarios:
                self._tr_msg("Não achei usuários no PS3.", "#FBBF24")
            else:
                self._tr_msg(f"{len(jogos)} jogo(s) com troféus. Depois de destravar, NÃO sincronize com a PSN "
                             "(a Sony pode banir a conta).", "#FBBF24")
            if mudou and self._tr_ativo():
                self.tela_trofeus()
            else:
                self._tr_desenhar_jogos()
                self._tr_desenhar_trofeus()

        def erro(e):
            st["jogos"] = []
            self._tr_msg(f"Não consegui ler os troféus ({str(e)[:60]})", "#F87171")
            self._tr_desenhar_jogos()

        def fim():
            st["lendo"] = False
            self._tr_botoes()
        self.em_thread(trabalho, ok, erro, fim)

    def tr_escolher(self, cod, recarregar=False):
        st = self._tr()
        if st["sel"] != cod:
            st["marcados"] = set()
        st["sel"] = cod
        jogo = next((j for j in st["jogos"] or [] if j["codigo"] == cod), None)
        if jogo and jogo.get("erro") and not recarregar:
            st["lista"][cod] = ErroTrofeu(jogo["erro"])
        elif jogo and (recarregar or cod not in st["lista"] or isinstance(st["lista"].get(cod), Exception)):
            st["lista"].pop(cod, None)

            def trabalho(ftp):
                arqs = {"TROPUSR.DAT": ler_bytes_remoto(ftp, f"{jogo['pasta']}/TROPUSR.DAT")}
                for nome in ("TROP_17.SFM", "TROP_07.SFM", "TROP.SFM", "TROPCONF.SFM"):   # nomes em português
                    try:
                        arqs[nome] = ler_bytes_remoto(ftp, f"{jogo['pasta']}/{nome}")
                        break
                    except ftplib.all_errors:
                        continue
                trofeus, nome_jogo = resumo_trofeus(arqs)
                return {"trofeus": trofeus, "jogo": nome_jogo}

            def ok(r):
                st["lista"][cod] = r
                jogo["ganhos"] = sum(1 for t in r["trofeus"] if t["destravado"])
                self._tr_desenhar_trofeus()
                self._tr_desenhar_jogos()
                self._tr_botoes()

            def erro(e):
                st["lista"][cod] = e
                self._tr_desenhar_trofeus()
            self.em_thread(trabalho, ok, erro)
        self._tr_desenhar_jogos()
        self._tr_desenhar_trofeus()
        self._tr_botoes()

    def tr_marcar_todos(self):
        st = self._tr()
        info = st["lista"].get(st["sel"])
        if not isinstance(info, dict):
            return
        st["marcados"] = {t["id"] for t in info["trofeus"] if not t["destravado"]}
        self._tr_desenhar_trofeus()
        self._tr_botoes()

    def tr_destravar(self):
        st = self._tr()
        cod, ids, u = st["sel"], sorted(st["marcados"]), st["usuario"]
        jogo = next((j for j in st["jogos"] or [] if j["codigo"] == cod), None)
        if st["ocupado"] or not ids or not jogo:
            return
        st["ocupado"] = True
        self._tr_botoes()
        self._tr_msg("Fazendo backup e conferindo a assinatura dos troféus… (deixe o PS3 no XMB, sem jogo aberto)")

        def trabalho(ftp):
            arqs = baixar_pasta_trofeu(ftp, jogo["pasta"])
            for nome in ("PARAM.PFD", "TROPUSR.DAT", "TROPTRNS.DAT"):
                if nome not in arqs:
                    raise ErroTrofeu(f"{nome} não existe nesta pasta")
            pasta = os.path.join(pasta_backup_trofeus(u, cod), time.strftime("%Y-%m-%d_%H-%M-%S"))
            os.makedirs(pasta, exist_ok=True)
            for nome, dados in arqs.items():                  # backup antes de tudo
                with open(os.path.join(pasta, nome), "wb") as f:
                    f.write(dados)
            novos, n, pulou = destravar_trofeus(arqs, ids)
            if not n:
                return 0, False
            self.fila.put(("cb", lambda: self._tr_msg("Gravando no PS3…")))
            try:
                gravar_trofeus_ps3(ftp, jogo["pasta"], novos, arqs)
            except Exception as e:
                raise ErroTrofeu(f"{e}. O PSTudo voltou os arquivos originais; a cópia de segurança "
                                 "está em Backups.") from None
            depois = os.path.join(pasta, "depois")         # como ficou: o Desfazer confere antes de voltar
            os.makedirs(depois, exist_ok=True)
            for nome, dados in novos.items():
                with open(os.path.join(depois, nome), "wb") as f:
                    f.write(dados)
            return n, pulou

        def ok(r):
            n, pulou = r
            st["marcados"] = set()
            if n:
                extra = " A platina ficou de fora: ela só vem com todos os troféus do jogo." if pulou else ""
                self._tr_msg(f"✓ {n} troféu(s) destravado(s). Reinicie o PS3 para aparecerem. "
                             f"Não sincronize com a PSN.{extra}", "#34D399")
            else:
                self._tr_msg("Esses troféus já estavam destravados.", CINZA)
            self.tr_escolher(cod, recarregar=True)

        def erro(e):
            self._tr_msg(f"Não destravei: {str(e)[:150]}", "#F87171")

        def fim():
            st["ocupado"] = False
            self._tr_botoes()
        self.em_thread(trabalho, ok, erro, fim)

    def _tr_aplicar(self, msg_inicio, mexer, ao_terminar):
        """Backup no PC, mexer(arquivos) -> (novos, n), grava no PS3 e guarda "depois" para o Desfazer."""
        st = self._tr()
        cod, u = st["sel"], st["usuario"]
        jogo = next((j for j in st["jogos"] or [] if j["codigo"] == cod), None)
        if st["ocupado"] or not jogo:
            return
        st["ocupado"] = True
        self._tr_botoes()
        self._tr_msg(msg_inicio)

        def trabalho(ftp):
            arqs = baixar_pasta_trofeu(ftp, jogo["pasta"])
            for nome in ("PARAM.PFD", "TROPUSR.DAT", "TROPTRNS.DAT"):
                if nome not in arqs:
                    raise ErroTrofeu(f"{nome} não existe nesta pasta")
            pasta = os.path.join(pasta_backup_trofeus(u, cod), time.strftime("%Y-%m-%d_%H-%M-%S"))
            os.makedirs(pasta, exist_ok=True)
            for nome, dados in arqs.items():                  # backup antes de tudo
                with open(os.path.join(pasta, nome), "wb") as f:
                    f.write(dados)
            novos, n = mexer(arqs)
            if not n:
                return 0
            self.fila.put(("cb", lambda: self._tr_msg("Gravando no PS3…")))
            try:
                gravar_trofeus_ps3(ftp, jogo["pasta"], novos, arqs)
            except Exception as e:
                raise ErroTrofeu(f"{e}. O PSTudo voltou os arquivos originais; a cópia de segurança "
                                 "está em Backups.") from None
            depois = os.path.join(pasta, "depois")         # como ficou: o Desfazer confere antes de voltar
            os.makedirs(depois, exist_ok=True)
            for nome, dados in novos.items():
                with open(os.path.join(depois, nome), "wb") as f:
                    f.write(dados)
            return n

        def ok(n):
            ao_terminar(n)
            self.tr_escolher(cod, recarregar=True)

        def erro(e):
            self._tr_msg(f"Não mudei: {str(e)[:150]}", "#F87171")

        def fim():
            st["ocupado"] = False
            self._tr_botoes()
        self.em_thread(trabalho, ok, erro, fim)

    def tr_datas(self):
        """Janela para escolher a data e a hora dos troféus ganhos que ainda não foram para a PSN."""
        st = self._tr()
        info = st["lista"].get(st["sel"])
        if not isinstance(info, dict) or st["ocupado"]:
            return
        editaveis = [t for t in info["trofeus"] if t["destravado"] and not t["sync"]]
        if not editaveis:
            return
        fmt = formato_data()
        j = self._janela("Data e hora", 600, 600)
        f_tit = ctk.CTkFont(family=F_LIGHT, size=22)
        f_txt = ctk.CTkFont(family=F_REG, size=12)
        f_n = ctk.CTkFont(family=F_SEMI, size=12)
        ctk.CTkLabel(j, text="Data e hora dos troféus", font=f_tit, text_color=BRANCO).pack(anchor="w", padx=24,
                                                                                            pady=(20, 2))
        ctk.CTkLabel(j, text="Muda só no seu PS3, para a lista ficar do seu jeito. Troféus que já foram para a PSN "
                             "não aparecem aqui. Continue sem sincronizar com a PSN.",
                     font=f_txt, text_color=CINZA, wraplength=540, justify="left").pack(anchor="w", padx=24)
        exemplo = time.strftime(fmt, time.localtime())
        todos = ctk.CTkFrame(j, fg_color="transparent")
        todos.pack(fill="x", padx=24, pady=(12, 6))
        ctk.CTkLabel(todos, text="Mudar a data de todos para", font=f_txt, text_color=BRANCO).pack(side="left")
        e_todos = ctk.CTkEntry(todos, width=110, height=30, corner_radius=8, fg_color="#111C33",
                               border_color="#26324D", font=f_txt, placeholder_text=exemplo)
        e_todos.pack(side="left", padx=8)
        lista = ctk.CTkScrollableFrame(j, fg_color="#0B1426", corner_radius=12, scrollbar_button_color="#1E2A44")
        lista.pack(fill="both", expand=True, padx=24, pady=(4, 0))
        campos = {}
        for t in editaveis:
            linha = ctk.CTkFrame(lista, fg_color="#0F1B33", corner_radius=10)
            linha.pack(fill="x", pady=2, padx=(0, 4))
            nome = t["nome"]
            ctk.CTkLabel(linha, text=nome if len(nome) <= 34 else nome[:33] + "…", font=f_n, text_color=BRANCO,
                         anchor="w").pack(side="left", padx=10, pady=8)
            atual = time.localtime(tempo_unix(t["tempo"])) if t["tempo"] else time.localtime()
            e_h = ctk.CTkEntry(linha, width=64, height=28, corner_radius=8, fg_color="#111C33", border_color="#26324D",
                               font=f_txt)
            e_h.insert(0, time.strftime("%H:%M", atual))
            e_h.pack(side="right", padx=(4, 10))
            e_d = ctk.CTkEntry(linha, width=104, height=28, corner_radius=8, fg_color="#111C33",
                               border_color="#26324D", font=f_txt)
            e_d.insert(0, time.strftime(fmt, atual))
            e_d.pack(side="right")
            campos[t["id"]] = (e_d, e_h, t)

        def aplicar_todos():
            v = e_todos.get().strip()
            if v:
                for e_d, _e_h, _t in campos.values():
                    e_d.delete(0, "end")
                    e_d.insert(0, v)
        ctk.CTkButton(todos, text="Aplicar", width=80, height=30, corner_radius=15, fg_color=BTN,
                      hover_color=BTN_HOVER, font=f_n, command=aplicar_todos).pack(side="left")
        rodape = ctk.CTkFrame(j, fg_color="transparent")
        rodape.pack(fill="x", padx=24, pady=14)
        aviso = ctk.CTkLabel(rodape, text="", font=f_txt, text_color="#F87171", wraplength=360, justify="left")
        aviso.pack(side="left")

        def salvar():
            novas = {}
            for tid, (e_d, e_h, t) in campos.items():
                texto = f"{e_d.get().strip()} {e_h.get().strip()}"
                try:
                    try:
                        st_ = time.strptime(texto, fmt + " %H:%M")
                    except ValueError:
                        st_ = time.strptime(texto, fmt + " %H:%M:%S")
                except ValueError:
                    aviso.configure(text=f"Data ou hora inválida em \"{t['nome'][:30]}\" (use {exemplo} e 21:30).")
                    return
                quando = time.mktime(st_)
                if not DATA_MINIMA_TROFEU <= quando <= time.time() + 60:
                    aviso.configure(text=f"\"{t['nome'][:30]}\": a data precisa ficar entre 11/11/2006 e agora.")
                    return
                if abs(quando - tempo_unix(t["tempo"])) >= 60 or not t["tempo"]:   # só o que mudou de verdade
                    novas[tid] = quando
            j.destroy()
            if not novas:
                return

            def terminou(n):
                if n:
                    self._tr_msg(f"✓ Data e hora de {n} troféu(s) mudadas. Reinicie o PS3 para ver. "
                                 "Não sincronize com a PSN.", "#34D399")
                else:
                    self._tr_msg("Nada mudou.", CINZA)
            self._tr_aplicar("Fazendo backup e mudando as datas… (deixe o PS3 no XMB, sem jogo aberto)",
                             lambda arqs: mudar_datas_trofeus(arqs, novas), terminou)
        ctk.CTkButton(rodape, text="Salvar", width=120, height=38, corner_radius=19, fg_color="#0070D1",
                      hover_color="#1888F0", font=ctk.CTkFont(family=F_SEMI, size=14), command=salvar).pack(
            side="right")

    def tr_restaurar(self):
        """Volta os troféus do jogo escolhido para o backup mais recente."""
        st = self._tr()
        cod, u = st["sel"], st["usuario"]
        jogo = next((j for j in st["jogos"] or [] if j["codigo"] == cod), None)
        base = pasta_backup_trofeus(u, cod) if u and cod else None
        if st["ocupado"] or not jogo or not base or not os.path.isdir(base):
            return
        backups = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d, "depois"))
                         and not d.endswith("_desfeito"))      # só o que o PSTudo gravou de fato
        if not backups:
            return
        escolhido = os.path.join(base, backups[-1])    # o mais recente = como estava antes do último destravar
        st["ocupado"] = True
        self._tr_botoes()
        self._tr_msg("Restaurando o backup…")

        def trabalho(ftp):
            antes = {}
            for nome in ARQS_TROFEU_MUDAM:
                with open(os.path.join(escolhido, nome), "rb") as f:
                    antes[nome] = f.read()
            atuais = {n: ler_bytes_remoto(ftp, f"{jogo['pasta']}/{n}") for n in ARQS_TROFEU_MUDAM}
            depois = os.path.join(escolhido, "depois")
            for nome in ARQS_TROFEU_MUDAM:
                with open(os.path.join(depois, nome), "rb") as f:
                    if f.read() != atuais[nome]:
                        raise ErroTrofeu("os troféus mudaram no PS3 depois que o PSTudo destravou (você ganhou "
                                         "algum jogando?). Desfazer agora apagaria isso, então não mexi.")
            gravar_trofeus_ps3(ftp, jogo["pasta"], antes, atuais)
            os.rename(escolhido, escolhido + "_desfeito")     # o próximo "Desfazer" volta mais um passo
            return backups[-1]

        def ok(qual):
            self._tr_msg(f"✓ Desfeito: os troféus voltaram a como estavam em {qual.replace('_', ' ')}. "
                         "Reinicie o PS3.", "#34D399")
            self.tr_escolher(cod, recarregar=True)

        def erro(e):
            self._tr_msg(f"Não consegui restaurar: {str(e)[:120]}", "#F87171")

        def fim():
            st["ocupado"] = False
            self._tr_botoes()
        self.em_thread(trabalho, ok, erro, fim)

    def tr_abrir_backups(self):
        pasta = os.path.join(os.path.expanduser("~"), "PSTudo", "backup_trofeus")
        os.makedirs(pasta, exist_ok=True)
        try:
            os.startfile(pasta)
        except (AttributeError, OSError):
            self._tr_msg(f"Backups em: {pasta}")


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
class App(Extras, Console, Controles, Tela, Conversor, Updates, ControleRemoto, Trofeus):
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
        self._pintores = {round(escala, 3): self.p}     # imagens prontas de cada tamanho de janela
        p = self.p
        self.root.configure(fg_color="#050B18")
        self.c = tk.Canvas(self.root, width=p.px(W), height=p.px(H), highlightthickness=0, bd=0, bg="#050b18")
        self.c.pack(expand=True)
        self._icone = ImageTk.PhotoImage(icone_app(64))
        self.root.iconphoto(True, self._icone)

        self.cfg = self.carregar_cfg()
        carregar_idioma(self.cfg.get("idioma", "pt"))
        self.jogos = []
        self.estado_ps3 = "busca"
        self.fila = queue.Queue()
        self.cancelar = threading.Event()
        self.enviando = False
        self.aba = "enviar"
        self.widgets = []
        self.raps = []
        self.fm_path = "/dev_hdd0"
        self.fm_marcados = set()
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
        # em segundo plano: fundo já no tamanho da tela inteira, para o maximizar não travar
        esc_tela = min(self.root.winfo_screenwidth() / W, self.root.winfo_screenheight() / H)
        self.root.after(1200, lambda: threading.Thread(target=preparar_fundo_grande, args=(W, H, esc_tela),
                                                       daemon=True).start())

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
        self.pill_w = 152
        x = W - 48 - 44 - 10 - 44 - 10 - self.pill_w / 2
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
        # botão do controle remoto (usar o controle do PC no PS3)
        px_ = gx - 44 - 10
        self.pad_n = self.eng_n
        self.pad_h = self.eng_h
        self.pad_on = p.ret(44, 44, 22, AZUL + (255,), outline=(255, 255, 255, 90), largura=1)
        self.pad_btn = c.create_image(p.px(px_), p.px(56), image=self.pad_n, tags=("padb",))
        self.pad_tx = c.create_text(p.px(px_), p.px(57), text="🎮", fill=BRANCO, font=(F_SYM, -p.px(18)),
                                    tags=("padb",))

        def pad_hover(dentro):
            c.config(cursor="hand2" if dentro else "")
            if not self.remoto_ativo():
                c.itemconfig(self.pad_btn, image=self.pad_h if dentro else self.pad_n)
        c.tag_bind("padb", "<Enter>", lambda e: pad_hover(True))
        c.tag_bind("padb", "<Leave>", lambda e: pad_hover(False))
        c.tag_bind("padb", "<Button-1>", lambda e: self.alternar_remoto())
        self._pintar_remoto()
        self.atualizar_status("busca")

    def atualizar_status(self, estado):
        self.estado_ps3 = estado
        textos = {"ok": "PS3 conectado", "busca": "Procurando…", "erro": "PS3 offline"}
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
        if getattr(self, "aba", "") == "trofeus" and self._tr_ativo():
            self._tr_botoes()
            st = self._tr()
            if estado == "ok" and st["jogos"] is None and not st["lendo"]:
                self.tr_ler()
        if getattr(self, "aba", "") == "updates" and self._up_ativo():
            self._up_botoes()
            st = self._up()
            if estado == "ok" and st["jogos"] is None and not st["lendo"]:
                self.up_ler_jogos()
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
            self._botao_xmb_canto()
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
        self._botao_xmb_canto()

    def _botao_xmb_canto(self):
        """Botão pequeno no canto de baixo: atualizar a lista de jogos do XMB quando quiser."""
        b = Botao(self, W - 24 - 70, 556, 140, 32, "Atualizar XMB", lambda: self._xmb_canto(b), "secundario",
                  tamanho_fonte=12)
        self.btn_xmb = b

    def _xmb_canto(self, b):
        if not b.ativo:
            return
        if self.estado_ps3 != "ok":
            self._aviso_app("Conecte o PS3 primeiro.", "#FBBF24")
            return
        b.set_ativo(False)
        b.set_texto("Atualizando…")
        ip = self.cfg.get("ip")

        def tarefa():
            try:
                ok = atualizar_xmb(ip)
                msg, cor = (("XMB atualizado: os jogos novos já aparecem.", "#34D399") if ok else
                            ("Lista de jogos atualizada. Saia e entre no usuário do PS3 para ver.", "#34D399"))
            except Exception as e:
                msg, cor = f"Não consegui atualizar o XMB ({str(e)[:50]}).", "#F87171"

            def fim():
                b.set_texto("Atualizar XMB")
                b.set_ativo(True)
                self._aviso_app(msg, cor)
            self.fila.put(("cb", fim))
        threading.Thread(target=tarefa, daemon=True).start()

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
        if getattr(self, "instalando_info", None):
            self._mostrar_instalando()

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
                   acao_tentar=None, acao_voltar=None, botao_xmb=False):
        self.limpar()
        p, c = self.p, self.c
        c.create_image(p.px(W / 2), p.px(250), tags="view",
                       image=p.ret(120, 120, 60, (0, 0, 0, 0), icone="check" if sucesso else "alerta", icone_y=0.5))
        c.create_text(p.px(W / 2), p.px(336), text=titulo, fill=BRANCO, font=(F_LIGHT, -p.px(30)), tags="view")
        c.create_text(p.px(W / 2), p.px(378), text=sub, fill=CINZA, font=(F_REG, -p.px(15)), tags="view", width=p.px(620),
                      justify="center")
        self.tx_final_extra = c.create_text(p.px(W / 2), p.px(412), text=extra or "", fill=CINZA_ESCURO,
                                            font=(F_REG, -p.px(12)), tags="view", width=p.px(620), justify="center")
        if sucesso and botao_xmb:
            b = Botao(self, W / 2 - 125, 500, 230, 52, "Atualizar jogos no XMB", lambda: self.atualizar_jogos_xmb(b))
            Botao(self, W / 2 + 125, 500, 230, 52, texto_ok, acao_ok or self.recomecar, "secundario")
        elif sucesso:
            Botao(self, W / 2, 500, 220, 52, texto_ok, acao_ok or self.recomecar)
        else:
            Botao(self, W / 2 - 115, 500, 210, 52, "Tentar de novo", acao_tentar or self.iniciar_envio)
            Botao(self, W / 2 + 115, 500, 210, 52, "Voltar", acao_voltar or self.tela_inicio, "secundario")

    def atualizar_jogos_xmb(self, botao):
        if self.estado_ps3 != "ok" or not botao.ativo:
            return
        botao.set_ativo(False)
        botao.set_texto("Atualizando…")
        self.c.itemconfig(self.tx_final_extra, text="Atualizando a lista de jogos do webMAN e recarregando o XMB…",
                          fill=CINZA)
        ip = self.cfg.get("ip")

        def tarefa():
            try:
                if atualizar_xmb(ip):
                    msg, cor = "Pronto! O XMB recarregou com os jogos novos.", "#34D399"
                else:
                    msg, cor = ("Lista de jogos atualizada. Seu webMAN não recarrega o XMB sozinho: "
                                "saia e entre no usuário do PS3 para ver os jogos."), "#34D399"
            except Exception as e:
                msg, cor = f"Não consegui atualizar ({str(e)[:70]}). Tente de novo com o PS3 no XMB.", "#F87171"

            def mostrar():
                try:
                    if self.c.type(self.tx_final_extra):
                        self.c.itemconfig(self.tx_final_extra, text=msg, fill=cor)
                        botao.set_texto("Atualizar de novo" if cor == "#34D399" else "Tentar de novo")
                        botao.set_ativo(True)
                except tk.TclError:
                    pass
            self.fila.put(("cb", mostrar))
        threading.Thread(target=tarefa, daemon=True).start()

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
        self.instalando_info = None
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

    def _mostrar_instalando(self):
        i, n, nome = self.instalando_info
        self._atualizar_aba_envio(1.0, "Instal…")
        if not getattr(self, "vendo_envio", False):
            return
        c = self.c
        c.itemconfig(self.tx_jogo, text=nome if len(nome) <= 44 else nome[:42] + "…")
        c.itemconfig(self.tx_sub, text=f"Instalando no PS3 ({i} de {n})" if n > 1 else "Instalando no PS3")
        c.itemconfig(self.tx_pct, text="100%")
        self._atualizar_barra(1.0)
        c.itemconfig(self.tx_rest, text="O andamento aparece na tela do PS3. Fique no XMB, sem abrir jogos.")

    def _progresso(self, d):
        if getattr(self, "instalando_info", None):
            return
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
        if tipo == "instalando":
            self.instalando_info = dados
            self._mostrar_instalando()
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
            if tipo != "fim":
                self.instalando_info = None
            self.ultimo_prog = None
            if tipo == "cancelado":
                self._atualizar_aba_envio(None)
                return
            self.envio_pendente = (tipo, dados)
            if tipo == "fim":
                self._som_fim()
                self._atualizar_aba_envio(None, "Pronto ✓")
                self._aviso_app(f"{dados[3]} pacote(s) instalado(s) no PS3!" if dados[3] else
                                f"{dados[0]} {'jogo enviado' if dados[0] == 1 else 'jogos enviados'} para o PS3!")
            else:
                self._atualizar_aba_envio(None, "Erro ✕")
                self._aviso_app("O envio parou. Abra a aba Enviar para ver.", "#F87171")
        elif tipo == "fim":
            if self.enviando:      # não toca de novo ao abrir um resultado que ficou pendente
                self._som_fim()
            self.enviando = False
            self.ultimo_prog = None
            self._atualizar_aba_envio(None)
            n, enviado, tempo, instalados, manual = dados
            minutos = max(1, round(tempo / 60))
            sub = f"{n} {'jogo enviado' if n == 1 else 'jogos enviados'} para o PS3 em {minutos} min."
            extra = ("Clique em Atualizar jogos no XMB para eles aparecerem na lista (o PS3 precisa estar no XMB, "
                     "fora de jogo).")
            if instalados:
                sub = f"{n} {'item enviado' if n == 1 else 'itens enviados'} e {instalados} pacote(s) instalado(s) " \
                      f"no PS3 em {minutos} min."
            if manual:
                extra = ("Os .pkg ficaram em /dev_hdd0/packages: este webMAN não instala sozinho. No PS3, abra "
                         "Package Manager › Install Package Files › Standard.")
            self.instalando_info = None
            self.tela_final(True, "Tudo pronto!", sub, extra, botao_xmb=True)
        elif tipo == "cancelado":
            self.enviando = False
            self.ultimo_prog = None
            self.instalando_info = None
            self._atualizar_aba_envio(None)
            self.tela_inicio()
        elif tipo == "erro":
            self.enviando = False
            self.ultimo_prog = None
            self.instalando_info = None
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
        f_ = self.p.s / self.escala_base
        j.geometry(f"{int(420 * f_)}x{int(720 * f_)}")
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
        sw_som.pack(anchor="w", padx=28, pady=(2, 10))
        ln_idioma = ctk.CTkFrame(j, fg_color="transparent")
        ln_idioma.pack(fill="x", padx=28, pady=(0, 14))
        ctk.CTkLabel(ln_idioma, text="Idioma", font=fonte, text_color=BRANCO).pack(side="left")
        op_idioma = ctk.CTkOptionMenu(ln_idioma, values=list(IDIOMAS.values()), width=150, height=32, corner_radius=10,
                                      fg_color="#111C33", button_color="#1A2744", button_hover_color="#24365C",
                                      font=fonte)
        op_idioma.set(IDIOMAS.get(self.cfg.get("idioma", "pt"), "Português"))
        op_idioma.pack(side="right")

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
            novo_idioma = next((k for k, v in IDIOMAS.items() if v == op_idioma.get()), "pt")
            mudou_idioma = novo_idioma != IDIOMA["atual"]
            self.cfg["idioma"] = novo_idioma
            for k, v in novos.items():
                self.cfg[f"atalho_{k}"] = v
            if getattr(self, "tl_gpu", None):
                self.tl_gpu.trocar_atalhos({"fsr": self.atalho("fsr"), "interp": self.atalho("interp")})
            self.salvar_cfg()
            j.destroy()
            if mudou_idioma:                 # refaz a interface já no idioma novo
                carregar_idioma(novo_idioma)
                self._reconstruir(self.p.s)
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
        try:
            estado = self.root.state()
        except tk.TclError:
            estado = ""
        mudou_estado = estado != getattr(self, "_estado_janela", estado)
        self._estado_janela = estado
        # maximizar/restaurar: refaz já; arrastando a borda: espera parar de mexer
        self._espera_tam = self.root.after(1 if mudou_estado else 160, self._ajustar_escala)

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
        pintores = self.__dict__.setdefault("_pintores", {})
        self.p = pintores.setdefault(round(escala, 3), Pintor(escala))   # imagens já feitas ficam guardadas
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
        self.desligar_remoto(esperar=2.0)      # solta os botões no PS3 antes de fechar
        self.tl_parar()
        self.cancelar.set()
        self.salvar_cfg()
        self.root.destroy()

    def rodar(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().rodar()
