"""Gera assets/rife46.bin a partir do modelo RIFE 4.6 do rife-ncnn-vulkan (nihui, MIT).

Uso: python tools/empacotar_rife.py <pasta com flownet.param e flownet.bin> assets/rife46.bin

Formato: "PSTRIFE1", quantidade de camadas (uint32) e, para cada camada:
tipo (0 = conv 3x3, 1 = deconv 4x4), saídas, entradas, passo (uint32 cada),
pesos em float16 (saídas x entradas x k x k) e bias em float32.
"""
import struct
import sys

from ncnn_ler import ler


def main(pasta, saida):
    camadas = ler(pasta + "/flownet.param", pasta + "/flownet.bin")
    blocos = []
    with open(saida, "wb") as f:
        convs = [c for c in camadas if c["tipo"] in ("Convolution", "Deconvolution")]
        f.write(b"PSTRIFE1" + struct.pack("<I", len(convs)))
        for c in convs:
            p = c["p"]
            k = p[1]
            cout = p[0]
            cin = p[6] // (cout * k * k)
            tipo = 0 if c["tipo"] == "Convolution" else 1
            f.write(struct.pack("<IIII", tipo, cout, cin, p.get(3, 1)))
            f.write(c["w"].astype("<f2").tobytes())
            f.write(c["b"].astype("<f4").tobytes())
            blocos.append((c["nome"], tipo, cout, cin, k))
    print(len(blocos), "camadas")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
