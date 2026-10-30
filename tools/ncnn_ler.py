import struct, numpy as np
def ler(param, binf):
    linhas = open(param).read().split("\n")
    n_layers, n_blobs = map(int, linhas[1].split())
    camadas = []
    b = open(binf, "rb").read(); pos = 0
    def pega(n, flag=True):
        nonlocal pos
        if flag:
            f = struct.unpack_from("<I", b, pos)[0]; pos += 4
            if f == 0x01306B47:
                d = np.frombuffer(b, "<f2", n, pos).astype(np.float32); pos += n * 2
                pos = (pos + 3) // 4 * 4
                return d
            assert f == 0, hex(f)
        d = np.frombuffer(b, "<f4", n, pos).copy(); pos += n * 4
        return d
    for l in linhas[2:]:
        if not l.strip(): continue
        p = l.split()
        tipo, nome, ni, no = p[0], p[1], int(p[2]), int(p[3])
        ins = p[4:4 + ni]; outs = p[4 + ni:4 + ni + no]
        params = {}
        for kv in p[4 + ni + no:]:
            k, v = kv.split("=")
            k = int(k)
            if k <= -23300:
                vals = v.split(",")[1:]
                params[-k - 23300] = [float(x) for x in vals]
            else:
                params[k] = float(v) if ("." in v or "e" in v) else int(v)
        c = dict(tipo=tipo, nome=nome, ins=ins, outs=outs, p=params)
        if tipo in ("Convolution", "Deconvolution"):
            nw = params[6]
            c["w"] = pega(nw)
            if params.get(5, 0): c["b"] = pega(params[0], flag=False)
        camadas.append(c)
    assert pos == len(b), (pos, len(b))
    return camadas
if __name__ == "__main__":
    import sys
    cs = ler(sys.argv[1], sys.argv[2])
    for c in cs:
        if c["tipo"] in ("Convolution","Deconvolution","Interp","BinaryOp","Eltwise","Crop"):
            print(c["tipo"], c["nome"], c["ins"], c["outs"], c["p"], c.get("w", np.zeros(0)).shape)
