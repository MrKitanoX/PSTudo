"""Fluidez com IA para a aba Tela do PSTudo.

Roda a rede RIFE 4.6 (Real-Time Intermediate Flow Estimation, hzwer, licença MIT; pesos convertidos do
rife-ncnn-vulkan de nihui, licença MIT) direto na placa de vídeo com OpenGL, sem nenhuma biblioteca de IA.
A rede calcula, para um instante t entre dois quadros do jogo, o movimento até cada um deles e uma máscara
que diz de qual quadro cada pixel deve vir. O quadro intermediário é montado em resolução cheia pela tela.

Cada tensor fica numa textura RGBA "em fila": o grupo g de 4 canais ocupa as colunas [g*L, (g+1)*L).
"""
import os
import struct

import numpy as np

VS = """
#version {ver}
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

CAB_SSBO = """
#version 430
layout(std430, binding = 0) readonly buffer Pesos { vec4 PW[]; };
#define P(i) PW[(i)]
"""
CAB_TEX = """
#version 330
uniform sampler2D pesos;
#define P(i) texelFetch(pesos, ivec2((i) & 4095, (i) >> 12), 0)
"""

# ---- convolução 3x3 (passo 1 ou 2, borda zero) + LeakyReLU 0.2; "RES" soma a entrada antes (bloco residual)
FS_CONV = """
uniform sampler2D X;
uniform int base;
out vec4 cor;
void main() {
    ivec2 fc = ivec2(gl_FragCoord.xy);
    int og = fc.x / WOUT;
    ivec2 p = ivec2(fc.x - og * WOUT, fc.y);
    vec4 acc = P(base + og);
    int wb = base + GOUT + og * (GIN * 36);
    ivec2 q0 = p * PASSO - 1;
    for (int ig = 0; ig < GIN; ig++) {
        int xo = ig * WIN;
        int wi = wb + ig * 36;
        for (int ky = 0; ky < 3; ky++) {
            int y = q0.y + ky;
            if (y < 0 || y >= HIN) continue;
            for (int kx = 0; kx < 3; kx++) {
                int x = q0.x + kx;
                if (x < 0 || x >= WIN) continue;
                vec4 v = texelFetch(X, ivec2(xo + x, y), 0);
                int i = wi + ((ky * 3 + kx) << 2);
                acc += mat4(P(i), P(i + 1), P(i + 2), P(i + 3)) * v;
            }
        }
    }
#if RES
    acc += texelFetch(X, ivec2(og * WIN + p.x, p.y), 0);
#endif
    cor = max(acc, acc * 0.2);
}
"""

# ---- deconvolução 4x4 passo 2 + PixelShuffle(2), juntas: saída com 6 canais (2 grupos)
FS_DECONV = """
uniform sampler2D X;
uniform int base;
out vec4 cor;
void main() {
    ivec2 fc = ivec2(gl_FragCoord.xy);
    int og = fc.x / WOUT;
    ivec2 p = ivec2(fc.x - og * WOUT, fc.y);
    ivec2 fase = p & 1;
    ivec2 D = p >> 1;
    ivec4 oc = (ivec4(0, 1, 2, 3) + og * 4) * 4 + fase.y * 2 + fase.x;
    bvec4 vale = lessThan(ivec4(0, 1, 2, 3) + og * 4, ivec4(6));
    oc = ivec4(mix(ivec4(0), oc, vale));
    vec4 acc = vec4(P(base + oc.x).x, P(base + oc.y).x, P(base + oc.z).x, P(base + oc.w).x);
    int wb = base + 24;
    ivec2 ihi = (D + 1) >> 1;
    ivec2 khi = D + 1 - 2 * ihi;
    for (int a = 0; a < 2; a++) {
        int iy = ihi.y - a, ky = khi.y + 2 * a;
        if (iy < 0 || iy >= HIN) continue;
        for (int b = 0; b < 2; b++) {
            int ix = ihi.x - b, kx = khi.x + 2 * b;
            if (ix < 0 || ix >= WIN) continue;
            int k = ky * 4 + kx;
            for (int ig = 0; ig < GIN; ig++) {
                vec4 v = texelFetch(X, ivec2(ig * WIN + ix, iy), 0);
                int j = ig * 16 + k;
                acc.x += dot(v, P(wb + oc.x * GIN * 16 + j));
                acc.y += dot(v, P(wb + oc.y * GIN * 16 + j));
                acc.z += dot(v, P(wb + oc.z * GIN * 16 + j));
                acc.w += dot(v, P(wb + oc.w * GIN * 16 + j));
            }
        }
    }
    cor = mix(vec4(0.0), acc, vec4(vale));
}
"""

# amostra bilinear de um grupo de um tensor em fila, com a mesma regra de borda do Interp do ncnn
COMUM = """
vec4 grupo(sampler2D T, int g, int L, ivec2 q) { return texelFetch(T, ivec2(g * L + q.x, q.y), 0); }
void eixo(float f, int n, out int i0, out int i1, out float a) {
    f = max(f, 0.0);
    i0 = int(floor(f));
    a = f - float(i0);
    if (i0 >= n - 1) { i0 = max(n - 2, 0); a = n > 1 ? 1.0 : 0.0; }
    i1 = min(i0 + 1, n - 1);
}
vec4 interp(sampler2D T, int g, int L, int A, vec2 f) {
    int x0, x1, y0, y1; float ax, ay;
    eixo(f.x, L, x0, x1, ax);
    eixo(f.y, A, y0, y1, ay);
    vec4 c00 = grupo(T, g, L, ivec2(x0, y0)), c10 = grupo(T, g, L, ivec2(x1, y0));
    vec4 c01 = grupo(T, g, L, ivec2(x0, y1)), c11 = grupo(T, g, L, ivec2(x1, y1));
    return mix(mix(c00, c10, ax), mix(c01, c11, ax), ay);
}
// leitura com a borda "presa" do grid_sample (padding border) usado no treino da rede
vec4 warp(sampler2D I, ivec2 p, vec2 f) {
    vec2 s = clamp(vec2(p) + f, vec2(0.0), vec2(LN - 1, AN - 1));
    ivec2 i0 = ivec2(floor(s));
    ivec2 i1 = min(i0 + 1, ivec2(LN - 1, AN - 1));
    vec2 a = s - vec2(i0);
    vec4 c00 = texelFetch(I, i0, 0), c10 = texelFetch(I, ivec2(i1.x, i0.y), 0);
    vec4 c01 = texelFetch(I, ivec2(i0.x, i1.y), 0), c11 = texelFetch(I, i1, 0);
    return mix(mix(c00, c10, a.x), mix(c01, c11, a.x), a.y);
}
"""

# ---- entrada do bloco 0: imagens + instante t, reduzidas 8x
FS_ENTRADA0 = """
uniform sampler2D I0;
uniform sampler2D I1;
uniform float t;
out vec4 cor;
void main() {
    ivec2 fc = ivec2(gl_FragCoord.xy);
    int og = fc.x / WOUT;
    ivec2 p = ivec2(fc.x - og * WOUT, fc.y);
    vec2 f = (vec2(p) + 0.5) * ESC - 0.5;
    vec4 a = interp(I0, 0, LN, AN, f), b = interp(I1, 0, LN, AN, f);
    cor = og == 0 ? vec4(a.rgb, b.r) : vec4(b.g, b.b, t, 0.0);
}
"""

# ---- entrada dos blocos 1 e 2: estado (imagens deformadas, t, máscara, movimento) reduzido
FS_ENTRADA = """
uniform sampler2D S;
out vec4 cor;
void main() {
    ivec2 fc = ivec2(gl_FragCoord.xy);
    int og = fc.x / WOUT;
    ivec2 p = ivec2(fc.x - og * WOUT, fc.y);
    vec2 f = (vec2(p) + 0.5) * ESC - 0.5;
    vec4 v = interp(S, og, LN, AN, f);
    cor = og == 2 ? v / ESC : v;
}
"""

# ---- fim do bloco: amplia o resultado, soma no movimento/máscara e deforma as imagens
FS_ATUALIZA = """
uniform sampler2D T;
uniform sampler2D S;
uniform sampler2D I0;
uniform sampler2D I1;
uniform float t;
out vec4 cor;
void main() {
    ivec2 fc = ivec2(gl_FragCoord.xy);
    int og = fc.x / LN;
    ivec2 p = ivec2(fc.x - og * LN, fc.y);
#if ESC == 1
    vec4 u0 = grupo(T, 0, LT, p), u1 = grupo(T, 1, LT, p);
#else
    vec2 f = (vec2(p) + 0.5) / float(ESC) - 0.5;
    vec4 u0 = interp(T, 0, LT, AT, f), u1 = interp(T, 1, LT, AT, f);
#endif
    vec4 fluxo = u0 * float(ESC);
    float mascara = u1.x;
#if PRIMEIRO == 0
    fluxo += grupo(S, 2, LN, p);
    mascara += grupo(S, 1, LN, p).w;
#endif
    if (og == 2) { cor = fluxo; return; }
    vec3 w1 = warp(I1, p, fluxo.zw).rgb;
    if (og == 1) { cor = vec4(w1.g, w1.b, t, mascara); return; }
    vec3 w0 = warp(I0, p, fluxo.xy).rgb;
    cor = vec4(w0, w1.r);
}
"""

# ---- reduz o quadro do jogo para a resolução da rede (o resto fica preto, como no RIFE)
FS_PREPARA = """
uniform sampler2D fonte;
uniform vec2 conteudo;   // largura/altura da imagem dentro da textura da rede
uniform float reducao;   // quantas vezes o quadro original é maior que a rede
out vec4 cor;
void main() {
    vec2 p = gl_FragCoord.xy;
    if (p.x > conteudo.x || p.y > conteudo.y) { cor = vec4(0.0); return; }
    vec2 uv = p / conteudo;
    if (reducao <= 2.0) { cor = vec4(texture(fonte, uv).rgb, 0.0); return; }   // até 2x: 1 amostra já é a média
    vec2 d = 0.25 / conteudo;
    vec3 c = texture(fonte, uv + vec2(-d.x, -d.y)).rgb + texture(fonte, uv + vec2(d.x, -d.y)).rgb +
             texture(fonte, uv + vec2(-d.x, d.y)).rgb + texture(fonte, uv + vec2(d.x, d.y)).rgb;
    cor = vec4(c * 0.25, 0.0);
}
"""

# Montagem do quadro intermediário em resolução cheia (usado pela tela, depois de inferir)
FS_MONTA = """
#version 330
uniform sampler2D A;
uniform sampler2D B;
uniform sampler2D S;      // estado final da rede
uniform vec2 rede;        // LN, AN (tamanho da textura da rede, com sobra)
uniform vec2 conteudo;    // parte útil da rede
uniform vec2 tam_fonte;   // tamanho do quadro original
out vec4 cor;
vec4 g(int k, ivec2 q) {
    q = clamp(q, ivec2(0), ivec2(conteudo) - 1);
    return texelFetch(S, ivec2(k * int(rede.x) + q.x, q.y), 0);
}
vec4 bil(int k, vec2 s) {
    vec2 f = s - 0.5;
    ivec2 i = ivec2(floor(f));
    vec2 a = f - vec2(i);
    return mix(mix(g(k, i), g(k, i + ivec2(1, 0)), a.x), mix(g(k, i + ivec2(0, 1)), g(k, i + ivec2(1, 1)), a.x), a.y);
}
void main() {
    vec2 uv = gl_FragCoord.xy / tam_fonte;
    vec2 s = uv * conteudo;
    vec4 fl = bil(2, s);
    float m = 1.0 / (1.0 + exp(-bil(1, s).w));
    vec2 u0 = uv + fl.xy / conteudo, u1 = uv + fl.zw / conteudo;
    vec3 c0 = texture(A, u0).rgb, c1 = texture(B, u1).rgb;
    cor = vec4(c0 * m + c1 * (1.0 - m), 1.0);
}
"""

ESCALAS = (8, 4, 2, 1)
CANAIS = (192, 128, 96, 64)


def caminho_pesos():
    import sys
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    for p in (os.path.join(base, "rife46.bin"), os.path.join(base, "assets", "rife46.bin")):
        if os.path.exists(p):
            return p
    raise FileNotFoundError("rife46.bin")


def ler_pesos(caminho=None):
    """Lista de camadas (tipo, saídas, entradas, passo, pesos float32 [s, e, k, k], bias)."""
    d = open(caminho or caminho_pesos(), "rb").read()
    if d[:8] != b"PSTRIFE1":
        raise ValueError("arquivo de pesos inválido")
    n = struct.unpack_from("<I", d, 8)[0]
    pos, camadas = 12, []
    for _ in range(n):
        tipo, cout, cin, passo = struct.unpack_from("<IIII", d, pos)
        pos += 16
        k = 3 if tipo == 0 else 4
        nw = cout * cin * k * k
        w = np.frombuffer(d, "<f2", nw, pos).astype(np.float32).reshape(cout, cin, k, k)
        pos += nw * 2
        b = np.frombuffer(d, "<f4", cout, pos).copy()
        pos += cout * 4
        camadas.append((tipo, cout, cin, passo, w, b))
    return camadas


def _g(c):
    return (c + 3) // 4


def arrumar_conv(w, b):
    """Conv 3x3 -> [bias por grupo de saída] + [og][ig][k][coluna] (mat4 por par de grupos)."""
    cout, cin = w.shape[:2]
    go, gi = _g(cout), _g(cin)
    wp = np.zeros((go * 4, gi * 4, 9), np.float32)
    wp[:cout, :cin] = w.reshape(cout, cin, 9)
    bias = np.zeros(go * 4, np.float32)
    bias[:cout] = b
    # mat4(col0..col3) * v: coluna j = pesos da entrada (4ig+j) para as 4 saídas do grupo
    m = wp.reshape(go, 4, gi, 4, 9).transpose(0, 2, 4, 3, 1)   # og, ig, k, coluna(entrada), linha(saída)
    return np.concatenate([bias.reshape(go, 4), m.reshape(-1, 4)])


def arrumar_deconv(w, b):
    """Deconv 4x4 (24 saídas) -> [24 bias] + [oc][ig][k] vec4 sobre as entradas."""
    cout, cin = w.shape[:2]
    gi = _g(cin)
    wp = np.zeros((cout, gi * 4, 16), np.float32)
    wp[:, :cin] = w.reshape(cout, cin, 16)
    m = wp.reshape(cout, gi, 4, 16).transpose(0, 1, 3, 2)      # oc, ig, k, entrada
    bias = np.zeros((cout, 4), np.float32)
    bias[:, 0] = b
    return np.concatenate([bias, m.reshape(-1, 4)])


class RifeGL:
    """Executa o RIFE 4.6 em um contexto ModernGL já criado (tela cheia do PSTudo ou teste sem janela)."""

    def __init__(self, ctx, pesos=None, vagas=4):
        import moderngl
        self.n_vagas = vagas
        self.mgl = moderngl
        self.ctx = ctx
        self.ssbo = ctx.version_code >= 430
        camadas = ler_pesos(pesos) if not isinstance(pesos, list) else pesos
        partes, self.bases, pos = [], [], 0
        for tipo, cout, cin, passo, w, b in camadas:
            a = arrumar_conv(w, b) if tipo == 0 else arrumar_deconv(w, b)
            self.bases.append(pos)
            partes.append(a)
            pos += len(a)
        self.camadas = [(tipo, cout, cin, passo) for tipo, cout, cin, passo, *_ in camadas]
        todos = np.concatenate(partes).astype(np.float32)
        if self.ssbo:
            self.buf = ctx.buffer(todos.tobytes())
        else:
            linhas = (len(todos) + 4095) // 4096
            cheio = np.zeros((linhas * 4096, 4), np.float32)
            cheio[:len(todos)] = todos
            self.tex_pesos = ctx.texture((4096, linhas), 4, cheio.tobytes(), dtype="f4")
            self.tex_pesos.filter = (moderngl.NEAREST, moderngl.NEAREST)
        self.cab = CAB_SSBO if self.ssbo else CAB_TEX
        self.ver = "430" if self.ssbo else "330"
        self.vao_vazio = {}
        self.progs = {}
        self.tam = None
        self.ultimo_t = None

    # ---- utilidades
    def _prog(self, chave, fonte, defs, comum=False):
        p = self.progs.get(chave)
        if p is None:
            d = "".join(f"#define {k} {v}\n" for k, v in defs.items())
            fs = self.cab + d + (COMUM if comum else "") + fonte
            p = self.ctx.program(vertex_shader=VS.replace("{ver}", self.ver), fragment_shader=fs)
            self.progs[chave] = p
            self.vao_vazio[chave] = self.ctx.vertex_array(p, [])
            if not self.ssbo and "pesos" in p:
                p["pesos"] = 7
        return p

    def _tex(self, larg, alt, grupos=1):
        t = self.ctx.texture((larg * grupos, alt), 4, dtype="f4")
        t.filter = (self.mgl.NEAREST, self.mgl.NEAREST)
        t.repeat_x = t.repeat_y = False
        return t, self.ctx.framebuffer(color_attachments=[t])

    def _rodar(self, chave, fbo, texs, **unis):
        p = self.progs[chave]
        for k, v in unis.items():
            p[k] = v
        for unidade, t in texs:
            t.use(unidade)
        fbo.use()
        fbo.viewport = (0, 0) + fbo.size
        self.vao_vazio[chave].render(self.mgl.TRIANGLES, vertices=3)

    # ---- preparo para um tamanho de rede (múltiplo de 32)
    def preparar(self, larg, alt):
        """larg/alt: tamanho útil da imagem na rede. A textura usada tem sobra até múltiplo de 32."""
        LN, AN = (larg + 31) // 32 * 32, (alt + 31) // 32 * 32
        self.conteudo = (larg, alt)
        if self.tam == (LN, AN):
            return
        self.liberar_texturas()
        self.tam = (LN, AN)
        base = {"LN": LN, "AN": AN}
        self.imgs = [self._tex(LN, AN) for _ in range(self.n_vagas)]   # quadros do jogo já reduzidos
        self.S = [self._tex(LN, AN, 3) for _ in range(2)]
        self.blocos = []
        ic = 0
        for b, (esc, c) in enumerate(zip(ESCALAS, CANAIS)):
            L1, A1 = LN // esc, AN // esc         # entrada do bloco
            L2, A2 = L1 // 2, A1 // 2             # depois da 1ª conv
            L3, A3 = L2 // 2, A2 // 2             # resto do bloco
            gin0 = 2 if b == 0 else 3
            blk = {"esc": esc, "L1": L1, "A1": A1}
            if b > 0 and esc > 1:
                blk["X"] = self._tex(L1, A1, 3)
                self._prog(("ent", esc), FS_ENTRADA, dict(base, WOUT=L1, ESC=float(esc)), True)
            elif b == 0:
                blk["X"] = self._tex(L1, A1, 2)
                self._prog(("ent0",), FS_ENTRADA0, dict(base, WOUT=L1, ESC=float(esc)), True)
            blk["F1"] = self._tex(L2, A2, _g(c // 2))
            blk["FA"] = self._tex(L3, A3, _g(c))
            blk["FB"] = self._tex(L3, A3, _g(c))
            blk["T"] = self._tex(L1, A1, 2)
            blk["c0a"] = ic
            self._prog(("conv", b, "a"), FS_CONV, dict(WIN=L1, HIN=A1, GIN=gin0, WOUT=L2, GOUT=_g(c // 2),
                                                        PASSO=2, RES=0))
            self._prog(("conv", b, "b"), FS_CONV, dict(WIN=L2, HIN=A2, GIN=_g(c // 2), WOUT=L3, GOUT=_g(c),
                                                        PASSO=2, RES=0))
            self._prog(("conv", b, "r"), FS_CONV, dict(WIN=L3, HIN=A3, GIN=_g(c), WOUT=L3, GOUT=_g(c),
                                                        PASSO=1, RES=1))
            self._prog(("dec", b), FS_DECONV, dict(WIN=L3, HIN=A3, GIN=_g(c), WOUT=L1))
            self._prog(("atu", b), FS_ATUALIZA, dict(base, LT=L1, AT=A1, ESC=esc, PRIMEIRO=int(b == 0)), True)
            ic += 11
            self.blocos.append(blk)
        self._prog(("prep",), FS_PREPARA, {})
        self.ultimo_t = None

    def liberar_texturas(self):
        if not self.tam:
            return
        for t, f in self.imgs + self.S:
            f.release()
            t.release()
        for blk in self.blocos:
            for k, v in blk.items():
                if isinstance(v, tuple):
                    v[1].release()
                    v[0].release()
        self.tam = None

    def liberar(self):
        self.liberar_texturas()
        for p in self.progs.values():
            p.release()
        self.progs.clear()
        if self.ssbo:
            self.buf.release()
        else:
            self.tex_pesos.release()

    # ---- uso
    def carregar_quadro(self, vaga, textura_fonte):
        """Reduz um quadro (textura já com R, G, B certos, linha 0 = topo) para uma vaga da rede."""
        t, f = self.imgs[vaga]
        self._rodar(("prep",), f, [(0, textura_fonte)], fonte=0, conteudo=tuple(float(v) for v in self.conteudo),
                    reducao=textura_fonte.width / self.conteudo[0])

    def inferir(self, va, vb, t):
        """Roda a rede entre as vagas va e vb no instante t. Devolve a textura do estado final."""
        if self.ssbo:
            self.buf.bind_to_storage_buffer(0)
        else:
            self.tex_pesos.use(7)
        I0, I1 = self.imgs[va][0], self.imgs[vb][0]
        s_atual = None
        n_s = 0
        for b, blk in enumerate(self.blocos):
            ic = blk["c0a"]
            if b == 0:
                self._rodar(("ent0",), blk["X"][1], [(0, I0), (1, I1)], I0=0, I1=1, t=float(t))
                X = blk["X"][0]
            elif blk["esc"] > 1:
                self._rodar(("ent", blk["esc"]), blk["X"][1], [(0, s_atual)], S=0)
                X = blk["X"][0]
            else:
                X = s_atual
            self._rodar(("conv", b, "a"), blk["F1"][1], [(0, X)], X=0, base=self.bases[ic])
            self._rodar(("conv", b, "b"), blk["FA"][1], [(0, blk["F1"][0])], X=0, base=self.bases[ic + 1])
            atual, outro = blk["FA"], blk["FB"]
            for r in range(8):
                self._rodar(("conv", b, "r"), outro[1], [(0, atual[0])], X=0, base=self.bases[ic + 2 + r])
                atual, outro = outro, atual
            self._rodar(("dec", b), blk["T"][1], [(0, atual[0])], X=0, base=self.bases[ic + 10])
            destino = self.S[n_s % 2]
            texs = [(0, blk["T"][0]), (2, I0), (3, I1)]
            unis = dict(T=0, I0=2, I1=3, t=float(t))
            if b > 0:
                texs.append((1, s_atual))
                unis["S"] = 1
            self._rodar(("atu", b), destino[1], texs, **unis)
            s_atual = destino[0]
            n_s += 1
        self.estado = s_atual
        return s_atual
